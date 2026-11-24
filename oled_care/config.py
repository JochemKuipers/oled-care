# Copyright (c) 2026 Jochem Kuipers
"""Persistent user configuration for OLED Care."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "oled-care"
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass
class Config:
    """User settings stored in ``~/.config/oled-care/config.json``."""

    enabled: bool = True
    idle_minutes: float = 5.0
    pixel_shift: bool = True

    @classmethod
    def load(cls) -> Config:
        """Load config from disk, or return defaults if missing/invalid."""
        if not CONFIG_PATH.is_file():
            return cls()
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        return cls(
            enabled=bool(data.get("enabled", True)),
            idle_minutes=float(data.get("idle_minutes", 5.0)),
            pixel_shift=bool(data.get("pixel_shift", True)),
        )

    def save(self) -> None:
        """Write the current settings to disk."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(asdict(self), indent=2) + "\n",
            encoding="utf-8",
        )

    @property
    def idle_ms(self) -> int:
        """Idle timeout in milliseconds (minimum 1)."""
        return max(1, int(self.idle_minutes * 60_000))
