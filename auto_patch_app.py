"""Standalone desktop/CLI for the actual offline RC2 APK patch pipeline."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from rc2vi.auto_patch import AutoPatchBuilder, atomic_json
from rc2vi.auto_workflow import AutoPatchRun
from rc2vi.usb_windows import discover
from rc2vi.hud_tools import sha256_file
from rc2vi.fly_versions import SUPPORTED


def locations():
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local')))
    return base / 'assets', local / 'RC2AutoPatch'


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
        root = self.root
        root.title('RC2 · Tiếng Việt + menu mới · r13.1')
        root.geometry('820x650')
        root.minsize(730, 590)
        root.configure(bg='#171b22')
        style = ttk.Style(root)
        style.theme_use('clam')
        for name in ('TFrame', 'TLabel', 'TCheckbutton'):
            style.configure(name, background='#171b22', foreground='#f4f6f9', font=('Segoe UI', 10))
        style.configure('TButton', padding=(14, 8), background='#2a3441', foreground='#f4f6f9', font=('Segoe UI', 10))
        style.map('TButton', background=[('active', '#3a4858')], foreground=[('disabled', '#8d98a7')])
        style.configure('Primary.TButton', background='#80e1bf', foreground='#102b23', font=('Segoe UI', 11, 'bold'))
        style.map('Primary.TButton', background=[('active', '#a4efd5'), ('disabled', '#354b46')], foreground=[('disabled', '#829e94')])
        style.configure('TCombobox', fieldbackground='#252d38', foreground='#f4f6f9', padding=7)
        style.map('TCombobox', fieldbackground=[('readonly', '#252d38')], foreground=[('readonly', '#f4f6f9')])
        style.map('TCheckbutton', background=[('active', '#171b22')])
        style.configure('Horizontal.TProgressbar', background='#80e1bf', troughcolor='#252d38')
        body = ttk.Frame(root, padding=24)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='RC2  /  TỰ PATCH & CÀI', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        ttk.Label(body, text='Menu local nâng cao + tiếng Việt tích hợp trong một APK', foreground='#80e1bf').pack(anchor='w', pady=(4, 5))
        ttk.Label(body, text='Fly RC 1.21.8 / 1.21.10 · Đèn càng · HUD · Xuất hình · FCC/EC · Nâng cao · Hiệu chỉnh gimbal',
                  foreground='#b0b9c8', wraplength=740).pack(anchor='w', pady=(0, 20))
        row = ttk.Frame(body)
        row.pack(fill='x')
        ttk.Label(row, text='Tay RC 2').pack(side='left', padx=(0, 12))
        self.selector = ttk.Combobox(row, textvariable=self.serial, state='readonly')
        self.selector.pack(side='left', fill='x', expand=True)
        self.scan_button = ttk.Button(row, text='Quét lại', command=self.scan)
        self.scan_button.pack(side='left', padx=(10, 0))
        self.selector.bind('<<ComboboxSelected>>', lambda _: self.controls())
        ttk.Label(body, text='Khi tay hiện “Allow USB debugging”, chọn “Always allow” rồi bấm “Allow”.',
                  foreground='#b0b9c8').pack(anchor='w', pady=(8, 18))
        self.ground_check = ttk.Checkbutton(body, text='Máy bay đã hạ cánh và động cơ đã dừng',
                                          variable=self.grounded, command=self.controls)
        self.ground_check.pack(anchor='w')
        self.reset_check = ttk.Checkbutton(body, text='Tùy chọn: cho phép gỡ/cài lại nếu khác chữ ký (xóa dữ liệu Fly)',
                                         variable=self.reset, command=self.controls)
        self.reset_check.pack(anchor='w', pady=(8, 18))
        actions = ttk.Frame(body)
        actions.pack(fill='x')
        self.start_button = ttk.Button(actions, text='Tự patch tiếng Việt + menu và cài',
                                       style='Primary.TButton', command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(actions, text='Dừng', command=self.stop)
        self.stop_button.pack(side='right')
        self.reconnect_button = ttk.Button(actions, text='Xin quyền USB lại', command=self.request_reconnect)
        self.reconnect_button.pack(side='right',padx=(8,8))
        ttk.Label(body, textvariable=self.stage, font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(20, 5))
        self.progress = ttk.Progressbar(body)
        self.progress.pack(fill='x', pady=(0, 8))
        ttk.Label(body, textvariable=self.status, wraplength=740, foreground='#b0b9c8').pack(anchor='w', pady=(0, 12))
        self.log = tk.Text(body, height=8, bg='#11151b', fg='#c7d1de', relief='flat',
                           font=('Consolas', 9), wrap='word', state='disabled', padx=10, pady=8)
        self.log.pack(fill='both', expand=True)
        footer = ttk.Frame(body)
        footer.pack(fill='x', pady=(12, 0))
        ttk.Button(footer, text='Mở APK / báo cáo', command=self.open_output).pack(side='left')
        self.output_button = ttk.Button(footer, text='Kích hoạt nút xuất hình', command=self.activate_output)
        self.output_button.pack(side='left', padx=(10, 0))
        self.folder_button = ttk.Button(footer, text='Chọn thư mục làm việc', command=self.choose_work)
        self.folder_button.pack(side='right')
        self.controls()

    def scan(self):
        if self.thread and self.thread.is_alive(): return
        try:
            devices = discover()
            values = [device.serial for device in devices]
            self.selector['values'] = values
            if self.serial.get() not in values:
                self.serial.set(values[0] if len(values) == 1 else '')
            self.status.set('Đã thấy RC 2. Xác nhận đã hạ cánh rồi bấm Tự patch để bắt đầu.' if values
                            else 'Chưa thấy RC 2 trên USB. Nối cáp dữ liệu rồi bấm Quét lại.')
        except Exception as error:
            self.status.set(str(error))
        self.controls()

    def controls(self):
        busy = bool(self.thread and self.thread.is_alive())
        enabled = not busy and not self.closing
        self.selector.configure(state='readonly' if enabled else 'disabled')
        for widget in (self.scan_button, self.folder_button, self.ground_check, self.reset_check):
            widget.configure(state='normal' if enabled else 'disabled')
        self.start_button.configure(state='normal' if enabled and self.serial.get()
                                    and self.grounded.get() else 'disabled')
        self.output_button.configure(state='normal' if enabled and self.serial.get()
                                     and self.grounded.get() else 'disabled')
        self.stop_button.configure(state='normal' if busy and not self.cancel.is_set() else 'disabled')
        self.reconnect_button.configure(state='normal' if busy and self.usb_recovery
                                        and not self.cancel.is_set() else 'disabled')

    def start(self):
        if self.thread and self.thread.is_alive(): return
        if not (self.serial.get() and self.grounded.get()): return
        allow_data_reset = self.reset.get()
        serial = self.serial.get()
        import hashlib
        self.current_work = self.base / ('rc2-' + hashlib.sha256(serial.encode()).hexdigest()[:16])
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
        if self.thread and self.thread.is_alive() and self.usb_recovery and not self.cancel.is_set():
            self.reconnect_event.set()
            self.status.set('Đã yêu cầu tạo lại phiên ADB. Bấm Allow trên tay nếu hộp thoại xuất hiện.')

    def stop(self):
        if self.current_work and self.current_work.is_dir():
            (self.current_work / 'STOP').write_text('RC2-AUTO-PATCH-STOP', 'utf-8')
        self.cancel.set()
        self.status.set('Đang dừng sau lệnh hiện tại; giữ APK và tiến độ để tiếp tục.')
        self.controls()

    def close(self):
        self.closing = True
        self.cancel.set()
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
                  'disconnected': 'USB vừa gián đoạn', 'reconnecting': 'Đang xin kết nối USB lại',
                  'stopped': 'Đã dừng, giữ tiến độ', 'retry': 'Đang chờ kết nối để tiếp tục'}
        try:
            while True:
                state, message = self.events.get_nowait()
                if state == 'idle':
                    self.progress.stop()
                    if self.closing:
                        self.root.after(100, self.close)
                    else:
                        self.root.after(100, self.controls)
                    continue
                self.stage.set('Chờ màn hình RC 2' if state=='waiting_ui' else labels.get(state, self.stage.get()))
                if state in {'disconnected','reconnecting','pairing','retry'}:
                    self.usb_recovery=True
                elif state in {'connected','identity','installed'}:
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
                if state == 'installed':
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
    if not args.run and not args.self_test and args.build_from_apk is None:
        root = tk.Tk()
        app = App(root, assets, work)
        if args.smoke_ui:
            root.after(1200, lambda: (report_path.parent.mkdir(parents=True, exist_ok=True),
                atomic_json(report_path, {'status': 'PASS', 'title': root.title(), 'width': root.winfo_width(),
                                          'height': root.winfo_height(), 'usb_opened': False,
                                          'output_button_visible': bool(app.output_button.winfo_viewable()),
                                          'reconnect_button_visible': bool(app.reconnect_button.winfo_viewable()),
                                          'reconnect_button_idle_state': str(app.reconnect_button['state'])}), root.destroy()))
        root.mainloop()
        return 0
    def emit(state, message):
        if sys.stdout is not None:
            print(json.dumps({'state': state, 'message': message}, ensure_ascii=True), flush=True)
    try:
        work.mkdir(parents=True, exist_ok=True)
        if args.self_test:
            from rc2vi.activation import verify_bundle
            verify_bundle(assets)
            builder = AutoPatchBuilder(assets, work / 'self-test-tools', emit)
            builder._translation()
            recipes = {}
            for profile in SUPPORTED:
                builder.select_profile(profile)
                manifest, _, _, _, _ = builder.menu._bundle()
                recipes[profile.version] = manifest['recipe_sha256']
            builder.tools.prepare()
            result = {'status': 'PASS', 'usb_opened': False, 'offline_runtime_ready': True,
                      'recipes': recipes, 'supported_versions': list(recipes), 'vietnamese_embedded': True,
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
