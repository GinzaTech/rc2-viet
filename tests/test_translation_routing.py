from unittest.mock import Mock
import pytest

from rc2vi.activation import Activator
from rc2vi.core import SUPPORTED_APK, HUD_APK
from rc2vi.phone_overlay import PhoneOverlay, TARGET_HASH
from test_activation import FakeAdb
from test_phone_overlay import FakePhone


@pytest.mark.parametrize('version,code', [('1.21.8',3115809),('1.20.0',300001),('1.22.5',500012),('9.99.0',9999999)])
@pytest.mark.parametrize('digest', [SUPPORTED_APK,HUD_APK,'A'*64])
def test_every_rc_version_and_hash_routes_to_builder(tmp_path,version,code,digest):
    class Device(FakeAdb):
        def shell(self,command,**kwargs):
            if command=='dumpsys package dji.go.v5':return f'versionName={version} versionCode={code}'
            if command.startswith(('cmd overlay','pm path local.')):
                raise AssertionError('Public routing must not probe legacy overlays')
            return super().shell(command,**kwargs)
    adb=Device(hash_value=digest);adaptive=Mock()
    adaptive.apply.return_value={'status':'enabled','message':'translated'}
    activation=Activator(tmp_path,tmp_path,Mock(),verify_assets=False,adaptive=adaptive)
    assert activation.apply(adb) is adaptive.apply.return_value
    adaptive.apply.assert_called_once()
    args=adaptive.apply.call_args.args
    assert args[:3]==(adb,adb,30)
    assert activation.target_info['digest']==digest.lower()
    args[3]()
    assert not adb.mutations


@pytest.mark.parametrize('version,code', [('1.21.12',3131451),('1.20.0',300001),('2.3.0',6000000)])
@pytest.mark.parametrize('digest', [TARGET_HASH,'B'*64])
def test_every_phone_version_and_hash_routes_to_builder(tmp_path,version,code,digest):
    class Phone(FakePhone):
        def shell(self,command,**kwargs):
            if command=='dumpsys package dji.go.v5':return f'versionName={version} versionCode={code}'
            if 'cmd overlay' in command or 'pm path local.' in command:
                raise AssertionError('Public routing must not probe legacy overlays')
            return super().shell(command,**kwargs)
    phone=Phone(installed=True,enabled=True);phone.target_hash=digest
    adaptive=Mock();adaptive.apply.return_value={'status':'enabled','message':'translated'}
    tool=PhoneOverlay(tmp_path,tmp_path,Mock(),adaptive=adaptive)
    assert tool.apply(phone) is adaptive.apply.return_value
    adaptive.apply.assert_called_once()
    args=adaptive.apply.call_args.args
    assert args[0] is phone and args[1].adb is phone and args[2]==35
    args[3]()
    assert not any(isinstance(c,tuple) for c in phone.calls)


def test_rc_disable_needs_neither_fly_nor_overlay_probe(tmp_path):
    class Device(FakeAdb):
        def shell(self,command,**kwargs):
            if command.startswith(('pm path','dumpsys package','sha256sum','cmd overlay')):
                raise AssertionError('Disable must delegate without Fly or overlay probes')
            return super().shell(command,**kwargs)
    adb=Device();adaptive=Mock();adaptive.disable.return_value={'status':'disabled'}
    activation=Activator(tmp_path,tmp_path,Mock(),verify_assets=False,adaptive=adaptive)
    assert activation.disable(adb) is adaptive.disable.return_value
    adaptive.disable.assert_called_once()
    root,safe=adaptive.disable.call_args.args
    assert root is adb
    safe();adb.flight=True
    with pytest.raises(ValueError):safe()
    assert not adb.mutations


@pytest.mark.parametrize('direct', [True,False])
def test_phone_disable_needs_neither_fly_nor_overlay_probe(tmp_path,direct):
    class Phone(FakePhone):
        def shell(self,command,**kwargs):
            if any(text in command for text in ('pm path','dumpsys package','sha256sum','cmd overlay')):
                raise AssertionError('Disable must delegate without Fly or overlay probes')
            return super().shell(command,**kwargs)
    phone=Phone();adaptive=Mock();adaptive.disable.return_value={'status':'disabled'}
    tool=PhoneOverlay(tmp_path,tmp_path,Mock(),adaptive=adaptive)
    result=tool.disable(phone) if direct else tool.apply(phone,enable=False)
    assert result is adaptive.disable.return_value
    adaptive.disable.assert_called_once()
    root,safe=adaptive.disable.call_args.args
    assert root.adb is phone
    safe();phone.foreground='dji.go.v5/.Camera'
    with pytest.raises(ValueError):safe()


@pytest.mark.parametrize('kind', ['rc','phone'])
def test_default_adaptive_is_lazy_and_preserves_cancel(tmp_path,monkeypatch,kind):
    from rc2vi import translation_install
    factory=Mock();monkeypatch.setattr(translation_install,'AdaptiveTranslation',factory)
    emit=Mock();cancel=object()
    if kind=='rc':
        tool=Activator(tmp_path,tmp_path,emit,verify_assets=False);tool.cancel=cancel;adb=FakeAdb()
    else:
        tool=PhoneOverlay(tmp_path,tmp_path,emit,cancel=cancel);adb=FakePhone()
    factory.assert_not_called()
    tool.apply(adb)
    factory.assert_called_once_with(tmp_path,tmp_path/'adaptive',emit,cancel=cancel)
    factory.return_value.apply.assert_called_once()
    assert tool._adaptive() is factory.return_value
