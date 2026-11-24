# Copyright (c) 2026 Jochem Kuipers
"""Display power inhibit and PowerDevil idle-inhibit tracking."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusReply

log = logging.getLogger(__name__)

_SELF_NAMES = frozenset({"oled-care"})
_BUSCTL = "/usr/bin/busctl"
_INHIBIT_FIELDS = 5


class PowerManager(QObject):
    """Inhibit DPMS/screen-off and track foreign PowerDevil idle inhibits.

    Browsers (e.g. Firefox “Playing video”) register an ``idle`` inhibit.
    Audio-only playback usually only takes ``sleep``, which we ignore so music
    can keep playing under a black OLED.
    """

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
        self._poll = QTimer(self)
        self._poll.setInterval(1_000)
        self._poll.timeout.connect(self._refresh_screen_inhibit)
        self._poll.start()
        self._refresh_screen_inhibit()

    @property
    def screen_inhibited(self) -> bool:
        """Whether another app holds an idle inhibit (e.g. playing video)."""
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
        inhibited = self._foreign_idle_inhibit_active()
        if inhibited != self._screen_inhibited:
            self._screen_inhibited = inhibited
            self.screen_inhibit_changed.emit(inhibited)

    def _foreign_idle_inhibit_active(self) -> bool:
        for what, who, why, _mode, _flags in self._active_inhibitions():
            if what != "idle":
                continue
            if who in _SELF_NAMES or who.endswith("/oled-care"):
                continue
            log.debug("foreign idle inhibit: %s (%s)", who, why)
            return True
        return False

    @staticmethod
    def _active_inhibitions() -> list[tuple[str, str, str, str, int]]:
        """Return PowerDevil ActiveInhibitions as (what, who, why, mode, flags)."""
        if not Path(_BUSCTL).is_file():
            log.warning("busctl not found at %s", _BUSCTL)
            return []
        try:
            out = subprocess.check_output(  # noqa: S603 — fixed /usr/bin/busctl argv
                [
                    _BUSCTL,
                    "--user",
                    "--json=short",
                    "get-property",
                    "org.kde.Solid.PowerManagement",
                    "/org/kde/Solid/PowerManagement/PolicyAgent",
                    "org.kde.Solid.PowerManagement.PolicyAgent",
                    "ActiveInhibitions",
                ],
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("failed to read ActiveInhibitions: %s", exc)
            return []

        try:
            payload: dict[str, Any] = json.loads(out)
            rows = payload.get("data", [])
        except json.JSONDecodeError as exc:
            log.warning("invalid ActiveInhibitions JSON: %s", exc)
            return []

        result: list[tuple[str, str, str, str, int]] = []
        for row in rows:
            if not isinstance(row, list) or len(row) < _INHIBIT_FIELDS:
                continue
            what, who, why, mode, flags = row[:_INHIBIT_FIELDS]
            result.append((str(what), str(who), str(why), str(mode), int(flags)))
        return result
