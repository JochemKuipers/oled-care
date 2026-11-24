# Copyright (c) 2026 Jochem Kuipers
"""CLI entrypoint for ``oled-care``."""

from __future__ import annotations

from oled_care.app import run


def main() -> None:
    """Run the tray application and exit with its status code."""
    raise SystemExit(run())


if __name__ == "__main__":
    main()
