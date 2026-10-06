from pathlib import Path
import struct
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
    return Activator(assets,tmp_path/'work',lambda *args:None,verify_assets=False)

def test_already_enabled_is_read_only(activator):
    adb=FakeAdb()
    result=activator.apply(adb)
    assert result['status']=='already_enabled'
    assert adb.mutations==[]

@pytest.mark.parametrize('kwargs',[{'hash_value':'0'*64},{'root':False}])
def test_unsupported_target_has_no_mutations(activator,kwargs):
    adb=FakeAdb(**kwargs)
    with pytest.raises(ValueError): activator.apply(adb)
    assert adb.mutations==[]

def test_active_flight_screen_blocks_cache_changes(activator):
    adb=FakeAdb(active=False,flight=True)
    with pytest.raises(ValueError): activator.apply(adb)
    assert adb.mutations==[]

def test_apply_verified_inactive_pack(activator):
    adb=FakeAdb(active=False)
    result=activator.apply(adb)
    assert result['status']=='enabled'
    assert any(isinstance(x,str) and x.startswith('cmd overlay enable') for x in adb.mutations)
    assert not any('uninstall' in str(x) or 'reboot' in str(x) for x in adb.mutations)

def test_failed_readback_disables_pack_and_restores_previous_cache(activator):
    class FailedReadback(FakeAdb):
        def shell(self,cmd,timeout=20):
            if cmd.startswith('cmd overlay lookup'):return 'Connect to Aircraft'
            return super().shell(cmd,timeout)
    adb=FailedReadback(active=False)
    with pytest.raises(RuntimeError,match='Đọc lại'):activator.apply(adb)
    assert any('cmd overlay disable' in str(x) for x in adb.mutations)
    assert any('/previous' in str(x) and 'restorecon' in str(x) for x in adb.mutations)

def test_missing_overlay_is_installed_without_touching_fly(activator):
    class MissingOverlay(FakeAdb):
        installed=False
        def shell(self,cmd,timeout=20):
            if cmd=='pm path local.dji.fly.vietnamese' and not self.installed:return ''
            if cmd.startswith('pm install'):self.installed=True
            return super().shell(cmd,timeout)
    adb=MissingOverlay(active=False)
    assert activator.apply(adb)['status']=='enabled'
    assert adb.installed

def test_disable_has_readback_and_guard(activator):
    class Disabled(FakeAdb):
        def shell(self,cmd,timeout=20):
            if cmd.startswith('cmd overlay disable'):self.active=False
            return super().shell(cmd,timeout)
    assert activator.disable(Disabled())['status']=='disabled'
    with pytest.raises(RuntimeError):activator.disable(FakeAdb())

def test_bundle_integrity_before_any_device_call(tmp_path):
    import hashlib,json
    from rc2vi.activation import verify_bundle
    from rc2vi.core import HOME_APK_HASH,LAWNCHAIR_APK_HASH,FREEFCC_APK_HASH
    assets=tmp_path/'assets';(assets/'adb').mkdir(parents=True)
    names=['adb/adb.exe','adb/AdbWinApi.dll','adb/AdbWinUsbApi.dll','vietnamese-resources.apk','home-bridge.apk','lawnchair.apk','freefcc.apk']
    for name in names:(assets/name).write_bytes(b'tampered')
    manifest={name:hashlib.sha256(b'tampered').hexdigest() for name in names}
    (assets/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):verify_bundle(assets)
    manifest['vietnamese-resources.apk']=OVERLAY_HASH
    manifest['home-bridge.apk']=HOME_APK_HASH
    manifest['lawnchair.apk']=LAWNCHAIR_APK_HASH
    manifest['freefcc.apk']=FREEFCC_APK_HASH
    (assets/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='bị thay đổi'):verify_bundle(assets)
