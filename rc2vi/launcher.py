"""Opt-in Home routing for the exact DJI framework inspected on the controller."""
import shlex
from pathlib import Path
import uuid
import hashlib
from .core import validate_package_path,HOME_APK_HASH

SERVICES_HASH='1372cd839fc8f495d4e166bd4f29e08a446ca7fcd4154bfa642174ca4e7352ed'
HOME_VALUE='local.rc2.home_local.rc2.home.HomeActivity'
COMPONENT='local.rc2.home/local.rc2.home.HomeActivity'


def make_lawnchair_home(adb,checks,assets=None):
    checks.verify(adb);checks._safe(adb)
    digest=adb.shell('sha256sum /system/framework/services.jar',timeout=45).split()[0]
    if digest!=SERVICES_HASH:
        raise ValueError('Firmware khác bản đã kiểm chứng; chưa thay đổi màn hình Home.')
    path=adb.shell('pm path app.lawnchair')
    if not path.startswith('package:'):raise ValueError('Cài Lawnchair trước khi đặt làm màn hình chính.')
    validate_package_path(path[8:])
    if adb.shell('getprop persist.dji.sysboot.set_fly_home')!='1':
        raise ValueError('Chế độ Home của firmware khác bản đã kiểm chứng; đã dừng.')
    helper=adb.shell('pm path local.rc2.home')
    if helper:
        helper=validate_package_path(helper[8:])
        if adb.shell('sha256sum '+shlex.quote(helper)).split()[0]!=HOME_APK_HASH:
            raise ValueError('Gói cầu khởi động khác bản đã kiểm chứng; đã dừng.')
    else:
        apk=Path(assets)/'home-bridge.apk'
        if hashlib.sha256(apk.read_bytes()).hexdigest()!=HOME_APK_HASH:
            raise ValueError('Tệp cầu khởi động bị thay đổi.')
        temporary='/data/local/tmp/rc2vi-home-'+uuid.uuid4().hex+'.apk'
        try:
            adb.command('push',str(apk),temporary,timeout=30)
            if 'Success' not in adb.shell('pm install --user 0 '+temporary,timeout=45):
                raise RuntimeError('Chưa cài được cầu khởi động.')
        finally:adb.shell('rm -f '+temporary)
    previous=adb.shell('getprop persist.dji.fw.home')
    output=adb.shell('cmd package set-home-activity --user 0 '+COMPONENT)
    if 'Success' not in output:raise RuntimeError('Android chưa chọn được Lawnchair làm Home.')
    try:
        adb.shell('setprop persist.dji.fw.home '+HOME_VALUE)
        if adb.shell('getprop persist.dji.fw.home')!=HOME_VALUE:
            raise RuntimeError('Firmware chưa lưu đường dẫn Home mới.')
        resolved=adb.shell('cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME')
        if 'local.rc2.home/' not in resolved:
            raise RuntimeError('Lệnh Home vẫn chưa chọn Lawnchair.')
    except Exception:
        adb.shell('setprop persist.dji.fw.home '+shlex.quote(previous));raise
    return {'status':'lawnchair_home','previous_property':previous,'home_property':HOME_VALUE,'uses_direct_boot_bridge':True}
