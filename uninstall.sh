#!/usr/bin/env bash
set -euo pipefail
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -f "$HOME/.local/bin/aoc-monitor-control" \
  "$DATA/applications/aoc-monitor-control.desktop" \
  "$DATA/icons/hicolor/scalable/apps/aoc-monitor-control.svg"
rm -rf -- "$DATA/aoc-monitor-control"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DATA/applications" >/dev/null 2>&1 || true
fi
printf 'AOC Monitor Control uninstalled.\n'
