"""Standalone desktop/CLI for the actual offline RC2 APK patch pipeline."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from rc2vi.auto_patch import AutoPatchBuilder, atomic_json, TRANSLATION_SHA256
from rc2vi.auto_workflow import AutoPatchRun
from rc2vi.usb_windows import discover
from rc2vi.hud_tools import sha256_file
from rc2vi.fly_versions import SUPPORTED


def locations():
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local')))
    return base / 'assets', local / 'RC2AutoPatch'


def patch_work_directory(base, assets, serial):
    """Resume one device/recipe combination while retaining earlier releases."""
    fingerprint = hashlib.sha256()
    fingerprint.update(('rc2-auto-work-v1:' + TRANSLATION_SHA256).encode('ascii'))
    for profile in SUPPORTED:
        fingerprint.update((profile.translation_directory + ':' +
                            (profile.translation_sha256 or TRANSLATION_SHA256)).encode('ascii'))
        manifest = Path(assets) / profile.recipe_directory / 'manifest.json'
        if not manifest.is_file() or not 0 < manifest.stat().st_size <= 256 * 1024:
            raise ValueError('Thiếu hoặc không đọc được dữ liệu phiên bản menu đã kiểm chứng.')
        fingerprint.update(profile.recipe_directory.encode('ascii'))
        fingerprint.update(hashlib.sha256(manifest.read_bytes()).digest())
    device = hashlib.sha256(serial.encode('utf-8')).hexdigest()[:16]
    return Path(base) / ('rc2-' + device + '-' + fingerprint.hexdigest()[:16])


class App:
    def __init__(self, root, assets, work):
        self.root, self.assets, self.base = root, Path(assets), Path(work)
        self.events = queue.Queue()
        self.thread = None
        self.cancel = threading.Event()
        self.reconnect_event = threading.Event()
        self.usb_recovery = False
        self.closing = False
        self.current_work = None
        self.animation_editor = None
        self.animation_job = False
        self.usb_authorization_job = False
        self.active_page = 'patch'
        self._page_geometry = {'animation': '1240x760'}
        self.serial = tk.StringVar(root)
        self.grounded = tk.BooleanVar(root, False)
        self.reset = tk.BooleanVar(root, False)
        self.status = tk.StringVar(root, 'Bật RC 2, nối USB và giữ tay ở Launcher/Settings.')
        self.stage = tk.StringVar(root, 'Sẵn sàng')
        self.last_log = None
        self._view()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)
        self.scan()

    def _view(self):
        from rc2vi import desktop_theme as ui

        root = self.root
        root.title('RC2 Studio · Tiếng Việt, menu & Animation · r14.6')
        root.geometry('900x760')
        root.minsize(800, 680)
        ui.setup(root)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('Studio.Horizontal.TProgressbar', background=ui.ACCENT,
                        troughcolor=ui.FIELD, bordercolor=ui.FIELD, lightcolor=ui.ACCENT,
                        darkcolor=ui.ACCENT, relief='flat', borderwidth=0, thickness=4)
        body = self.patch_page = ui.frame(root)
        body.pack(fill='both', expand=True, padx=24, pady=20)
        heading = ui.frame(body)
        heading.pack(fill='x')
        mark = ui.frame(heading, color=ui.PANEL, radius=16, width=52, height=52)
        mark.pack(side='left', padx=(0, 14))
        mark.pack_propagate(False)
        ui.label(mark, 'RC', size=19, bold=True, text_color=ui.ACCENT).pack(expand=True)
        identity = ui.frame(heading)
        identity.pack(side='left', fill='x', expand=True)
        title = ui.frame(identity)
        title.pack(anchor='w')
        ui.label(title, 'RC2 Studio', size=28, bold=True).pack(side='left')
        version = ui.frame(title, color=ui.PANEL, radius=10)
        version.pack(side='left', padx=(12, 0))
        ui.label(version, 'r14.6', muted=True, size=11).pack(padx=10, pady=3)
        ui.label(identity, 'Tiếng Việt  /  Menu nâng cao  /  Animation',
                 muted=True, size=13).pack(anchor='w', pady=(1, 0))
        self.animation_button = ui.button(heading, 'Mở Animation  →', self.open_animation,
                                          width=170, height=42)
        self.animation_button.pack(side='right', padx=(16, 0))
        supported = ' / '.join(profile.version for profile in SUPPORTED)
        ui.label(body, 'Fly RC ' + supported + ' · Đèn càng · HUD · Xuất hình · FCC/EC · Hiệu chỉnh gimbal',
                 muted=True, size=12, wraplength=820, anchor='w').pack(fill='x', pady=(12, 18))

        device = ui.frame(body, color=ui.SURFACE, radius=20)
        device.pack(fill='x')
        device_inner = ui.frame(device)
        device_inner.pack(fill='x', padx=20, pady=16)
        device_heading = ui.frame(device_inner)
        device_heading.pack(fill='x', pady=(0, 12))
        ui.label(device_heading, 'Kết nối tay điều khiển', size=16, bold=True).pack(side='left')
        device_badge = ui.frame(device_heading, color=ui.PANEL, radius=10)
        device_badge.pack(side='right')
        ui.label(device_badge, '01  ·  THIẾT BỊ', muted=True, size=10).pack(padx=10, pady=4)
        row = ui.frame(device_inner)
        row.pack(fill='x')
        self.selector = ui.combo(row, self.serial, values=(), width=400, height=38,
                                 command=lambda _: self.controls())
        self.selector.pack(side='left', fill='x', expand=True)
        self.scan_button = ui.button(row, 'Quét lại', self.scan, width=108, height=38)
        self.scan_button.pack(side='left', padx=(12, 0))
        ui.label(device_inner, 'Khi RC 2 hỏi quyền USB debugging, chọn “Always allow” rồi bấm “Allow”.',
                 muted=True, size=12, wraplength=760, anchor='w').pack(fill='x', pady=(7, 12))
        self.ground_check = ui.check(device_inner, 'Máy bay đã hạ cánh và động cơ đã dừng',
                                     self.grounded, command=self.controls)
        self.ground_check.pack(anchor='w')
        self.reset_check = ui.check(device_inner,
                                    'Cho phép gỡ/cài lại khi khác chữ ký (xóa dữ liệu Fly)',
                                    self.reset, command=self.controls)
        self.reset_check.pack(anchor='w', pady=(8, 0))

        actions = ui.frame(body)
        actions.pack(fill='x', pady=16)
        self.stop_button = ui.button(actions, 'Dừng', self.stop, width=76, height=42)
        self.stop_button.pack(side='right')
        self.reconnect_button = ui.button(actions, 'Xin lại quyền USB', self.request_reconnect,
                                          width=156, height=42, variant='ghost')
        self.reconnect_button.pack(side='right', padx=10)
        self.start_button = ui.button(actions, 'Patch tiếng Việt + menu và cài', self.start,
                                      variant='primary', height=42)
        self.start_button.pack(side='left', fill='x', expand=True)

        footer = ui.frame(body)
        footer.pack(side='bottom', fill='x', pady=(12, 0))
        ui.button(footer, 'APK & báo cáo', self.open_output,
                  width=146, height=34, variant='ghost').pack(side='left')
        self.output_button = ui.button(footer, 'Kích hoạt xuất hình', self.activate_output,
                                       width=168, height=34, variant='ghost')
        self.output_button.pack(side='left', padx=(8, 0))
        self.folder_button = ui.button(footer, 'Thư mục làm việc', self.choose_work,
                                       width=160, height=34, variant='ghost')
        self.folder_button.pack(side='right')

        activity = ui.frame(body, color=ui.SURFACE, radius=20)
        activity.pack(fill='both', expand=True)
        activity_inner = ui.frame(activity)
        activity_inner.pack(fill='both', expand=True, padx=18, pady=16)
        activity_heading = ui.frame(activity_inner)
        activity_heading.pack(fill='x')
        ui.label(activity_heading, textvariable=self.stage, size=15, bold=True).pack(side='left')
        ui.label(activity_heading, 'NHẬT KÝ', muted=True, size=10).pack(side='right')
        progress_track = ui.frame(activity_inner, color=ui.FIELD, radius=2, height=5)
        progress_track.pack(fill='x', pady=(12, 10))
        progress_track.pack_propagate(False)
        self.progress = ttk.Progressbar(progress_track, style='Studio.Horizontal.TProgressbar')
        self.progress.pack(fill='both', expand=True)
        self.status_label = ui.label(activity_inner, textvariable=self.status, muted=True,
                                      size=12, wraplength=760, anchor='w', justify='left')
        self.status_label.pack(fill='x', pady=(0, 12))
        log_surface = ui.frame(activity_inner, color=ui.FIELD, radius=12)
        log_surface.pack(fill='both', expand=True)
        self.log = tk.Text(log_surface, height=5, bg=ui.FIELD, fg='#c7d1de', relief='flat',
                           borderwidth=0, highlightthickness=0, insertbackground=ui.ACCENT,
                           font=('Consolas', 10), wrap='word', state='disabled', padx=10, pady=8)
        self.log.pack(fill='both', expand=True)
        self.log.pack_configure(padx=8, pady=6)
        activity_inner.bind('<Configure>',
                            lambda event: self.status_label.configure(wraplength=max(300, event.width)))
        self.controls()

    def scan(self):
        if self.thread and self.thread.is_alive(): return
        try:
            devices = discover()
            values = [device.serial for device in devices]
            self.selector.configure(values=values)
            if self.serial.get() not in values:
                self.serial.set(values[0] if len(values) == 1 else '')
            self.status.set('Đã thấy RC 2. Xác nhận đã hạ cánh trước khi cài đặt hoặc kích hoạt tính năng.' if values
                            else 'Chưa thấy RC 2 trên USB. Nối cáp dữ liệu rồi bấm Quét lại.')
        except Exception as error:
            self.status.set(str(error))
        self.controls()

    def controls(self):
        busy = bool(self.thread and self.thread.is_alive())
        enabled = not busy and not self.closing
        self.animation_button.configure(state='normal' if not self.closing else 'disabled')
        self.selector.configure(state='readonly' if enabled else 'disabled')
        for widget in (self.scan_button, self.folder_button, self.ground_check, self.reset_check):
            widget.configure(state='normal' if enabled else 'disabled')
        self.start_button.configure(state='normal' if enabled and self.serial.get()
                                    and self.grounded.get() else 'disabled')
        self.output_button.configure(state='normal' if enabled and self.serial.get()
                                     and self.grounded.get() else 'disabled')
        self.stop_button.configure(state='normal' if busy and not self.cancel.is_set() else 'disabled')
        self.reconnect_button.configure(state='normal' if self.can_request_usb() else 'disabled')

    def can_request_usb(self):
        if self.closing or not self.serial.get():
            return False
        busy = bool(self.thread and self.thread.is_alive())
        return not busy or (self.usb_recovery and not self.cancel.is_set())

    def animation_devices(self):
        self.scan()
        return list(self.selector['values'])

    def open_animation(self):
        if self.closing:
            return
        if self.active_page == 'patch':
            self._page_geometry['patch'] = self.root.geometry()
        editor = self.animation_editor
        if editor is not None:
            try:
                if editor._destroyed or not editor.view.winfo_exists():
                    editor = None
            except tk.TclError:
                editor = None
        if editor is None:
            from rc2vi.animation_editor import AnimationEditor
            editor = AnimationEditor(self.root, self.base / 'animation',
                install_callback=self.install_animation,
                busy_callback=lambda: bool(self.thread and self.thread.is_alive()) or self.closing,
                serial_var=self.serial, grounded_var=self.grounded, scan_callback=self.animation_devices,
                device_status_var=self.status, embedded=True, back_callback=self.show_patch,
                reconnect_callback=self.request_reconnect, reconnect_state_callback=self.can_request_usb)
            self.animation_editor = editor
        if editor._closing:
            return editor
        if self.active_page != 'animation':
            self.patch_page.pack_forget()
            self.root.minsize(1050, 650)
            self.root.geometry(self._page_geometry['animation'])
            self.active_page = 'animation'
        if not editor._visible:
            editor.show()
        return editor

    def show_patch(self):
        if self.closing:
            return False
        if self.active_page == 'animation':
            self._page_geometry['animation'] = self.root.geometry()
            if self.animation_editor is not None:
                self.animation_editor.hide()
            self.active_page = 'patch'
            self.root.minsize(800, 680)
            self.root.geometry(self._page_geometry.get('patch', '900x760'))
            self.patch_page.pack(fill='both', expand=True, padx=24, pady=20)
        self.root.title('RC2 Studio · Tiếng Việt, menu & Animation · r14.6')
        self.controls()
        return True

    def install_animation(self, package_path, kind='boot', restore=False):
        if self.closing or (self.thread and self.thread.is_alive()):
            messagebox.showerror('Đang có thao tác khác', 'Chờ thao tác RC 2 hiện tại hoàn tất trước khi cài animation.', parent=self.root)
            return False
        if not self.serial.get() or not self.grounded.get():
            messagebox.showerror('Chưa sẵn sàng cài',
                'Chọn đúng RC 2 và xác nhận máy bay đã hạ cánh, động cơ dừng.', parent=self.root)
            return False
        if kind not in {'boot', 'shutdown'}:
            raise ValueError('Loại animation không hợp lệ.')
        serial = self.serial.get()
        self.cancel = threading.Event()
        self.animation_job = True
        self.reconnect_event.clear()
        self.usb_recovery = False
        self.current_work = self.base / 'animation' / 'device'
        self.stage.set('Khôi phục animation gốc' if restore else 'Đang cài animation')
        self.status.set('Kết nối đúng RC 2; chọn Allow USB debugging trên tay nếu được hỏi.')
        self.progress.configure(mode='indeterminate')
        self.progress.start(12)
        def run():
            try:
                from rc2vi.animation_install import install_animation, restore_animation
                options = dict(grounded=True, emit=lambda state,message:self.events.put((state,message)),
                               cancel=self.cancel, reconnect_event=self.reconnect_event)
                if restore:
                    result = restore_animation(self.assets, self.current_work, serial, kind, **options)
                else:
                    result = install_animation(self.assets, self.current_work, serial, Path(package_path), kind, **options)
                if not result.get('restored_verified' if restore else 'installed_verified'):
                    raise RuntimeError('Chưa xác minh được cấu hình animation trên RC 2; chưa báo hoàn tất.')
                atomic_json(self.current_work / 'last-result.json', result)
                self.events.put(('animation_restored' if restore else 'animation_installed',
                    'Đã khôi phục cấu hình animation trước đó. Có hiệu lực ở lần bật/tắt tay tiếp theo.' if restore else
                    'Đã cài và xác minh animation. Có hiệu lực ở lần bật/tắt tay tiếp theo; chưa khởi động lại tay.'))
            except Exception as error:
                self.events.put(('stopped' if self.cancel.is_set() else 'error', str(error)))
            finally:
                self.events.put(('idle',''))
        self.thread = threading.Thread(target=run, name='RC2-animation-install', daemon=False)
        self.thread.start()
        self.controls()
        return True

    def start(self):
        if self.thread and self.thread.is_alive(): return
        if not (self.serial.get() and self.grounded.get()): return
        allow_data_reset = self.reset.get()
        serial = self.serial.get()
        try:
            self.current_work = patch_work_directory(self.base, self.assets, serial)
        except (OSError, ValueError) as error:
            messagebox.showerror('Chưa thể tiếp tục', str(error), parent=self.root)
            return
        stop_file = self.current_work / 'STOP'
        if stop_file.exists():
            if stop_file.read_text('utf-8').strip() != 'RC2-AUTO-PATCH-STOP':
                messagebox.showerror('Chưa thể tiếp tục', 'Tệp STOP không thuộc app; kiểm tra thư mục tiến độ.', parent=self.root)
                return
            stop_file.unlink()
        self.cancel = threading.Event()
        self.reconnect_event.clear()
        self.usb_recovery = False
        self.progress.configure(mode='indeterminate')
        self.progress.start(12)
        self.stage.set('Đang kết nối RC 2')
        def run():
            try:
                import shutil
                self.base.mkdir(parents=True, exist_ok=True)
                if shutil.disk_usage(self.base).free < 5 * 1024**3:
                    raise ValueError('Cần ít nhất 5 GiB trống để lấy, patch, ký và kiểm chứng APK.')
                runner = AutoPatchRun(self.assets, self.current_work, serial,
                                      lambda state, message: self.events.put((state, message)), self.cancel,
                                      reconnect_event=self.reconnect_event)
                runner.run(grounded=True, allow_data_reset=allow_data_reset)
            except Exception as error:
                self.events.put(('stopped' if self.cancel.is_set() else 'error', str(error)))
            finally:
                self.events.put(('idle', ''))
        self.thread = threading.Thread(target=run, name='RC2-auto-patch', daemon=False)
        self.thread.start()
        self.controls()

    def activate_output(self):
        if self.thread and self.thread.is_alive():return
        if not (self.serial.get() and self.grounded.get()):return
        serial=self.serial.get()
        self.cancel=threading.Event();self.reconnect_event.clear();self.usb_recovery=False
        self.current_work=self.base/'displayport-activation'
        stop_file=self.current_work/'STOP'
        if stop_file.exists():
            if stop_file.read_text('utf-8').strip()!='RC2-AUTO-PATCH-STOP':
                messagebox.showerror('Chưa thể tiếp tục','Tệp STOP không thuộc app; kiểm tra thư mục tiến độ.',parent=self.root)
                return
            stop_file.unlink()
        self.progress.configure(mode='indeterminate');self.progress.start(12)
        self.stage.set('Kích hoạt nút xuất hình')
        def run():
            try:
                from rc2vi.displayport_access import activate_existing
                activate_existing(self.assets,self.current_work,serial,True,
                    lambda state,message:self.events.put((state,message)),self.cancel,self.reconnect_event)
            except Exception as error:
                self.events.put(('stopped' if self.cancel.is_set() else 'error',str(error)))
            finally:self.events.put(('idle',''))
        self.thread=threading.Thread(target=run,name='RC2-output-permission',daemon=False)
        self.thread.start();self.controls()

    def request_reconnect(self):
        if not self.can_request_usb():
            return False
        if self.thread and self.thread.is_alive():
            self.reconnect_event.set()
            self.status.set('Đã yêu cầu tạo lại phiên ADB. Bấm Allow trên tay nếu hộp thoại xuất hiện.')
            return True
        serial = self.serial.get()
        self.cancel = threading.Event()
        self.reconnect_event.clear()
        cancel, reconnect_event = self.cancel, self.reconnect_event
        self.usb_authorization_job = True
        self.usb_recovery = True
        self.stage.set('Đang xin quyền USB')
        self.status.set('Chọn Allow USB debugging trên tay. Chưa được chấp thuận sau 10 giây sẽ tự xin lại.')
        self.progress.configure(mode='indeterminate')
        self.progress.start(12)
        def run():
            try:
                from rc2vi.usb_authorization import authorize_usb
                result = authorize_usb(self.assets, serial,
                    emit=lambda state,message:self.events.put((state,message)),
                    cancel=cancel, reconnect_event=reconnect_event)
                if not result.get('authorized_verified'):
                    raise RuntimeError('Chưa xác minh được quyền USB trên đúng RC2 đã chọn.')
                report = self.base / 'usb-authorization' / 'last-result.json'
                try:
                    report.parent.mkdir(parents=True, exist_ok=True)
                    atomic_json(report.parent.resolve() / report.name, result)
                except (OSError, ValueError) as error:
                    self.events.put(('warning', 'Đã xác minh quyền USB nhưng chưa lưu được báo cáo: ' + str(error)))
                self.events.put(('usb_authorized', 'Đã xác minh quyền USB trên đúng RC2. Có thể tiếp tục cài đặt.'))
            except Exception as error:
                self.events.put(('stopped' if cancel.is_set() else 'error', str(error)))
            finally:
                self.events.put(('idle', ''))
        self.thread = threading.Thread(target=run, name='RC2-usb-authorization', daemon=False)
        self.thread.start()
        self.controls()
        return True

    def stop(self):
        if not self.animation_job and not self.usb_authorization_job and self.current_work and self.current_work.is_dir():
            (self.current_work / 'STOP').write_text('RC2-AUTO-PATCH-STOP', 'utf-8')
        self.cancel.set()
        self.status.set('Đang dừng chờ quyền USB.' if self.usb_authorization_job else
                        'Đang dừng cài animation sau lệnh hiện tại.' if self.animation_job else
                        'Đang dừng sau lệnh hiện tại; giữ APK và tiến độ để tiếp tục.')
        self.controls()

    def close(self):
        self.closing = True
        self.cancel.set()
        if self.animation_editor is not None:
            try:
                if not self.animation_editor._destroyed and not self.animation_editor.close():
                    if self.animation_editor._closing:
                        self.root.after(150, self.close)
                    else:
                        self.closing = False
                        self.status.set('Kiểm tra ô nhập chưa hợp lệ trong Animation trước khi đóng.')
                        self.open_animation()
                        self.controls()
                    return
            except tk.TclError:
                pass
        if self.thread and self.thread.is_alive():
            self.status.set('Đang kết thúc lệnh hiện tại và lưu tiến độ…')
            self.controls()
        else:
            self.root.destroy()

    def choose_work(self):
        folder = filedialog.askdirectory(parent=self.root, initialdir=str(self.base.parent),
                                         title='Chọn nơi lưu APK và tiến độ')
        if folder:
            self.base = Path(folder) / 'RC2AutoPatch'
            self.status.set('APK và báo cáo sẽ lưu tại: ' + str(self.base))

    def open_output(self):
        folder = self.current_work or self.base
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))

    def poll(self):
        labels = {'pairing': 'Chờ Allow USB debugging', 'connected': 'Đã kết nối RC 2',
                  'capturing': 'Đang lấy APK từ tay', 'recovering': 'Đang xác minh nguồn APK',
                  'building': 'Đang patch và kiểm chứng APK', 'built': 'Đã dựng APK',
                  'installing': 'Đang truyền và cài', 'upload': 'Đang truyền APK',
                  'installed': 'Đã cài và xác minh thành công', 'error': 'Chưa hoàn tất',
                  'animation_installed': 'Đã cài animation', 'animation_restored': 'Đã khôi phục animation',
                  'usb_authorized': 'Đã xác minh quyền USB',
                  'disconnected': 'USB vừa gián đoạn', 'reconnecting': 'Đang xin kết nối USB lại',
                  'stopped': 'Đã dừng, giữ tiến độ', 'retry': 'Đang chờ kết nối để tiếp tục'}
        try:
            while True:
                state, message = self.events.get_nowait()
                if state == 'idle':
                    if self.thread and self.thread.is_alive():
                        self.root.after(100, lambda: self.events.put(('idle', '')))
                        continue
                    self.animation_job = False
                    self.usb_authorization_job = False
                    self.usb_recovery = False
                    self.progress.stop()
                    if self.closing:
                        self.root.after(100, self.close)
                    else:
                        self.root.after(100, self.controls)
                    continue
                self.stage.set('Chờ màn hình RC 2' if state=='waiting_ui' else labels.get(state, self.stage.get()))
                if state in {'disconnected','reconnecting','pairing','retry'}:
                    self.usb_recovery=True
                elif state in {'connected','identity','installed','animation_installed','animation_restored','usb_authorized','error','stopped'}:
                    self.usb_recovery=False
                self.controls()
                display = message
                if state == 'retry' and 'not enumerated' in message:
                    display = 'Windows chưa thấy RC 2. Khi tay xuất hiện lại, app sẽ tạo phiên mới và xin Allow nếu cần.'
                elif state == 'retry' and 'RC2_WAIT_ANDROID_SETTINGS' in message:
                    display = 'Thoát Fly về Launcher/Settings để bộ cài tiếp tục.'
                self.status.set(display)
                if state == 'upload':
                    import re
                    match = re.search(r'(\d+)/(\d+)', message)
                    if match:
                        self.progress.stop()
                        self.progress.configure(mode='determinate', maximum=int(match[2]), value=int(match[1]))
                if state in {'installed','animation_installed','animation_restored','usb_authorized'}:
                    self.progress.stop()
                    self.progress.configure(mode='determinate', maximum=100, value=100)
                if (state, display) != self.last_log:
                    self.log.configure(state='normal')
                    self.log.insert('end', display + '\n')
                    self.log.see('end')
                    self.log.configure(state='disabled')
                    self.last_log = (state, display)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


def main(argv=None):
    parser = argparse.ArgumentParser(description='RC2 tự patch tiếng Việt + menu local và cài')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--run', action='store_true')
    modes.add_argument('--self-test', action='store_true')
    modes.add_argument('--smoke-ui', action='store_true')
    modes.add_argument('--smoke-animation-ui', action='store_true')
    modes.add_argument('--animation-self-test', action='store_true')
    modes.add_argument('--animation-ui-self-test', action='store_true',
                       help='Đo phản hồi nhập chữ và kiểm tra nút Animation; không kết nối RC2.')
    modes.add_argument('--navigation-ui-self-test', action='store_true',
                       help='Kiểm tra Animation cùng cửa sổ, Quay lại và giữ thiết kế; không kết nối RC2.')
    modes.add_argument('--animation-package-ui-self-test', action='store_true',
                       help='Kiểm tra chọn ZIP có sẵn và nút xin lại quyền USB; không kết nối RC2.')
    modes.add_argument('--animation-export', type=Path,
                       help='Xuất animation từ dự án .rc2anim; không kết nối RC 2.')
    modes.add_argument('--build-from-apk', type=Path,
                       help='Dựng APK ngoại tuyến từ bản nguồn được nhận diện; không kết nối RC 2.')
    parser.add_argument('--serial')
    parser.add_argument('--work', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--grounded', action='store_true')
    parser.add_argument('--allow-data-reset', action='store_true')
    args = parser.parse_args(argv)
    assets, default_work = locations()
    work = args.work or default_work
    report_path = args.report or work / 'command-result.json'
    if (not args.run and not args.self_test and args.build_from_apk is None
            and not args.animation_self_test and args.animation_export is None):
        if args.animation_package_ui_self_test:
            from rc2vi.animation_package_ui_check import run_package_ui_check
            report_path.parent.mkdir(parents=True, exist_ok=True)
            result = run_package_ui_check(work / 'animation-package-ui-self-test')
            atomic_json(report_path, result)
            return 0 if result.get('status') == 'PASS' else 1
        if args.navigation_ui_self_test:
            from rc2vi.navigation_ui_check import run_navigation_check
            report_path.parent.mkdir(parents=True, exist_ok=True)
            result = run_navigation_check(work / 'navigation-ui-self-test')
            atomic_json(report_path, result)
            return 0 if result.get('status') == 'PASS' else 1
        if args.animation_ui_self_test:
            from rc2vi.animation_ui_check import run_ui_check
            report_path.parent.mkdir(parents=True, exist_ok=True)
            result = run_ui_check(work / 'animation-ui-self-test')
            atomic_json(report_path, result)
            return 0 if result.get('status') == 'PASS' else 1
        from rc2vi.desktop_theme import ctk
        root = ctk.CTk()
        app = App(root, assets, work)
        if args.smoke_ui:
            def inspect_main():
                try:
                    from PIL import ImageGrab
                    root.update_idletasks()
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    screenshot = report_path.with_suffix('.png')
                    capture = ImageGrab.grab(window=int(root.winfo_id()))
                    if all(low == high for low, high in capture.getextrema()):
                        raise RuntimeError('Ảnh giao diện chưa được Windows dựng đầy đủ.')
                    capture.save(screenshot)
                    atomic_json(report_path, {
                        'status': 'PASS', 'title': root.title(), 'width': root.winfo_width(),
                        'height': root.winfo_height(), 'usb_opened': False,
                        'output_button_visible': bool(app.output_button.winfo_viewable()),
                        'animation_button_visible': bool(app.animation_button.winfo_viewable()),
                        'reconnect_button_visible': bool(app.reconnect_button.winfo_viewable()),
                        'reconnect_button_idle_state': str(app.reconnect_button['state']),
                        'screenshot': str(screenshot),
                    })
                except Exception as error:
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    atomic_json(report_path, {'status': 'FAILED', 'error': str(error), 'usb_opened': False})
                finally:
                    root.destroy()
            root.after(1200, inspect_main)
        elif args.smoke_animation_ui:
            def inspect_editor():
                try:
                    editor = app.open_animation()
                    editor.window.update()
                    state = editor.get_smoke_state()
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    from PIL import ImageGrab
                    window = editor.window
                    screenshot = report_path.with_suffix('.png')
                    capture = ImageGrab.grab(window=int(window.winfo_id()))
                    if all(low == high for low, high in capture.getextrema()):
                        raise RuntimeError('Ảnh giao diện chưa được Windows dựng đầy đủ.')
                    capture.save(screenshot)
                    atomic_json(report_path, {'status':'PASS','usb_opened':False,
                        'title':window.title(),'editor':state,'screenshot':str(screenshot)})
                except Exception as error:
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    atomic_json(report_path, {'status':'FAILED','error':str(error),'usb_opened':False})
                finally:
                    if app.animation_editor is not None:
                        app.animation_editor.close()
                    root.destroy()
            def prepare_editor():
                editor = app.open_animation()
                editor.time_var.set(max(0.,float(editor.project['intro'])-.2))
                root.after(800, inspect_editor)
            root.after(400, prepare_editor)
        root.mainloop()
        return 0
    def emit(state, message):
        if sys.stdout is not None:
            print(json.dumps({'state': state, 'message': message}, ensure_ascii=True), flush=True)
    try:
        work.mkdir(parents=True, exist_ok=True)
        if args.animation_self_test:
            from PIL import Image, ImageDraw
            from rc2vi import animation
            folder = work / 'animation-self-test'
            folder.mkdir(parents=True,exist_ok=True)
            image = Image.new('RGB',(240,160),'#103446')
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((12,12,227,147),radius=24,outline='#80e1bf',width=5)
            draw.line((60,110,110,50,175,110),fill='#ffffff',width=9)
            source_image = folder / 'import-test.png'
            image.save(source_image)
            project = animation.new_project()
            project.update(name='GinzaTech - kiểm tra Animation',width=640,height=360,fps=12)
            project['layers'].append(animation.make_layer('image',image=str(source_image),
                name='Ảnh nhập thử',x=0.86,y=0.82,width=0.13,start=0.5,duration=0.7,effect='zoom'))
            saved = animation.save_project(project,folder/'demo.rc2anim')
            reopened = animation.load_project(saved,folder/'loaded')
            exported = animation.export_animation(reopened,folder/'export')
            result = {**exported,'status':'PASS','usb_opened':False,'device_modified':False,
                      'portable_project':str(saved),'effects':dict(animation.EFFECTS),
                      'loop_effects':dict(animation.LOOP_EFFECTS),'presets':dict(animation.PRESETS),
                      'image_imported':True,'multiple_layers':len(reopened['layers'])}
        elif args.animation_export is not None:
            from rc2vi import animation
            project = animation.load_project(args.animation_export,work/'animation-import')
            exported = animation.export_animation(project,work/'animation-export')
            result = {**exported,'status':'PASS','usb_opened':False,'device_modified':False}
        elif args.self_test:
            from rc2vi.activation import verify_bundle
            verify_bundle(assets)
            builder = AutoPatchBuilder(assets, work / 'self-test-tools', emit)
            builder._translation()
            recipes = {}
            translations = {}
            for profile in SUPPORTED:
                builder.select_profile(profile)
                builder._translation()
                manifest, _, _, _, _ = builder.menu._bundle()
                recipes[profile.version] = manifest['recipe_sha256']
                translations[profile.version] = builder.translation_sha256
            builder.tools.prepare()
            result = {'status': 'PASS', 'usb_opened': False, 'offline_runtime_ready': True,
                      'recipes': recipes, 'supported_versions': list(recipes), 'vietnamese_embedded': True,
                      'translations': translations,
                      'full_fly_apk_embedded': False, 'private_signing_key_embedded': False}
        elif args.build_from_apk is not None:
            import uuid
            builder = AutoPatchBuilder(assets, work / 'build', emit)
            source = work / ('offline-source-' + uuid.uuid4().hex + '.apk')
            try:
                builder.recover(args.build_from_apk.absolute(), source)
                source.replace(work / 'source.apk')
            finally:
                source.unlink(missing_ok=True)
            profile = builder.version_profile
            builder = AutoPatchBuilder(assets, work / profile.build_directory, emit)
            result = {**builder.build(work / 'source.apk'), 'status': 'PASS',
                      'usb_opened': False, 'device_modified': False}
        else:
            if not args.serial:
                raise ValueError('Chỉ định --serial của đúng RC 2 để chạy tự động.')
            result = AutoPatchRun(assets, work, args.serial, emit).run(
                grounded=args.grounded, allow_data_reset=args.allow_data_reset)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(report_path, result)
        return 0
    except Exception as error:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(report_path, {'status': 'FAILED', 'error': str(error), 'type': type(error).__name__})
        emit('error', str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
