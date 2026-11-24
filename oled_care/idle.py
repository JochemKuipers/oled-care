# Copyright (c) 2026 Jochem Kuipers
"""Wayland seat idle monitoring via ext-idle-notify-v1."""

from __future__ import annotations

import logging
import select
from contextlib import suppress
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from pywayland.client import Display
from pywayland.protocol.ext_idle_notify_v1 import ExtIdleNotifierV1
from pywayland.protocol.wayland import WlSeat

log = logging.getLogger(__name__)


class WaylandIdleMonitor(QObject):
    """Watch seat idle via ext-idle-notify-v1 (works on KWin Wayland).

    Uses get_input_idle_notification so our own ScreenSaver.Inhibit (and
    media idle-inhibitors) do not prevent blanking. PolicyAgent screen
    inhibits are still honored by the app before blanking.
    """

    idled = Signal()
    resumed = Signal()
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        """Create an idle monitor; call ``start`` to connect to the compositor."""
        super().__init__(parent)
        self._display: Display | None = None
        self._seat: Any = None
        self._notifier: Any = None
        self._notification: Any = None
        self._poll = QTimer(self)
        self._poll.setInterval(250)
        self._poll.timeout.connect(self._pump)
        self._timeout_ms = 300_000
        self._ready = False

    @property
    def ready(self) -> bool:
        """Whether the Wayland idle connection is active."""
        return self._ready

    def start(self, timeout_ms: int) -> None:
        """Connect (if needed) and arm an idle notification for ``timeout_ms``."""
        self._timeout_ms = max(0, int(timeout_ms))
        try:
            self._connect()
            self._arm_notification()
            self._poll.start()
        except Exception as exc:
            log.exception("idle monitor failed")
            self.failed.emit(str(exc))

    def set_timeout(self, timeout_ms: int) -> None:
        """Re-arm the idle notification with a new timeout."""
        self._timeout_ms = max(0, int(timeout_ms))
        if self._ready:
            self._arm_notification()

    def stop(self) -> None:
        """Tear down the idle notification and Wayland connection."""
        self._poll.stop()
        self._destroy_notification()
        if self._notifier is not None:
            with suppress(Exception):
                self._notifier.destroy()
            self._notifier = None
        self._seat = None
        if self._display is not None:
            with suppress(Exception):
                self._display.disconnect()
            self._display = None
        self._ready = False

    def _connect(self) -> None:
        if self._display is not None:
            return

        display = Display()
        display.connect()

        seat_holder: dict[str, Any] = {}
        notifier_holder: dict[str, Any] = {}

        def on_global(
            registry: object,
            name: int,
            interface: str,
            version: int,
        ) -> None:
            if interface == "wl_seat" and "seat" not in seat_holder:
                seat_holder["seat"] = registry.bind(name, WlSeat, min(version, 1))
            elif interface == "ext_idle_notifier_v1" and "notifier" not in notifier_holder:
                notifier_holder["notifier"] = registry.bind(
                    name,
                    ExtIdleNotifierV1,
                    min(version, 2),
                )

        registry = display.get_registry()
        registry.dispatcher["global"] = on_global
        display.roundtrip()

        seat = seat_holder.get("seat")
        notifier = notifier_holder.get("notifier")
        if seat is None or notifier is None:
            display.disconnect()
            missing = []
            if seat is None:
                missing.append("wl_seat")
            if notifier is None:
                missing.append("ext_idle_notifier_v1")
            msg = "Wayland idle unavailable (missing: " + ", ".join(missing) + ")"
            raise RuntimeError(msg)

        self._display = display
        self._seat = seat
        self._notifier = notifier
        self._ready = True

    def _arm_notification(self) -> None:
        if not self._ready or self._notifier is None or self._seat is None:
            return
        self._destroy_notification()
        # Ignore surface idle-inhibitors; we gate on PolicyAgent instead.
        self._notification = self._notifier.get_input_idle_notification(
            self._timeout_ms,
            self._seat,
        )
        self._notification.dispatcher["idled"] = self._on_idled
        self._notification.dispatcher["resumed"] = self._on_resumed
        if self._display is None:
            msg = "Wayland display missing after idle arm"
            raise RuntimeError(msg)
        self._display.flush()

    def _destroy_notification(self) -> None:
        if self._notification is None:
            return
        with suppress(Exception):
            self._notification.destroy()
        self._notification = None
        if self._display is not None:
            with suppress(Exception):
                self._display.flush()

    def _pump(self) -> None:
        if self._display is None:
            return
        try:
            self._display.flush()
            # dispatch(block=False) only drains the local queue; read() pulls
            # from the Wayland socket first (prepare_read / read_events).
            self._display.dispatch(block=False)
            fd = self._display.get_fd()
            ready, _, _ = select.select([fd], [], [], 0)
            if ready:
                self._display.read()
                self._display.dispatch(block=False)
        except Exception:
            log.exception("wayland dispatch failed")

    def _on_idled(self, _notification: object) -> int:
        # Defer into the Qt event loop — avoid Qt work inside the cffi callback.
        QTimer.singleShot(0, self.idled.emit)
        return 0

    def _on_resumed(self, _notification: object) -> int:
        QTimer.singleShot(0, self.resumed.emit)
        return 0
