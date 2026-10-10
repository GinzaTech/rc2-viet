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
from .hud_tools import check_cancel


def choose_device(devices,selected):
    if selected:
        return next((d for d in devices if d.serial==selected),None)
    return devices[0] if len(devices)==1 else None


class Worker:
    def __init__(self,assets: Path,activator,emit,discover=discover_usb,connection_factory=Connection,
                 hud_builder=None,hud_installer=None,stop_event=None):
        self.assets=assets;self.activator=activator;self.emit=emit
        self.discover=discover;self.factory=connection_factory
        self.connection=None;self.adb=None;self.selected='';self.auto=True;self.handled=False
        self.commands=queue.Queue();self.stop_event=stop_event or threading.Event();self.last_devices=None
        self.hud_builder=hud_builder;self.hud_installer=hud_installer

    def request(self,command,value=None):
        self.commands.put((command,value))

    def close(self):
        self.stop_event.set()
        safe=not self.hud_installer or self.hud_installer.cancel_for_close()
        if safe and self.connection and getattr(self.connection,'relay',None):
            self.connection.relay.stop_event.set()

    def _cleanup_hud(self):
        if self.hud_installer and hasattr(self.hud_installer,'cleanup_pending'):
            serial=self.connection.device.serial if self.connection else None
            self.hud_installer.cleanup_pending(self.adb,serial)

    def _release(self):
        if self.hud_installer:self.hud_installer.cancel_pending()
        try:self._cleanup_hud()
        except Exception:
            self.emit('warning','Chưa dọn được tệp HUD tạm; giữ báo cáo khôi phục để kiểm tra lại.')
        finally:
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

    def _hud_result(self,result):
        if result['status']=='hud_confirmation_required':self.emit('hud_confirm',result)
        elif result['status']=='hud_built':self.emit('hud_built',result)
        elif result['status']=='hud_recovery_required':
            self.emit('error','Chưa xác nhận được khôi phục DJI Fly. Kết nối lại tay và giữ bản sao lưu: '
                      +str(result.get('recovery_report','')))
        elif result['status']=='hud_rolled_back':
            self.emit('warning','Cài HUD không thành công; đã khôi phục APK và tệp dữ liệu trước đó. '
                      'Phiên đăng nhập/Keystore có thể cần kiểm tra lại.')
        elif result['status']=='hud_installed':self.emit('ready','APK HUD đã cài và kiểm tra trên RC 2.')
        elif result['status']=='hud_already_installed':self.emit('ready','RC 2 đã có đúng APK HUD vừa tạo.')
        else:raise ValueError('Trạng thái quy trình HUD không hợp lệ.')

    def _patch_hud_menu(self,source: Path | None=None):
        """Build and prepare the new receipt only on the original connection."""
        check_cancel(self.stop_event)
        connection,adb,selected=self.connection,self.adb,self.selected
        if not adb or not connection or not connection.alive():
            self.emit('error','Chưa kết nối RC 2.');return
        if not self.hud_builder:
            self.emit('error','Chưa có công cụ tạo APK HUD.');return
        if not self.hud_installer:
            self.emit('error','Chưa có công cụ cài APK HUD.');return
        serial=connection.device.serial
        if selected and selected!=serial:
            self.emit('error','RC 2 đã chọn khác thiết bị đang kết nối.');return
        def unchanged():
            return (self.connection is connection and self.adb is adb and self.selected==selected
                    and connection.device.serial==serial and connection.alive())
        if source is None:
            self.emit('applying','Đang kiểm tra và lấy DJI Fly từ RC 2…')
            source=self.hud_installer.pull_source(adb,serial)
            check_cancel(self.stop_event)
            if not unchanged():
                self.emit('error','Kết nối hoặc RC 2 đã chọn thay đổi trong khi lấy APK.');return
        self.emit('applying','Đang tạo và ký APK HUD từ APK Fly gốc…')
        result=self.hud_builder.build(Path(source))
        check_cancel(self.stop_event)
        if not isinstance(result,dict) or result.get('status')!='hud_built' or not result.get('receipt'):
            raise ValueError('Chưa có receipt APK HUD vừa tạo; không bắt đầu cài đặt.')
        self._hud_result(result)
        self.emit('applying','Đang kiểm tra RC 2 trước khi cài APK HUD vừa tạo…')
        check_cancel(self.stop_event)
        if not unchanged():
            self.emit('error','Kết nối hoặc RC 2 đã chọn thay đổi trong khi tạo APK HUD.');return
        self._hud_result(self.hud_installer.prepare(adb,serial,result['receipt']))
        self.handled=True

    def _command(self,command,value):
        if command=='select':
            if value!=self.selected:self._release()
            self.selected=value;return
        if command=='auto':self.auto=bool(value);return
        if command=='refresh':self._release();return
        if command=='hud_cancel':
            if self.hud_installer:self.hud_installer.cancel_pending()
            self._cleanup_hud()
            self.emit('ready','Đã hủy thay APK DJI Fly; giữ bản hiện có.');return
        if command=='hud_build':
            if not self.hud_builder:self.emit('error','Chưa có công cụ tạo APK HUD.');return
            self._hud_result(self.hud_builder.build(Path(value)));return
        if command=='hud_patch_menu':
            self._patch_hud_menu(value);return
        if not self.adb:
            self.emit('error','Chưa kết nối RC 2.');return
        if command in {'hud_install','hud_approve'}:
            if not self.hud_installer:self.emit('error','Chưa có công cụ cài APK HUD.');return
            serial=self.connection.device.serial
            if command=='hud_approve':
                if not isinstance(value,dict) or value.get('serial')!=serial:
                    self.emit('error','RC 2 đã chọn khác thiết bị được xác nhận.');return
                result=self.hud_installer.approve(self.adb,serial,value.get('token',''))
            else:result=self.hud_installer.prepare(self.adb,serial)
            self._hud_result(result);self.handled=True;return
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
