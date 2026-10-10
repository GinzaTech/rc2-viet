from pathlib import Path
import struct
import hashlib
import json
from unittest.mock import Mock
from rc2vi import activation as module
import pytest
from rc2vi.activation import Activator
from rc2vi.core import SUPPORTED_APK,OVERLAY_HASH

class FakeAdb:
    def __init__(self,active=True,hash_value=SUPPORTED_APK,root=True,flight=False):
        self.active=active; self.hash_value=hash_value; self.root=root; self.flight=flight; self.mutations=[]
        self.target='/data/app/dji.go.v5-abc/base.apk'
        self.overlay='/data/app/local.dji.fly.vietnamese-abc/base.apk'

    def shell(self,cmd,timeout=20):
        if cmd=='getprop ro.product.model': return 'DJI RC 2'
        if cmd=='getprop ro.product.device': return 'rc331'
        if cmd=='getprop ro.build.version.sdk': return '30'
        if cmd=='id': return 'uid=0(root)' if self.root else 'uid=2000(shell)'
        if cmd.startswith('dumpsys package dji.go.v5'): return 'versionCode=3115809 minSdk=24\nversionName=1.21.8'
        if cmd=='pm path dji.go.v5': return 'package:'+self.target
        if cmd=='pm path local.dji.fly.vietnamese': return 'package:'+self.overlay
        if cmd.startswith('sha256sum'):
            return (OVERLAY_HASH if self.overlay in cmd else self.hash_value)+'  '+self.target
        if cmd.startswith('cmd overlay dump'): return 'STATE_ENABLED' if self.active else 'STATE_NO_IDMAP'
        if cmd.startswith('cmd overlay list'): return ''
        if cmd.startswith('cmd overlay lookup'): return 'Kết nối máy bay' if self.active else 'Connect to Aircraft'
        if cmd.startswith('dumpsys activity'): return 'dji.go.v5/com.dji.fpv.DJIFpvActivity' if self.flight else 'dji.go.v5/com.dji.mainpageui.device.DJIDeviceActivity'
        self.mutations.append(cmd)
        if cmd.startswith('cmd overlay enable'): self.active=True
        if cmd.startswith('pm install'): return 'Success\nRC2VI_OK'
        return 'RC2VI_OK' if cmd.endswith(' && echo RC2VI_OK') else ''

    def command(self,*args,timeout=20,check=True):
        self.mutations.append(args)
        if args[0]=='pull':
            data=struct.pack('<5IB',0x504d4449,4,1,2,1,0)+self.target.encode().ljust(256,b'\0')+self.overlay.encode().ljust(256,b'\0')+b'\0'*4
            Path(args[-1]).write_bytes(data)
        return ''

@pytest.fixture
def activator(tmp_path):
    assets=tmp_path/'assets'; assets.mkdir()
    adaptive=Mock()
    adaptive.apply.return_value={'status':'enabled'}
    adaptive.disable.return_value={'status':'disabled'}
    return Activator(assets,tmp_path/'work',Mock(),verify_assets=False,adaptive=adaptive)


@pytest.mark.parametrize('active', [True, False])
def test_known_rc_always_delegates_without_prepared_pack(activator, active):
    adb=FakeAdb(active=active)
    assert not (activator.assets/'vietnamese-resources.apk').exists()
    assert activator.apply(adb) is activator.adaptive.apply.return_value
    args=activator.adaptive.apply.call_args.args
    assert args[:3]==(adb,adb,30)
    args[3]()
    adb.flight=True
    with pytest.raises(ValueError):args[3]()
    assert not adb.mutations


@pytest.mark.parametrize('command,response', [
    ('getprop ro.product.model','Phone'),
    ('getprop ro.product.device','wrong'),
    ('getprop ro.build.version.sdk','35'),
    ('id','uid=2000(shell)'),
    ('dumpsys package dji.go.v5','versionName=2.0 versionCode=0'),
    ('dumpsys package dji.go.v5','versionCode=3'),
    ('dumpsys package dji.go.v5','versionName=2.0'),
    ('pm path dji.go.v5',''),
    ('pm path dji.go.v5','package:/data/app/base.apk\npackage:/data/app/split.apk'),
    ('pm path dji.go.v5','package:/data/app/../../bad.apk'),
    ('sha256sum',''),
    ('sha256sum','invalid file'),
    ('dumpsys activity',''),
    ('dumpsys activity','dji.go.v5/com.dji.fpv.DJIFpvActivity'),
])
def test_rc_guards_block_adaptive_and_writes(activator, command, response):
    class Device(FakeAdb):
        def shell(self, cmd, **kwargs):
            return response if cmd.startswith(command) else super().shell(cmd, **kwargs)
    adb=Device()
    with pytest.raises(ValueError):activator.apply(adb)
    activator.adaptive.apply.assert_not_called()
    assert not adb.mutations


@pytest.mark.parametrize('command,response', [
    ('getprop ro.product.model','Phone'), ('getprop ro.product.device','wrong'),
    ('getprop ro.build.version.sdk','35'), ('id','uid=2000(shell)'),
    ('dumpsys activity',''), ('dumpsys activity','dji.go.v5/.Camera'),
])
def test_rc_disable_keeps_identity_and_foreground_guards(activator, command, response):
    class Device(FakeAdb):
        def shell(self, cmd, **kwargs):
            return response if cmd.startswith(command) else super().shell(cmd, **kwargs)
    adb=Device()
    with pytest.raises(ValueError):activator.disable(adb)
    activator.adaptive.disable.assert_not_called()
    assert not adb.mutations


def test_optional_package_path_remains_available_for_launchers(activator):
    adb=Mock();adb.shell.return_value=''
    assert activator._path(adb,'launcher',required=False) is None
    with pytest.raises(ValueError):activator._path(adb,'launcher')
    adb.shell.return_value='package:/data/app/launcher/base.apk'
    assert activator._path(adb,'launcher')=='/data/app/launcher/base.apk'


BUNDLE_FILES=('adb/adb.exe','adb/AdbWinApi.dll','adb/AdbWinUsbApi.dll',
              'home-bridge.apk','lawnchair.apk','freefcc.apk')


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    assets=tmp_path/'assets';(assets/'adb').mkdir(parents=True)
    manifest={}
    for name in BUNDLE_FILES:
        payload=name.encode();(assets/name).write_bytes(payload)
        manifest[name]=hashlib.sha256(payload).hexdigest()
    for name,constant in [('home-bridge.apk','HOME_APK_HASH'),
                          ('lawnchair.apk','LAWNCHAIR_APK_HASH'),('freefcc.apk','FREEFCC_APK_HASH')]:
        monkeypatch.setattr(module,constant,manifest[name])
    (assets/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    return assets,manifest


@pytest.mark.parametrize('legacy_row', [False, True])
def test_bundle_does_not_require_or_read_legacy_pack(bundle, legacy_row):
    assets,manifest=bundle
    if legacy_row:
        manifest={**manifest,'vietnamese-resources.apk':'ignored obsolete hash'}
        (assets/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    module.verify_bundle(assets)
    # A directory at the old APK path makes accidental reads fail.
    (assets/'vietnamese-resources.apk').mkdir()
    Activator(assets,assets/'work',Mock())


@pytest.mark.parametrize('name', BUNDLE_FILES)
def test_bundle_still_rejects_each_tampered_required_file(bundle,name):
    assets,_=bundle
    (assets/name).write_bytes(b'tampered')
    with pytest.raises(ValueError,match='bị thay đổi'):module.verify_bundle(assets)


@pytest.mark.parametrize('name', BUNDLE_FILES)
def test_bundle_still_requires_each_manifest_entry(bundle,name):
    assets,manifest=bundle
    manifest={key:value for key,value in manifest.items() if key!=name}
    (assets/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(ValueError,match='Danh sách'):module.verify_bundle(assets)


@pytest.mark.parametrize('name', ['home-bridge.apk','lawnchair.apk','freefcc.apk'])
def test_bundle_pins_required_apks_even_if_manifest_matches_tampering(bundle,name):
    assets,manifest=bundle
    (assets/name).write_bytes(b'tampered')
    manifest={**manifest,name:hashlib.sha256(b'tampered').hexdigest()}
    (assets/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(ValueError,match='Danh sách'):module.verify_bundle(assets)


def test_bundle_rejects_unexpected_manifest_path(bundle):
    assets,manifest=bundle
    (assets/'manifest.json').write_text(json.dumps({**manifest,'../unexpected.exe':'ignored'}),encoding='utf-8')
    with pytest.raises(ValueError,match='Danh sách'):module.verify_bundle(assets)
