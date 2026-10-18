#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP="$DATA/aoc-monitor-control"
DESKTOP="$DATA/applications"
ICON="$DATA/icons/hicolor/scalable/apps"
BIN="$HOME/.local/bin"

missing=()
command -v ddcutil >/dev/null 2>&1 || missing+=(ddcutil)
command -v python3 >/dev/null 2>&1 || missing+=(python3)
if ! /usr/bin/python3 -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk' >/dev/null 2>&1; then
  missing+=(python3-gi gir1.2-gtk-3.0)
fi
if ((${#missing[@]})); then
  printf 'Missing dependencies: %s\n' "${missing[*]}" >&2
  if command -v apt-get >/dev/null 2>&1; then
    printf 'On Mint/Ubuntu/Debian, install them with:\n  sudo apt install %s\n' "${missing[*]}" >&2
  fi
  exit 1
fi
python3 -m py_compile "$ROOT/aoc_control.py"
mkdir -p "$APP" "$DESKTOP" "$ICON" "$BIN"
install -m 755 "$ROOT/aoc_control.py" "$APP/aoc_control.py"
install -m 644 "$ROOT/assets/aoc-monitor-control.svg" "$ICON/aoc-monitor-control.svg"
cat > "$BIN/aoc-monitor-control" <<'LAUNCHER'
#!/bin/sh
exec /usr/bin/python3 "${XDG_DATA_HOME:-$HOME/.local/share}/aoc-monitor-control/aoc_control.py" "$@"
LAUNCHER
chmod 755 "$BIN/aoc-monitor-control"
cat > "$DESKTOP/aoc-monitor-control.desktop" <<DESKTOP_ENTRY
[Desktop Entry]
Type=Application
Version=1.0
Name=AOC Monitor Control
GenericName=Monitor Settings
Comment=Unofficial Linux DDC/CI monitor control
Exec=$BIN/aoc-monitor-control
Icon=aoc-monitor-control
Terminal=false
Categories=Settings;HardwareSettings;
StartupNotify=true
DESKTOP_ENTRY
if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "$DESKTOP/aoc-monitor-control.desktop"
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP" >/dev/null 2>&1 || true
fi
printf '\nInstalled AOC Monitor Control. Launch from your application menu.\n'
printf 'To upgrade: git pull && ./install.sh\n'
