"""Device APK acquisition contracts; no live Android mutation or APK execution."""
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rc2vi import hud_device_source as source
from rc2vi.hud_tools import HudCancelled


class Transport:
    def __init__(self, body):
        self.body=body; self.calls=[]; self.cancel=None
    def command(self,*args,**kwargs):
        self.calls.append(args)
        assert args[0]=='pull'
        Path(args[2]).write_bytes(self.body)
        if self.cancel:self.cancel()
        return '1 file pulled'


@pytest.fixture
def setup_source(tmp_path,monkeypatch):
    stock=b'pinned synthetic stock'; mod=b'installed synthetic mod'
    stock_hash=hashlib.sha256(stock).hexdigest()
    monkeypatch.setattr(source,'SUPPORTED_APK',stock_hash)
    monkeypatch.setattr(source,'make_private',lambda *a,**k:None)
    transport=Transport(stock)
    snapshot={'serial':'RC','apk_path':'/data/app/dji.go.v5/base.apk',
              'digest':stock_hash,'uid':10029}
    host=SimpleNamespace(work=tmp_path/'hud',assets=tmp_path/'assets',cancel=None,
        emit=Mock(),_check_cancel=Mock(),_device=Mock(),_installed=Mock(return_value=snapshot),
        _device_sources={},builder=Mock())
    monkeypatch.setattr(source,'PinnedAdb',lambda adb,serial:adb)
    return host,transport,snapshot,stock,mod


def test_stock_is_pulled_from_exact_package_and_hashed_before_use(setup_source):
    host,adb,snapshot,stock,_=setup_source
    result=source.acquire_source(host,adb,'RC')
    assert result.read_bytes()==stock
    assert adb.calls[0][:2]==('pull',snapshot['apk_path'])
    host._device.assert_called_with(adb)
    assert host._installed.call_count==2
    host.builder.verify_device_apk.assert_not_called()
    assert host._device_sources=={}


def test_mod_is_recovered_without_caller_stock_file_and_registered(setup_source,monkeypatch):
    host,adb,snapshot,stock,mod=setup_source
    adb.body=mod; snapshot['digest']=hashlib.sha256(mod).hexdigest()
    recovery=Mock(side_effect=lambda pulled,template,target,cancel=None:(target.write_bytes(stock),target)[1])
    monkeypatch.setattr(source,'recover_stock',recovery)
    host.builder.verify_device_apk.return_value={'digest':snapshot['digest'],'apk':'verified'}
    result=source.acquire_source(host,adb,'RC')
    assert result.read_bytes()==stock
    pulled,template,target=recovery.call_args.args
    assert pulled.read_bytes()==mod and template==host.assets/'hud/source-recovery.zip'
    host.builder.verify_device_apk.assert_called_once_with(pulled,result)
    assert host._device_sources[snapshot['digest']]==(pulled,result)


def test_bad_pull_never_recovers_builds_or_registers(setup_source,monkeypatch):
    host,adb,*_=setup_source; adb.body=b'truncated'
    recovery=Mock();monkeypatch.setattr(source,'recover_stock',recovery)
    with pytest.raises(ValueError,match='SHA'):
        source.acquire_source(host,adb,'RC')
    recovery.assert_not_called();assert host._device_sources=={}
    assert list((host.work/'imports').iterdir())==[]


def test_package_changes_during_pull_rejected(setup_source):
    host,adb,snapshot,*_=setup_source
    host._installed.side_effect=[snapshot,{**snapshot,'uid':10030}]
    with pytest.raises(ValueError,match='thay đổi'):
        source.acquire_source(host,adb,'RC')
    assert host._device_sources=={}


def test_cancellation_after_pull_never_publishes_source(setup_source):
    host,adb,*_=setup_source
    def cancel():host._check_cancel.side_effect=HudCancelled('Canceled')
    adb.cancel=cancel
    with pytest.raises(HudCancelled):source.acquire_source(host,adb,'RC')
    assert host._device_sources=={}


def test_unrecognized_mod_fails_closed(setup_source,monkeypatch):
    host,adb,snapshot,stock,mod=setup_source
    adb.body=mod;snapshot['digest']=hashlib.sha256(mod).hexdigest()
    monkeypatch.setattr(source,'recover_stock',lambda p,t,o,cancel=None:(o.write_bytes(stock),o)[1])
    host.builder.verify_device_apk.side_effect=ValueError('Unknown recipe')
    with pytest.raises(ValueError):source.acquire_source(host,adb,'RC')
    assert host._device_sources=={}


def test_wrong_recovered_source_is_not_used(setup_source,monkeypatch):
    host,adb,snapshot,_,mod=setup_source
    adb.body=mod;snapshot['digest']=hashlib.sha256(mod).hexdigest()
    monkeypatch.setattr(source,'recover_stock',lambda p,t,o,cancel=None:(o.write_bytes(b'wrong'),o)[1])
    with pytest.raises(ValueError,match='gốc'):
        source.acquire_source(host,adb,'RC')
    host.builder.verify_device_apk.assert_not_called();assert host._device_sources=={}


def test_model_or_foreground_guard_failure_prevents_pull(setup_source):
    host,adb,*_=setup_source;host._device.side_effect=ValueError('Unsupported')
    with pytest.raises(ValueError):source.acquire_source(host,adb,'RC')
    assert adb.calls==[]
