"""USB identity and endpoint contracts for composite and adb-only RC firmware."""
from rc2vi.usb_windows import usb_identity, adb_pipes
import pytest


def test_composite_and_adb_only_modes_preserve_serial():
    assert usb_identity('\\\\?\\usb#vid_2ca3&pid_1021&mi_02#x',
                        'USB\\VID_2CA3&PID_1021&MI_02\\X','USB\\VID_2CA3&PID_1021\\SAMPLE')=='SAMPLE'
    assert usb_identity('\\\\?\\usb#vid_18d1&pid_4ee7#SAMPLE',
                        'USB\\VID_18D1&PID_4EE7\\SAMPLE','USB\\ROOT_HUB30\\X')=='SAMPLE'
    assert usb_identity('usb#vid_ffff&pid_0001','USB\\VID_FFFF&PID_0001\\X','') is None


def test_bulk_directions_are_discovered_without_swapping_read_and_write():
    assert adb_pipes([(2,3,512),(2,132,512)])==(3,132)
    assert adb_pipes([(2,1,512),(2,129,512)])==(1,129)
    for pipes in ([(2,1,512)],[(2,1,512),(2,2,512)],[(1,1,512),(2,129,512)],[(2,1,16),(2,129,16)]):
        with pytest.raises(ValueError):adb_pipes(pipes)
