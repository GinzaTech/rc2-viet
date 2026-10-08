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
        self.worker=None;self.phone_worker=None;self.thread=None;self.phone_thread=None;self.mode='rc'
        self.platforms={mode:{'devices':(), 'selected':'', 'status':'Đang chờ kết nối…', 'state':'waiting', 'last':None}
                        for mode in ('phone','rc')}
        from rc2vi.desktop_view import build
        build(self);self.set_mode('rc')
        root.update_idletasks()
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.poll_after=None
        root.bind('<Destroy>',self.on_root_destroyed,add='+')
        if start_worker:
            try:
                from rc2vi.phone import PhoneWorker
                self.phone_worker=PhoneWorker(assets,work/'phone',lambda *e:self.emit_for('phone',*e))
                self.phone_thread=threading.Thread(target=self.phone_worker.run,daemon=True);self.phone_thread.start()
                activation=Activator(assets,work/'cache',self.emit)
                self.worker=Worker(assets,activation,self.emit);self.worker.auto=False
                self.thread=threading.Thread(target=self.worker.run,daemon=True);self.thread.start()
            except Exception as exc:self.emit('error',str(exc))
        self.poll_after=root.after(150,self.poll)

    def emit(self,*event):self.emit_for('rc',*event)
    def emit_for(self,mode,*event):self.events.put((mode,*event))

    def set_mode(self,mode):
        if mode not in self.platforms:raise ValueError('Nền tảng không hợp lệ')
        self.platforms[self.mode]['selected']=self.selector.get()
        self.mode=mode;state=self.platforms[mode]
        for name,button in self.tabs.items():
            button.configure(style='Selected.Tab.TButton' if name==mode else 'Tab.TButton')
        self.phone_actions.pack_forget();self.rc_actions.pack_forget()
        (self.phone_actions if mode=='phone' else self.rc_actions).pack(fill='x')
        self.device_heading.set('Điện thoại' if mode=='phone' else 'Tay RC 2')
        self.selector['values']=state['devices'];self.selector.set(state['selected'])
        self.status.set(state['status']);self.update_progress(state['state'])

    def send(self,command,value=None):
        worker=self.phone_worker if self.mode=='phone' else self.worker
        if worker and not self.closing:worker.request(command,value)

    def open_developer_options(self):
        if self.mode!='rc':return
        if not self.closing and messagebox.askokcancel(
                'Cảnh báo kết nối USB trên RC 2',DEVELOPER_WARNING,
                parent=self.root,icon='warning',default='cancel'):
            self.send('developer')

    def update_progress(self,state):
        self.progress.stop()
        if state in {'connecting','pairing','checking','applying'}:
            self.progress.configure(mode='indeterminate');self.progress.start(12)
        else:self.progress.configure(mode='determinate',value=0)

    def poll(self):
        if self.poll_after is not None:
            self.root.after_cancel(self.poll_after);self.poll_after=None
        while not self.events.empty():
            mode,state,message=self.events.get_nowait();platform=self.platforms[mode]
            if state=='devices':
                platform['devices']=message
                if platform['selected'] and platform['selected'] not in message:
                    platform['status']='Thiết bị đã chọn đã ngắt kết nối.'
                if len(message)==1 and not platform['selected']:platform['selected']=message[0]
                if mode==self.mode:
                    self.selector['values']=message;self.selector.set(platform['selected'])
                continue
            if (state,message)==platform['last']:continue
            platform['last']=(state,message);platform['state']=state;platform['status']=message
            if mode==self.mode:self.status.set(message);self.update_progress(state)
            label='Android' if mode=='phone' else 'RC 2'
            line=datetime.now().strftime('%H:%M:%S')+'  ['+label+']  '+message
            self.entries=(self.entries+[line])[-200:]
            self.log.configure(state='normal');self.log.delete('1.0','end');self.log.insert('end','\n'.join(self.entries));self.log.see('end');self.log.configure(state='disabled')
        if self.closing and all(not t or not t.is_alive() for t in (self.thread,self.phone_thread)):
            self.root.destroy();return
        self.poll_after=self.root.after(150,self.poll)

    def on_root_destroyed(self,event):
        if event.widget is self.root and self.poll_after is not None:
            self.root.after_cancel(self.poll_after);self.poll_after=None

    def save_report(self):
        path=filedialog.asksaveasfilename(title='Lưu báo cáo',defaultextension='.txt',initialfile='RC2-chan-doan.txt')
        if path:
            try:Path(path).write_text('\n'.join(self.entries),encoding='utf-8')
            except OSError:self.emit('error','Không lưu được báo cáo vào vị trí đã chọn.')

    def close(self):
        self.closing=True;self.status.set('Đang đóng kết nối USB…')
        if self.worker:self.worker.close()
        if self.phone_worker:self.phone_worker.close()


def main():
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--verify-once',action='store_true');mode.add_argument('--scan',action='store_true')
    mode.add_argument('--enable-dev-mode',action='store_true')
    mode.add_argument('--phone-inspect',action='store_true')
    mode.add_argument('--phone-verify',action='store_true')
    parser.add_argument('--serial',default='')
    parser.add_argument('--report',type=Path);parser.add_argument('--gui-smoke',action='store_true')
    args=parser.parse_args();assets,work=paths()
    if args.phone_inspect or args.phone_verify:
        from rc2vi.phone import parse_devices,inspect_phone
        from rc2vi.phone_overlay import PhoneOverlay
        from rc2vi.transport import Adb,check_standard_server
        events=[]
        try:
            verify_bundle(assets);check_standard_server()
            devices=parse_devices(Adb(assets/'adb/adb.exe').command('devices','-l'))
            devices=tuple(d for d in devices if d.device.lower()!='rc331' and d.model.lower()!='rc331')
            chosen=next((d for d in devices if d.serial==args.serial),None) if args.serial else (devices[0] if len(devices)==1 else None)
            if not chosen or chosen.state!='device':raise ValueError('Chọn đúng một điện thoại đã cho phép ADB; dùng --serial khi có nhiều thiết bị.')
            adb=Adb(assets/'adb/adb.exe',serial=chosen.serial)
            emit=lambda state,message:events.append({'state':state,'message':message})
            report=PhoneOverlay(assets,work/'phone',emit).apply(adb) if args.phone_verify else inspect_phone(adb)
            report=dict(report,serial=chosen.serial,events=events)
        except Exception as exc:report={'status':'error','message':str(exc),'events':events}
        if args.report:args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if sys.stdout:print(json.dumps(report,ensure_ascii=False))
        return 1 if report['status']=='error' else 0
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
