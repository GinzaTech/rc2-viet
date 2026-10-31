"""Standard ADB phone discovery. Never send the RC firmware patch to a phone."""
from dataclasses import dataclass
from pathlib import Path
import queue
import re
import subprocess
import threading
from .transport import Adb, check_standard_server


@dataclass(frozen=True)
class PhoneDevice:
    serial: str
    state: str
    model: str = ''
    device: str = ''


def parse_devices(output):
    devices=[]
    for line in output.splitlines():
        match=re.fullmatch(r'([\w.:-]+)\s+(device|offline|unauthorized)(?:\s+(.*))?',line.strip())
        if not match:continue
        fields=dict(re.findall(r'(\w+):([^\s]+)',match[3] or ''))
        devices.append(PhoneDevice(match[1],match[2],fields.get('model',''),fields.get('device','')))
    return tuple(devices)


def inspect_phone(adb):
    model=adb.shell('getprop ro.product.model')
    device=adb.shell('getprop ro.product.device')
    sdk=adb.shell('getprop ro.build.version.sdk')
    if device.lower()=='rc331' or model.lower() in {'rc331','dji rc 2'}:
        raise ValueError('Đây là RC 2. Chọn trang Tay DJI RC 2 để thao tác.')
    paths=adb.shell('pm path dji.go.v5')
    base={'model':model,'device':device,'sdk':sdk}
    if not paths:return dict(base,status='fly_missing',message='Điện thoại chưa cài DJI Fly. Cài bản chính thức từ DJI rồi kiểm tra lại.')
    info=adb.shell('dumpsys package dji.go.v5')
    version=re.search(r'versionName=([^\s]+)',info)
    code=re.search(r'versionCode=(\d+)',info)
    try:root='uid=0(root)' in adb.shell("su -c 'id'",timeout=8)
    except (RuntimeError,TimeoutError,subprocess.TimeoutExpired):root=False
    return dict(base,status='inspected',version=version[1] if version else '',
                version_code=int(code[1]) if code else 0,root=root,paths=paths)


class PhoneWorker:
    def __init__(self,assets:Path,work:Path,emit,adb_factory=Adb,server_check=check_standard_server):
        self.assets=assets;self.work=work;self.emit=emit;self.factory=adb_factory;self.server_check=server_check
        self.commands=queue.Queue();self.stop_event=threading.Event();self.selected='';self.adb=None
        self.last_devices=None;self.last_identity=None

    def request(self,command,value=None):self.commands.put((command,value))
    def close(self):self.stop_event.set()

    def inspect(self):
        result=inspect_phone(self.adb)
        if result['status']=='fly_missing':message=result['message']
        else:
            message=f"{result['model']} · Android SDK {result['sdk']} · DJI Fly {result['version']} · "
            message+=('Có root' if result['root'] else 'Chưa có quyền root cho ADB')
        self.emit('ready',message)
        return result

    def execute(self,command,value):
        if command=='select':self.selected=value;self.adb=None;self.last_identity=None;return
        if command=='refresh':self.adb=None;self.last_identity=None;return
        if not self.adb:raise ValueError('Chọn điện thoại có trạng thái device và cho phép USB debugging.')
        if command=='inspect':self.inspect()
        elif command in {'apply','disable'}:
            from .phone_overlay import PhoneOverlay
            result=PhoneOverlay(self.assets,self.work,self.emit,cancel=self.stop_event).apply(self.adb,enable=command=='apply')
            self.emit('ready',result['message'])
        elif command=='fly':
            result=self.inspect()
            if result['status']=='fly_missing':return
            lines=self.adb.shell('cmd package resolve-activity --brief dji.go.v5').splitlines()
            component=lines[-1] if lines else ''
            if not re.fullmatch(r'dji\.go\.v5/[\w.$]+',component):raise ValueError('Không tìm thấy màn hình mở DJI Fly.')
            self.adb.shell('am start -W -n '+component)
            self.emit('opened','Đã mở DJI Fly trên điện thoại.')
        else:raise ValueError('Chức năng này chỉ dành cho RC 2.')

    def step(self):
        self.server_check()
        devices=parse_devices(self.factory(self.assets/'adb/adb.exe').command('devices','-l'))
        devices=tuple(d for d in devices if d.device.lower()!='rc331' and d.model.lower()!='rc331')
        identity=tuple((d.serial,d.state,d.model) for d in devices)
        if identity!=self.last_devices:
            self.emit('devices',tuple(d.serial for d in devices));self.last_devices=identity
        chosen=next((d for d in devices if d.serial==self.selected),None) if self.selected else (devices[0] if len(devices)==1 else None)
        if not chosen or chosen.state!='device':
            self.adb=None;self.last_identity=None
            state=chosen.state if chosen else ('choose' if len(devices)>1 else 'waiting')
            message={'offline':'Điện thoại đang offline. Kiểm tra cáp và USB debugging.',
                     'unauthorized':'Bấm Allow USB debugging trên điện thoại.',
                     'choose':'Chọn số sê-ri điện thoại để kết nối.',
                     'waiting':'Cắm điện thoại bằng cáp USB và bật USB debugging.'}[state]
            self.emit(state,message)
        else:
            # Pin the sole discovered phone; never switch to another phone
            # automatically after the selected USB cable is disconnected.
            if not self.selected:self.selected=chosen.serial
            self.adb=self.factory(self.assets/'adb/adb.exe',serial=chosen.serial)
            if identity!=self.last_identity:self.inspect();self.last_identity=identity
        while not self.commands.empty():
            command,value=self.commands.get_nowait()
            try:self.execute(command,value)
            except Exception as exc:self.emit('error',str(exc))

    def run(self):
        while not self.stop_event.is_set():
            try:self.step()
            except Exception as exc:self.emit('error',str(exc))
            self.stop_event.wait(3)
