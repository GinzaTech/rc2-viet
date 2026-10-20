"""Offline animation studio used by the RC2 desktop application.

The editor never takes ownership of a USB connection. Installation is delegated
to the desktop application's callback after an export has completed.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import colorchooser, filedialog, ttk

from PIL import ImageTk

from .animation import (
    EFFECTS, LOOP_EFFECTS, PRESETS, export_animation, load_project,
    make_layer, new_project, render_frame, save_project, validate_project,
)
from .animation_install import _validate_zip
from . import desktop_theme as theme
from .desktop_theme import ctk, BG, SURFACE, PANEL, FIELD, LINE, FG, MUTED, ACCENT


def _file_digest(path):
    with Path(path).open('rb') as source:
        digest = hashlib.sha256()
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _file_signature(path):
    info = Path(path).stat()
    return info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _fingerprint(project, asset_cache=None):
    """Include imported content so unchanged paths cannot hide changed assets."""
    assets = set()
    background = project.get('background', {})
    if background.get('image'):
        assets.add(str(background['image']))
    for layer in project.get('layers', []):
        assets.update(str(layer[field]) for field in ('image', 'font') if layer.get(field))
    provenance = {}
    for value in sorted(assets):
        try:
            path = Path(value).expanduser().resolve()
            key = (str(path),) + _file_signature(path)
            if asset_cache is not None and key in asset_cache:
                digest = asset_cache[key]
            else:
                digest = _file_digest(path)
                if asset_cache is not None:
                    # Keep only the current signature for each source file.
                    for old_key in tuple(asset_cache):
                        if old_key[0] == str(path):
                            del asset_cache[old_key]
                    asset_cache[key] = digest
            provenance[value] = digest
        except (OSError, ValueError) as error:
            provenance[value] = f'unavailable:{type(error).__name__}'
    content = {'project': project, 'assets': provenance}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


class _ScrollPanel(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=SURFACE, corner_radius=0)
        self.canvas = tk.Canvas(self, bg=SURFACE, highlightthickness=0, bd=0)
        scroll = ctk.CTkScrollbar(self, orientation='vertical', command=self.canvas.yview,
                                  width=10, fg_color=SURFACE, button_color=LINE,
                                  button_hover_color='#516476')
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = theme.frame(self.canvas, color=SURFACE)
        window = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda _: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda event: self.canvas.itemconfigure(window, width=event.width))
        for widget in (self.canvas, self.body):
            widget.bind('<MouseWheel>', self._wheel)

    def _wheel(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120), 'units')


class AnimationEditor:
    """Animation workspace, optionally hosted inside the desktop application's page."""

    def __init__(self, parent, work, *, install_callback=None, busy_callback=None,
                 serial_var=None, grounded_var=None, scan_callback=None,
                 device_status_var=None, embedded=False, back_callback=None,
                 reconnect_callback=None, reconnect_state_callback=None):
        self.parent = parent
        self.embedded = bool(embedded)
        self.back_callback = back_callback
        self._visible = not self.embedded
        self._bindings = []
        self.work = Path(work)
        self.library = self.work / 'projects'
        self.cache = self.work / 'cache'
        self.exports = self.work / 'exports'
        for folder in (self.library, self.cache, self.exports):
            folder.mkdir(parents=True, exist_ok=True)
        self.install_callback = install_callback
        self.busy_callback = busy_callback or (lambda: False)
        self.scan_callback = scan_callback
        self.reconnect_callback = reconnect_callback
        self.reconnect_state_callback = reconnect_state_callback
        self.project = new_project('scifi')
        self.project_path = None
        self._recovery_path = None
        self.current_export = None
        self.export_fingerprint = None
        self.export_sha256 = None
        self._export_stat = None
        self._asset_cache = {}
        self.selected = 0 if self.project['layers'] else -1
        self.dirty = False
        self._loading = False
        self._closing = False
        self._destroyed = False
        self._after = set()
        self._form_job = None
        self._forms_valid = True
        self._preview_job = None
        self._worker = None
        self._cancel = threading.Event()
        self._events = queue.Queue()
        self._package_job = None
        self._package_generation = 0
        self._package_cancel = threading.Event()
        self._package_worker = None
        self._package_observed_key = None
        self._package_pending_key = None
        self._package_validated_key = None
        self._package_details = None
        self._package_state = 'empty'
        self._package_cache = {}
        self._package_path_remembered = False
        self._package_persistence_error = None
        self._playing = False
        self._play_clock = 0.0
        self._play_offset = 0.0
        self._showing_poster = False
        self._preview_photo = None
        self._preview_item = None
        self._preview_bounds = (0, 0, 1, 1)
        self._library_paths = []
        if self.embedded:
            self.window = parent.winfo_toplevel()
        else:
            self.window = ctk.CTkToplevel(parent)
            self.window.title('RC2 · Animation Studio · r14.4')
            self.window.geometry('1240x760')
            self.window.minsize(1050, 650)
            theme.setup(self.window)
            self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.view = theme.frame(parent if self.embedded else self.window, color=BG)
        if self._visible:
            self.view.pack(fill='both', expand=True)
        self.serial_var = serial_var if serial_var is not None else tk.StringVar(self.window)
        self.grounded_var = grounded_var if grounded_var is not None else tk.BooleanVar(self.window, False)
        self.device_status_var = device_status_var
        self.status = tk.StringVar(self.window, 'Thêm chữ hoặc ảnh, chọn chuyển động rồi xem ngay ở giữa.')
        self.name_var = tk.StringVar(self.window)
        self.preset_var = tk.StringVar(self.window, str(PRESETS.get('scifi', 'scifi')))
        self.time_var = tk.DoubleVar(self.window, 0.0)
        self.clock_var = tk.StringVar(self.window, '0.00 s · Mở đầu')
        self.package_path_var = tk.StringVar(self.window, self._load_package_path())
        self.package_status_var = tk.StringVar(self.window, 'Chọn ZIP để cài. Sửa thiết kế cần xuất lại ZIP.')
        self.layer_vars = {}
        self.scene_vars = {}
        self.background_vars = {}
        self._style()
        self._build()
        self._sync_all()
        # Open on the composed sample so the canvas is useful before playback.
        self.time_var.set(max(0.0, float(self.project['intro']) - .2))
        self._showing_poster = True
        self._request_preview()
        self._refresh_library()
        self._schedule(120, self._poll)
        self._bind_owned('<Control-s>', lambda _: self.save(), shortcut=True)
        self._bind_owned('<Control-o>', lambda _: self.open_project(), shortcut=True)
        self._bind_owned('<Control-n>', lambda _: self.create_project(), shortcut=True)
        self._bind_owned('<MouseWheel>', self._scroll_properties)
        self.package_path_var.trace_add('write', self._package_changed)
        self._package_changed()

    def _bind_owned(self, sequence, callback, *, shortcut=False):
        def when_visible(event):
            if self._visible and not self._closing and not self._destroyed:
                callback(event)
                if shortcut:
                    return 'break'
            return None
        binding = self.window.bind(sequence, when_visible, add='+')
        self._bindings.append((sequence, binding))

    def _update_title(self):
        if self._visible and not self._destroyed:
            title = f"RC2 · Animation Studio · r14.4 · {self.project['name']}"
            if self.dirty:
                title += ' *'
            if self.window.title() != title:
                self.window.title(title)

    def show(self):
        if self._destroyed or self._closing:
            return False
        self._visible = True
        self.view.pack(fill='both', expand=True)
        self._update_title()
        self._update_controls()
        self._request_preview()
        return True

    def hide(self):
        if self._destroyed:
            return
        self._visible = False
        self._playing = False
        self.play_button.configure(text='▶ Phát')
        self._unschedule(self._preview_job)
        self._preview_job = None
        self.view.pack_forget()

    @property
    def busy(self):
        return bool(self._worker and self._worker.is_alive())

    def _schedule(self, delay, callback):
        if self._destroyed:
            return None
        token = None
        def run():
            self._after.discard(token)
            if not self._destroyed:
                callback()
        token = self.window.after(delay, run)
        self._after.add(token)
        return token

    def _unschedule(self, token):
        if token:
            self._after.discard(token)
            try:
                self.window.after_cancel(token)
            except tk.TclError:
                pass

    def _style(self):
        self.view.configure(fg_color=BG)
        style = ttk.Style(self.window)
        if style.theme_use() != 'clam':
            style.theme_use('clam')
        style.configure('Anim.Horizontal.TProgressbar', background=ACCENT,
                        troughcolor=FIELD, borderwidth=0, bordercolor=FIELD,
                        lightcolor=FIELD, darkcolor=FIELD, thickness=4,
                        troughrelief='flat', pbarrelief='flat')

    def _button(self, parent, text, command, **kwargs):
        kwargs.setdefault('width', 80)
        kwargs.setdefault('height', 32)
        return theme.button(parent, text, command, **kwargs)

    def _label(self, parent, text='', **kwargs):
        return theme.label(parent, text, **kwargs)

    def _section(self, parent, title, *, hint=None):
        section = theme.frame(parent, color=SURFACE)
        section.pack(fill='x', padx=(8, 4), pady=(8, 4))
        self._label(section, title, size=13, bold=True).pack(anchor='w', pady=(2, 6))
        if hint:
            self._label(section, hint, muted=True, size=11, wraplength=245,
                        justify='left').pack(anchor='w', pady=(0, 6))
        return section

    def _pair(self, parent):
        row = theme.frame(parent)
        row.pack(fill='x')
        row.columnconfigure((0, 1), weight=1, uniform='field')
        left, right = theme.frame(row), theme.frame(row)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        right.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        return left, right

    def _build(self):
        top = theme.frame(self.view)
        top.pack(fill='x', padx=20, pady=(16, 10))
        if self.back_callback is not None:
            self.back_button = self._button(top, '← Quay lại', self.back_callback,
                                            variant='ghost', width=96, height=36)
            self.back_button.pack(side='left', padx=(0, 10))
        mark = theme.frame(top, color='#263f39', radius=14, width=44, height=44)
        mark.pack(side='left', padx=(0, 12)); mark.pack_propagate(False)
        self._label(mark, 'A', size=24, bold=True, text_color=ACCENT,
                    anchor='center').pack(fill='both', expand=True, padx=7, pady=7)
        heading = theme.frame(top); heading.pack(side='left')
        self._label(heading, 'Animation Studio', size=22, bold=True).pack(anchor='w')
        self._label(heading, 'Tạo dấu ấn riêng cho tay RC2', muted=True, size=12).pack(anchor='w')
        for text, command, variant in (('Lưu thành…', self.save_as, 'ghost'),
                                       ('Lưu thiết kế', self.save, 'primary'),
                                       ('Mở…', self.open_project, 'secondary'),
                                       ('+ Mới', self.create_project, 'ghost')):
            self._button(top, text, command, variant=variant, height=36,
                         width=104 if variant == 'primary' else 76).pack(side='right', padx=(6, 0))

        names = theme.frame(self.view)
        names.pack(fill='x', padx=22, pady=(0, 12))
        self._label(names, 'Thiết kế', muted=True, size=12).pack(side='left', padx=(0, 12))
        self.name_entry = theme.entry(names, self.name_var, width=260, height=34)
        self.name_entry.pack(side='left', fill='x', expand=True)
        self.name_var.trace_add('write', self._name_changed)
        self._button(names, 'Nhân bản thiết kế', self.duplicate_project, variant='ghost',
                     width=132).pack(side='left', padx=(8, 0))

        footer = theme.frame(self.view)
        footer.pack(side='bottom', fill='x', padx=22, pady=(8, 10))
        self.status_label = self._label(footer, textvariable=self.status, muted=True,
                                       size=11, wraplength=1180, justify='left')
        self.status_label.pack(anchor='w')
        footer.bind('<Configure>', lambda event: self.status_label.configure(wraplength=max(300, event.width)))

        workspace = theme.frame(self.view)
        workspace.pack(fill='both', expand=True, padx=20)
        workspace.rowconfigure(0, weight=1)
        workspace.columnconfigure(0, minsize=208)
        workspace.columnconfigure(1, weight=1)
        workspace.columnconfigure(2, minsize=292)
        left = theme.frame(workspace, color=SURFACE, radius=18, width=208)
        center = theme.frame(workspace)
        right = theme.frame(workspace, color=SURFACE, radius=18, width=292)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 12))
        center.grid(row=0, column=1, sticky='nsew')
        right.grid(row=0, column=2, sticky='nsew', padx=(12, 0))
        left.grid_propagate(False); right.pack_propagate(False)
        left.columnconfigure(0, weight=1); left.rowconfigure(1, weight=1)

        presets = theme.frame(left)
        presets.grid(row=0, column=0, sticky='ew', padx=14, pady=(14, 10))
        self._label(presets, 'Bắt đầu từ mẫu', bold=True, size=14).pack(anchor='w', pady=(0, 7))
        self.preset_combo = theme.combo(presets, self.preset_var, PRESETS.values(), width=164, height=32)
        self.preset_combo.pack(fill='x')
        self._button(presets, 'Dùng mẫu này', self.apply_preset, height=30,
                     fg_color='#29453d', text_color=ACCENT).pack(fill='x', pady=(6, 0))

        layers = theme.frame(left)
        layers.grid(row=1, column=0, sticky='nsew', padx=14)
        self._label(layers, 'Các lớp', bold=True, size=14).pack(anchor='w', pady=(0, 6))
        layer_well = theme.frame(layers, color=FIELD, radius=12)
        layer_well.pack(fill='both', expand=True)
        self.layer_list = tk.Listbox(layer_well, bg=FIELD, fg=FG, selectbackground='#345c52',
                                    selectforeground=FG, highlightthickness=0, bd=0,
                                    relief='flat', activestyle='none', exportselection=False,
                                    font=('Segoe UI', 11), height=3)
        self.layer_list.pack(fill='both', expand=True, padx=9, pady=9)
        self.layer_list.bind('<<ListboxSelect>>', self._select_layer)
        row = theme.frame(layers); row.pack(fill='x', pady=(8, 0))
        self.add_text_button = self._button(row, '+ Chữ', self.add_text, width=64)
        self.add_text_button.pack(side='left', fill='x', expand=True)
        self.add_image_button = self._button(row, '+ Ảnh', self.import_image, width=64)
        self.add_image_button.pack(side='left', fill='x', expand=True, padx=(6, 0))
        row = theme.frame(layers); row.pack(fill='x', pady=(4, 0))
        self._button(row, 'Nhân bản', self.duplicate_layer, variant='ghost', height=26,
                     width=70).pack(side='left', fill='x', expand=True)
        self._button(row, 'Xóa', self.remove_layer, variant='ghost', height=26,
                     width=48).pack(side='left', fill='x', expand=True, padx=(6, 0))
        row = theme.frame(layers); row.pack(fill='x')
        self._button(row, '↑ Lên', lambda: self.move_layer(-1), variant='ghost', height=26,
                     width=64).pack(side='left', fill='x', expand=True)
        self._button(row, '↓ Xuống', lambda: self.move_layer(1), variant='ghost', height=26,
                     width=64).pack(side='left', fill='x', expand=True, padx=(6, 0))

        library = theme.frame(left)
        library.grid(row=2, column=0, sticky='ew', padx=14, pady=(10, 12))
        self._label(library, 'Thư viện thiết kế', bold=True, size=14).pack(anchor='w', pady=(0, 6))
        library_well = theme.frame(library, color=FIELD, radius=12)
        library_well.pack(fill='x')
        self.library_list = tk.Listbox(library_well, bg=FIELD, fg=MUTED, selectbackground='#345c52',
                                      selectforeground=FG, highlightthickness=0, bd=0,
                                      relief='flat', activestyle='none', exportselection=False,
                                      font=('Segoe UI', 10), height=2)
        self.library_list.pack(fill='x', padx=9, pady=6)
        self.library_list.bind('<Double-1>', lambda _: self.open_library_project())
        self._button(library, 'Mở thiết kế đã chọn', self.open_library_project,
                     variant='ghost', height=26).pack(fill='x', pady=(4, 0))

        center.columnconfigure(0, weight=1); center.rowconfigure(0, weight=1)
        preview = theme.frame(center, color=SURFACE, radius=18)
        preview.grid(row=0, column=0, sticky='nsew')
        preview.columnconfigure(0, weight=1); preview.rowconfigure(1, weight=1)
        preview_top = theme.frame(preview)
        preview_top.grid(row=0, column=0, sticky='ew', padx=16, pady=(10, 6))
        self._label(preview_top, 'Xem trước', bold=True, size=15).pack(side='left')
        self._label(preview_top, '  LIVE  ', text_color=ACCENT, size=10, bold=True,
                    fg_color='#29453d', corner_radius=8, height=22).pack(side='right')
        screen = theme.frame(preview, color='#090d13', radius=14)
        screen.grid(row=1, column=0, sticky='nsew', padx=12)
        self.preview_canvas = tk.Canvas(screen, bg='#090d13', highlightthickness=0,
                                        bd=0, height=72, width=100)
        self.preview_canvas.pack(fill='both', expand=True, padx=8, pady=8)
        self.preview_canvas.bind('<Configure>', lambda _: self._request_preview())
        self.preview_canvas.bind('<Button-1>', self._drag_preview)
        self.preview_canvas.bind('<B1-Motion>', self._drag_preview)
        transport = theme.frame(preview)
        transport.grid(row=2, column=0, sticky='ew', padx=14, pady=(8, 0))
        self.play_button = self._button(transport, '▶ Phát', self.toggle_play, width=76, height=30)
        self.play_button.pack(side='left')
        self._button(transport, '↺ Từ đầu', self.restart_preview, variant='ghost',
                     width=82, height=30).pack(side='left', padx=(4, 0))
        self._label(transport, textvariable=self.clock_var, muted=True, size=11).pack(side='right')
        self.timeline = ctk.CTkSlider(preview, variable=self.time_var, from_=0, to=5,
                                      command=self._scrub, height=14, fg_color=LINE,
                                      progress_color=ACCENT, button_color=ACCENT,
                                      button_hover_color='#a4efd5', button_length=12,
                                      button_corner_radius=6)
        self.timeline.grid(row=3, column=0, sticky='ew', padx=18, pady=(4, 0))
        preview_hint = self._label(preview, 'Kéo chữ hoặc ảnh ngay trên khung để đổi vị trí.',
                                   muted=True, size=11, wraplength=520, justify='left')
        preview_hint.grid(row=4, column=0, sticky='w', padx=16, pady=(1, 8))
        self._preview_hint = preview_hint
        preview.bind('<Configure>', lambda event: preview_hint.configure(wraplength=max(200, event.width - 32)), add='+')

        delivery = theme.frame(center, color=SURFACE, radius=18)
        delivery.grid(row=1, column=0, sticky='ew', pady=(8, 0))
        controls = theme.frame(delivery)
        controls.pack(fill='x', padx=14, pady=(8, 8))
        export_row = theme.frame(controls); export_row.pack(fill='x')
        self.export_button = self._button(export_row, 'Xuất animation  ↗', self.export,
                                          variant='primary', height=34)
        self.export_button.pack(side='left', fill='x', expand=True)
        self.cancel_button = self._button(export_row, 'Hủy xuất', self.cancel_export,
                                          variant='ghost', width=72, height=30)
        self.cancel_button.pack(side='right', padx=(6, 0)); self.cancel_button.configure(state='disabled')
        progress_track = theme.frame(controls, color=FIELD, radius=3, height=4)
        progress_track.pack(fill='x', pady=(4, 5))
        self.progress = ttk.Progressbar(progress_track, maximum=100, style='Anim.Horizontal.TProgressbar')
        self.progress.place(relx=0, rely=0, relwidth=1, height=4)
        package = theme.frame(controls); package.pack(fill='x', pady=(0, 1))
        self._label(package, 'ZIP', muted=True, size=11).pack(side='left', padx=(0, 6))
        self.package_path_entry = theme.entry(package, self.package_path_var, width=120, height=30)
        self.package_path_entry.pack(side='left', fill='x', expand=True)
        self.package_browse_button = self._button(package, 'Chọn ZIP…', self.browse_package,
                                                 variant='ghost', width=84, height=30)
        self.package_browse_button.pack(side='left', padx=(4, 0))
        self.package_status_label = self._label(controls, textvariable=self.package_status_var,
                                                muted=True, size=10, height=16, anchor='w')
        self.package_status_label.pack(fill='x', pady=(0, 2))
        self._device_panel_open = False
        self.device_toggle_button = self._button(controls, 'Kết nối RC2 & cài đặt  ⌄',
                                                  self.toggle_device_panel, variant='ghost', height=28)
        self.device_toggle_button.pack(fill='x')
        self.device_panel = theme.frame(controls)
        device = theme.frame(self.device_panel); device.pack(fill='x')
        self._label(device, 'RC2', muted=True, size=12).pack(side='left', padx=(0, 6))
        initial_serial = self.serial_var.get()
        self.device_combo = theme.combo(device, self.serial_var, [initial_serial] if initial_serial else [],
                                         width=100, height=30)
        self.device_combo.pack(side='left', fill='x', expand=True)
        self.scan_button = self._button(device, 'Quét', self.scan_devices,
                                        variant='ghost', width=48, height=30)
        self.scan_button.pack(side='left', padx=(4, 0))
        self.reconnect_button = self._button(device, 'Xin lại quyền USB', self.request_reconnect,
                                              variant='ghost', width=124, height=30)
        self.reconnect_button.pack(side='left', padx=(4, 0))
        if not self.scan_callback:
            self.scan_button.configure(state='disabled')
        self.grounded_check = theme.check(self.device_panel, 'Máy bay đã hạ cánh, động cơ dừng', self.grounded_var,
                                           height=24)
        self.grounded_check.pack(anchor='w', pady=(4, 4))
        install = theme.frame(self.device_panel); install.pack(fill='x')
        self.install_boot_button = self._button(install, 'Cài lúc khởi động', lambda: self.install('boot'), height=32)
        self.install_boot_button.pack(side='left', fill='x', expand=True)
        self.install_shutdown_button = self._button(install, 'Cài lúc tắt máy', lambda: self.install('shutdown'), height=32)
        self.install_shutdown_button.pack(side='left', fill='x', expand=True, padx=(6, 0))
        restore = theme.frame(self.device_panel); restore.pack(fill='x', pady=(3, 0))
        self.restore_boot_button = self._button(restore, 'Khôi phục khởi động', lambda: self.install('boot', restore=True),
                                                variant='ghost', height=24)
        self.restore_boot_button.pack(side='left', fill='x', expand=True)
        self.restore_shutdown_button = self._button(restore, 'Khôi phục tắt máy', lambda: self.install('shutdown', restore=True),
                                                    variant='ghost', height=24)
        self.restore_shutdown_button.pack(side='left', fill='x', expand=True, padx=(6, 0))
        if self.device_status_var is not None:
            device_feedback = self._label(self.device_panel, textvariable=self.device_status_var,
                                          muted=True, size=10, wraplength=520, justify='left')
            device_feedback.pack(anchor='w', pady=(3, 0))
            delivery.bind('<Configure>', lambda event: device_feedback.configure(wraplength=max(200, event.width - 28)), add='+')

        self._label(right, 'Thuộc tính', bold=True, size=15).pack(anchor='w', padx=18, pady=(13, 0))
        notebook = ctk.CTkTabview(right, fg_color=SURFACE, corner_radius=14,
                                 border_width=0, segmented_button_fg_color=FIELD,
                                 segmented_button_selected_color='#345c52',
                                 segmented_button_selected_hover_color='#3c6b61',
                                 segmented_button_unselected_color=FIELD,
                                 segmented_button_unselected_hover_color=PANEL,
                                 text_color=FG, text_color_disabled=MUTED,
                                 width=280)
        notebook.pack(fill='both', expand=True, padx=6, pady=(0, 8))
        panels = []
        for name in ('Nội dung', 'Hiệu ứng', 'Nền', 'Cảnh'):
            tab = notebook.add(name)
            panel = _ScrollPanel(tab)
            panel.pack(fill='both', expand=True)
            panels.append(panel)
        layer, motion, background, scene = panels
        self._property_panels = tuple(panels)
        self._motion_body = motion.body
        self._build_layer_fields(layer.body)
        self._build_background_fields(background.body)
        self._build_scene_fields(scene.body)

    def set_device_panel(self, opened):
        """Let offline editing keep the canvas; reveal device actions on demand."""
        self._device_panel_open = bool(opened)
        if self._device_panel_open:
            self.device_panel.pack(fill='x', pady=(4, 0))
            self._preview_hint.grid_remove()
        else:
            self.device_panel.pack_forget()
            self._preview_hint.grid()
        self.device_toggle_button.configure(
            text='Kết nối RC2 & cài đặt  ⌃' if self._device_panel_open else 'Kết nối RC2 & cài đặt  ⌄')

    def toggle_device_panel(self):
        self.set_device_panel(not self._device_panel_open)

    def _field(self, parent, store, key, label, default='', *, choices=None, color=False, browse=None, boolean=False):
        var = tk.BooleanVar(self.window, default) if boolean else tk.StringVar(self.window, default)
        store[key] = var
        holder = theme.frame(parent)
        holder.pack(fill='x', pady=(0, 8))
        if boolean:
            widget = theme.check(holder, label, var)
            widget.pack(anchor='w')
        else:
            self._label(holder, label, muted=True, size=11, height=20).pack(anchor='w', pady=(0, 3))
            control = theme.frame(holder)
            control.pack(fill='x')
            if choices:
                widget = theme.combo(control, var, choices, width=90, height=33)
            else:
                widget = theme.entry(control, var, width=72, height=33)
            if color or browse:
                self._button(control, '…', (lambda: self._choose_color(var)) if color else browse,
                             width=28, height=30, corner_radius=10).pack(side='right', padx=(5, 0))
            widget.pack(side='left', fill='x', expand=True)
        var.trace_add('write', self._form_changed)
        return widget

    def _build_layer_fields(self, body):
        fields = self.layer_vars
        content = self._section(body, 'Chữ & hình ảnh')
        self._field(content, fields, 'name', 'Tên lớp')
        self.text_entry = self._field(content, fields, 'text', 'Nội dung chữ')
        self._button(content, 'Thay ảnh của lớp…', self.replace_image,
                     variant='ghost', height=28).pack(fill='x')
        appearance = self._section(body, 'Diện mạo')
        self._field(appearance, fields, 'style', 'Kiểu chữ', choices=['Phẳng', 'Kim loại nổi', 'Neon'])
        self._field(appearance, fields, 'font', 'Font chữ', browse=self.choose_font)
        left, right = self._pair(appearance)
        self._field(left, fields, 'font_size', 'Cỡ chữ · px')
        self._field(right, fields, 'opacity', 'Độ rõ · %')
        left, right = self._pair(appearance)
        self._field(left, fields, 'color', 'Màu chữ', color=True)
        self._field(right, fields, 'accent', 'Ánh sáng', color=True)
        position = self._section(body, 'Vị trí & kích thước')
        left, right = self._pair(position)
        self._field(left, fields, 'x', 'Ngang · %')
        self._field(right, fields, 'y', 'Dọc · %')
        left, right = self._pair(position)
        self._field(left, fields, 'width', 'Bề ngang · %')
        self._field(right, fields, 'rotation', 'Góc xoay · °')
        self._field(position, fields, 'visible', 'Hiện lớp này', True, boolean=True)
        motion = self._section(self._motion_body, 'Chuyển động của lớp',
                               hint='Mỗi lớp có hiệu ứng và thời điểm xuất hiện riêng.')
        self.effect_combo = self._field(motion, fields, 'effect', 'Cách xuất hiện', choices=EFFECTS.values())
        left, right = self._pair(motion)
        self._field(left, fields, 'start', 'Bắt đầu · giây')
        self._field(right, fields, 'duration', 'Thời gian · giây')
        self.loop_combo = self._field(motion, fields, 'loop_effect', 'Chuyển động giữ lặp', choices=LOOP_EFFECTS.values())
        tip = theme.frame(self._motion_body, color=FIELD, radius=12)
        tip.pack(fill='x', padx=(8, 4), pady=12)
        self._label(tip, 'Cho từng dòng hiện nối tiếp', size=12, bold=True,
                    wraplength=220).pack(anchor='w', padx=12, pady=(10, 4))
        self._label(tip, 'Đặt thời điểm bắt đầu của dòng dưới sau khi dòng trên hiện xong. Lớp cuối danh sách nằm trên các lớp trước.',
                    muted=True, size=11, wraplength=220, justify='left').pack(anchor='w', padx=12, pady=(0, 12))

    def _build_background_fields(self, body):
        fields = self.background_vars
        content = self._section(body, 'Không gian phía sau')
        self._field(content, fields, 'type', 'Kiểu nền', choices=['Một màu', 'Chuyển màu', 'Ảnh nền'])
        self._field(content, fields, 'color', 'Màu nền', color=True)
        self._field(content, fields, 'color2', 'Màu thứ hai', color=True)
        image = self._section(body, 'Dùng ảnh làm nền')
        self._field(image, fields, 'image', 'Tệp ảnh', browse=self.import_background)
        self._field(image, fields, 'fit', 'Cách đặt ảnh', choices=['Phủ kín', 'Giữ trọn ảnh'])
        self._label(image, 'Hỗ trợ PNG, JPG, WebP và BMP. Ảnh được lưu cùng thiết kế để mở lại trên máy khác.',
                    muted=True, size=11, wraplength=240, justify='left').pack(anchor='w', pady=(4, 12))

    def _build_scene_fields(self, body):
        fields = self.scene_vars
        canvas = self._section(body, 'Khung hình')
        left, right = self._pair(canvas)
        self._field(left, fields, 'width', 'Ngang · px')
        self._field(right, fields, 'height', 'Dọc · px')
        self._field(canvas, fields, 'fps', 'Khung hình / giây', choices=['12', '15', '20', '24', '25', '30'])
        self._button(canvas, 'Chuẩn RC2 · Full HD / 24 fps', self.rc2_resolution,
                     variant='ghost', height=30).pack(fill='x', pady=(0, 4))
        timing = self._section(body, 'Thời lượng')
        self._field(timing, fields, 'intro', 'Đoạn mở đầu · giây')
        self._field(timing, fields, 'loop', 'Đoạn giữ lặp · giây')
        self._label(timing, 'Mở đầu chạy một lần. Đoạn giữ lặp giữ chữ đã hiện và lặp chuyển động của mỗi lớp đến khi tay khởi động xong.',
                    muted=True, size=11, wraplength=240, justify='left').pack(anchor='w', pady=(4, 12))

    def _name_changed(self, *_):
        if not self._loading:
            self.project['name'] = self.name_var.get().strip() or 'Animation mới'
            self._mark_dirty()

    def _form_changed(self, *_):
        if self._loading or self._closing:
            return
        self._forms_valid = False
        # Keep the first deadline: sustained typing must not postpone the
        # preview until the user stops. Multiple writes share the next frame.
        if self._form_job is None:
            self._form_job = self._schedule(16, self._apply_forms)
        self._update_controls()

    @staticmethod
    def _number(var, label, minimum, maximum, integer=False):
        raw = var.get().strip().replace(',', '.')
        value = float(raw)
        if not minimum <= value <= maximum:
            raise ValueError(f'{label}: nhập từ {minimum:g} đến {maximum:g}.')
        if integer and value != int(value):
            raise ValueError(f'{label}: cần là số nguyên.')
        return int(value) if integer else value

    def _apply_forms(self):
        self._unschedule(self._form_job)
        self._form_job = None
        if self._loading or self._closing:
            return False
        project = copy.deepcopy(self.project)
        try:
            s = self.scene_vars
            for key, label, low, high in (('width', 'Chiều ngang', 64, 1920), ('height', 'Chiều dọc', 64, 1080), ('fps', 'Khung hình/giây', 6, 30)):
                project[key] = self._number(s[key], label, low, high, True)
            project['intro'] = self._number(s['intro'], 'Đoạn mở đầu', .1, 14.9)
            project['loop'] = self._number(s['loop'], 'Đoạn giữ lặp', .1, 10)
            b = self.background_vars
            project['background'].update(type={'Một màu': 'solid', 'Chuyển màu': 'gradient', 'Ảnh nền': 'image'}[b['type'].get()], color=b['color'].get(), color2=b['color2'].get(), image=b['image'].get(), fit={'Phủ kín': 'cover', 'Giữ trọn ảnh': 'contain'}[b['fit'].get()])
            if 0 <= self.selected < len(project['layers']):
                layer, v = project['layers'][self.selected], self.layer_vars
                for key in ('name', 'text', 'font', 'color', 'accent'):
                    layer[key] = v[key].get()
                layer['visible'] = v['visible'].get()
                layer['style'] = {'Phẳng': 'flat', 'Kim loại nổi': 'metal', 'Neon': 'neon'}[v['style'].get()]
                layer['effect'] = next((key for key, label in EFFECTS.items() if label == v['effect'].get()), 'none')
                layer['loop_effect'] = next((key for key, label in LOOP_EFFECTS.items() if label == v['loop_effect'].get()), 'none')
                layer['font_size'] = self._number(v['font_size'], 'Cỡ chữ', 8, 500, True)
                for key, label, low, high in (('x', 'Vị trí ngang', -100, 200), ('y', 'Vị trí dọc', -100, 200), ('width', 'Bề ngang', 2, 200), ('opacity', 'Độ rõ', 0, 100)):
                    layer[key] = self._number(v[key], label, low, high) / 100
                layer['rotation'] = self._number(v['rotation'], 'Góc xoay', -360, 360)
                layer['start'] = self._number(v['start'], 'Thời điểm bắt đầu', 0, 15)
                layer['duration'] = self._number(v['duration'], 'Thời gian hiện', .05, 15)
            project = validate_project(project)
        except (ValueError, TypeError, KeyError, OSError) as error:
            self._forms_valid = False
            self.status.set(f'Kiểm tra ô đang nhập: {error}')
            return False
        self._forms_valid = True
        changed = project != self.project
        self.project = project
        if changed:
            self._mark_dirty()
            self._refresh_layers()
            total = self._total_time()
            if float(self.timeline.cget('to')) != total:
                self.timeline.configure(to=total)
            self._request_preview()
        return True

    def _mark_dirty(self):
        self.dirty = True
        self._update_title()
        self._update_controls()

    def _sync_all(self):
        self._showing_poster = False
        self._forms_valid = True
        self._loading = True
        try:
            self.name_var.set(self.project.get('name', 'Animation mới'))
            for key, var in self.scene_vars.items():
                var.set(str(self.project[key]))
            background = self.project['background']
            for key in ('color', 'color2', 'image'):
                self.background_vars[key].set(background.get(key, ''))
            self.background_vars['type'].set({'solid': 'Một màu', 'gradient': 'Chuyển màu', 'image': 'Ảnh nền'}.get(background.get('type'), 'Một màu'))
            self.background_vars['fit'].set('Giữ trọn ảnh' if background.get('fit') == 'contain' else 'Phủ kín')
            self.timeline.configure(to=self._total_time())
            self.time_var.set(0)
        finally:
            self._loading = False
        self._sync_layer()
        self._refresh_layers()
        self._request_preview()
        self._update_controls()

    def _sync_layer(self):
        self._loading = True
        try:
            layer = self.project['layers'][self.selected] if 0 <= self.selected < len(self.project['layers']) else make_layer()
            for key in ('name', 'text', 'font', 'font_size', 'color', 'accent', 'rotation', 'start', 'duration', 'visible'):
                self.layer_vars[key].set(layer.get(key, ''))
            for key in ('x', 'y', 'width', 'opacity'):
                self.layer_vars[key].set(f"{float(layer.get(key, 1)) * 100:g}")
            self.layer_vars['style'].set({'flat': 'Phẳng', 'metal': 'Kim loại nổi', 'neon': 'Neon'}.get(layer.get('style'), 'Phẳng'))
            self.layer_vars['effect'].set(EFFECTS.get(layer.get('effect'), EFFECTS['none']))
            self.layer_vars['loop_effect'].set(LOOP_EFFECTS.get(layer.get('loop_effect'), LOOP_EFFECTS['none']))
            self.text_entry.configure(state='normal' if layer.get('kind') == 'text' and self.selected >= 0 else 'disabled')
        finally:
            self._loading = False

    def _refresh_layers(self):
        rows = []
        for layer in self.project['layers']:
            icon = 'T' if layer.get('kind') == 'text' else '▧'
            name = layer.get('name') or layer.get('text') or 'Ảnh'
            visible = '' if layer.get('visible', True) else ' (ẩn)'
            rows.append(f'{icon}  {name}{visible}')
        if tuple(rows) != self.layer_list.get(0, 'end'):
            self.layer_list.delete(0, 'end')
            for row in rows:
                self.layer_list.insert('end', row)
        if 0 <= self.selected < len(self.project['layers']):
            if self.layer_list.curselection() != (self.selected,):
                self.layer_list.selection_clear(0, 'end')
                self.layer_list.selection_set(self.selected)
                self.layer_list.see(self.selected)

    def _select_layer(self, _=None):
        selected = self.layer_list.curselection()
        if selected and selected[0] != self.selected:
            self._unschedule(self._form_job)
            if not self._apply_forms():
                # Restore the list selection without replacing the editable raw
                # values; the user can correct the invalid field in place.
                self._refresh_layers()
                return
            self.selected = selected[0]
            self._sync_layer()
            self._refresh_layers()

    def _scroll_properties(self, event):
        if not self._visible or self._destroyed:
            return
        widget = event.widget
        for panel in self._property_panels:
            cursor = widget
            while cursor is not None:
                if cursor is panel:
                    if widget not in (panel.canvas, panel.body):
                        panel._wheel(event)
                    return
                cursor = getattr(cursor, 'master', None)

    def _choose_color(self, var):
        color = colorchooser.askcolor(var.get() or '#ffffff', parent=self.window, title='Chọn màu')[1]
        if color:
            var.set(color)

    def choose_font(self):
        filename = filedialog.askopenfilename(parent=self.window, title='Chọn font chữ', initialdir='C:/Windows/Fonts', filetypes=[('Font chữ', '*.ttf *.otf *.ttc'), ('Tất cả tệp', '*.*')])
        if filename:
            self.layer_vars['font'].set(filename)

    def _image_path(self, title):
        return filedialog.askopenfilename(parent=self.window, title=title, filetypes=[('Ảnh', '*.png *.jpg *.jpeg *.webp *.bmp'), ('Tất cả tệp', '*.*')])

    def _prepare_layer_change(self):
        self._unschedule(self._form_job)
        return self._apply_forms()

    def add_text(self):
        if not self._prepare_layer_change():
            return
        if len(self.project['layers']) >= 32:
            self.status.set('Một thiết kế có tối đa 32 lớp. Xóa bớt lớp trước khi thêm.')
            return
        self.project['layers'].append(make_layer(kind='text', name='Chữ mới', text='Chữ của bạn', font_size=100, y=.65, start=2.0))
        self.selected = len(self.project['layers']) - 1
        self._layer_changed()

    def import_image(self):
        if not self._prepare_layer_change():
            return
        if len(self.project['layers']) >= 32:
            self.status.set('Một thiết kế có tối đa 32 lớp. Xóa bớt lớp trước khi thêm.')
            return
        filename = self._image_path('Thêm ảnh hoặc logo')
        if filename:
            self.project['layers'].append(make_layer(kind='image', name=Path(filename).stem, image=filename, width=.35, effect='zoom'))
            self.selected = len(self.project['layers']) - 1
            self._layer_changed()

    def replace_image(self):
        if 0 <= self.selected < len(self.project['layers']):
            layer = self.project['layers'][self.selected]
            if layer.get('kind') != 'image':
                self.status.set('Chọn một lớp ảnh ở danh sách để thay ảnh; bấm + Ảnh để thêm logo mới.')
                return
            filename = self._image_path('Thay ảnh của lớp')
            if filename:
                layer['image'] = filename
                self._layer_changed()

    def import_background(self):
        filename = self._image_path('Chọn ảnh nền')
        if filename:
            self.background_vars['image'].set(filename)
            self.background_vars['type'].set('Ảnh nền')

    def duplicate_layer(self):
        if not self._prepare_layer_change() or not 0 <= self.selected < len(self.project['layers']):
            return
        if len(self.project['layers']) >= 32:
            self.status.set('Một thiết kế có tối đa 32 lớp. Xóa bớt lớp trước khi thêm.')
            return
        source = copy.deepcopy(self.project['layers'][self.selected])
        source.pop('id', None)
        source['name'] = (source.get('name') or 'Lớp') + ' · bản sao'
        source['y'] = min(.95, float(source.get('y', .5)) + .08)
        self.project['layers'].insert(self.selected + 1, make_layer(**source))
        self.selected += 1
        self._layer_changed()

    def remove_layer(self):
        if not self._prepare_layer_change() or not 0 <= self.selected < len(self.project['layers']):
            return
        del self.project['layers'][self.selected]
        self.selected = min(self.selected, len(self.project['layers']) - 1)
        self._layer_changed()

    def move_layer(self, delta):
        if not self._prepare_layer_change():
            return
        other = self.selected + delta
        layers = self.project['layers']
        if 0 <= self.selected < len(layers) and 0 <= other < len(layers):
            layers[self.selected], layers[other] = layers[other], layers[self.selected]
            self.selected = other
            self._layer_changed()

    def _layer_changed(self):
        self._mark_dirty()
        self._refresh_layers()
        self._sync_layer()
        self._request_preview()

    def rc2_resolution(self):
        for key, value in (('width', '1920'), ('height', '1080'), ('fps', '24')):
            self.scene_vars[key].set(value)

    def _total_time(self):
        return float(self.project['intro']) + float(self.project['loop'])

    def _phase(self, value):
        intro = float(self.project['intro'])
        if value < intro:
            return value, 'intro'
        return (value - intro) % max(.01, float(self.project['loop'])), 'loop'

    def _request_preview(self):
        if self._visible and self._preview_job is None and not self._closing:
            self._preview_job = self._schedule(16, self._render_preview)

    def _render_preview(self):
        self._unschedule(self._preview_job)
        self._preview_job = None
        if self._closing or self._destroyed or not self._visible:
            return
        cw, ch = self.preview_canvas.winfo_width(), self.preview_canvas.winfo_height()
        if cw < 5 or ch < 5:
            return
        ratio = min((cw - 4) / self.project['width'], (ch - 4) / self.project['height'], 768 / self.project['width'], 432 / self.project['height'])
        width, height = max(1, int(self.project['width'] * ratio)), max(1, int(self.project['height'] * ratio))
        seconds, phase = self._phase(float(self.time_var.get()))
        try:
            frame = render_frame(self.project, seconds, size=(width, height), phase=phase)
            photo = ImageTk.PhotoImage(frame, master=self.window)
            x, y = (cw - width) // 2, (ch - height) // 2
            if self._preview_item is None:
                self._preview_item = self.preview_canvas.create_image(x, y, image=photo, anchor='nw')
            else:
                self.preview_canvas.coords(self._preview_item, x, y)
                self.preview_canvas.itemconfigure(self._preview_item, image=photo)
            # Retain the previous Tk image until the canvas points at the new
            # one, avoiding a blank frame between two valid previews.
            self._preview_photo = photo
            self._preview_bounds = (x, y, width, height)
            self.clock_var.set(f"{self.time_var.get():.2f} s · {'Mở đầu' if phase == 'intro' else 'Giữ lặp'}")
        except Exception as error:
            self.status.set(f'Chưa xem trước được: {error}')

    def _drag_preview(self, event):
        if self._playing or not 0 <= self.selected < len(self.project['layers']):
            return
        x, y, width, height = self._preview_bounds
        if not x <= event.x <= x + width or not y <= event.y <= y + height:
            return
        self.layer_vars['x'].set(f'{(event.x - x) / width * 100:.1f}')
        self.layer_vars['y'].set(f'{(event.y - y) / height * 100:.1f}')

    def _scrub(self, _=None):
        if self._loading:
            return
        self._showing_poster = False
        if self._playing:
            self._play_offset = float(self.time_var.get())
            self._play_clock = time.monotonic()
        self._request_preview()

    def toggle_play(self):
        if self._playing:
            self._playing = False
            self.play_button.configure(text='▶ Phát')
            return
        if not self._apply_forms():
            return
        if self._showing_poster:
            self._showing_poster = False
            self.time_var.set(0)
        self._playing = True
        self._play_clock = time.monotonic()
        self._play_offset = float(self.time_var.get())
        self.play_button.configure(text='Ⅱ Tạm dừng')
        self._tick()

    def _tick(self):
        if not self._playing or self._closing or not self._visible:
            return
        value = self._play_offset + time.monotonic() - self._play_clock
        if value >= self._total_time():
            value = float(self.project['intro']) + (value - float(self.project['intro'])) % max(.01, float(self.project['loop']))
        self.time_var.set(value)
        self._render_preview()
        self._schedule(65, self._tick)

    def restart_preview(self):
        self._showing_poster = False
        self.time_var.set(0)
        self._play_offset = 0
        self._play_clock = time.monotonic()
        self._request_preview()

    def _safe_name(self):
        return ''.join(char if char.isalnum() or char in '-_ ' else '-' for char in self.project['name']).strip(' .-')[:80] or 'Animation'

    def _available_project_path(self, name):
        path = self.library / (name + '.rc2anim')
        number = 2
        while path.exists():
            path = self.library / f'{name} ({number}).rc2anim'
            number += 1
        return path

    def _autosave(self):
        if not self.dirty:
            return True
        try:
            if self._recovery_path is None:
                self._recovery_path = self._available_project_path('Tự lưu - ' + self._safe_name())
            save_project(self.project, self._recovery_path)
            self._refresh_library()
            return True
        except Exception as error:
            self.status.set(f'Không lưu được bản tự phục hồi: {error}. Hãy lưu thiết kế trước khi đổi.')
            return False

    def _replace_project(self, project, path=None):
        self._playing = False
        self.play_button.configure(text='▶ Phát')
        self.project, self.project_path = project, path
        self._recovery_path = None
        self.current_export = None
        self.export_fingerprint = None
        self.export_sha256 = None
        self._export_stat = None
        self.selected = 0 if project['layers'] else -1
        self.dirty = False
        self._sync_all()
        self._update_title()

    def create_project(self, preset='scifi'):
        if self._prepare_layer_change() and self._autosave():
            self._replace_project(new_project(preset))
            self.status.set('Thiết kế mới đã sẵn sàng. Bản đang sửa trước đó được tự lưu trong thư viện.')

    def apply_preset(self):
        preset = next((key for key, label in PRESETS.items() if label == self.preset_var.get()), 'scifi')
        self.create_project(preset)

    def duplicate_project(self):
        if self._prepare_layer_change() and self._autosave():
            project = copy.deepcopy(self.project)
            project['name'] += ' · bản sao'
            self._replace_project(project)
            self._mark_dirty()
            self.status.set('Đã nhân bản toàn bộ chữ, ảnh, nền và chuyển động.')

    def _open_path(self, path):
        if not self._prepare_layer_change():
            return
        try:
            project = load_project(path, self.cache)
            if not self._autosave():
                return
            self._replace_project(project, Path(path))
            self.status.set(f'Đã mở {Path(path).name}.')
        except Exception as error:
            self.status.set(f'Không mở được thiết kế: {error}')

    def open_project(self):
        filename = filedialog.askopenfilename(parent=self.window, title='Mở thiết kế animation', initialdir=self.library, filetypes=[('Thiết kế RC2', '*.rc2anim'), ('Tất cả tệp', '*.*')])
        if filename:
            self._open_path(filename)

    def open_library_project(self):
        selection = self.library_list.curselection()
        if selection:
            self._open_path(self._library_paths[selection[0]])

    def _refresh_library(self):
        self._library_paths = sorted(self.library.glob('*.rc2anim'), key=lambda path: path.stat().st_mtime, reverse=True)
        self.library_list.delete(0, 'end')
        for path in self._library_paths:
            self.library_list.insert('end', path.stem)

    def save(self):
        if not self._prepare_layer_change():
            return False
        path = self.project_path or self._available_project_path(self._safe_name())
        return self._save_to(path)

    def save_as(self):
        if not self._prepare_layer_change():
            return False
        filename = filedialog.asksaveasfilename(parent=self.window, title='Lưu thiết kế và ảnh/font đi kèm', initialdir=self.library, initialfile=self._safe_name() + '.rc2anim', defaultextension='.rc2anim', filetypes=[('Thiết kế RC2', '*.rc2anim')])
        return self._save_to(Path(filename)) if filename else False

    def _save_to(self, path):
        try:
            self.project_path = Path(save_project(self.project, path))
            self.dirty = False
            self._update_title()
            self._refresh_library()
            self.status.set(f'Đã lưu {self.project_path.name} cùng ảnh và font chữ.')
            return True
        except Exception as error:
            self.status.set(f'Không lưu được thiết kế: {error}')
            return False

    def export(self):
        if self.busy or not self._prepare_layer_change():
            return
        filename = filedialog.asksaveasfilename(parent=self.window, title='Xuất boot animation', initialdir=self.exports, initialfile=self._safe_name() + '.zip', defaultextension='.zip', filetypes=[('Animation ZIP', '*.zip')])
        if filename:
            self.export_to(filename)

    def export_to(self, destination):
        """Start an export without a dialog, also useful to automated UI checks."""
        if self.busy or not self._prepare_layer_change():
            return False
        self._playing = False
        self.play_button.configure(text='▶ Phát')
        self._cancel.clear()
        project = copy.deepcopy(self.project)
        signature = _fingerprint(project)
        self.progress.configure(value=0)
        self.status.set('Đang tạo khung hình… Bạn có thể tiếp tục sửa thiết kế.')
        def progress(done, total, message):
            self._events.put(('progress', done, total, message))
        def worker():
            try:
                result = export_animation(project, destination, cancel=self._cancel, progress=progress)
                self._events.put(('complete', result, signature))
            except Exception as error:
                self._events.put(('cancelled' if self._cancel.is_set() else 'error', str(error)))
        self._worker = threading.Thread(target=worker, name='RC2AnimationExport', daemon=True)
        self._worker.start()
        self._update_controls()
        return True

    def cancel_export(self):
        if self.busy:
            self._cancel.set()
            self.status.set('Đang dừng xuất sau khung hình hiện tại…')
            self.cancel_button.configure(state='disabled')

    def _load_package_path(self):
        try:
            settings = self.work.resolve() / 'animation-package.json'
            if settings.stat().st_size > 16 * 1024:
                return ''
            value = json.loads(settings.read_text(encoding='utf-8')).get('package_path', '')
            return value if isinstance(value, str) and len(value) <= 4096 else ''
        except (OSError, ValueError, AttributeError):
            return ''

    def _remember_package_path(self, path):
        value = {'package_path': str(path)}
        try:
            # MSIX can redirect LOCALAPPDATA from C: to another volume. Rename
            # both files through the resolved physical directory, otherwise
            # Windows may reject a same-directory replace with WinError 17.
            settings = self.work.resolve() / 'animation-package.json'
            if settings.is_file() and settings.stat().st_size <= 16 * 1024:
                if json.loads(settings.read_text(encoding='utf-8')) == value:
                    self._package_path_remembered = True
                    self._package_persistence_error = None
                    return True
            temporary = settings.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(settings)
            if json.loads(settings.read_text(encoding='utf-8')) != value:
                raise OSError('Không xác minh được đường dẫn ZIP đã lưu.')
            self._package_path_remembered = True
            self._package_persistence_error = None
            return True
        except (OSError, ValueError) as error:
            self._package_path_remembered = False
            self._package_persistence_error = str(error)
            return False

    def _package_probe(self):
        raw = self.package_path_var.get().strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
            raw = raw[1:-1].strip()
        if not raw:
            return None, None, ''
        try:
            path = Path(raw).expanduser().absolute()
            info = path.stat()
            signature = (info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                         info.st_dev, info.st_ino)
            return path, (str(path), signature), ''
        except (OSError, ValueError) as error:
            return None, (raw, None), str(error)

    def _set_package_status(self, message, state):
        self._package_state = state
        short = message if len(message) <= 76 else message[:73] + '…'
        if self.package_status_var.get() != short:
            self.package_status_var.set(short)
        color = ACCENT if state == 'valid' else ('#f0b7b7' if state == 'invalid' else MUTED)
        if self.package_status_label.cget('text_color') != color:
            self.package_status_label.configure(text_color=color)

    def _package_changed(self, *_):
        if self._destroyed or self._closing:
            return
        self._package_generation += 1
        self._package_cancel.set()
        self._unschedule(self._package_job)
        self._package_job = None
        self._package_validated_key = None
        self._package_details = None
        self._package_pending_key = None
        path, key, error = self._package_probe()
        self._package_observed_key = key
        if key is None:
            self._set_package_status('Chọn ZIP để cài. Sửa thiết kế cần xuất lại ZIP.', 'empty')
        elif error:
            self._set_package_status('Không thấy tệp ZIP. Kiểm tra lại đường dẫn.', 'invalid')
        else:
            self._set_package_status('Đang chờ kiểm tra ZIP đã chọn…', 'checking')
            self._package_job = self._schedule(120, self._validate_selected_package)
        self._update_controls()

    def _check_package_selection(self):
        """Poll file metadata only; ZIP decoding and hashing stay off the UI."""
        _path, key, _error = self._package_probe()
        if key != self._package_observed_key:
            self._package_changed()

    def _validate_selected_package(self, *, force=False, install_kind=None):
        self._unschedule(self._package_job)
        self._package_job = None
        if self._destroyed or self._closing:
            return False
        path, key, error = self._package_probe()
        if path is None or error:
            self._package_changed()
            return False
        if not force and key in self._package_cache:
            self._accept_package_validation(self._package_generation, path, key,
                                            self._package_cache[key], None, None)
            return True
        self._package_generation += 1
        generation = self._package_generation
        self._package_cancel.set()
        cancel = self._package_cancel = threading.Event()
        self._package_validated_key = None
        self._package_details = None
        self._package_pending_key = key
        self._package_observed_key = key
        self._set_package_status('Đang kiểm tra ZIP trước khi cài…' if install_kind else
                                 'Đang kiểm tra cấu trúc và khung hình ZIP…', 'checking')

        def validate():
            details, failure = None, None
            try:
                details = _validate_zip(path, cancel=cancel)
                info = path.stat()
                after = (str(path), (info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                                     info.st_dev, info.st_ino))
                if after != key:
                    raise ValueError('ZIP thay đổi trong khi kiểm tra; hãy chọn lại tệp.')
            except Exception as problem:
                failure = str(problem)
            self._events.put(('package-validation', generation, path, key, details, failure, install_kind))

        self._package_worker = threading.Thread(target=validate, name='RC2AnimationZipCheck', daemon=True)
        self._package_worker.start()
        self._update_controls()
        return True

    def _accept_package_validation(self, generation, path, key, details, error, install_kind):
        if self._destroyed or self._closing or generation != self._package_generation:
            return
        current_path, current_key, _ = self._package_probe()
        if current_path != path or current_key != key:
            self._package_changed()
            return
        self._package_pending_key = None
        if error or details is None:
            self._package_cache.pop(key, None)
            self._package_validated_key = None
            self._package_details = None
            self._set_package_status('ZIP chưa hợp lệ: ' + (error or 'không đọc được tệp'), 'invalid')
            if install_kind:
                self.status.set('Chưa cài animation: ' + (error or 'ZIP không hợp lệ.'))
        else:
            # Keep a small metadata cache; imported PNGs are never retained here.
            if len(self._package_cache) >= 16:
                self._package_cache.pop(next(iter(self._package_cache)))
            self._package_cache[key] = details
            self._package_validated_key = key
            self._package_details = details
            remembered = self._remember_package_path(path)
            self._set_package_status(
                'ZIP hợp lệ. Cài ZIP đã chọn; sửa thiết kế cần xuất lại ZIP.' if remembered else
                'ZIP hợp lệ; chưa lưu đường dẫn. Lần mở sau cần chọn lại ZIP.', 'valid')
            if (self.status.get().startswith('Chưa cài animation:')
                    or self.status.get() == 'Chọn tệp animation ZIP hợp lệ trước khi cài.'):
                self.status.set('ZIP đã hợp lệ. Có thể cài tệp ZIP đang chọn.')
            if install_kind:
                self._submit_install(path, install_kind)
        self._update_controls()

    def browse_package(self):
        filename = filedialog.askopenfilename(parent=self.window, title='Chọn animation ZIP để cài',
                                              initialdir=self.exports,
                                              filetypes=[('Animation ZIP', '*.zip'), ('Tất cả tệp', '*.*')])
        if filename:
            self.package_path_var.set(filename)

    def _poll(self):
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == 'progress':
                self.progress.configure(value=event[1] / max(event[2], 1) * 100)
                self.status.set(f'{event[3]} · {event[1]}/{event[2]}')
            elif kind == 'complete':
                self.current_export = Path(event[1]['zip'])
                self.export_fingerprint = event[2]
                self.export_sha256 = event[1]['sha256']
                try:
                    self._export_stat = _file_signature(self.current_export)
                except OSError:
                    self._export_stat = None
                self.progress.configure(value=100)
                self.status.set(f"Đã xuất {event[1]['frames']} khung hình: {self.current_export}. Có GIF và ảnh xem trước cùng thư mục.")
                self.package_path_var.set(str(self.current_export))
            elif kind == 'package-validation':
                self._accept_package_validation(*event[1:])
            elif kind == 'cancelled':
                self.status.set('Đã hủy xuất animation. Thiết kế vẫn được giữ nguyên.')
            elif kind == 'error':
                self.status.set(f'Xuất animation chưa thành công: {event[1]}')
        if not self._closing:
            self._check_package_selection()
        self._update_controls()
        if self._closing:
            if not self.busy:
                self._destroy()
            else:
                self._schedule(100, self._poll)
        else:
            self._schedule(140, self._poll)

    def _update_controls(self):
        if self._destroyed:
            return
        exporting = self.busy
        self.export_button.configure(state='disabled' if exporting or self._closing else 'normal')
        self.cancel_button.configure(state='normal' if exporting and not self._cancel.is_set() else 'disabled')
        try:
            parent_busy = bool(self.busy_callback())
        except Exception:
            parent_busy = True
        install_ok = bool(self.install_callback and not parent_busy and not exporting and not self._closing)
        selected_zip_valid = bool(self._package_validated_key and self._package_state == 'valid')
        for button in (self.install_boot_button, self.install_shutdown_button):
            button.configure(state='normal' if install_ok and selected_zip_valid else 'disabled')
        for button in (self.restore_boot_button, self.restore_shutdown_button):
            button.configure(state='normal' if install_ok else 'disabled')
        try:
            reconnect_ok = bool(self.reconnect_callback and self.reconnect_state_callback
                                and self.reconnect_state_callback() and not self._closing)
        except Exception:
            reconnect_ok = False
        self.reconnect_button.configure(state='normal' if reconnect_ok else 'disabled')

    def scan_devices(self):
        if self.scan_callback:
            try:
                serials = self.scan_callback()
                if serials is not None:
                    self.device_combo.configure(values=list(serials))
                elif self.serial_var.get():
                    self.device_combo.configure(values=[self.serial_var.get()])
            except Exception as error:
                self.status.set(f'Chưa quét được tay: {error}')

    def install(self, kind, restore=False):
        if not self.install_callback or self.busy:
            return
        if self.busy_callback():
            self.status.set('Chờ thao tác trên tay hoàn tất trước khi cài animation.')
            return
        if restore:
            return self._submit_install(None, kind, restore=True)
        path, key, error = self._package_probe()
        if path is None or error:
            self._package_changed()
            self.status.set('Chọn tệp animation ZIP hợp lệ trước khi cài.')
            return False
        # Recheck off-thread on each explicit click, including metadata-preserving
        # replacements. The root installer also snapshots and validates again.
        return self._validate_selected_package(force=True, install_kind=kind)

    def _submit_install(self, path, kind, restore=False):
        if self._closing or self._destroyed or self.busy or not self.install_callback:
            return False
        if self.busy_callback():
            self.status.set('Chờ thao tác trên tay hoàn tất trước khi cài animation.')
            return False
        try:
            started = self.install_callback(path, kind, restore=restore)
            if started:
                self.status.set('Đã bắt đầu thao tác RC2. Bấm Quay lại để xem nhật ký và tiến trình cài.'
                                if self.embedded else
                                'Đã chuyển yêu cầu sang màn hình chính. Theo dõi tiến trình cài ở đó.')
            return bool(started)
        except Exception as error:
            self.status.set(f'Chưa bắt đầu được thao tác: {error}')
            return False

    def request_reconnect(self):
        try:
            if (not self._closing and self.reconnect_callback and self.reconnect_state_callback
                    and self.reconnect_state_callback()):
                self.reconnect_callback()
                return True
        except Exception as error:
            self.status.set(f'Chưa yêu cầu lại được quyền USB: {error}')
        return False

    def get_smoke_state(self):
        return {
            'exists': not self._destroyed,
            'mapped': bool(self.view.winfo_ismapped()) if not self._destroyed else False,
            'embedded': self.embedded,
            'visible': self._visible and not self._destroyed,
            'view_id': str(self.view),
            'project_name': self.project['name'],
            'layers': len(self.project['layers']),
            'selected_layer': self.selected,
            'presets': list(PRESETS),
            'effects': list(EFFECTS),
            'loop_effects': list(LOOP_EFFECTS),
            'resolution': [self.project['width'], self.project['height']],
            'fps': self.project['fps'],
            'preview_ready': self._preview_photo is not None,
            'preview_size': list(self._preview_bounds[2:]),
            'playing': self._playing,
            'busy': self.busy,
            'dirty': self.dirty,
            'export': str(self.current_export) if self.current_export else None,
            'status': self.status.get(),
            'device_panel_open': self._device_panel_open,
            'package_path': self.package_path_var.get(),
            'package_validation': self._package_state,
            'package_status': self.package_status_var.get(),
            'package_path_remembered': self._package_path_remembered,
            'package_persistence_error': self._package_persistence_error,
        }

    def close(self):
        if self._destroyed:
            return True
        if self._closing:
            return False
        self._unschedule(self._form_job)
        if not self._apply_forms():
            self.status.set('Chưa thể đóng: ' + self.status.get())
            return False
        if not self._autosave():
            return False
        self._closing = True
        self._playing = False
        self._cancel.set()
        self._package_cancel.set()
        self._update_controls()
        if self.busy:
            self.status.set('Đang dừng xuất và lưu thiết kế trước khi đóng…')
            return False
        else:
            self._destroy()
            return True

    def _destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        self._visible = False
        self._package_generation += 1
        self._package_cancel.set()
        for token in tuple(self._after):
            self._unschedule(token)
        for sequence, binding in self._bindings:
            if binding:
                try:
                    self.window.unbind(sequence, binding)
                except tk.TclError:
                    pass
        self._bindings.clear()
        self._preview_photo = None
        self.view.destroy()
        if not self.embedded:
            self.window.destroy()
