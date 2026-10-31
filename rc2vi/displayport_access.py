"""Grant only this Fly UID access to the HPD request node for the current boot."""
import re

HPD = '/sys/kernel/debug/drm_dp/hpd'
# Filled from byte-verified release builds; activation does not trust a version label.
APPROVED_APKS = {
    '1436b7bc9cd43befb7c3f282d9dd2a1398b3c83e856306dccd49a3e0047a3ab7',
    '42f1ae6f7f7b1b08aed3c7e9fdaa6ef552b3a9f301b19df347658e1f6b629664',
    'c2a51eb830a030682e90e56c776c20558cff437e627d4c6f29e405718c7560e9',
    'd59e2d7894f3d3f4aefec4eb003de034b64e717b007cb106f2870347b59d3861',
    '62ed6b3d37a8a172180faf663c1840426b052370fcefd640d10b81f1ba4c0825',
    '4e0131575f7411caba3c2b28f3d345e4ecb24c393e2b78eaae04191163d4d987',
}


def permission_command(uid):
    if not isinstance(uid, int) or isinstance(uid, bool) or not 10000 <= uid < 20000:
        raise ValueError('Unexpected Fly application UID')
    return (f'[ -f {HPD} ] && [ ! -L {HPD} ] && '
            f'[ "$(stat -c %u {HPD})" = 0 ] && '
            f'chgrp {uid} {HPD} && chmod 660 {HPD} && '
            f'[ "$(stat -c %u:%g:%a {HPD})" = 0:{uid}:660 ]')


def enable_session(deployment, expected_digest):
    snapshot = deployment.snapshot()
    if not snapshot or snapshot['digest'] != expected_digest:
        raise ValueError('APK changed before granting DisplayPort permission')
    identity = deployment.shell('cmd package list packages -U dji.go.v5', mutating=False)
    match = re.fullmatch(r'package:dji\.go\.v5 uid:(\d+)', identity.strip())
    if not match:
        raise ValueError('Cannot identify the installed Fly UID')
    uid = int(match.group(1))
    deployment.shell(permission_command(uid))
    return {'status': 'enabled_for_current_boot', 'uid': uid, 'node': HPD,
            'mode': '0660', 'reboot_requires_reactivation': True, 'physical_output_verified': False}


def activate_existing(assets, work, serial, grounded, emit, cancel=None, reconnect_event=None):
    if not grounded:
        raise ValueError('Xác nhận đã hạ cánh, động cơ dừng trước khi kích hoạt.')
    from .embedded_install import Deployment
    class Observed(Deployment):
        def emit(self, state, message):
            super().emit(state, message)
            emit(state, message)
    job = Observed(None, assets, work, serial, connect_only=True, cancel=cancel,
                   reconnect_event=reconnect_event)
    try:
        snapshot = job.retry(job.snapshot, 'identify_displayport_app')
        if not snapshot or snapshot['digest'] not in APPROVED_APKS:
            raise ValueError('Cần cài bản có nút Ép xuất đã kiểm chứng trước khi kích hoạt.')
        foreground = job.root.shell('dumpsys activity activities | grep mResumedActivity')
        if 'dji.go.v5/' in foreground:
            if 'dji.go.v5/com.dji.mainpageui.device.DJIDeviceActivity' not in foreground:
                raise ValueError('Về trang chủ Fly hoặc Settings trước khi kích hoạt nút xuất hình.')
            job.shell('am start -a android.settings.SETTINGS', mutating=False)
        result = enable_session(job, snapshot['digest'])
        job.status['displayport_permission'] = result
        job.save()
        emit('installed', 'Đã kích hoạt nút Ép xuất cho phiên bật tay hiện tại. Có thể rút PC và nối màn.')
        return result
    finally:
        job.close()
