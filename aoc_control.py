#!/usr/bin/env python3
"""Unofficial AOC Monitor Control — GTK3 frontend for ddcutil."""
import re
import subprocess
import threading

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

FEATURES = [('Brightness', '10'), ('Contrast', '12'), ('Sharpness', '87'),
            ('Red gain', '16'), ('Green gain', '18'), ('Blue gain', '1A')]
COLOR_PRESETS = [('Native', 0x02), ('5000 K', 0x04), ('6500 K', 0x05),
                 ('7500 K', 0x06), ('8200 K', 0x07), ('9300 K', 0x08),
                 ('11500 K', 0x0A), ('User 1', 0x0B)]
# AOC i-Menu enum mapping. Not all monitors implement these modes.
# 0x8F = Reset Color (an action), intentionally excluded.
PICTURE_MODES = [
    ('Standard', 0x80), ('Reading', 0x82), ('Internet', 0x83),
    ('Movie', 0x84), ('Sports', 0x85), ('Photographer', 0x86),
    ('HDR Picture', 0x87), ('HDR Movie', 0x88), ('HDR Game', 0x89),
    ('FPS', 0x8A), ('RTS', 0x8B), ('Racing', 0x8C),
    ('HDR Off', 0x90), ('DisplayHDR', 0x91),
    ('HDR Picture (alt)', 0x92), ('HDR Movie (alt)', 0x93),
    ('HDR Game (alt)', 0x94), ('Eco Mode', 0xB0),
]


def run_ddc(*args, timeout=20):
    return subprocess.run(['ddcutil', *map(str, args)], capture_output=True,
                          text=True, timeout=timeout)


def ddc(display, *args, allow_invalid_mode=False):
    proc = run_ddc('--display', display, *args)
    if proc.returncode and not (allow_invalid_mode and re.search(
            r'\bsl\s*=\s*0x[0-9a-f]+', proc.stdout, re.I)):
        raise RuntimeError((proc.stderr or proc.stdout).strip() or 'ddcutil failed')
    return proc.stdout


def discover_monitors():
    """Return [(ddcutil display number, descriptive label), ...]."""
    proc = run_ddc('detect', '--brief', timeout=30)
    output = proc.stdout + '\n' + proc.stderr
    # ddcutil detect --brief emits "Display 1" / "Display 2" blocks.
    blocks = re.split(r'(?=^Display\s+\d+\s*$)', output, flags=re.M | re.I)
    found = []
    for block in blocks:
        number = re.search(r'^Display\s+(\d+)\s*$', block, re.M | re.I)
        if not number:
            continue
        display = int(number.group(1))
        model = re.search(r'^\s*Model:\s*(.+)$', block, re.M | re.I)
        manufacturer = re.search(r'^\s*Monitor:\s*(.+)$', block, re.M | re.I)
        connector = re.search(r'^\s*DRM connector:\s*(.+)$', block, re.M | re.I)
        name = (model or manufacturer)
        label = name.group(1).strip() if name else 'DDC/CI monitor'
        if connector:
            label += ' · ' + connector.group(1).strip()
        found.append((display, f'Monitor {display} · {label}'))
    return found


def read_numeric(display, code):
    output = ddc(display, 'getvcp', code)
    match = re.search(r'current value\s*=\s*(\d+),\s*max value\s*=\s*(\d+)', output, re.I)
    if not match:
        raise ValueError(f'Cannot read VCP {code}: {output.strip()}')
    return int(match.group(1)), int(match.group(2))


def read_color_preset(display):
    output = ddc(display, 'getvcp', '14', allow_invalid_mode=True)
    match = re.search(r'\(0x([0-9a-f]+)\)', output, re.I)
    if not match:
        match = re.search(r'\bsl\s*=\s*0x([0-9a-f]+)', output, re.I)
    if not match:
        raise ValueError(f'Cannot read colour preset: {output.strip()}')
    return int(match.group(1), 16)


def read_picture_mode(display):
    output = ddc(display, 'getvcp', 'DC', allow_invalid_mode=True)
    match = re.search(r'\bsl\s*=\s*0x([0-9a-f]+)', output, re.I)
    if not match:
        raise ValueError(f'Cannot read picture mode: {output.strip()}')
    return int(match.group(1), 16)


# Q27B36X values captured from its actual DDC/CI capabilities response.
# Only use this fallback when the detected model matches exactly.
Q27B36X_DC = {0x80, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88,
              0x89, 0x8A, 0x8B, 0x8C, 0x8F, 0x90, 0x91, 0x92,
              0x93, 0x94, 0xB0}


def advertised_values(output, code):
    """Read enumerated capabilities from raw DDC string or decoded output."""
    # The raw string can be shown as 'Unparsed capabilities string:' and
    # ddcutil may also show a decoded 'Feature: DC' section.
    raw = re.search(r'\b' + re.escape(code) +
                    r'\s*\(\s*((?:[0-9a-fA-F]{2}\s*)+)\)', output, re.I)
    if raw:
        return {int(x, 16) for x in re.findall(r'[0-9a-fA-F]{2}', raw.group(1))}
    section = re.search(r'^\s*Feature:\s*' + re.escape(code) +
                        r'\b[^\n]*\n(?:(?!^\s*Feature:)[\s\S])*?',
                        output, re.I | re.M)
    # Anchor to this feature, and stop before the next feature.
    start = re.search(r'^\s*Feature:\s*' + re.escape(code) + r'\b',
                      output, re.I | re.M)
    if start:
        tail = output[start.end():]
        end = re.search(r'^\s*Feature:', tail, re.I | re.M)
        segment = tail[:end.start()] if end else tail
        values = re.search(r'^\s*Values \(unparsed\):\s*([^\n]+)',
                           segment, re.I | re.M)
        if values:
            return {int(x, 16) for x in re.findall(r'\b[0-9a-fA-F]{2}\b', values.group(1))}
    return set()


def capabilities(display):
    # Try verbose as well: some ddcutil builds omit the raw string normally.
    outputs = []
    for args in [('capabilities',), ('capabilities', '--verbose')]:
        try:
            outputs.append(ddc(display, *args))
        except (RuntimeError, subprocess.TimeoutExpired):
            pass
        if outputs and advertised_values(outputs[-1], 'DC'):
            break
    combined = '\n'.join(outputs)
    return {code: advertised_values(combined, code) for code in ('DC', '14')}, combined


def read_snapshot(display):
    """Read independent controls without making one unsupported feature fatal."""
    values = {}
    for _, code in FEATURES:
        try:
            values[code] = read_numeric(display, code)
        except (RuntimeError, ValueError, subprocess.TimeoutExpired):
            pass
    color = picture = None
    try:
        color = read_color_preset(display)
    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
        pass
    try:
        picture = read_picture_mode(display)
    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
        pass
    try:
        advertised, _ = capabilities(display)
    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
        advertised = {'DC': set(), '14': set()}
    return values, color, picture, advertised


class Window(Gtk.Window):
    def __init__(self):
        super().__init__(title='AOC Monitor Control')
        self.set_icon_name('aoc-monitor-control')
        self.set_default_size(580, 700)
        self.set_border_width(16)
        self.busy = False
        self.loading = False
        self.refresh_pending = False
        self.monitors = []
        self.display = None
        self.advertised = {}

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.add(scroller)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=11)
        scroller.add(root)
        title = Gtk.Label()
        title.set_markup('<span size="x-large" weight="bold">AOC Monitor Control</span>')
        title.set_xalign(0)
        root.pack_start(title, False, False, 0)
        subtitle = Gtk.Label(label='Unofficial DDC/CI monitor controls')
        subtitle.set_xalign(0)
        root.pack_start(subtitle, False, False, 0)

        selector = Gtk.Box(spacing=8)
        root.pack_start(selector, False, False, 0)
        self.select = Gtk.ComboBoxText()
        self.select.connect('changed', self.on_select)
        selector.pack_start(self.select, True, True, 0)
        rescan = Gtk.Button(label='Rescan')
        rescan.connect('clicked', lambda *_: self.scan())
        selector.pack_start(rescan, False, False, 0)
        refresh = Gtk.Button(label='Refresh')
        refresh.connect('clicked', lambda *_: self.request_refresh())
        selector.pack_start(refresh, False, False, 0)

        self.sliders = {}
        for label, code in FEATURES:
            line = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            name = Gtk.Label(label=label)
            name.set_xalign(0)
            line.pack_start(name, False, False, 0)
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
            scale.set_digits(0)
            scale.set_draw_value(True)
            scale.set_sensitive(False)
            scale.connect('button-release-event', self.on_release, code)
            scale.connect('key-release-event', self.on_release, code)
            line.pack_start(scale, False, False, 0)
            root.pack_start(line, False, False, 0)
            self.sliders[code] = scale

        color_row = Gtk.Box(spacing=8)
        root.pack_start(color_row, False, False, 0)
        color_row.pack_start(Gtk.Label(label='Colour temperature'), False, False, 0)
        self.color_combo = Gtk.ComboBoxText()
        self.color_combo.set_sensitive(False)
        self.color_combo.connect('changed', self.on_color_preset)
        color_row.pack_start(self.color_combo, True, True, 0)

        picture_row = Gtk.Box(spacing=8)
        root.pack_start(picture_row, False, False, 0)
        picture_row.pack_start(Gtk.Label(label='Picture mode'), False, False, 0)
        self.picture_combo = Gtk.ComboBoxText()
        self.picture_combo.set_sensitive(False)
        self.picture_combo.connect('changed', self.on_picture_mode)
        picture_row.pack_start(self.picture_combo, True, True, 0)

        self.copy_button = Gtk.Button(label='Copy selected monitor settings to…')
        self.copy_button.set_sensitive(False)
        self.copy_button.connect('clicked', self.on_copy)
        root.pack_start(self.copy_button, False, False, 0)

        self.status = Gtk.Label(label='Scanning for monitors…')
        self.status.set_xalign(0)
        self.status.set_line_wrap(True)
        root.pack_start(self.status, False, False, 0)
        self.scan()

    def task(self, fn, callback=None, message='Communicating with monitor…'):
        if self.busy:
            self.status.set_text('Please wait for the current operation.')
            return False
        self.busy = True
        self.status.set_text(message)

        def worker():
            try:
                result, error = fn(), None
            except Exception as exc:
                result, error = None, str(exc)
            GLib.idle_add(self.finished, callback, result, error)

        threading.Thread(target=worker, daemon=True).start()
        return True

    def finished(self, callback, result, error):
        self.busy = False
        if error:
            self.status.set_text('Error: ' + error)
        else:
            self.status.set_text('Ready')
            if callback:
                callback(result)
        if self.refresh_pending:
            self.refresh_pending = False
            self.request_refresh()
        return False

    def scan(self):
        previous = self.display
        def apply(found):
            self.loading = True
            try:
                self.monitors = found
                self.select.remove_all()
                for display, label in found:
                    self.select.append(str(display), label)
                self.display = previous if any(n == previous for n, _ in found) else (found[0][0] if found else None)
                if self.display is not None:
                    self.select.set_active_id(str(self.display))
                self.copy_button.set_sensitive(len(found) > 1)
                if not found:
                    self.status.set_text('No DDC/CI monitors detected. Check ddcutil detect and DDC/CI in the monitor OSD.')
                    for scale in self.sliders.values():
                        scale.set_sensitive(False)
                    self.color_combo.set_sensitive(False)
                    self.picture_combo.set_sensitive(False)
            finally:
                self.loading = False
            if self.display is not None:
                self.request_refresh()
        self.task(discover_monitors, apply, 'Detecting connected monitors…')

    def on_select(self, widget):
        selected = widget.get_active_id()
        if self.loading or selected is None:
            return
        self.display = int(selected)
        self.request_refresh()

    def request_refresh(self):
        if self.display is None:
            return
        if self.busy:
            self.refresh_pending = True
            return
        display = self.display

        def apply(result):
            values, color, picture, advertised = result
            if self.display != display:
                self.request_refresh()
                return
            self.loading = True
            try:
                self.advertised[display] = advertised
                for _, code in FEATURES:
                    scale = self.sliders[code]
                    scale.set_sensitive(code in values)
                    if code in values:
                        value, maximum = values[code]
                        scale.set_range(0, max(1, maximum))
                        scale.set_value(value)

                self.color_combo.remove_all()
                allowed_colors = advertised['14']
                for name, value in COLOR_PRESETS:
                    if not allowed_colors or value in allowed_colors:
                        self.color_combo.append(str(value), name)
                if color is not None and not any(color == v for _, v in COLOR_PRESETS):
                    self.color_combo.append(str(color), f'Current: 0x{color:02X}')
                self.color_combo.set_active_id(str(color) if color is not None else None)
                self.color_combo.set_sensitive(color is not None)

                self.picture_combo.remove_all()
                modes = set(advertised['DC'])
                # This exact model's supported values were independently
                # verified against the hardware, so retain them when ddcutil
                # provides a partial/unparseable capabilities response.
                model_label = next((label for n, label in self.monitors if n == display), '')
                if 'Q27B36X' in model_label.upper():
                    modes |= Q27B36X_DC
                advertised['DC'] = modes
                for name, value in PICTURE_MODES:
                    if value in modes:
                        self.picture_combo.append(f'{value:02X}', name)
                # A known current value is still named even if the monitor's
                # capabilities response is missing, cached, or unparsable.
                # This does not authorise writing unadvertised modes.
                known = dict((value, name) for name, value in PICTURE_MODES)
                if picture is not None and picture not in modes:
                    label = known.get(picture, f'Unknown mode 0x{picture:02X}')
                    self.picture_combo.append(f'{picture:02X}', f'{label} (current)')
                self.picture_combo.set_active_id(f'{picture:02X}' if picture is not None else None)
                self.picture_combo.set_sensitive(bool(modes) and picture is not None)
            finally:
                self.loading = False
        self.task(lambda: read_snapshot(display), apply,
                  f'Reading Monitor {display} (DDC/CI can take a while)…')

    def on_release(self, widget, _event, code):
        if not self.loading and self.display is not None and widget.get_sensitive():
            display, value = self.display, int(widget.get_value())
            self.task(lambda: ddc(display, 'setvcp', code, value),
                      lambda _: self.request_refresh())
        return False

    def on_color_preset(self, widget):
        selected = widget.get_active_id()
        if self.loading or selected is None or self.display is None:
            return
        display, value = self.display, int(selected)
        allowed = self.advertised.get(display, {}).get('14', set())
        if allowed and value not in allowed:
            return
        self.task(lambda: ddc(display, 'setvcp', '14', value),
                  lambda _: self.request_refresh())

    def on_picture_mode(self, widget):
        selected = widget.get_active_id()
        if self.loading or selected is None or self.display is None:
            return
        display, value = self.display, int(selected, 16)
        if value not in self.advertised.get(display, {}).get('DC', set()) or value == 0x8F:
            return
        self.task(lambda: ddc(display, 'setvcp', 'DC', f'0x{value:02X}'),
                  lambda _: self.request_refresh())

    def on_copy(self, _widget):
        if self.display is None:
            return
        targets = [(n, label) for n, label in self.monitors if n != self.display]
        if not targets:
            return
        dialog = Gtk.Dialog(title='Copy monitor settings', transient_for=self, flags=0)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                           'Copy settings', Gtk.ResponseType.OK)
        area = dialog.get_content_area()
        area.set_spacing(8)
        area.pack_start(Gtk.Label(label='Copy settings from selected monitor to:'), False, False, 0)
        destination = Gtk.ComboBoxText()
        for n, label in targets:
            destination.append(str(n), label)
        destination.set_active(0)
        area.pack_start(destination, False, False, 0)
        note = Gtk.Label(label='Only supported controls will be copied. This changes destination settings.')
        note.set_line_wrap(True)
        area.pack_start(note, False, False, 0)
        dialog.show_all()
        response = dialog.run()
        target = destination.get_active_id()
        dialog.destroy()
        if response != Gtk.ResponseType.OK or target is None:
            return
        src, dst = self.display, int(target)

        def execute():
            vals, color, picture, _ = read_snapshot(src)
            dst_vals, _, _, dst_cap = read_snapshot(dst)
            count = 0
            if picture is not None and picture in dst_cap['DC'] and picture != 0x8F:
                ddc(dst, 'setvcp', 'DC', f'0x{picture:02X}')
                count += 1
            if color is not None and (not dst_cap['14'] or color in dst_cap['14']):
                ddc(dst, 'setvcp', '14', color)
                count += 1
            for _, code in FEATURES:
                if code in vals and code in dst_vals:
                    value = min(vals[code][0], dst_vals[code][1])
                    ddc(dst, 'setvcp', code, value)
                    count += 1
            return count

        def after(count):
            self.status.set_text(f'Copied {count} supported settings to Monitor {dst}.')
            if self.display == dst:
                self.request_refresh()
        self.task(execute, after, f'Copying settings to Monitor {dst}…')


if __name__ == '__main__':
    window = Window()
    window.connect('destroy', Gtk.main_quit)
    window.show_all()
    Gtk.main()
