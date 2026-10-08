"""Serial-pinned worker state. All USB operations stay off the GUI thread."""
from pathlib import Path
import queue
import threading
from .transport import Connection
from .usb_windows import discover as discover_usb
from .launcher import make_rc_launcher_home
from .developer import enable_developer_options
from .lawnchair import install_lawnchair
from .freefcc import install_freefcc
from .rc_launcher import install_rc_launcher,RC_LAUNCHER_COMPONENT


def choose_device(devices,selected):
    if selected:
        return next((d for d in devices if d.serial==selected),None)
    return devices[0] if len(devices)==1 else None


class Worker:
    def __init__(self,assets: Path,activator,emit,discover=discover_usb,connection_factory=Connection):
        self.assets=assets;self.activator=activator;self.emit=emit
        self.discover=discover;self.factory=connection_factory
        self.connection=None;self.adb=None;self.selected='';self.auto=True;self.handled=False
        self.commands=queue.Queue();self.stop_event=threading.Event();self.last_devices=None

    def request(self,command,value=None):
        self.commands.put((command,value))

    def close(self):
        self.stop_event.set()
        if self.connection and getattr(self.connection,'relay',None):
            self.connection.relay.stop_event.set()

    def _release(self):
        if self.connection:self.connection.close()
        self.connection=None;self.adb=None;self.handled=False

    def _result(self,result):
        labels={'already_enabled':'Tiếng Việt đã bật và đọc lại thành công.',
                'enabled':'Đã bật bản tiếng Việt đã chỉnh sửa.',
                'disabled':'Đã tắt bản dịch. Mở lại DJI Fly để xem thay đổi.',
                'lawnchair_installed':'Đã cài và kiểm tra Lawnchair. Bấm Mở Lawnchair để dùng.',
                'lawnchair_already_installed':'Lawnchair đã được cài đúng bản. Bấm Mở Lawnchair để dùng.',
                'freefcc_installed':'Đã cài và kiểm tra FreeFCC. Mở từ danh sách ứng dụng trên tay.',
                'freefcc_already_installed':'FreeFCC đã được cài đúng bản. Mở từ danh sách ứng dụng trên tay.',
                'rc_launcher_installed':'Đã cài RC Launcher gọn nhẹ. Bấm Mở RC Launcher để dùng.',
                'rc_launcher_already_installed':'RC Launcher mới đã cài đúng bản. Bấm Mở RC Launcher để dùng.'}
        self.emit('ready',labels[result['status']])

    def _command(self,command,value):
        if command=='select':
            if value!=self.selected:self._release()
            self.selected=value;return
        if command=='auto':self.auto=bool(value);return
        if command=='refresh':self._release();return
        if not self.adb:
            self.emit('error','Chưa kết nối RC 2.');return
        if command=='apply':
            self._result(self.activator.apply(self.adb));self.handled=True
        elif command=='disable':
            self._result(self.activator.disable(self.adb));self.handled=True
        elif command in {'fly','lawnchair','rc_launcher'}:
            component={'fly':'dji.go.v5/com.dji.component.application.activity.DJIPureLaunchActivity',
                       'lawnchair':'app.lawnchair/app.lawnchair.LawnchairLauncher',
                       'rc_launcher':RC_LAUNCHER_COMPONENT}[command]
            self.adb.shell('input keyevent 224')
            self.adb.shell('am start -n '+component)
            self.emit('opened','Đã gửi lệnh mở '+{'fly':'DJI Fly','lawnchair':'Lawnchair','rc_launcher':'RC Launcher'}[command]+'.')
        elif command=='home':
            make_rc_launcher_home(self.adb,self.activator,self.assets)
            self.emit('ready','Đã đặt RC Launcher mới làm màn hình chính của RC 2.')
        elif command=='developer':
            self.emit('applying','Đang bật chế độ nhà phát triển…')
            enable_developer_options(self.adb)
            self.emit('ready','Đã bật chế độ nhà phát triển và mở Developer options trên RC 2.')
        elif command=='install_lawnchair':
            self.emit('applying','Đang kiểm tra trước khi cài Lawnchair…')
            self._result(install_lawnchair(self.adb,self.assets,self.emit))
        elif command=='install_freefcc':
            self.emit('applying','Đang kiểm tra trước khi cài FreeFCC…')
            self._result(install_freefcc(self.adb,self.assets,self.emit))
        elif command=='install_rc_launcher':
            self.emit('applying','Đang kiểm tra RC Launcher trước khi cài…')
            self._result(install_rc_launcher(self.adb,self.assets,self.emit))

    def step(self):
        devices=self.discover()
        serials=tuple(d.serial for d in devices)
        if serials!=self.last_devices:
            self.emit('devices',serials);self.last_devices=serials
        device=choose_device(devices,self.selected)
        if self.connection and (not device or device!=self.connection.device or not self.connection.alive()):
            self._release()
        while not self.commands.empty():
            self._command(*self.commands.get_nowait())
        if self.stop_event.is_set():return
        device=choose_device(devices,self.selected)
        if not device:
            self.emit('choose' if len(devices)>1 else 'waiting',
                      'Chọn số sê-ri RC 2 để kết nối.' if len(devices)>1 else 'Cắm RC 2 bằng cáp USB và bật nguồn.');return
        if not self.connection:
            self.emit('connecting','Đang kết nối RC 2 '+device.serial+'…')
            self.connection=self.factory(device,self.assets,self.emit)
            self.adb=self.connection.open()
        if self.stop_event.is_set():return
        if self.auto and not self.handled:
            # Mark attempted before running: errors wait for explicit Retry.
            self.handled=True
            self._result(self.activator.apply(self.adb))

    def run(self):
        try:
            while not self.stop_event.is_set():
                try:self.step()
                except Exception as exc:
                    self.emit('error',str(exc))
                    if self.connection and not self.connection.alive():self._release()
                self.stop_event.wait(2)
        finally:self._release()
