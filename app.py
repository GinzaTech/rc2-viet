"""Native Windows utility and report-based headless verification entry point."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from rc2vi.activation import Activator, verify_bundle
from rc2vi.controller import Worker
from rc2vi.transport import Connection
from rc2vi.usb_windows import discover
from rc2vi.developer import enable_developer_options

DEVELOPER_WARNING=(
    'KHÔNG TẮT THỦ CÔNG USB debugging (Gỡ lỗi USB) hoặc chế độ nhà phát triển trên RC 2.\n\n'
    'Nếu tắt, app PC có thể mất kết nối và không gửi được lệnh bật lại. '
    'Nếu không thể bật lại trên tay, bạn có thể phải khôi phục cài đặt gốc để khôi phục kết nối.\n\n'
    'Khôi phục cài đặt gốc sẽ xóa toàn bộ dữ liệu người dùng và ứng dụng đã cài trong bộ nhớ trong của tay.\n\n'
    'Nhấn OK để tiếp tục bật/mở chế độ nhà phát triển, hoặc Hủy để quay lại.'
)

def paths():
    base=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
    work=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'RC2Vietnamese'
    work.mkdir(parents=True,exist_ok=True)
    return base/'assets',work


class App:
    def __init__(self,root,assets,work,start_worker=True):
        self.root=root;self.work=work;self.events=queue.Queue();self.entries=[];self.closing=False
        self.last_status=None;self.worker=None;self.thread=None
        root.title('RC2 Việt • Bộ công cụ DJI RC 2');root.geometry('800x690');root.minsize(760,660)
        style=ttk.Style(root);style.theme_use('vista')
        style.configure('.',font=('Segoe UI',10));style.configure('Title.TLabel',font=('Segoe UI',21,'bold'))
        frame=ttk.Frame(root,padding=24);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='RC2 Việt',style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame,text='DJI RC 2 • Tiếng Việt DJI Fly • Lawnchair • FreeFCC').pack(anchor='w',pady=(5,22))
        box=ttk.LabelFrame(frame,text='Tay điều khiển',padding=12);box.pack(fill='x')
        ttk.Label(box,text='Số sê-ri:').pack(side='left')
        self.selector=ttk.Combobox(box,state='readonly',width=29);self.selector.pack(side='left',padx=10)
        self.selector.bind('<<ComboboxSelected>>',lambda e:self.send('select',self.selector.get()))
        ttk.Button(box,text='Kết nối lại',command=lambda:self.send('refresh')).pack(side='right')
        self.auto=tk.BooleanVar(value=True)
        ttk.Checkbutton(frame,text='Tự kiểm tra và bật tiếng Việt khi nhận RC 2',variable=self.auto,
                        command=lambda:self.send('auto',self.auto.get())).pack(anchor='w',pady=(14,12))
        self.status=tk.StringVar(value='Đang khởi tạo…')
        ttk.Label(frame,textvariable=self.status,wraplength=700,font=('Segoe UI',11,'bold')).pack(anchor='w')
        self.progress=ttk.Progressbar(frame,mode='indeterminate');self.progress.pack(fill='x',pady=12)
        buttons=ttk.Frame(frame);buttons.pack(fill='x')
        for title,action in [('Bật / cập nhật tiếng Việt','apply'),('Tắt bản dịch','disable'),('Mở DJI Fly','fly'),('Mở Lawnchair','lawnchair')]:
            ttk.Button(buttons,text=title,command=lambda a=action:self.send(a)).pack(side='left',padx=(0,7))
        device_buttons=ttk.Frame(frame);device_buttons.pack(fill='x',pady=(10,0))
        ttk.Button(device_buttons,text='Cài Lawnchair',command=lambda:self.send('install_lawnchair')).pack(side='left',padx=(0,7))
        ttk.Button(device_buttons,text='Cài FreeFCC',command=lambda:self.send('install_freefcc')).pack(side='left',padx=(0,7))
        ttk.Button(device_buttons,text='Đặt Lawnchair làm màn hình chính',command=lambda:self.send('home')).pack(side='left',padx=(0,7))
        ttk.Button(device_buttons,text='Bật chế độ nhà phát triển',command=self.open_developer_options).pack(side='left')
        ttk.Label(frame,text='Nếu tay hiện Allow USB debugging, chọn Allow. Có thể chọn Always allow from this computer để lưu ghép nối.',
                  wraplength=700).pack(anchor='w',pady=(15,8))
        ttk.Label(frame,text='Về trang chủ trước khi cập nhật. Bản dịch 1.21.8-vi-reviewed5. Công cụ cần quyền root sẵn có trên tay.',wraplength=700).pack(anchor='w')
        logbox=ttk.LabelFrame(frame,text='Tiến trình',padding=8);logbox.pack(fill='both',expand=True,pady=(12,5))
        self.log=tk.Text(logbox,height=5,state='disabled',font=('Segoe UI',9),wrap='word',borderwidth=0)
        self.log.pack(fill='both',expand=True)
        ttk.Button(frame,text='Lưu báo cáo chẩn đoán',command=self.save_report).pack(anchor='e')
        root.protocol('WM_DELETE_WINDOW',self.close)
        if start_worker:
            try:
                activation=Activator(assets,work/'cache',self.emit)
                self.worker=Worker(assets,activation,self.emit)
                self.thread=threading.Thread(target=self.worker.run,daemon=True);self.thread.start()
            except Exception as exc:self.emit('error',str(exc))
        root.after(150,self.poll)

    def emit(self,*event):self.events.put(event)

    def send(self,command,value=None):
        if self.worker and not self.closing:self.worker.request(command,value)

    def open_developer_options(self):
        if not self.closing and messagebox.askokcancel(
                'Cảnh báo kết nối USB trên RC 2',DEVELOPER_WARNING,
                parent=self.root,icon='warning',default='cancel'):
            self.send('developer')

    def poll(self):
        while not self.events.empty():
            state,message=self.events.get_nowait()
            if state=='devices':
                self.selector['values']=message
                if len(message)==1 and not self.selector.get():self.selector.set(message[0])
                if not message:self.selector.set('')
                continue
            if (state,message)==self.last_status:continue
            self.last_status=(state,message);self.status.set(message)
            if state in {'connecting','pairing','checking','applying'}:self.progress.start(12)
            else:self.progress.stop()
            line=datetime.now().strftime('%H:%M:%S')+'  '+message
            self.entries=(self.entries+[line])[-200:]
            self.log.configure(state='normal');self.log.delete('1.0','end');self.log.insert('end','\n'.join(self.entries));self.log.see('end');self.log.configure(state='disabled')
        if self.closing and (not self.thread or not self.thread.is_alive()):self.root.destroy();return
        self.root.after(150,self.poll)

    def save_report(self):
        path=filedialog.asksaveasfilename(title='Lưu báo cáo',defaultextension='.txt',initialfile='RC2-chan-doan.txt')
        if path:
            try:Path(path).write_text('\n'.join(self.entries),encoding='utf-8')
            except OSError:self.emit('error','Không lưu được báo cáo vào vị trí đã chọn.')

    def close(self):
        self.closing=True;self.status.set('Đang đóng kết nối USB…')
        if self.worker:self.worker.close()


def main():
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--verify-once',action='store_true');mode.add_argument('--scan',action='store_true')
    mode.add_argument('--enable-dev-mode',action='store_true')
    parser.add_argument('--report',type=Path);parser.add_argument('--gui-smoke',action='store_true')
    args=parser.parse_args();assets,work=paths()
    if args.scan or args.verify_once or args.enable_dev_mode:
        events=[];report={};connection=None
        try:
            verify_bundle(assets);devices=discover()
            if args.scan:report={'status':'scanned','serials':[d.serial for d in devices]}
            else:
                if len(devices)!=1:raise ValueError('Cần đúng một RC 2 để kiểm chứng không giao diện.')
                emit=lambda state,message:events.append({'state':state,'message':message})
                connection=Connection(devices[0],assets,emit)
                adb=connection.open()
                report=enable_developer_options(adb) if args.enable_dev_mode else Activator(assets,work/'cache',emit).apply(adb)
                report['serial']=devices[0].serial
        except Exception as exc:report={'status':'error','message':str(exc)}
        finally:
            if connection:connection.close()
        report['events']=events
        if args.report:args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if sys.stdout:print(json.dumps(report,ensure_ascii=False))
        return 1 if report['status']=='error' else 0
    root=tk.Tk()
    if args.gui_smoke:root.withdraw()
    app=App(root,assets,work,start_worker=not args.gui_smoke)
    if args.gui_smoke:
        root.update_idletasks();root.destroy();return 0
    root.mainloop();return 0


if __name__=='__main__':sys.exit(main())
