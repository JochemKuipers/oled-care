# Copyright (c) 2026 Jochem Kuipers
"""System tray application controller for OLED Care."""

from __future__ import annotations

import logging
import sys

from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from oled_care.blanker import Blanker
from oled_care.config import Config
from oled_care.idle import WaylandIdleMonitor
from oled_care.power import PowerManager

log = logging.getLogger(__name__)


def _tray_icon(*, enabled: bool) -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    fill = QColor("#1a1a1a") if enabled else QColor("#555555")
    border = QColor("#7ec8e3") if enabled else QColor("#888888")
    p.setBrush(fill)
    p.setPen(border)
    p.drawRoundedRect(8, 12, 48, 36, 6, 6)
    p.setBrush(QColor("#000000"))
    p.drawRect(14, 18, 36, 24)
    p.end()
    return QIcon(pix)


class OledCareApp:
    """Tray UI wiring idle monitoring, blanking, and power inhibits."""

    def __init__(self) -> None:
        """Load config, start inhibits/idle, and build the tray menu."""
        self.config = Config.load()
        self.power = PowerManager()
        self.blanker = Blanker()
        self.idle = WaylandIdleMonitor()
        self.tray = QSystemTrayIcon(_tray_icon(enabled=self.config.enabled))
        self._build_menu()
        self.tray.setContextMenu(self._menu)
        self.tray.setToolTip(self._tooltip())
        self.tray.activated.connect(self._on_tray_activated)

        self.blanker.dismissed.connect(self._on_blanker_dismissed)
        self.idle.idled.connect(self._on_idle)
        self.idle.failed.connect(self._on_idle_failed)
        self.power.screen_inhibit_changed.connect(
            lambda inhibited: self._on_screen_inhibit(inhibited=inhibited),
        )

        self.power.inhibit_display_power_off()
        if self.config.enabled:
            self.idle.start(self.config.idle_ms)

    def _build_menu(self) -> None:
        self._menu = QMenu()
        self._act_enabled = QAction("Protection enabled", self._menu)
        self._act_enabled.setCheckable(True)
        self._act_enabled.setChecked(self.config.enabled)
        self._act_enabled.triggered.connect(
            lambda checked: self._toggle_enabled(checked=checked),
        )
        self._menu.addAction(self._act_enabled)

        self._act_blank = QAction("Blank now", self._menu)
        self._act_blank.triggered.connect(self._blank_now)
        self._menu.addAction(self._act_blank)

        self._act_timeout = QAction(
            f"Idle timeout: {self._format_timeout()}…",
            self._menu,
        )
        self._act_timeout.triggered.connect(self._set_timeout)
        self._menu.addAction(self._act_timeout)

        self._act_shift = QAction("Pixel shift", self._menu)
        self._act_shift.setCheckable(True)
        self._act_shift.setChecked(self.config.pixel_shift)
        self._act_shift.triggered.connect(
            lambda checked: self._toggle_shift(checked=checked),
        )
        self._menu.addAction(self._act_shift)

        self._menu.addSeparator()
        quit_act = QAction("Quit", self._menu)
        quit_act.triggered.connect(self.quit)
        self._menu.addAction(quit_act)

    def _format_timeout(self) -> str:
        minutes = self.config.idle_minutes
        if minutes == int(minutes):
            return f"{int(minutes)} min"
        return f"{minutes:g} min"

    def _tooltip(self) -> str:
        state = "on" if self.config.enabled else "off"
        blanked = " · blanked" if self.blanker.active else ""
        inhibit = " · screen inhibit" if self.power.screen_inhibited else ""
        return f"OLED Care ({state}) · idle {self._format_timeout()}{blanked}{inhibit}"

    def _refresh_tray(self) -> None:
        self.tray.setIcon(_tray_icon(enabled=self.config.enabled))
        self.tray.setToolTip(self._tooltip())
        self._act_timeout.setText(f"Idle timeout: {self._format_timeout()}…")

    def show(self) -> None:
        """Show the tray icon (and exit if no tray is available)."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(
                None,
                "OLED Care",
                "System tray is not available.",
            )
            sys.exit(1)
        self.tray.show()
        self.tray.showMessage(
            "OLED Care",
            f"Protecting OLED · blank after {self._format_timeout()} idle",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._blank_now()

    def _toggle_enabled(self, *, checked: bool) -> None:
        self.config.enabled = checked
        self.config.save()
        if checked:
            self.idle.start(self.config.idle_ms)
        else:
            self.idle.stop()
            if self.blanker.active:
                self.blanker.hide()
        self._refresh_tray()

    def _toggle_shift(self, *, checked: bool) -> None:
        self.config.pixel_shift = checked
        self.config.save()
        self.blanker.set_pixel_shift(enabled=checked)

    def _set_timeout(self) -> None:
        value, ok = QInputDialog.getDouble(
            None,
            "OLED Care",
            "Idle minutes before blanking:",
            self.config.idle_minutes,
            0.5,
            120.0,
            1,
        )
        if not ok:
            return
        self.config.idle_minutes = value
        self.config.save()
        if self.config.enabled:
            self.idle.set_timeout(self.config.idle_ms)
        self._refresh_tray()

    def _blank_now(self) -> None:
        self.blanker.set_pixel_shift(enabled=self.config.pixel_shift)
        self.blanker.show()
        self._refresh_tray()

    def _on_idle(self) -> None:
        if not self.config.enabled:
            return
        if self.power.screen_inhibited:
            log.info("idle reached but screen inhibit active — skip blank")
            return
        if self.blanker.active:
            return
        log.info("idle timeout — blanking")
        self._blank_now()

    def _on_blanker_dismissed(self) -> None:
        self._refresh_tray()
        # Re-arm idle timeout after wake.
        if self.config.enabled and self.idle.ready:
            self.idle.set_timeout(self.config.idle_ms)

    def _on_screen_inhibit(self, *, inhibited: bool) -> None:
        self._refresh_tray()
        if inhibited and self.blanker.active:
            # Don't fight fullscreen video / presentation inhibits.
            self.blanker.hide()

    def _on_idle_failed(self, message: str) -> None:
        log.error("idle monitor: %s", message)
        self.tray.showMessage(
            "OLED Care",
            f"Idle detection failed: {message}\nUse Blank now from the tray.",
            QSystemTrayIcon.MessageIcon.Warning,
            8000,
        )

    def quit(self) -> None:
        """Stop idle monitoring, dismiss blankers, and quit the Qt app."""
        self.idle.stop()
        if self.blanker.active:
            self.blanker.hide()
        self.power.release()
        self.tray.hide()
        instance = QApplication.instance()
        if instance is not None:
            instance.quit()


def run() -> int:
    """Start the Qt application and block until quit."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    QApplication.setApplicationName("oled-care")
    QApplication.setOrganizationName("oled-care")
    QApplication.setDesktopFileName("oled-care")
    # Ensure we don't quit when blanker windows close.
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not sys.platform.startswith("linux"):
        QMessageBox.critical(None, "OLED Care", "Linux / Wayland only.")
        return 1

    # Keep a strong ref on the QApplication so GC does not drop the controller.
    care = OledCareApp()
    app.setProperty("oledCareController", care)
    care.show()
    return app.exec()
