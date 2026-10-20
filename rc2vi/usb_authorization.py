"""Request ordinary ADB authorization and read back the selected RC2 identity.

This entry point performs no device changes. It owns one Connection; that
connection owns its USB lease and any pending-authorization retries.
"""
from pathlib import Path
import re

from .core import validate_rc_device
from .transport import Connection
from .usb_windows import discover


def _check_cancel(cancel):
    if cancel is not None and (cancel.is_set() if hasattr(cancel, 'is_set') else cancel()):
        raise InterruptedError('Đã dừng xin quyền kết nối USB.')


def authorize_usb(assets, serial, *, emit=None, cancel=None, reconnect_event=None,
                  connection_factory=Connection, discover_fn=discover):
    """Wait for Allow on exactly the selected RC2, verify identity, then close.

    Grounded consent is unnecessary for this authorization-only operation:
    every shell command is an identity read. Manual requests are separate from
    cancellation and are consumed only inside Connection's opening handshake.
    """
    if not isinstance(serial, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', serial):
        raise ValueError('Chọn một serial RC 2 hợp lệ trước khi xin quyền USB.')
    _check_cancel(cancel)
    matches = [device for device in discover_fn() if device.serial == serial]
    if len(matches) != 1:
        raise ValueError('Cần đúng một thiết bị USB khớp serial RC 2 đã chọn.')
    _check_cancel(cancel)
    emit = emit or (lambda *_args: None)
    connection = connection_factory(matches[0], Path(assets), emit)
    try:
        connection._opening_cancel = cancel
        connection._opening_reconnect_event = reconnect_event
        _check_cancel(cancel)
        adb = connection.open()
        _check_cancel(cancel)

        def read(command):
            _check_cancel(cancel)
            value = adb.shell(command, timeout=15)
            _check_cancel(cancel)
            if not isinstance(value, str):
                raise ValueError('Không đọc được danh tính RC 2 qua ADB.')
            return value.strip()

        if read('getprop ro.serialno') != serial:
            raise ValueError('Serial ADB không khớp đúng tay RC 2 đã chọn.')
        model = read('getprop ro.product.model')
        device = read('getprop ro.product.device')
        identity = read('id')
        validate_rc_device(model, device, identity)
        if read('getprop ro.build.version.sdk') != '30':
            raise ValueError('Kết nối này chỉ hỗ trợ DJI RC 2 chạy Android 11 đã kiểm chứng.')
        _check_cancel(cancel)
        emit('identity', 'Đã xác minh đúng serial, DJI RC 2, Android 11 và quyền shell; không thay đổi thiết bị.')
        return {'status': 'authorized', 'authorized_verified': True,
                'device_modified': False, 'serial': serial}
    finally:
        connection.close()
