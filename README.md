# AOC Monitor Control for Linux

A lightweight, **unofficial** GTK3 interface for changing monitor settings through `ddcutil` (DDC/CI). No Windows or Wine required.

**Tested:** two AOC Q27B36X monitors on Linux Mint 22.3 (HDMI and DisplayPort). Other models are experimental; not all controls or picture presets are available on every display.

## Features

- Automatically discovers DDC/CI displays rather than assuming fixed monitor numbers.
- Brightness, contrast, sharpness and RGB gains, where available.
- Colour-temperature controls.
- Picture presets through manufacturer-specific VCP `0xDC`, limited to advertised modes.
- Copy settings between connected displays.
- GTK3 desktop launcher; DDC operations run off the UI thread.

The Q27B36X may report `Invalid value (sl=0x80)` for its Standard picture mode; this is a `ddcutil` interpretation issue, not necessarily a hardware error.

## Quick install (Linux Mint / Ubuntu / Debian)

```bash
sudo apt update
sudo apt install git python3 python3-gi gir1.2-gtk-3.0 ddcutil
git clone https://github.com/jeffbelfort/aoc-monitor-control-linux.git
cd aoc-monitor-control-linux
bash install.sh
```

Launch **AOC Monitor Control** from the desktop application menu, or use `~/.local/bin/aoc-monitor-control`.

The installer checks dependencies and installs into your **user account**, without root permissions. System package installation may require `sudo`.

### Upgrade

```bash
cd aoc-monitor-control-linux
git pull --ff-only
bash install.sh
```

### Uninstall

```bash
bash uninstall.sh
```

## Run without installing

```bash
python3 aoc_control.py
```

## Troubleshooting

1. Enable DDC/CI in your monitor's on-screen settings.
2. Check `ddcutil detect --brief` and `ddcutil --display 1 capabilities`.
3. If permission errors occur, consult the `ddcutil` documentation for I²C permissions on your distribution.
4. Some docks, adapters, graphics drivers and displays do not support all DDC/CI features.

## Compatibility and safety

This software is tested only with AOC Q27B36X. Other monitors may have different manufacturer-specific VCP mappings. Avoid forcing undocumented values. Hardware support depends on each display's reported capabilities.

## Licence and attribution

This project is independently developed and is **not affiliated with or endorsed by AOC**. It does not distribute AOC's proprietary i-Menu code or artwork. The generic SVG icon is a project asset.

See `LICENSE` for the repository's licence, if included.
