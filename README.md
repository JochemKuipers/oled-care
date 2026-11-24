# OLED Care

HDMI-safe OLED blanker for **KDE Plasma on Wayland**.

Plasma’s “Turn off display” drops the video link, which can power down an AV receiver on HDMI CEC / signal loss. OLED Care paints **true black** fullscreen windows instead, so pixels rest while HDMI (and your music) stay up.

## Features

- Blank after idle (default **5 minutes**) via Wayland `ext-idle-notify-v1`
- Tray: enable/disable, **Blank now**, set timeout, pixel-shift toggle
- Keeps Plasma from hard-powering the panel (`ScreenSaver.Inhibit`) while running
- Skips auto-blank while PowerDevil reports a **screen** inhibit (fullscreen video, etc.)
- Optional slow ±1–2px pixel-shift nudge

## Requirements

- Linux, Wayland compositor with `ext_idle_notifier_v1` (KWin does)
- `python`, `pyside6`, `python-pywayland`

## Install (AUR)

```bash
# from the AUR once published
yay -S oled-care
# or
paru -S oled-care
```

Local package build from this repo:

```bash
./packaging/aur/build-local.sh
# then
sudo pacman -U packaging/aur/oled-care-*.pkg.tar.zst
```

## Run

```bash
oled-care
```

Autostart: System Settings → Autostart → add `OLED Care`, or copy the desktop file:

```bash
cp /usr/share/applications/oled-care.desktop ~/.config/autostart/
```

## Config

`~/.config/oled-care/config.json`

```json
{
  "enabled": true,
  "idle_minutes": 5.0,
  "pixel_shift": true
}
```

## KDE tip

Leave **Turn off screen** on *Never* (or rely on OLED Care’s inhibit). Dim-only is fine; full DPMS off is what kills the AVR.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
oled-care
```

Lint / format (Ruff, `select = ALL`):

```bash
ruff format oled_care
ruff check oled_care
```

CI runs the same Ruff gates on every push/PR. Versioning is **CalVer** (`YYYY.MM.DD`). Pushing a `vYYYY.MM.DD` tag runs the Release workflow (Ruff + wheel/sdist + GitHub Release + AUR `oled-care` update).

## License

MIT
