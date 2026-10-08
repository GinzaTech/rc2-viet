"""Opt-in Home routing for the exact DJI framework inspected on the controller."""
import shlex
from pathlib import Path
import uuid
import hashlib
from .core import validate_package_path,HOME_APK_HASH,PREVIOUS_HOME_APK_HASH,PREVIOUS_HOME_V2_HASH

SERVICES_HASH='1372cd839fc8f495d4e166bd4f29e08a446ca7fcd4154bfa642174ca4e7352ed'
HOME_VALUE='local.rc2.home_local.rc2.home.HomeActivity'
COMPONENT='local.rc2.home/local.rc2.home.HomeActivity'

def _install_bridge(adb,assets,upgrade):
    apk=Path(assets)/'home-bridge.apk'
    if hashlib.sha256(apk.read_bytes()).hexdigest()!=HOME_APK_HASH:
        raise ValueError('Tệp cầu khởi động bị thay đổi.')
    temporary='/data/local/tmp/rc2vi-home-'+uuid.uuid4().hex+'.apk'
    try:
        adb.command('push',str(apk),temporary,timeout=30)
        command='pm install '+('-r ' if upgrade else '')+'--user 0 '+temporary
        if 'Success' not in adb.shell(command,timeout=45).splitlines():
            raise RuntimeError('Chưa cài được cầu khởi động.')
        output=adb.shell('pm path local.rc2.home')
        if not output.startswith('package:') or len(output.splitlines())!=1:
            raise RuntimeError('Chưa đọc lại được cầu khởi động đã cài.')
        installed=validate_package_path(output[8:])
        if adb.shell('sha256sum '+shlex.quote(installed)).split()[0]!=HOME_APK_HASH:
            raise RuntimeError('APK cầu khởi động đã cài không khớp bản đóng gói.')
    finally:adb.shell('rm -f '+temporary)


def make_rc_launcher_home(adb,checks,assets=None):
    checks.verify(adb);checks._safe(adb)
    digest=adb.shell('sha256sum /system/framework/services.jar',timeout=45).split()[0]
    if digest!=SERVICES_HASH:
        raise ValueError('Firmware khác bản đã kiểm chứng; chưa thay đổi màn hình Home.')
    path=adb.shell('pm path dev.rclauncher.rc2.debug')
    if not path.startswith('package:'):raise ValueError('Cài RC Launcher trước khi đặt làm màn hình chính.')
    target=validate_package_path(path[8:])
    from .rc_launcher import RC_LAUNCHER_HASH
    if adb.shell("sha256sum "+shlex.quote(target)).split()[0]!=RC_LAUNCHER_HASH:
        raise ValueError("RC Launcher khác bản đã kiểm chứng; chưa đổi Home.")
    if adb.shell('getprop persist.dji.sysboot.set_fly_home')!='1':
        raise ValueError('Chế độ Home của firmware khác bản đã kiểm chứng; đã dừng.')
    helper=adb.shell('pm path local.rc2.home')
    if helper:
        helper=validate_package_path(helper[8:])
        helper_hash=adb.shell('sha256sum '+shlex.quote(helper)).split()[0]
        if helper_hash not in {HOME_APK_HASH,PREVIOUS_HOME_APK_HASH,PREVIOUS_HOME_V2_HASH}:
            raise ValueError('Gói cầu khởi động khác bản đã kiểm chứng; đã dừng.')
        if helper_hash!=HOME_APK_HASH:_install_bridge(adb,assets,upgrade=True)
    else:
        _install_bridge(adb,assets,upgrade=False)
    previous=adb.shell('getprop persist.dji.fw.home')
    output=adb.shell('cmd package set-home-activity --user 0 '+COMPONENT)
    if 'Success' not in output:raise RuntimeError('Android chưa chọn được RC Launcher làm Home.')
    try:
        adb.shell('setprop persist.dji.fw.home '+HOME_VALUE)
        if adb.shell('getprop persist.dji.fw.home')!=HOME_VALUE:
            raise RuntimeError('Firmware chưa lưu đường dẫn Home mới.')
        resolved=adb.shell('cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME')
        if 'local.rc2.home/' not in resolved:
            raise RuntimeError('Lệnh Home vẫn chưa chọn RC Launcher.')
    except Exception:
        adb.shell('setprop persist.dji.fw.home '+shlex.quote(previous));raise
    return {'status':'rc_launcher_home','previous_property':previous,'home_property':HOME_VALUE,'uses_direct_boot_bridge':True}
