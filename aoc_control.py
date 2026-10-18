#!/usr/bin/env python3
"""AOC Monitor Control v0.4 — GTK3 frontend for ddcutil."""
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
# From AOC i-Menu's StandardGameModes_E; the monitor's own capabilities
# determine which values appear in the dropdown. 0x8F is Reset Color,
# deliberately excluded because it is an action rather than a preset.
PICTURE_MODES = [
    ('Standard', 0x80), ('Reading', 0x82), ('Internet', 0x83),
    ('Movie', 0x84), ('Sports', 0x85), ('Photographer', 0x86),
    ('HDR Picture', 0x87), ('HDR Movie', 0x88), ('HDR Game', 0x89),
    ('FPS', 0x8A), ('RTS', 0x8B), ('Racing', 0x8C),
    ('HDR Off', 0x90), ('DisplayHDR', 0x91),
    ('HDR Picture (alt)', 0x92), ('HDR Movie (alt)', 0x93),
    ('HDR Game (alt)', 0x94), ('Eco Mode', 0xB0),
]


def ddc(display, *args, allow_invalid_mode=False):
    command = ['ddcutil', '--display', str(display), *map(str, args)]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=18)
    if proc.returncode and not (allow_invalid_mode and re.search(r'\bsl\s*=\s*0x[0-9a-f]+', proc.stdout, re.I)):
        raise RuntimeError((proc.stderr or proc.stdout).strip() or 'ddcutil failed')
    return proc.stdout


def read_numeric(display, code):
    output = ddc(display, 'getvcp', code)
    match = re.search(r'current value\s*=\s*(\d+),\s*max value\s*=\s*(\d+)', output, re.I)
    if not match:
        raise ValueError(f'Cannot read VCP {code}: {output.strip()}')
    return int(match.group(1)), int(match.group(2))


def read_color_preset(display):
    output = ddc(display, 'getvcp', '14')
    match = re.search(r'\(0x([0-9a-f]+)\)', output, re.I)
    if not match:
        raise ValueError(f'Cannot read colour temperature: {output.strip()}')
    return int(match.group(1), 16)


def read_picture_mode(display):
    # ddcutil may print "Invalid value (sl=0x80)" for AOC's valid modes.
    output = ddc(display, 'getvcp', 'DC', allow_invalid_mode=True)
    match = re.search(r'\bsl\s*=\s*0x([0-9a-f]+)', output, re.I)
    if not match:
        raise ValueError(f'Cannot read picture mode: {output.strip()}')
    return int(match.group(1), 16)


def supported_picture_modes(display):
    # Prefer the monitor's raw VCP capabilities list.  The human-readable
    # section also contains "Feature: DC (Display Mode)"; do NOT mistake
    # that description for a list of hexadecimal values.
    output = ddc(display, 'capabilities')
    match = re.search(r'\bDC\s*\(\s*((?:[0-9a-fA-F]{2}\s*)+)\)', output, re.I)
    if match:
        supported = {int(value, 16) for value in re.findall(r'[0-9a-fA-F]{2}', match.group(1))}
    else:
        # ddcutil may show only its decoded "Feature: DC" section.
        section = re.search(r'Feature:\s*DC\s*\(Display Mode\).*?Values \(unparsed\):\s*([^\n]+)',
                            output, re.I | re.S)
        if section:
            supported = {int(value, 16) for value in re.findall(r'\b[0-9a-fA-F]{2}\b', section.group(1))}
        else:
            # Q27B36X-specific fallback, obtained from the user's actual
            # capabilities response. Never expose Reset Color (0x8F).
            supported = {0x80, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87,
                         0x88, 0x89, 0x8A, 0x8B, 0x8C, 0x90, 0x91,
                         0x92, 0x93, 0x94, 0xB0}
    return [(label, value) for label, value in PICTURE_MODES if value in supported]


class Window(Gtk.Window):
    def __init__(self):
        super().__init__(title='AOC Monitor Control')
        self.set_default_size(560, 700)
        self.set_border_width(18)
        self.busy = False
        self.loading = False
        self.display = 1
        self.modes_by_display = {}
        self.refresh_pending = False
        self.picture_combo = None

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=11)
        self.add(root)
        heading = Gtk.Label()
        heading.set_markup('<span size="x-large" weight="bold">AOC Monitor Control</span>')
        heading.set_xalign(0)
        root.pack_start(heading, False, False, 0)
        subtitle = Gtk.Label(label='Q27B36X · Hardware DDC/CI controls')
        subtitle.set_xalign(0)
        root.pack_start(subtitle, False, False, 0)

        selector = Gtk.Box(spacing=8)
        root.pack_start(selector, False, False, 0)
        self.select = Gtk.ComboBoxText()
        self.select.append_text('Monitor 1 · HDMI')
        self.select.append_text('Monitor 2 · DisplayPort')
        self.select.set_active(0)
        self.select.connect('changed', self.on_select)
        selector.pack_start(self.select, True, True, 0)
        refresh = Gtk.Button(label='Refresh')
        refresh.connect('clicked', lambda *_: self.request_refresh())
        selector.pack_start(refresh, False, False, 0)

        self.sliders = {}
        for label, code in FEATURES:
            line = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            title = Gtk.Label(label=label)
            title.set_xalign(0)
            line.pack_start(title, False, False, 0)
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
            scale.set_digits(0)
            scale.set_draw_value(True)
            scale.connect('button-release-event', self.on_release, code)
            scale.connect('key-release-event', self.on_release, code)
            line.pack_start(scale, False, False, 0)
            root.pack_start(line, False, False, 0)
            self.sliders[code] = scale

        color_row = Gtk.Box(spacing=8)
        root.pack_start(color_row, False, False, 0)
        color_row.pack_start(Gtk.Label(label='Colour temperature'), False, False, 0)
        self.color_combo = Gtk.ComboBoxText()
        for label, value in COLOR_PRESETS:
            self.color_combo.append(str(value), label)
        self.color_combo.connect('changed', self.on_color_preset)
        color_row.pack_start(self.color_combo, True, True, 0)

        picture_row = Gtk.Box(spacing=8)
        root.pack_start(picture_row, False, False, 0)
        picture_row.pack_start(Gtk.Label(label='Picture mode'), False, False, 0)
        self.picture_combo = Gtk.ComboBoxText()
        self.picture_combo.append('loading', 'Loading picture modes…')
        self.picture_combo.set_active_id('loading')
        self.picture_combo.set_sensitive(False)
        self.picture_combo.connect('changed', self.on_picture_mode)
        picture_row.pack_start(self.picture_combo, True, True, 0)

        buttons = Gtk.Box(spacing=8)
        root.pack_start(buttons, False, False, 0)
        for label, src, dst in [('Copy 1 → 2', 1, 2), ('Copy 2 → 1', 2, 1)]:
            button = Gtk.Button(label=label)
            button.connect('clicked', lambda _b, s=src, d=dst: self.copy(s, d))
            buttons.pack_start(button, True, True, 0)

        self.status = Gtk.Label(label='Ready')
        self.status.set_xalign(0)
        self.status.set_line_wrap(True)
        root.pack_start(self.status, False, False, 0)
        self.request_refresh()

    def task(self, fn, callback=None):
        if self.busy:
            self.status.set_text('Please wait for the current operation.')
            return False
        self.busy = True
        self.status.set_text('Reading monitor settings (DDC/CI may take several seconds)…')

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

    def on_select(self, widget):
        index = widget.get_active()
        if index < 0:
            return
        self.display = index + 1
        self.request_refresh()

    def request_refresh(self):
        if self.busy:
            self.refresh_pending = True
            return
        display = self.display

        def read():
            # Picture mode is independent of slider readings. Do not let a
            # single unavailable VCP prevent the dropdown from loading.
            picture = read_picture_mode(display)
            modes = supported_picture_modes(display)
            values = {}
            for _, code in FEATURES:
                try:
                    values[code] = read_numeric(display, code)
                except (RuntimeError, ValueError, subprocess.TimeoutExpired):
                    pass
            try:
                color = read_color_preset(display)
            except (RuntimeError, ValueError, subprocess.TimeoutExpired):
                color = None
            return display, values, color, picture, modes

        def apply(result):
            source, values, color, picture, modes = result
            if source != self.display:
                self.request_refresh()
                return
            self.loading = True
            try:
                for code, (value, maximum) in values.items():
                    slider = self.sliders[code]
                    slider.set_range(0, max(1, maximum))
                    slider.set_value(value)
                if color is not None:
                    self.color_combo.set_active_id(str(color))
                self.modes_by_display[source] = modes
                self.picture_combo.remove_all()
                for label, value in modes:
                    self.picture_combo.append(f'{value:02X}', label)
                # Display the actual reported mode, including a valid but
                # unmapped value, without presenting it as a selectable preset.
                if not any(value == picture for _, value in modes):
                    self.picture_combo.append(f'{picture:02X}', f'Current: 0x{picture:02X} (unknown)')
                self.picture_combo.set_active_id(f'{picture:02X}')
                self.picture_combo.set_sensitive(bool(modes))
                if not modes:
                    self.status.set_text('No supported picture modes found in monitor capabilities.')
            finally:
                self.loading = False

        self.task(read, apply)

    def on_release(self, widget, _event, code):
        if not self.loading:
            display, value = self.display, int(widget.get_value())
            self.task(lambda: ddc(display, 'setvcp', code, value))
        return False

    def on_color_preset(self, widget):
        selected = widget.get_active_id()
        if not self.loading and selected is not None:
            display, value = self.display, int(selected)
            if self.task(lambda: ddc(display, 'setvcp', '14', value),
                         lambda _: self.request_refresh()):
                pass

    def on_picture_mode(self, widget):
        selected = widget.get_active_id()
        if self.loading or selected is None:
            return
        display, value = self.display, int(selected, 16)
        if value not in {v for _, v in self.modes_by_display.get(display, [])}:
            return
        self.task(lambda: ddc(display, 'setvcp', 'DC', f'0x{value:02X}'),
                  lambda _: self.request_refresh())

    def copy(self, src, dst):
        dialog = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=f'Copy Monitor {src} settings to Monitor {dst}?')
        dialog.format_secondary_text(
            'Copies picture mode (when supported), colour temperature, '
            'brightness, contrast, sharpness and RGB gains. '
            'Changing picture mode may reset some monitor settings.')
        answer = dialog.run()
        dialog.destroy()
        if answer != Gtk.ResponseType.OK:
            return

        def execute():
            values = {code: read_numeric(src, code)[0] for _, code in FEATURES}
            color = read_color_preset(src)
            picture = read_picture_mode(src)
            destination_modes = {value for _, value in supported_picture_modes(dst)}
            copied_picture = picture in destination_modes and picture != 0x8F
            if copied_picture:
                ddc(dst, 'setvcp', 'DC', f'0x{picture:02X}')
            ddc(dst, 'setvcp', '14', color)
            for _, code in FEATURES:
                ddc(dst, 'setvcp', code, values[code])
            return dst, copied_picture

        def after(result):
            destination, copied_picture = result
            if self.display == destination:
                self.request_refresh()
            else:
                suffix = '' if copied_picture else ' (picture mode not copied: unsupported)'
                self.status.set_text(f'Monitor {destination} settings copied{suffix}.')

        self.task(execute, after)


if __name__ == '__main__':
    window = Window()
    window.connect('destroy', Gtk.main_quit)
    window.show_all()
    Gtk.main()
