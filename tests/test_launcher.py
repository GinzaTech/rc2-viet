import pytest
from pathlib import Path
from rc2vi.launcher import make_lawnchair_home,SERVICES_HASH,HOME_VALUE
from rc2vi.core import HOME_APK_HASH

class Checks:
    def verify(self,adb):return 'verified'
    def _safe(self,adb):
        if adb.flight:raise ValueError('camera')

class Fake:
    def __init__(self,wrong_hash=False,flight=False,failed=False):
        self.wrong_hash=wrong_hash;self.flight=flight;self.failed=failed;self.property='';self.mutations=[]
    def shell(self,command,timeout=20):
        if command.startswith('sha256sum'):
            return ('0'*64 if self.wrong_hash else HOME_APK_HASH if 'local.rc2.home-' in command else SERVICES_HASH)+' file'
        if command=='pm path app.lawnchair':return 'package:/data/app/app.lawnchair-abc/base.apk'
        if command=='pm path local.rc2.home':return 'package:/data/app/local.rc2.home-abc/base.apk'
        if command=='getprop persist.dji.sysboot.set_fly_home':return '1'
        if command=='getprop persist.dji.fw.home':return self.property
        if command.startswith('cmd package resolve-activity'):
            return 'dji.go.v5/Old' if self.failed else 'local.rc2.home/.HomeActivity'
        self.mutations.append(command)
        if command.startswith('setprop persist.dji.fw.home'):
            self.property=HOME_VALUE if HOME_VALUE in command else ''
        return 'Success'

def test_firmware_and_screen_gate_prevent_changes():
    for adb in [Fake(wrong_hash=True),Fake(flight=True)]:
        with pytest.raises(ValueError):make_lawnchair_home(adb,Checks())
        assert adb.mutations==[]

def test_oem_home_route_is_verified():
    adb=Fake();result=make_lawnchair_home(adb,Checks())
    assert result['status']=='lawnchair_home' and adb.property==HOME_VALUE
    assert not any('set_fly_home' in s and s.startswith('setprop') for s in adb.mutations)

def test_home_resolution_failure_restores_property():
    adb=Fake(failed=True)
    with pytest.raises(RuntimeError):make_lawnchair_home(adb,Checks())
    assert adb.property==''

def test_missing_bridge_installs_verified_package_only():
    class MissingBridge(Fake):
        installed=False
        def command(self,*args,**kwargs):self.mutations.append(args)
        def shell(self,command,timeout=20):
            if command=='pm path local.rc2.home' and not self.installed:return ''
            if command.startswith('pm install'):self.installed=True
            return super().shell(command,timeout)
    adb=MissingBridge()
    make_lawnchair_home(adb,Checks(),Path(__file__).parents[1]/'assets')
    assert adb.installed and adb.property==HOME_VALUE
    assert not any('uninstall' in str(c) or 'reboot' in str(c) for c in adb.mutations)

def test_corrupted_bridge_asset_is_never_pushed(tmp_path):
    class MissingBridge(Fake):
        def shell(self,command,timeout=20):
            if command=='pm path local.rc2.home':return ''
            return super().shell(command,timeout)
    (tmp_path/'home-bridge.apk').write_bytes(b'not the verified app')
    adb=MissingBridge()
    with pytest.raises(ValueError,match='bị thay đổi'):make_lawnchair_home(adb,Checks(),tmp_path)
    assert adb.mutations==[]
