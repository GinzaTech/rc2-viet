"""Shared verified installation of fixed bundled APKs on an authorized RC2."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import shlex
import uuid

from .core import foreground_safe,validate_package_path

@dataclass(frozen=True)
class BundledAPK:
    label: str
    asset_name: str
    package: str
    component: str
    sha256: str
    status_prefix: str


def _package_path(adb,app):
    output=adb.shell('pm path '+shlex.quote(app.package))
    if not output:return None
    lines=output.splitlines()
    if len(lines)!=1 or not lines[0].startswith('package:'):
        raise ValueError('Không đọc được một APK duy nhất của '+app.label+'.')
    return validate_package_path(lines[0][8:])


def _digest(adb,path,label):
    output=adb.shell('sha256sum '+shlex.quote(path),timeout=45).split()
    if not output or not re.fullmatch(r'[0-9a-f]{64}',output[0]):
        raise RuntimeError('Không đọc được mã kiểm tra APK '+label+' trên tay.')
    return output[0]


def _verify_installed(adb,path,app):
    if _digest(adb,path,app.label)!=app.sha256:
        raise ValueError('APK '+app.label+' trên tay khác bản đóng gói; công cụ không ghi đè bản khác.')
    resolved=adb.shell('cmd package resolve-activity --brief -n '+shlex.quote(app.component))
    package,activity=app.component.split('/',1)
    short=package+'/'+activity[len(package):]
    if not {app.component,short}.intersection(resolved.splitlines()):
        raise RuntimeError('Chưa xác nhận được màn hình mở '+app.label+' trên tay.')


def _verify_device(adb,label):
    model=adb.shell('getprop ro.product.model').replace('_',' ').strip()
    device=adb.shell('getprop ro.product.device')
    sdk=adb.shell('getprop ro.build.version.sdk')
    identity=adb.shell('id')
    if model!='DJI RC 2' or device!='rc331' or sdk!='30':
        raise ValueError('Thiết bị hoặc Android khác RC 2 đã kiểm chứng; chưa cài '+label+'.')
    if not identity.startswith('uid=0('):
        raise ValueError('Cần quyền root sẵn có trên RC 2 để cài theo cách đã kiểm chứng.')


def _install(adb,apk,remote,app,emit):
    try:
        emit('applying','Đang gửi APK '+app.label+' sang RC 2…')
        adb.command('push',str(apk),remote,timeout=90)
        if _digest(adb,remote,app.label)!=app.sha256:
            raise ValueError('APK '+app.label+' gửi sang tay không khớp; chưa cài đặt.')
        emit('applying','Đang cài và kiểm tra '+app.label+' trên RC 2…')
        result=adb.shell('pm install --user 0 '+shlex.quote(remote),timeout=90)
        if 'Success' not in result.splitlines():
            raise RuntimeError('Chưa cài được '+app.label+': '+result[:300])
        path=_package_path(adb,app)
        if not path:raise RuntimeError('Chưa tìm thấy '+app.label+' sau khi cài.')
        _verify_installed(adb,path,app)
    finally:
        try:adb.shell('rm -f '+shlex.quote(remote))
        except Exception:
            emit('warning','Chưa xóa được APK '+app.label+' tạm trên tay; kiểm tra lại khi USB kết nối.')


def install_bundled_apk(adb,assets: Path,app: BundledAPK,emit):
    _verify_device(adb,app.label)
    apk=Path(assets)/app.asset_name
    if hashlib.sha256(apk.read_bytes()).hexdigest()!=app.sha256:
        raise ValueError('Tệp '+app.label+' đóng gói bị thay đổi; chưa cài đặt.')
    existing=_package_path(adb,app)
    if existing:
        _verify_installed(adb,existing,app)
        return {'status':app.status_prefix+'_already_installed','component':app.component}
    foreground=adb.shell('dumpsys activity activities | grep mResumedActivity')
    if not foreground or not foreground_safe(foreground):
        raise ValueError('Về trang chủ DJI Fly hoặc Settings trước khi cài '+app.label+', khi không bay.')
    remote='/data/local/tmp/rc2vi-'+app.status_prefix+'-'+uuid.uuid4().hex+'.apk'
    _install(adb,apk,remote,app,emit)
    return {'status':app.status_prefix+'_installed','component':app.component}
