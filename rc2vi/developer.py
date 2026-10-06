"""Enable and open the RC2's existing Developer options dashboard."""
import shlex

COMPONENT='com.android.settings/com.android.settings.Settings$DevelopmentSettingsDashboardActivity'


def enable_developer_options(adb):
    device=adb.shell('getprop ro.product.device')
    sdk=adb.shell('getprop ro.build.version.sdk')
    identity=adb.shell('id')
    if device!='rc331' or sdk!='30':
        raise ValueError('Thiết bị hoặc Android khác RC 2 đã kiểm chứng; chưa thay đổi cài đặt.')
    if not identity.startswith('uid=0('):
        raise ValueError('Cần quyền root sẵn có trên RC 2 để bật màn hình nhà phát triển.')
    package=adb.shell('cmd package resolve-activity --brief --query-flags 512 -n '+shlex.quote(COMPONENT),timeout=15)
    short='com.android.settings/.Settings$DevelopmentSettingsDashboardActivity'
    if COMPONENT not in package and short not in package:
        raise ValueError('Không tìm thấy màn hình nhà phát triển trong Settings của tay này.')
    adb.shell('settings put global development_settings_enabled 1')
    state=adb.shell('pm enable --user 0 '+shlex.quote(COMPONENT))
    if 'new state: enabled' not in state:
        raise RuntimeError('Chưa xác nhận được màn hình nhà phát triển đã bật.')
    if adb.shell('settings get global development_settings_enabled')!='1':
        raise RuntimeError('Chưa xác nhận được chế độ nhà phát triển đã bật.')
    opened=adb.shell('am start -W -n '+shlex.quote(COMPONENT),timeout=30)
    if 'Status: ok' not in opened:
        raise RuntimeError('Đã bật chế độ nhà phát triển nhưng chưa mở được màn hình Settings.')
    return {'status':'developer_enabled','development_settings_enabled':'1',
            'component':COMPONENT,'dashboard_opened':True}
