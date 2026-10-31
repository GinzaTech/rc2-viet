"""Compact private RC2 GUI. All worker events/dialogs are handled on Tk's thread."""
from datetime import datetime
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

MAIN_BUTTON = 'Cài menu Nâng cao 1.21.10'


class App:
    def __init__(self, root, assets, work, start_worker=True, worker=None):
        self.root, self.events = root, queue.Queue()
        self.main_thread = threading.get_ident()
        self.work = Path(work)
        self.work_label = tk.StringVar(root, str(self.work))
        self.entries, self.selected, self.closing, self.poll_after = [], '', False, None
        if worker is None and start_worker:
            from .clean_worker import CleanWorker
            worker = CleanWorker(assets, work, self.emit)
        self.worker = worker
        self.status = tk.StringVar(root, 'Cắm RC 2, bấm Quét rồi Connect. Khi tay hỏi USB, bấm Allow.')
        self.grounded = tk.BooleanVar(root, False)
        self.wipe_ack = tk.BooleanVar(root, False)
        self.vietnamese = tk.BooleanVar(root, True)
        self._view()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.bind('<Destroy>', self._destroyed, add='+')
        self.refresh_controls()
        self.poll_after = root.after(100, self.poll)
        if self.worker and getattr(self.worker,'clean_workflow',False):
            root.after(0,self.worker.resume_pending)

    def _view(self):
        root = self.root
        root.title('RC2 · Quy trình sạch · r2.2 · Riêng tư')
        root.configure(background='#000000')
        root.geometry('720x530')
        root.minsize(640, 460)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame', background='#000000')
        style.configure('TLabel', background='#000000', foreground='#eeeeee', font=('Segoe UI', 10))
        style.configure('TButton', padding=(10, 5), background='#202020', foreground='#eeeeee')
        style.map('TButton', background=[('active', '#333333')], foreground=[('disabled', '#888888')])
        style.configure('Advanced.TButton', background='#c72232', font=('Segoe UI', 10, 'bold'))
        style.configure('TCheckbutton', background='#000000', foreground='#eeeeee')
        style.map('TCheckbutton', background=[('active', '#000000')], foreground=[('disabled', '#888888')])
        style.configure('TCombobox', fieldbackground='#202020', foreground='#eeeeee')
        style.map('TCombobox', fieldbackground=[('readonly', '#202020')],
                  foreground=[('readonly', '#eeeeee')])
        style.configure('Horizontal.TProgressbar', background='#c72232', troughcolor='#202020', thickness=4)
        body = ttk.Frame(root, padding=16)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='RC2  /  NÂNG CAO 1.21.10', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        ttk.Label(body, text='DJI RC 2 · Android 11 · Menu cơ bản + Nâng cao + Hiệu chỉnh gimbal').pack(anchor='w', pady=(2, 14))
        row = ttk.Frame(body)
        row.pack(fill='x')
        ttk.Label(row, text='RC 2').pack(side='left', padx=(0, 10))
        self.selector = ttk.Combobox(row, state='readonly', width=27)
        self.selector.pack(side='left', fill='x', expand=True)
        self.selector.bind('<<ComboboxSelected>>', self.on_select)
        self.scan_button = ttk.Button(row, text='Quét', command=lambda: self.send('scan'))
        self.scan_button.pack(side='left', padx=6)
        self.connect_button = ttk.Button(row, text='Connect', command=lambda: self.send('connect'))
        self.connect_button.pack(side='left')
        workspace = ttk.Frame(body)
        workspace.pack(fill='x', pady=(8, 0))
        self.work_button = ttk.Button(workspace, text='Thư mục làm việc', command=self.choose_work)
        self.work_button.pack(side='left', padx=(0, 10))
        ttk.Label(workspace, textvariable=self.work_label, wraplength=490).pack(side='left', fill='x', expand=True)
        self.status_label = ttk.Label(body, textvariable=self.status, wraplength=660)
        self.status_label.pack(anchor='w', pady=(12, 6))
        self.progress = ttk.Progressbar(body, mode='determinate')
        self.progress.pack(fill='x', pady=(0, 10))
        self.ground_checkbox = ttk.Checkbutton(body, text='Tôi xác nhận đã hạ cánh và động cơ đã dừng',
                                             variable=self.grounded, command=self.refresh_controls)
        self.ground_checkbox.pack(anchor='w')
        self.wipe_checkbox=ttk.Checkbutton(body,text='Tôi đồng ý xóa dữ liệu DJI Fly trên RC 2 (đăng nhập, cài đặt, nhật ký)',
                                          variable=self.wipe_ack,command=self.refresh_controls)
        self.wipe_checkbox.pack(anchor='w',pady=(4,0))
        options = ttk.Frame(body)
        options.pack(fill='x', pady=8)
        self.vietnamese_checkbox = ttk.Checkbutton(options, text='Bật tiếng Việt', variable=self.vietnamese)
        self.vietnamese_checkbox.pack(side='left')
        self.translation_button = ttk.Button(options, text='Bật tiếng Việt', command=lambda: self.send('translate'))
        self.translation_button.pack(side='right')
        actions = ttk.Frame(body)
        actions.pack(fill='x', pady=(0, 12))
        self.install_button = ttk.Button(actions, text=MAIN_BUTTON, style='Advanced.TButton',
                                         command=lambda: self.send('install'))
        self.install_button.pack(side='left')
        self.resume_button=ttk.Button(actions,text='Tiếp tục',command=lambda:self.send('resume'))
        self.resume_button.pack(side='right',padx=6)
        self.cancel_button = ttk.Button(actions, text='Stop', command=self.cancel)
        self.cancel_button.pack(side='right')
        self.log = tk.Text(body, background='#101010', foreground='#cccccc', insertbackground='#eeeeee',
                           height=8, wrap='word', font=('Consolas', 9), relief='flat', state='disabled')
        self.log.pack(fill='both', expand=True)

    def emit(self, state, message):
        self.events.put((state, message))

    def on_select(self, event=None):
        if self.worker and self.worker.busy:
            self.selector.set(self.selected)
            return
        selected = self.selector.get()
        if selected != self.selected and self.worker:
            self.worker.request('release')
        self.selected = selected
        self.refresh_controls()

    def send(self, operation):
        if self.closing or not self.worker:
            return False
        if operation == 'scan':
            result = self.worker.request('scan')
        elif operation in {'install', 'translate','resume'}:
            arguments={'grounded':self.grounded.get(),'translate':self.vietnamese.get()}
            if getattr(self.worker,'clean_workflow',False):arguments['wipe']=self.wipe_ack.get()
            result = self.worker.request(operation, self.selector.get(), **arguments)
        else:
            result = self.worker.request(operation, self.selector.get())
        self.refresh_controls()
        return result

    def refresh_controls(self):
        busy = bool(self.worker and self.worker.busy)
        available = not self.closing and not busy
        chosen = bool(self.selector.get())
        pending=bool(getattr(self.worker,'clean_workflow',False) and getattr(self.worker,'can_resume',False))
        self.selector.configure(state='readonly' if available else 'disabled')
        for button in (self.scan_button, self.work_button, self.ground_checkbox, self.wipe_checkbox,self.vietnamese_checkbox):
            button.configure(state='normal' if available else 'disabled')
        self.connect_button.configure(state='normal' if available and chosen else 'disabled')
        acknowledged=self.grounded.get() and (self.wipe_ack.get() if not self.worker or getattr(self.worker,'clean_workflow',False) else True)
        for button in (self.install_button, self.translation_button):
            button.configure(state='normal' if available and chosen and acknowledged and not pending else 'disabled')
        self.work_button.configure(state='normal' if available and not pending else 'disabled')
        pending_serial=getattr(self.worker,'pending_serial','')
        self.resume_button.configure(state='normal' if available and chosen and acknowledged and
                                     getattr(self.worker,'can_resume',False) and
                                     (not pending_serial or pending_serial==self.selector.get()) else 'disabled')
        self.cancel_button.configure(state='normal' if busy and not self.closing else 'disabled')
        if busy:
            self.progress.configure(mode='indeterminate')
            self.progress.start(15)
        else:
            self.progress.stop()
            self.progress.configure(mode='determinate', value=0)

    def choose_work(self):
        if self.closing or (self.worker and self.worker.busy):
            return
        chosen = filedialog.askdirectory(parent=self.root, title='Chọn thư mục làm việc (cần khoảng 3 GiB trống)',
                                        initialdir=str(self.work), mustexist=True)
        if chosen and (not self.worker or self.worker.set_work(Path(chosen))):
            self.work = Path(chosen)
            self.work_label.set(str(self.work))
            self.status.set('Đã chọn thư mục làm việc. Khóa ký vẫn được giữ trong AppData riêng.')

    def _confirm(self, plan):
        if self.closing or not self.worker:
            return
        if threading.get_ident() != self.main_thread:
            raise RuntimeError('Hộp xác nhận phải chạy trên main thread.')
        backup = plan.get('backup_path') or plan.get('backup', '')
        message = (str(plan.get('summary', '')) + '\n\nBản sao lưu riêng tư: ' + str(backup)
                   + '\n\nGỡ/cài có thể yêu cầu đăng nhập lại. Khóa phần cứng Keystore không được '
                   'bảo đảm khôi phục. Xác nhận chỉ áp dụng cho RC 2 và APK vừa kiểm chứng.')
        approved = messagebox.askokcancel(title='Xác nhận thay chữ ký DJI Fly', message=message,
                                         parent=self.root, icon='warning', default='cancel')
        self.worker.answer_confirmation(plan, approved)

    def poll(self):
        if self.poll_after is not None:
            self.root.after_cancel(self.poll_after)
            self.poll_after = None
        while True:
            try:
                state, message = self.events.get_nowait()
            except queue.Empty:
                break
            if state == 'confirmation':
                self._confirm(message)
                continue
            if state=='disconnected' and self.worker and not self.worker.busy:
                # Release a dead idle WinUSB handle promptly so Windows can
                # enumerate the RC again; active jobs own their own recovery.
                self.worker.request('release')
            if state=='resume_state':
                self.selected=message['serial'];self.selector['values']=(self.selected,);self.selector.set(self.selected)
                self.work=Path(message['work']);self.work_label.set(str(self.work))
                self.grounded.set(True);self.wipe_ack.set(True);self.vietnamese.set(message['translate'])
                continue
            if state=='pending_state':
                self.selected=message['serial'];self.selector['values']=(self.selected,);self.selector.set(self.selected)
                self.work=Path(message['work']);self.work_label.set(str(self.work))
                self.vietnamese.set(message['translate'])
                continue
            if state=='phase':
                names={'capture':'Đọc tay và lấy APK','patch':'Patch và ký','clear':'Xóa dữ liệu Fly',
                       'install':'Cài APK','language':'Bật tiếng Việt','verify':'Kiểm tra kết quả','cleanup':'Dọn tệp tạm'}
                message=names.get(message,message)
            if state == 'devices':
                self.selector['values'] = message
                if not self.selected and len(message) == 1:
                    self.selected = message[0]
                self.selector.set(self.selected)  # Never silently switch a lost selected serial.
                if self.selected and self.selected not in message:
                    self.status.set('RC 2 đã chọn đã ngắt kết nối: ' + self.selected)
                continue
            if state != 'idle' and isinstance(message, str) and message:
                self.status.set(message)
                self.entries = (self.entries + [datetime.now().strftime('%H:%M:%S') + '  ' + message])[-180:]
                self.log.configure(state='normal')
                self.log.delete('1.0', 'end')
                self.log.insert('end', '\n'.join(self.entries))
                self.log.see('end')
                self.log.configure(state='disabled')
        self.refresh_controls()
        if self.closing and (not self.worker or not self.worker.busy):
            self.root.destroy()
            return
        self.poll_after = self.root.after(100, self.poll)

    def cancel(self):
        if self.worker:
            self.worker.cancel()
            self.status.set('Đang Stop; lệnh đã gửi có thể hoàn tất, sau đó không chạy thêm bước mới. Tiến độ đã lưu.')

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.status.set('Đang lưu tiến độ và đóng; tác vụ chưa Stop sẽ tiếp tục lần mở app sau…')
        if self.worker:
            self.worker.close()
        self.refresh_controls()

    def _destroyed(self, event):
        if event.widget is self.root:
            if self.poll_after is not None:
                self.root.after_cancel(self.poll_after)
                self.poll_after = None
            if not self.closing and self.worker:
                self.worker.close()

