# AOC Monitor Control v0.1

Linux Mint GTK 3 application for two AOC Q27B36X monitors. Uses `ddcutil` and standard DDC/CI VCP codes.

## Install dependencies

```bash
sudo apt install ddcutil python3-gi gir1.2-gtk-3.0
sudo modprobe i2c-dev
```

## Run

```bash
python3 aoc_control.py
```

If DDC permission is denied, configure access to `/dev/i2c-*` via the `i2c` group and udev rules. Avoid running the GUI with sudo.

## Safety

Copy operations require confirmation. Manufacturer-specific display mode (`0xDC`) is intentionally not modified. Test each control and check whether your monitor accepts RGB writes under the current colour preset. Display numbering is based on `ddcutil detect` and may change after reconnecting displays.
