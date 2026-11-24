# Copyright (c) 2026 Jochem Kuipers
"""Display power inhibit and PowerDevil screen-inhibit tracking."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage, QDBusReply

# PowerDevil PolicyAgent: ChangeScreenSettings
_SCREEN_INHIBIT = 2


class PowerManager(QObject):
    """Inhibit DPMS/screen-off and track PolicyAgent screen inhibits."""

    screen_inhibit_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        """Connect to session D-Bus interfaces and start inhibit polling."""
        super().__init__(parent)
        self._cookie: int | None = None
        self._screen_inhibited = False
        bus = QDBusConnection.sessionBus()
        self._screensaver = QDBusInterface(
            "org.freedesktop.ScreenSaver",
            "/ScreenSaver",
            "org.freedesktop.ScreenSaver",
            bus,
            self,
        )
        self._policy = QDBusInterface(
            "org.kde.Solid.PowerManagement",
            "/org/kde/Solid/PowerManagement/PolicyAgent",
            "org.kde.Solid.PowerManagement.PolicyAgent",
            bus,
            self,
        )
        self._poll = QTimer(self)
        self._poll.setInterval(2_000)
        self._poll.timeout.connect(self._refresh_screen_inhibit)
        self._poll.start()
        self._refresh_screen_inhibit()

    @property
    def screen_inhibited(self) -> bool:
        """Whether another app currently holds a screen inhibit."""
        return self._screen_inhibited

    def inhibit_display_power_off(self) -> None:
        """Ask the session screensaver service not to turn the display off."""
        if self._cookie is not None:
            return
        reply = QDBusReply(
            self._screensaver.call(
                "Inhibit",
                "oled-care",
                "OLED burn-in protection keeps HDMI link alive",
            ),
        )
        if reply.isValid():
            self._cookie = int(reply.value())

    def release(self) -> None:
        """Drop the display-power inhibit cookie, if any."""
        if self._cookie is None:
            return
        self._screensaver.call("UnInhibit", self._cookie)
        self._cookie = None

    def _refresh_screen_inhibit(self) -> None:
        msg = self._policy.call("HasInhibition", _SCREEN_INHIBIT)
        inhibited = False
        if msg.type() != QDBusMessage.MessageType.ErrorMessage:
            args = msg.arguments()
            if args:
                inhibited = bool(args[0])
        if inhibited != self._screen_inhibited:
            self._screen_inhibited = inhibited
            self.screen_inhibit_changed.emit(inhibited)
