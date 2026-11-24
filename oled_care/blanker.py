# Copyright (c) 2026 Jochem Kuipers
"""Fullscreen true-black blanker windows with optional pixel-shift."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QScreen,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget


class BlankWindow(QWidget):
    """Frameless fullscreen black surface that reports user input."""

    activity = Signal()

    def __init__(self, screen: QScreen, parent: QWidget | None = None) -> None:
        """Place a black window on ``screen``."""
        super().__init__(parent)
        self.setScreen(screen)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, on=False)
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: #000000;")
        self._base_geo = screen.geometry()
        self.setGeometry(self._base_geo)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Fill the window with pure black."""
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))
        painter.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Treat any key as wake activity."""
        self.activity.emit()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Treat mouse clicks as wake activity."""
        self.activity.emit()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Treat pointer motion as wake activity."""
        self.activity.emit()
        event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Treat scroll as wake activity."""
        self.activity.emit()
        event.accept()

    def apply_shift(self, dx: int, dy: int) -> None:
        """Nudge the window by ``dx``/``dy`` pixels from its base geometry."""
        geo = self._base_geo.adjusted(dx, dy, dx, dy)
        self.setGeometry(geo)

    def reset_geometry(self) -> None:
        """Restore the window to the current screen geometry."""
        screen = self.screen()
        if screen is not None:
            self._base_geo = screen.geometry()
        self.setGeometry(self._base_geo)


class Blanker(QObject):
    """Manage one black window per screen."""

    dismissed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        """Create a blanker; call ``show`` to cover all screens."""
        super().__init__(parent)
        self._windows: list[BlankWindow] = []
        self._active = False
        self._pixel_shift = True
        self._shift_index = 0
        self._shift_pattern = [
            (0, 0),
            (1, 0),
            (1, 1),
            (0, 1),
            (-1, 1),
            (-1, 0),
            (-1, -1),
            (0, -1),
            (1, -1),
        ]
        self._shift_timer = QTimer(self)
        self._shift_timer.setInterval(60_000)
        self._shift_timer.timeout.connect(self._nudge)
        # Ignore input briefly after show so the tray click / enter event
        # that triggered blanking does not immediately dismiss it.
        self._input_armed = False
        self._arm_timer = QTimer(self)
        self._arm_timer.setSingleShot(True)
        self._arm_timer.setInterval(750)
        self._arm_timer.timeout.connect(self._arm_input)

        app = QGuiApplication.instance()
        if app is not None:
            app.screenAdded.connect(self._on_screens_changed)
            app.screenRemoved.connect(self._on_screens_changed)

    @property
    def active(self) -> bool:
        """Whether blanker windows are currently shown."""
        return self._active

    def set_pixel_shift(self, *, enabled: bool) -> None:
        """Enable or disable the slow geometry nudge while blanked."""
        self._pixel_shift = enabled
        if self._active:
            if enabled:
                self._shift_timer.start()
            else:
                self._shift_timer.stop()
                for win in self._windows:
                    win.reset_geometry()

    def show(self) -> None:
        """Cover every screen with a black window."""
        if self._active:
            return
        self._active = True
        self._input_armed = False
        self._shift_index = 0
        self._rebuild_windows()
        if self._pixel_shift:
            self._shift_timer.start()
        QGuiApplication.setOverrideCursor(QCursor(Qt.CursorShape.BlankCursor))
        self._arm_timer.start()

    def hide(self) -> None:
        """Dismiss blanker windows and restore the cursor."""
        if not self._active:
            return
        self._active = False
        self._input_armed = False
        self._arm_timer.stop()
        self._shift_timer.stop()
        self._clear_windows()
        QGuiApplication.restoreOverrideCursor()
        self.dismissed.emit()

    def _arm_input(self) -> None:
        self._input_armed = True

    def _on_activity(self) -> None:
        if self._input_armed:
            self.hide()

    def _rebuild_windows(self) -> None:
        self._clear_windows()
        for screen in QGuiApplication.screens():
            win = BlankWindow(screen)
            win.activity.connect(self._on_activity)
            win.showFullScreen()
            win.raise_()
            win.activateWindow()
            self._windows.append(win)

    def _clear_windows(self) -> None:
        for win in self._windows:
            win.activity.disconnect(self._on_activity)
            win.hide()
            win.deleteLater()
        self._windows.clear()

    def _on_screens_changed(self, *_args: object) -> None:
        if self._active:
            self._rebuild_windows()

    def _nudge(self) -> None:
        if not self._windows:
            return
        self._shift_index = (self._shift_index + 1) % len(self._shift_pattern)
        dx, dy = self._shift_pattern[self._shift_index]
        for win in self._windows:
            win.apply_shift(dx, dy)
