from unittest.mock import Mock
import pytest

from rc2vi.activation import Activator
from rc2vi.phone_overlay import PhoneOverlay
from test_activation import FakeAdb
from test_phone_overlay import FakePhone


@pytest.mark.parametrize('version,code', [('1.20.0', 300001), ('1.22.5', 500012), ('9.99.0', 9999999)])
def test_every_rc_fly_version_routes_to_resource_builder(tmp_path, version, code):
    class Device(FakeAdb):
        def shell(self, command, **kwargs):
            if command == 'dumpsys package dji.go.v5':
                return f'versionName={version}\nversionCode={code}'
            return super().shell(command, **kwargs)
    adb = Device(hash_value='a' * 64)
    adaptive = Mock()
    adaptive.apply.return_value = {'status': 'enabled', 'message': 'translated'}
    activation = Activator(tmp_path, tmp_path, Mock(), verify_assets=False, adaptive=adaptive)
    assert activation.apply(adb)['message'] == 'translated'
    args = adaptive.apply.call_args.args
    assert args[:3] == (adb, adb, 30)
    args[3]()
    assert not adb.mutations


def test_same_version_different_hash_is_also_adaptive(tmp_path):
    adaptive = Mock()
    adb = FakeAdb(hash_value='c' * 64)
    activation = Activator(tmp_path, tmp_path, Mock(), verify_assets=False, adaptive=adaptive)
    activation.apply(adb)
    adaptive.apply.assert_called_once()


def test_phone_future_fly_version_routes_to_resource_builder(tmp_path):
    class Phone(FakePhone):
        def shell(self, command, **kwargs):
            if command == 'dumpsys package dji.go.v5':
                return 'versionName=2.3.0 versionCode=6000000'
            return super().shell(command, **kwargs)
    phone = Phone()
    phone.target_hash = 'b' * 64
    adaptive = Mock()
    adaptive.apply.return_value = {'status': 'enabled', 'message': 'translated'}
    tool = PhoneOverlay(tmp_path, tmp_path, Mock(), adaptive=adaptive)
    assert tool.apply(phone)['message'] == 'translated'
    args = adaptive.apply.call_args.args
    assert args[0] is phone and args[2] == 35
    args[3]()
    assert not any(isinstance(c, tuple) for c in phone.calls)


def test_rc_can_disable_adaptive_pack_without_reading_fly_apk(tmp_path):
    class Device(FakeAdb):
        def shell(self, command, **kwargs):
            if command.startswith('cmd overlay list'):
                return '[x] local.dji.fly.vi.auto.r' + 'a'*16 + 'c' + 'b'*8 + 's' + 'c'*8
            if command.startswith(('pm path dji.go.v5', 'dumpsys package dji.go.v5', 'sha256sum')):
                raise AssertionError('Disabling resources must not inspect Fly APK')
            return super().shell(command, **kwargs)
    adb = Device()
    adaptive = Mock()
    adaptive.disable.return_value = {'status': 'disabled', 'message': 'disabled'}
    activation = Activator(tmp_path, tmp_path, Mock(), verify_assets=False, adaptive=adaptive)
    assert activation.disable(adb)['status'] == 'disabled'
    adaptive.disable.assert_called_once()


def test_phone_can_disable_adaptive_pack_when_fly_is_missing(tmp_path):
    class Phone(FakePhone):
        def shell(self, command, **kwargs):
            if command == 'pm path dji.go.v5':
                raise AssertionError('Disable must work even when pm path Fly fails')
            if 'cmd overlay list' in command:
                return '[x] local.dji.fly.vi.auto.r' + 'a'*16 + 'c' + 'b'*8 + 's' + 'c'*8 + '\nPHONEVI_OK'
            return super().shell(command, **kwargs)
    adaptive = Mock()
    adaptive.disable.return_value = {'status': 'disabled', 'message': 'disabled'}
    tool = PhoneOverlay(tmp_path, tmp_path, Mock(), adaptive=adaptive)
    assert tool.apply(Phone(), enable=False)['status'] == 'disabled'
    adaptive.disable.assert_called_once()
