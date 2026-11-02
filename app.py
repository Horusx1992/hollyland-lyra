#!/usr/bin/env python3
"""English GTK camera workspace for native Hollyland Lyra settings."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import subprocess
import datetime
import time
import uuid

# GTK3's shared-memory Wayland path halves presentation cadence on this GPU.
# Prefer GTK's GL compositor for this process; preserve explicit user overrides.
# GDK retains its Cairo fallback if a GL context cannot be created.
os.environ.setdefault('GDK_GL', 'always')

import recording

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib, Gtk, Pango

import lyra_backend as camera
import preferences
import virtual_camera
from video_preview import Preview, MODES, SHAPES, GstVideo
from camview import effects

ROOT = Path(__file__).resolve().parent
from ui_theme import CSS



def label(text, css=None):
    widget = Gtk.Label(label=text, xalign=0)
    if css:
        widget.get_style_context().add_class(css)
    return widget


def button(text, callback, primary=False):
    widget = Gtk.Button(label=text)
    if primary:
        widget.get_style_context().add_class('primary')
    widget.connect('clicked', callback)
    return widget


def icon_button(icon, title, callback):
    widget = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
    widget.set_tooltip_text(title)
    widget.get_accessible().set_name(title)
    widget.get_style_context().add_class('icon-button')
    widget.get_style_context().add_class('flat')
    widget.connect('clicked', callback)
    return widget


class SettingRow(Gtk.Box):
    def __init__(self, window, name, setting, zoom=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.get_style_context().add_class('setting-row')
        self.window, self.name, self.setting, self.zoom = window, name, setting, zoom
        self._syncing = self._pending = False
        header = Gtk.Box(spacing=8)
        header.pack_start(label(camera.SETTINGS[name], 'section' if zoom else None), True, True, 0)
        self.auto = None
        if name in ('white-balance', 'shutter', 'iso') or setting.get('isAuto', 2) != 2:
            self.auto = Gtk.CheckButton(label='Auto')
            self.auto.get_accessible().set_name(f'Automatic {camera.SETTINGS[name]}')
            self.auto.set_active(setting['isAuto'] == 0)
            self.auto.connect('toggled', self.auto_toggled)
            self.auto.set_tooltip_text('Applies immediately and verifies camera state. Anti-flicker must be OFF for Auto shutter.')
            header.pack_start(self.auto, False, False, 0)
        self.pack_start(header, False, False, 0)
        controls = Gtk.Box(spacing=8)
        if 'list' in setting:
            self.editor = Gtk.ComboBoxText()
            for text in setting['list']:
                self.editor.append_text(str(text))
            self.editor.set_active(int(setting['cur']))
        elif zoom:
            self.editor = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,
                setting['min'], setting['max'], setting['step'])
            self.editor.set_draw_value(False)
            self.editor.set_value(setting['cur'])
        else:
            self.editor = Gtk.SpinButton.new_with_range(setting['min'], setting['max'], setting['step'])
            self.editor.set_digits(0 if setting['step'] >= 1 else 2)
            self.editor.set_value(setting['cur'])
        self.editor.set_hexpand(True)
        self.editor.get_accessible().set_name(camera.SETTINGS[name])
        controls.pack_start(self.editor, True, True, 0)
        self.apply_button = button('Apply', self.apply)
        self.apply_button.get_accessible().set_name(f'Apply {camera.SETTINGS[name]}')
        controls.pack_start(self.apply_button, False, False, 0)
        self.pack_start(controls, False, False, 0)
        if zoom:
            presets = Gtk.Box(spacing=8)
            self.value_label = label('', 'zoom-value')
            presets.pack_start(self.value_label, True, True, 0)
            self.presets = []
            for value in (1, 2, 3, 4):
                preset = button(f'{value}×', lambda _, v=value: self.preset(v))
                preset.set_sensitive(setting['min'] <= value <= setting['max'])
                self.presets.append(preset)
                presets.pack_start(preset, False, False, 0)
            self.pack_start(presets, False, False, 0)
            self.editor.connect('value-changed', lambda _: self._value_text())
            self._value_text()
        else:
            if setting.get('enable') != 1:
                self.pack_start(label('Read-only on this camera', 'muted'), False, False, 0)
            elif self.auto and setting.get('isAuto') == 2:
                self.pack_start(label('Auto requires Anti-flicker OFF', 'muted'), False, False, 0)
            elif 'list' not in setting:
                self.editor.set_tooltip_text(f"Supported range: {setting['min']:g} to {setting['max']:g}")
        self._availability()

    def _availability(self):
        enabled = self.setting.get('enable') == 1 and self.name in camera.WRITABLE
        self.apply_button.set_sensitive(enabled and not (self.auto and self.auto.get_active()))
        self.editor.set_sensitive(enabled and not (self.auto and self.auto.get_active()))
        if self.auto:
            self.auto.set_sensitive(enabled and self.setting.get('isAuto') != 2 and not self._pending)

    def auto_toggled(self, *_):
        if self._syncing:
            return
        requested = self.auto.get_active()
        self._pending = True
        self._availability()
        def task():
            current = camera.read(self.name)
            return camera.apply(self.name, current['cur'], requested)
        def failed(_error):
            self._pending = False
            self.sync_auto()
            self._availability()
        accepted = self.window.submit(task, self.applied,
            f"Setting {camera.SETTINGS[self.name]} to {'Auto' if requested else 'Manual'}…", failed=failed)
        if accepted is False:
            failed(None)

    def sync_auto(self):
        if self.auto:
            self._syncing = True
            self.auto.set_active(self.setting.get('isAuto') == 0)
            self._syncing = False

    def _value_text(self):
        self.value_label.set_text(f'{self.editor.get_value():.1f}×')

    def preset(self, value):
        self.editor.set_value(value)
        self.apply()

    def apply(self, *_):
        value = self.editor.get_active() if 'list' in self.setting else self.editor.get_value()
        if 'list' not in self.setting:
            minimum, step = self.setting['min'], self.setting['step']
            value = min(self.setting['max'], max(minimum,
                minimum+round((value-minimum)/step)*step))
        automatic = bool(self.auto and self.auto.get_active())
        self.window.submit(lambda: camera.apply(self.name, value, automatic), self.applied,
                           f'Applying {camera.SETTINGS[self.name]}…')

    def applied(self, setting):
        self._pending = False
        self.setting = setting
        if 'list' in setting:
            self.editor.set_active(int(setting['cur']))
        else:
            self.editor.set_value(setting['cur'])
        self.sync_auto()
        self._availability()
        mode = ' · Auto' if setting.get('isAuto') == 0 else (' · Manual' if setting.get('isAuto') == 1 else '')
        self.window.status.set_text(f'{camera.SETTINGS[self.name]}{mode} confirmed by the camera.')
        if self.name == 'anti-flicker':
            self.window.refresh()


def section(text, hint=None):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.pack_start(label(text, 'section'), False, False, 0)
    if hint:
        note = label(hint, 'muted')
        note.set_line_wrap(True)
        box.pack_start(note, False, False, 0)
    return box


class Window(Gtk.Window):
    def __init__(self):
        GLib.set_prgname('lyra-control')
        GLib.set_application_name('Lyra Control')
        Gtk.Widget.set_default_direction(Gtk.TextDirection.LTR)
        super().__init__(title='Lyra Control')
        self.set_icon_from_file(str(ROOT/'assets/icon.svg'))
        self.set_default_size(1360, 840)
        self.set_size_request(980, 640)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='lyra-hid')
        self.record_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='lyra-record')
        self.closed = self.busy = self.record_finalizing = self.close_pending = False
        self.preview_only = self.is_fullscreen = self.auto_preview_started = False
        self.auth_process = None
        self.rows = {}
        self.startup_profile_pending = preferences.load_option('startup_camera_profile', 'none') == 'medium-light'
        self.mics = []
        self.last_recording = None
        self.record_folder = Path(preferences.load_option('record_folder', str(Path.home()/'Videos/Lyra Control')))
        if not self.record_folder.is_absolute():
            self.record_folder = Path.home()/'Videos/Lyra Control'
        self.connect('destroy', self.close)
        self.connect('delete-event', self.delete_event)
        self.connect('key-press-event', self.key_pressed)
        self.connect('window-state-event', self.window_state)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)
        self.header = Gtk.Box(spacing=12)
        self.header.get_style_context().add_class('workspace-header')
        camera_icon = Gtk.Image.new_from_icon_name('camera-video-symbolic', Gtk.IconSize.LARGE_TOOLBAR)
        camera_icon.get_style_context().add_class('brand-icon')
        self.header.pack_start(camera_icon, False, False, 0)
        brand = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        brand.pack_start(label('Lyra Control', 'title'), False, False, 0)
        self.device_label = label('Connecting to Hollyland Lyra…', 'muted')
        brand.pack_start(self.device_label, False, False, 0)
        self.header.pack_start(brand, True, True, 0)
        self.format_chip = label('4K · 30 fps', 'source-chip')
        self.format_chip.get_style_context().add_class('mono')
        self.header.pack_start(self.format_chip, False, False, 0)
        self.preview_button = button('Start preview', self.preview, primary=True)
        self.preview_button.set_image(Gtk.Image.new_from_icon_name('media-playback-start-symbolic', Gtk.IconSize.BUTTON))
        self.preview_button.set_always_show_image(True)
        self.refresh_button = icon_button('view-refresh-symbolic', 'Refresh camera', self.refresh)
        self.header.pack_start(self.preview_button, False, False, 0)
        self.header.pack_start(self.refresh_button, False, False, 0)
        root.pack_start(self.header, False, False, 0)
        self.access_button = button('Allow camera access', self.grant_access)
        self.access_button.set_no_show_all(True)
        body = Gtk.Box(spacing=18)
        body.set_border_width(16)
        root.pack_start(body, True, True, 0)
        self.preview_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.preview_panel.set_hexpand(True)
        self.preview_heading = Gtk.Box(spacing=10)
        self.preview_heading.get_style_context().add_class('preview-heading')
        self.preview_heading.pack_start(label('LIVE VIEW', 'eyebrow'), False, False, 0)
        self.preview_badge = label('STOPPED', 'badge')
        self.preview_heading.pack_start(self.preview_badge, False, False, 0)
        self.preview_options = Gtk.Box(spacing=4)
        self.preview_options.pack_start(icon_button('view-reveal-symbolic', 'Picture only · Esc restores controls', lambda _: self.set_preview_only(True)), False, False, 0)
        self.preview_options.pack_start(icon_button('view-fullscreen-symbolic', 'Fullscreen · F / F11', lambda _: self.toggle_fullscreen()), False, False, 0)
        menu = Gtk.MenuButton()
        menu.set_image(Gtk.Image.new_from_icon_name('view-more-symbolic', Gtk.IconSize.BUTTON))
        menu.get_style_context().add_class('icon-button')
        menu.get_style_context().add_class('flat')
        menu.set_tooltip_text('Window options')
        menu.get_accessible().set_name('Window options')
        popover = Gtk.Popover.new(menu)
        popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        popover_box.set_border_width(12)
        top = Gtk.CheckButton(label='Keep window above others')
        top.connect('toggled', lambda item: self.set_keep_above(item.get_active()))
        popover_box.pack_start(top, False, False, 0)
        popover.add(popover_box)
        menu.set_popover(popover)
        popover_box.show_all()
        self.preview_options.pack_start(menu, False, False, 0)
        self.preview_heading.pack_end(self.preview_options, False, False, 0)
        self.preview_panel.pack_start(self.preview_heading, False, False, 0)
        self.video = Preview(self.video_status)
        self.video.rotation = preferences.load_rotation()
        overlay = Gtk.Overlay()
        overlay.add(self.video)
        self.restore_button = button('Show controls · Esc', lambda _: self.set_preview_only(False))
        self.restore_button.set_halign(Gtk.Align.END)
        self.restore_button.set_valign(Gtk.Align.START)
        self.restore_button.set_margin_top(10)
        self.restore_button.set_margin_end(10)
        self.restore_button.set_no_show_all(True)
        overlay.add_overlay(self.restore_button)
        self.placeholder = Gtk.EventBox()
        self.placeholder.get_style_context().add_class('placeholder')
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        empty.set_halign(Gtk.Align.CENTER)
        empty.set_valign(Gtk.Align.CENTER)
        empty_icon = Gtk.Image.new_from_icon_name('camera-video-symbolic', Gtk.IconSize.DIALOG)
        empty.pack_start(empty_icon, False, False, 0)
        empty.pack_start(label('Camera preview', 'section'), False, False, 0)
        empty.pack_start(label('Start the preview to see your Lyra.', 'muted'), False, False, 0)
        self.empty_preview_button = button('Start preview', self.preview, primary=True)
        empty.pack_start(self.empty_preview_button, False, False, 4)
        self.placeholder.add(empty)
        overlay.add_overlay(self.placeholder)
        canvas = Gtk.Frame()
        canvas.set_shadow_type(Gtk.ShadowType.NONE)
        canvas.get_style_context().add_class('canvas-shell')
        canvas.add(overlay)
        self.preview_panel.pack_start(canvas, True, True, 0)
        self.capture_strip = Gtk.Box(spacing=10)
        self.capture_strip.get_style_context().add_class('capture-strip')
        self.preview_panel.pack_start(self.capture_strip, False, False, 0)
        body.pack_start(self.preview_panel, True, True, 0)
        self.inspector_shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.inspector_shell.get_style_context().add_class('inspector')
        self.inspector_shell.set_size_request(388, -1)
        self.inspector_shell.set_hexpand(False)
        self.sidebar = Gtk.Notebook()
        self.sidebar.set_size_request(386, -1)
        self.sidebar.set_hexpand(False)
        self.sidebar.set_scrollable(True)
        self.camera_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.camera_notice = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.camera_notice.set_no_show_all(True)
        self.camera_notice.pack_start(label('Camera controls', 'section'), False, False, 0)
        self.camera_notice_text = label('Reading camera settings…', 'muted')
        self.camera_notice_text.set_line_wrap(True)
        self.camera_notice.pack_start(self.camera_notice_text, False, False, 0)
        self.camera_notice.pack_start(self.access_button, False, False, 0)
        self.camera_retry_button = button('Retry connection', self.refresh)
        self.camera_notice.pack_start(self.camera_retry_button, False, False, 0)
        self.camera_page.pack_start(self.camera_notice, False, False, 0)
        self.controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.camera_page.pack_start(self.controls, False, False, 0)
        self.add_tab(self.camera_page, 'Camera')
        self.framing = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.add_tab(self.framing, 'Framing')
        self.record_options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.add_tab(self.record_options, 'Recording')
        self.inspector_shell.pack_start(self.sidebar, True, True, 0)
        body.pack_start(self.inspector_shell, False, False, 0)
        self.record_bar = Gtk.Box(spacing=16)
        self.record_bar.get_style_context().add_class('transport')
        self.record_button = button('Record', self.toggle_recording)
        self.record_button.set_image(Gtk.Image.new_from_icon_name('media-record-symbolic', Gtk.IconSize.BUTTON))
        self.record_button.set_always_show_image(True)
        self.record_button.get_style_context().add_class('record')
        self.record_button.set_sensitive(False)
        self.record_bar.pack_start(self.record_button, False, False, 0)
        self.record_timer = label('00:00', 'record-timer')
        self.record_timer.set_width_chars(5)
        self.record_bar.pack_start(self.record_timer, False, False, 0)
        context = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.record_context = label('MP4 · Best quality', 'section')
        context.pack_start(self.record_context, False, False, 0)
        self.record_state = label('Select a microphone in Recording', 'record-status')
        self.record_state.set_ellipsize(Pango.EllipsizeMode.END)
        self.record_state.set_max_width_chars(48)
        self.record_state.connect('notify::label', lambda item, _: item.set_tooltip_text(item.get_text()))
        context.pack_start(self.record_state, False, False, 0)
        self.record_details = context
        self.record_bar.pack_start(context, True, True, 0)
        self.record_folder_shortcut = icon_button('folder-open-symbolic', 'Open recordings folder', self.open_record_folder)
        self.record_settings_shortcut = button('Recording settings', lambda _: self.show_recording_settings())
        self.record_bar.pack_end(self.record_folder_shortcut, False, False, 0)
        self.record_bar.pack_end(self.record_settings_shortcut, False, False, 0)
        root.pack_start(self.record_bar, False, False, 0)
        self.footer = Gtk.Box()
        self.status = label('Connecting to camera…', 'status')
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        self.status.set_selectable(True)
        self.status.connect('notify::label', self.status_changed)
        self.footer.pack_start(self.status, True, True, 0)
        root.pack_start(self.footer, False, False, 0)
        self.build_preview_options()
        self.build_record_options()
        self.record_tick = GLib.timeout_add(100, self.recording_tick)
        self.auto_poll_inflight = False
        self.auto_tick = GLib.timeout_add(1500, self.poll_auto)
        self.show_all()
        self.show_camera_notice('Reading camera settings…')
        self.refresh_microphones()
        self.refresh()

    def add_tab(self, content, title):
        content.set_border_width(14)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(content)
        index = self.sidebar.append_page(scroll, label(title))
        self.sidebar.child_set_property(scroll, 'tab-expand', True)
        return index

    def status_changed(self, widget, _param):
        message = widget.get_text()
        widget.set_tooltip_text(message)
        context = widget.get_style_context()
        problem = any(word in message.lower() for word in ('error', 'could not', 'blocked', 'interrupted', 'rejected'))
        context.add_class('error') if problem else context.remove_class('error')

    def show_recording_settings(self):
        if self.preview_only:
            self.set_preview_only(False)
        self.sidebar.set_current_page(2)

    def submit(self, task, done, message, failed=None):
        if self.closed or self.busy:
            return False
        self.busy = True
        self.controls.set_sensitive(False)
        self.refresh_button.set_sensitive(False)
        self.access_button.set_sensitive(False)
        self.empty_preview_button.set_sensitive(False)
        self.camera_retry_button.set_sensitive(False)
        self.status.set_text(message)
        future = self.pool.submit(task)
        def completed(future):
            def update():
                if self.closed:
                    return False
                self.busy = False
                self.controls.set_sensitive(not self.camera_notice.get_visible())
                self.refresh_button.set_sensitive(True)
                self.access_button.set_sensitive(True)
                self.empty_preview_button.set_sensitive(True)
                self.camera_retry_button.set_sensitive(True)
                try:
                    value = future.result()
                except PermissionError as error:
                    self.status.set_text('Camera access is blocked. Click Allow camera access to continue.')
                    self.controls.set_sensitive(False)
                    self.access_button.show()
                    self.camera_unavailable(error)
                    if failed:
                        failed(error)
                except Exception as error:
                    self.status.set_text(f'Could not complete the operation: {error}')
                    if failed:
                        failed(error)
                else:
                    self.access_button.hide()
                    done(value)
                return False
            GLib.idle_add(update)
        future.add_done_callback(completed)
        return True

    def refresh(self, *_):
        self.submit(self.load_camera_settings, self.loaded, 'Reading camera settings…',
                    failed=self.camera_unavailable)

    def load_camera_settings(self):
        if self.startup_profile_pending:
            result = camera.apply_medium_light_profile()
            self.startup_profile_pending = False
            return dict(result['snapshot'], applied_profile='Medium light')
        return camera.snapshot()

    def show_camera_notice(self, message):
        self.camera_notice_text.set_text(message)
        # no-show-all prevents the recovered state reappearing on parent.show_all.
        for child in self.camera_notice.get_children():
            if child is not self.access_button:
                child.show_all()
        self.camera_notice.show()

    def camera_unavailable(self, error):
        blocked = isinstance(error, PermissionError)
        message = ('Camera access is blocked. Allow access to load zoom, '
                   'image and exposure controls.' if blocked else
                   f'Camera controls are unavailable: {error}. Connect your Lyra and retry.')
        self.status.set_text(message)
        self.show_camera_notice(message)
        self.access_button.set_visible(blocked)
        self.controls.set_sensitive(False)

    def loaded(self, data):
        self.camera_notice.hide()
        self.access_button.hide()
        self.controls.set_sensitive(True)
        image_expanded = getattr(self, 'image_expander', None)
        image_expanded = image_expanded.get_expanded() if image_expanded else False
        exposure_expanded = getattr(self, 'exposure_expander', None)
        exposure_expanded = exposure_expanded.get_expanded() if exposure_expanded else True
        for child in self.controls.get_children():
            child.destroy()
        self.rows = {}
        profile_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.medium_light_button = button('Apply Medium light', self.apply_medium_light)
        self.medium_light_button.set_tooltip_text('Neutral image, Auto ISO and white balance, 50Hz anti-flicker and 1/100 shutter. Zoom is unchanged.')
        profile_box.pack_start(self.medium_light_button, False, False, 0)
        self.profile_check = Gtk.CheckButton(label='Use Medium light on startup')
        self.profile_check.set_active(preferences.load_option('startup_camera_profile', 'none') == 'medium-light')
        self.profile_check.connect('toggled', lambda item: preferences.save_option(
            'startup_camera_profile', 'medium-light' if item.get_active() else 'none'))
        profile_box.pack_start(self.profile_check, False, False, 0)
        self.controls.pack_start(profile_box, False, False, 0)
        self.device_label.set_text(f"Hollyland Lyra · {data['info'].get('swVer', '')}")
        values = data['settings']
        zoom = SettingRow(self, 'zoom', values['zoom'], zoom=True)
        zoom.get_style_context().add_class('card')
        zoom.get_style_context().add_class('zoom-panel')
        self.rows['zoom'] = zoom
        self.controls.pack_start(zoom, False, False, 0)
        heading = Gtk.Box(spacing=8)
        heading.pack_start(label('Image & exposure', 'section'), True, True, 0)
        self.reset_button = button('Reset to defaults', self.reset_image)
        self.reset_button.get_style_context().add_class('flat')
        self.reset_button.set_tooltip_text('Restore the first verified Lyra settings, including Anti-flicker OFF and Auto modes. Disables the Medium light startup profile. Zoom is unchanged.')
        heading.pack_end(self.reset_button, False, False, 0)
        self.controls.pack_start(heading, False, False, 0)
        note = label('Auto applies instantly. Apply saves manual values.', 'muted')
        note.set_line_wrap(True)
        self.controls.pack_start(note, False, False, 0)
        for group, names, expanded in [
                ('Exposure & white balance', ('white-balance', 'shutter', 'iso', 'anti-flicker'), exposure_expanded),
                ('Image adjustments', ('brightness', 'contrast', 'saturation', 'sharpness', 'focus-mode'), image_expanded)]:
            expander = Gtk.Expander(label=group)
            expander.set_expanded(expanded)
            panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            panel.get_style_context().add_class('control-group')
            for index, name in enumerate(names):
                if index:
                    panel.pack_start(Gtk.Separator(), False, False, 0)
                row = SettingRow(self, name, values[name])
                self.rows[name] = row
                panel.pack_start(row, False, False, 0)
            expander.add(panel)
            self.controls.pack_start(expander, False, False, 0)
            if group.startswith('Exposure'):
                self.exposure_expander = expander
            else:
                self.image_expander = expander
        self.controls.show_all()
        self.status.set_text('Connected. Medium light startup profile applied.' if data.get('applied_profile') else
                             'Connected. Camera settings are up to date.')
        if not self.auto_preview_started:
            self.auto_preview_started = True
            self.preview()

    def reset_image(self, *_):
        def done(result):
            self.loaded(result['snapshot'])
            self.profile_check.set_active(False)
            note = ' Camera changed Auto availability.' if result['mode_changes'] else ''
            skipped = f" {len(result['skipped'])} unavailable controls skipped." if result['skipped'] else ''
            self.status.set_text(f"Reset {len(result['settings'])} settings; zoom unchanged.{note}{skipped}")
        self.submit(camera.reset_image_defaults, done, 'Restoring image and exposure defaults…')

    def apply_medium_light(self, *_):
        def done(result):
            self.loaded(result['snapshot'])
            self.profile_check.set_active(True)
            self.startup_profile_pending = False
            self.status.set_text('Medium light applied and selected for startup. Auto ISO / white balance · 50Hz · 1/100.')
        self.submit(camera.apply_medium_light_profile, done, 'Applying Medium light profile…')

    def authorize(self, helper):
        if self.closed:
            raise RuntimeError('The window was closed.')
        process = subprocess.Popen(['pkexec', '/usr/bin/python3', '-I', '-B', str(ROOT/helper)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.auth_process = process
        try:
            if self.closed:
                process.terminate()
            _, error = process.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.communicate()
            raise RuntimeError('Authorization timed out. Try again.')
        finally:
            self.auth_process = None
        if process.returncode:
            raise RuntimeError(error.strip() or 'Authorization was not granted. Try again.')

    def grant_access(self, *_):
        def grant():
            self.authorize('grant_lyra_access.py')
            return self.load_camera_settings()
        self.submit(grant, self.loaded, 'Waiting for system authorization…')

    def preview(self, *_):
        if self.video.recorder.active or self.record_finalizing:
            self.status.set_text('Stop recording before stopping the preview.')
            return
        if self.video.running:
            self.video.stop()
            self.video_status('Preview and virtual output stopped.', False)
        else:
            self.submit(video_device, self.open_preview, 'Opening preview…')

    def open_preview(self, node):
        self.video_action(lambda: self.video.start(node, self.mode_choice.get_active_text()))
        if self.video.running:
            self.preview_button.set_label('Stop preview')

    def video_status(self, text, playing):
        self.status.set_text(text)
        self.preview_button.set_label('Stop preview' if playing else 'Start preview')
        preview_style = self.preview_button.get_style_context()
        preview_style.remove_class('primary') if playing else preview_style.add_class('primary')
        self.preview_button.set_image(Gtk.Image.new_from_icon_name(
            'media-playback-stop-symbolic' if playing else 'media-playback-start-symbolic', Gtk.IconSize.BUTTON))
        self.placeholder.set_visible(not playing)
        self.preview_badge.set_text('LIVE' if playing else 'STOPPED')
        badge_style = self.preview_badge.get_style_context()
        badge_style.add_class('live') if playing else badge_style.remove_class('live')
        self.update_capture_label()
        if not playing and self.video.recorder.active and not self.record_finalizing:
            self.stop_recording(reason=text)
        self.update_record_controls()

    def video_action(self, task):
        try:
            task()
        except Exception as error:
            self.status.set_text(str(error))
            if not self.video.running:
                self.preview_button.set_label('Start preview')
                self.preview_button.get_style_context().add_class('primary')
                self.placeholder.show()
                self.preview_badge.set_text('STOPPED')
                self.preview_badge.get_style_context().remove_class('live')
                if hasattr(self, 'mic_choice'):
                    self.update_record_controls()

    def choice(self, names, callback):
        combo = Gtk.ComboBoxText()
        for key, text in names:
            combo.append(key, text)
        combo.set_active(0)
        combo.connect('changed', lambda item: self.video_action(lambda: callback(item)))
        return combo

    def field(self, parent, title, control, hint=None):
        box = section(title, hint)
        box.pack_start(control, False, False, 0)
        parent.pack_start(box, False, False, 0)
        control.get_accessible().set_name(title)

    def build_preview_options(self):
        self.mode_choice = self.choice([(name, name) for name in MODES], self.change_mode)
        saved_mode = preferences.load_option('capture_mode', '4K · 30 fps')
        self.mode_choice.set_active_id(saved_mode if saved_mode in MODES else '4K · 30 fps')
        self.mode_choice.get_accessible().set_name('Capture quality')
        self.mode_choice.set_tooltip_text('Native capture quality used by preview and recordings')
        self.mode_choice.set_size_request(190, -1)
        self.mode_choice.set_hexpand(False)
        self.capture_strip.pack_start(label('Capture', 'muted'), False, False, 0)
        self.capture_strip.pack_start(self.mode_choice, False, False, 0)
        portrait = button('Portrait / Reels', self.portrait)
        portrait.set_tooltip_text('Rotate a vertically mounted camera without cropping')
        self.capture_strip.pack_start(portrait, False, False, 0)
        self.mirror_check = Gtk.CheckButton(label='Mirror')
        self.mirror_check.get_accessible().set_name('Mirror camera horizontally')
        self.mirror_check.connect('toggled', lambda item: self.video_action(lambda: self.video.set_mirror(item.get_active())))
        self.capture_strip.pack_end(self.mirror_check, False, False, 0)
        self.framing.pack_start(section('Composition', 'These changes appear in the preview and recordings.'), False, False, 0)
        self.rotation_choice = self.choice([('0', 'Original · 0°'), ('90', '90° clockwise'),
            ('270', '90° counterclockwise'), ('180', '180°')], self.change_rotation)
        self.rotation_choice.set_active_id(str(self.video.rotation))
        self.field(self.framing, 'Orientation', self.rotation_choice)
        self.shape_choice = self.choice(list(SHAPES.items()), lambda item: self.video.set_shape(item.get_active_id()))
        self.field(self.framing, 'Frame shape', self.shape_choice,
            'Portrait crop trims the image. Use Portrait / Reels for a vertically mounted camera.')
        self.framing.pack_start(Gtk.Separator(), False, False, 0)
        self.effect_choice = self.choice([(item.id, item.label) for item in effects.ALL],
            lambda item: self.video.set_effect(item.get_active_id()))
        self.field(self.framing, 'Look', self.effect_choice)
        self.software_zoom = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.25, 4, 0.25)
        self.software_zoom.set_value(1)
        self.software_zoom.set_digits(2)
        self.software_zoom.connect('value-changed', lambda item: self.video_action(lambda: self.video.set_software_zoom(item.get_value())))
        self.field(self.framing, 'Framing zoom', self.software_zoom,
            'Below 1× adds a black border. Camera zoom is in Camera.')

    def build_record_options(self):
        self.record_options.pack_start(section('Recording setup', 'MP4 video with your selected microphone.'), False, False, 0)
        self.record_quality = self.choice([(key, value[0]) for key, value in recording.QUALITY_PROFILES.items()], self.change_record_quality)
        saved_quality = preferences.load_option('record_quality', 'best')
        self.record_quality.set_active_id(saved_quality if saved_quality in recording.QUALITY_PROFILES else 'best')
        self.field(self.record_options, 'Video quality', self.record_quality)
        self.record_quality.set_tooltip_text('Lossless preserves processed pixels and creates much larger files.')
        self.capture_label = label('', 'muted')
        self.capture_label.set_line_wrap(True)
        self.record_options.pack_start(self.capture_label, False, False, 0)
        self.update_capture_label()
        self.record_options.pack_start(Gtk.Separator(), False, False, 0)
        audio_row = Gtk.Box(spacing=8)
        self.mic_choice = Gtk.ComboBoxText()
        self.mic_choice.set_hexpand(True)
        self.mic_choice.get_accessible().set_name('Recording microphone')
        self.mic_choice.append('none', 'No audio · Video only')
        self.mic_choice.append('default', 'System default microphone')
        self.mic_choice.set_active_id('default')
        self.mic_choice.connect('changed', self.microphone_changed)
        audio_row.pack_start(self.mic_choice, True, True, 0)
        self.mic_refresh = icon_button('view-refresh-symbolic', 'Refresh microphone list', self.refresh_microphones)
        audio_row.pack_start(self.mic_refresh, False, False, 0)
        self.field(self.record_options, 'Microphone', audio_row)
        self.mic_hint = label('Finding microphones…', 'muted')
        self.mic_hint.set_line_wrap(True)
        self.record_options.pack_start(self.mic_hint, False, False, 0)
        self.audio_meter = Gtk.ProgressBar()
        self.audio_meter.set_show_text(True)
        self.audio_meter.set_text('Input level · active while recording')
        self.record_options.pack_start(self.audio_meter, False, False, 0)
        self.record_options.pack_start(Gtk.Separator(), False, False, 0)
        destination = section('Save location')
        self.folder_label = label(str(self.record_folder), 'muted')
        self.folder_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.folder_label.set_max_width_chars(36)
        self.folder_label.set_selectable(True)
        self.folder_label.set_tooltip_text(str(self.record_folder))
        destination.pack_start(self.folder_label, False, False, 0)
        folder_actions = Gtk.Box(spacing=8)
        self.folder_button = button('Choose folder…', self.choose_folder)
        self.open_folder_button = button('Open folder', self.open_record_folder)
        folder_actions.pack_start(self.folder_button, True, True, 0)
        folder_actions.pack_start(self.open_folder_button, True, True, 0)
        destination.pack_start(folder_actions, False, False, 4)
        self.record_options.pack_start(destination, False, False, 0)
        self.virtual_expander = Gtk.Expander(label='Virtual camera output')
        output_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.output_button = button('Enable virtual camera', self.toggle_output)
        self.vlc_button = button('Open output in VLC', self.open_vlc)
        self.vlc_button.set_sensitive(False)
        output_box.pack_start(self.output_button, False, False, 0)
        output_box.pack_start(self.vlc_button, False, False, 0)
        self.output_label = label('Choose Lyra Control in VLC / OBS. Video only.', 'muted')
        self.output_label.set_line_wrap(True)
        output_box.pack_start(self.output_label, False, False, 0)
        self.virtual_expander.add(output_box)
        self.record_options.pack_start(self.virtual_expander, False, False, 0)

    def refresh_microphones(self, *_):
        if self.video.recorder.active or self.record_finalizing:
            return
        self.mic_refresh.set_sensitive(False)
        selected = self.mic_choice.get_active_id() or preferences.load_option('microphone', 'default')
        future = self.pool.submit(recording.microphones)
        def completed(future):
            def update():
                if self.closed:
                    return False
                self.mic_refresh.set_sensitive(True)
                try:
                    self.mics = future.result()
                except Exception as error:
                    self.mic_hint.set_text(f'Could not list microphones: {error}. Video-only recording is available.')
                    return False
                saved = preferences.load_option('microphone', selected)
                self.mic_choice.handler_block_by_func(self.microphone_changed)
                self.mic_choice.remove_all()
                self.mic_choice.append('none', 'No audio · Video only')
                self.mic_choice.append('default', 'System default microphone')
                for mic in self.mics:
                    self.mic_choice.append(mic.name, mic.description)
                valid = {'none', 'default'} | {mic.name for mic in self.mics}
                self.mic_choice.set_active_id(saved if saved in valid else 'default')
                self.mic_choice.handler_unblock_by_func(self.microphone_changed)
                self.mic_hint.set_text(f'{len(self.mics)} inputs available · Captured only while recording')
                self.update_record_controls()
                return False
            GLib.idle_add(update)
        future.add_done_callback(completed)

    def change_record_quality(self, item):
        preferences.save_option('record_quality', item.get_active_id())
        self.update_capture_label()

    def update_capture_label(self):
        mode = self.mode_choice.get_active_text() if hasattr(self, 'mode_choice') else '4K · 30 fps'
        if hasattr(self, 'format_chip'):
            self.format_chip.set_text(mode)
        if hasattr(self, 'capture_label'):
            details = f'Native capture · {mode}'
            if self.video.last_caps:
                info = GstVideo.VideoInfo.new_from_caps(self.video.last_caps)
                details += f' · {info.width} × {info.height}'
            self.capture_label.set_text(details)
        if hasattr(self, 'record_quality') and hasattr(self, 'record_context'):
            self.record_context.set_text('MP4 · '+str(self.record_quality.get_active_text() or 'Best quality'))

    def poll_auto(self):
        if self.closed:
            return False
        names = [name for name, row in self.rows.items()
                 if row.auto and row.setting.get('isAuto') == 0 and not row._pending]
        if self.busy or self.auto_poll_inflight or not names:
            return True
        self.auto_poll_inflight = True
        rows = {name: self.rows[name] for name in names}
        future = self.pool.submit(lambda: {name: camera.read(name) for name in names})
        def completed(future):
            def update():
                self.auto_poll_inflight = False
                if self.closed:
                    return False
                try:
                    values = future.result()
                except Exception:
                    return False
                for name, setting in values.items():
                    row = self.rows.get(name)
                    if row is rows[name] and not row._pending and row.setting.get('isAuto') == 0:
                        row.setting = setting
                        if 'list' in setting:
                            row.editor.set_active(int(setting['cur']))
                        else:
                            row.editor.set_value(setting['cur'])
                        row.sync_auto()
                        row._availability()
                return False
            GLib.idle_add(update)
        future.add_done_callback(completed)
        return True

    def microphone_changed(self, *_):
        selected = self.mic_choice.get_active_id()
        if selected:
            preferences.save_option('microphone', selected)
            self.update_record_controls()

    def choose_folder(self, *_):
        dialog = Gtk.FileChooserDialog(title='Choose recording folder', parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Choose folder', Gtk.ResponseType.OK)
        dialog.set_current_folder(str(self.record_folder if self.record_folder.exists() else Path.home()))
        if dialog.run() == Gtk.ResponseType.OK:
            self.record_folder = Path(dialog.get_filename())
            preferences.save_option('record_folder', str(self.record_folder))
            self.folder_label.set_text(str(self.record_folder))
            self.folder_label.set_tooltip_text(str(self.record_folder))
        dialog.destroy()

    def open_record_folder(self, *_):
        try:
            self.record_folder.mkdir(parents=True, exist_ok=True)
            Gtk.show_uri_on_window(self, self.record_folder.as_uri(), Gdk.CURRENT_TIME)
        except Exception as error:
            self.status.set_text(f'Could not open folder: {error}')

    def toggle_recording(self, *_):
        if self.record_finalizing:
            return
        if self.video.recorder.active:
            self.stop_recording()
            return
        if not self.video.running or self.video.last_caps is None:
            self.status.set_text('Start the preview and wait for a camera frame first.')
            return
        selected = self.mic_choice.get_active_id()
        if selected is None:
            self.status.set_text('Select a microphone or choose No audio.')
            return
        stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        path = self.record_folder/f'Lyra_{stamp}_{uuid.uuid4().hex[:6]}.mp4'
        try:
            self.video.recorder.start(path, self.video.last_caps,
                microphone=None if selected == 'none' else selected,
                quality=self.record_quality.get_active_id())
        except Exception as error:
            self.status.set_text(f'Could not start recording: {error}')
            return
        self.record_state.set_text('Recording · '+(self.mic_choice.get_active_text() or ''))
        self.status.set_text(f'Recording to {path}')
        self.update_record_controls()

    def stop_recording(self, reason=None):
        if self.record_finalizing or not self.video.recorder.active:
            return
        self.record_finalizing = True
        self.record_state.set_text('Finishing MP4…')
        self.update_record_controls()
        future = self.record_pool.submit(self.video.recorder.finish)
        def complete(future):
            def done():
                self.record_finalizing = False
                try:
                    result = future.result()
                except Exception as error:
                    if not self.closed:
                        self.status.set_text(f'Recording interrupted: {error}')
                        self.record_state.set_text('Recording interrupted · check the saved file')
                else:
                    self.last_recording = result
                    if not self.closed:
                        self.status.set_text(f"Saved {result['path']}"+(f' · {reason}' if reason else ''))
                        self.record_state.set_text('Saved · '+Path(result['path']).name)
                if self.closed:
                    Gtk.main_quit()
                elif self.close_pending:
                    self.destroy()
                else:
                    self.update_record_controls()
                return False
            GLib.idle_add(done)
        future.add_done_callback(complete)

    def update_record_controls(self):
        active = self.video.recorder.active or self.record_finalizing
        self.record_bar.set_visible(not self.preview_only or active)
        context = self.record_state.get_style_context()
        context.add_class('recording') if active else context.remove_class('recording')
        self.record_button.set_label('Stop recording' if active else 'Record')
        self.record_button.set_image(Gtk.Image.new_from_icon_name(
            'media-playback-stop-symbolic' if active else 'media-record-symbolic', Gtk.IconSize.BUTTON))
        self.record_button.set_sensitive(not self.record_finalizing and (active or (self.video.running and self.video.last_caps is not None)))
        self.framing.set_sensitive(not active)
        self.capture_strip.set_sensitive(not active)
        for widget in (self.mic_choice, self.mic_refresh, self.folder_button, self.output_button, self.preview_button, self.record_quality):
            widget.set_sensitive(not active)
        if not active and not self.last_recording:
            self.record_state.set_text(self.mic_choice.get_active_text() or 'Select a microphone')

    def recording_tick(self):
        if self.closed:
            return False
        recorder = self.video.recorder
        if recorder.active and not self.record_finalizing:
            elapsed = int(time.monotonic()-recorder.started)
            self.record_timer.set_text(f'{elapsed//60:02}:{elapsed%60:02}')
            try:
                recorder.poll()
            except Exception as error:
                self.stop_recording(reason=str(error))
            self.audio_meter.set_fraction(recorder.peak)
            self.audio_meter.set_text('Microphone level' if recorder.audio_enabled else 'Video only · no audio track')
        return True

    def change_rotation(self, item):
        degrees = int(item.get_active_id())
        self.video.set_rotation(degrees)
        preferences.save_rotation(degrees)
        self.update_capture_label()

    def portrait(self, *_):
        self.shape_choice.set_active_id('rectangle')
        self.rotation_choice.set_active_id('90')
        self.status.set_text('Full-frame portrait. Choose 90° counterclockwise if your camera is mounted the other way.')

    def toggle_output(self, *_):
        if self.busy or self.video.recorder.active or self.record_finalizing:
            return
        if self.video.output_device:
            self.video_action(lambda: self.video.set_output_device(None))
            self.output_button.set_label('Enable virtual camera')
            self.vlc_button.set_sensitive(False)
            self.output_label.set_text('Virtual camera disabled.')
            return
        def setup():
            import os
            node = virtual_camera.find_device()
            if not node or not os.access(node, os.W_OK):
                self.authorize('setup_virtual_camera.py')
                node = virtual_camera.find_device()
            if not node:
                raise RuntimeError('Virtual camera not found after setup.')
            return node, video_device()
        def enabled(result):
            node, source = result
            try:
                self.video.set_output_device(node)
                if not self.video.running:
                    self.video.start(source, self.mode_choice.get_active_text())
            except Exception as error:
                self.video.output_device = None
                self.status.set_text(f'Could not start virtual output: {error}')
                return
            self.output_button.set_label('Disable virtual camera')
            self.vlc_button.set_sensitive(True)
            self.output_label.set_text(f'Lyra Control · {node}. Close the consumer before changing output size/orientation.')
        self.submit(setup, enabled, 'Setting up virtual output; system authorization may appear…')

    def open_vlc(self, *_):
        node = self.video.output_device
        if not node or node != virtual_camera.find_device() or not self.video.running:
            self.status.set_text('Start the preview and enable virtual output first.')
            return
        try:
            subprocess.Popen(['vlc', '--no-one-instance', '--no-video-title-show',
                              f'v4l2://{node}', ':v4l2-chroma=YUYV', ':live-caching=80'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as error:
            self.status.set_text(f'Could not open VLC: {error}')

    def change_mode(self, item):
        preferences.save_option('capture_mode', item.get_active_text())
        self.update_capture_label()
        if self.video.running:
            self.video.start(self.video.capture.device, item.get_active_text())

    def set_preview_only(self, enabled):
        if enabled and not self.preview_only:
            self.previous_size = self.get_size()
        self.preview_only = enabled
        for widget in (self.sidebar, self.inspector_shell, self.header, self.status,
                       self.footer, self.preview_options, self.preview_heading, self.capture_strip):
            widget.set_visible(not enabled)
        self.restore_button.set_visible(enabled)
        for widget in (self.record_details, self.record_folder_shortcut, self.record_settings_shortcut):
            widget.set_visible(not enabled)
        self.record_bar.set_visible(not enabled or self.video.recorder.active or self.record_finalizing)
        self.set_decorated(not enabled)
        if enabled:
            self.set_size_request(220, 160)
            self.video.set_size_request(180, 120)
            self.resize(640, 400)
        else:
            self.set_size_request(980, 640)
            self.video.set_size_request(400, 280)
            self.resize(*getattr(self, 'previous_size', (1280, 820)))

    def toggle_fullscreen(self):
        self.unfullscreen() if self.is_fullscreen else self.fullscreen()

    def window_state(self, widget, event):
        self.is_fullscreen = bool(event.new_window_state & Gdk.WindowState.FULLSCREEN)
        return False

    def key_pressed(self, widget, event):
        key = Gdk.keyval_name(event.keyval)
        focus = self.get_focus()
        typing = isinstance(focus, (Gtk.Entry, Gtk.SpinButton))
        if key in ('F11',) or (key in ('f', 'F') and not typing):
            self.toggle_fullscreen()
            return True
        if key == 'Escape':
            if self.preview_only:
                self.set_preview_only(False)
            elif self.is_fullscreen:
                self.unfullscreen()
            return True
        return False

    def delete_event(self, *_):
        if self.video.recorder.active or self.record_finalizing:
            self.close_pending = True
            self.stop_recording()
            return True
        return False

    def close(self, *_):
        self.closed = True
        if self.record_tick:
            GLib.source_remove(self.record_tick)
            self.record_tick = 0
        if self.auto_tick:
            GLib.source_remove(self.auto_tick)
            self.auto_tick = 0
        if self.auth_process and self.auth_process.poll() is None:
            try:
                self.auth_process.terminate()
            except ProcessLookupError:
                pass
        if self.video.recorder.active and not self.record_finalizing:
            self.stop_recording()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.record_pool.shutdown(wait=False)
        self.video.stop()
        if not self.record_finalizing:
            Gtk.main_quit()


def video_device():
    for entry in sorted(Path('/sys/class/video4linux').glob('video*')):
        device = (entry/'device').resolve()
        matches = False
        for parent in (device, *device.parents):
            try:
                if (parent/'idVendor').read_text().strip() == '3547' and (parent/'idProduct').read_text().strip() == '0500':
                    matches = True
                    break
            except FileNotFoundError:
                pass
        if matches:
            node = '/dev/'+entry.name
            result = subprocess.run(['v4l2-ctl', '-d', node, '--list-formats-ext'],
                                    capture_output=True, text=True, timeout=2)
            if result.returncode == 0 and 'NV12' in result.stdout:
                return node
    raise RuntimeError('No available Lyra video capture interface was found.')


if __name__ == '__main__':
    Window()
    Gtk.main()
