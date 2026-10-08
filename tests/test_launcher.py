import pytest
from pathlib import Path
from rc2vi.launcher import make_rc_launcher_home,SERVICES_HASH,HOME_VALUE
from rc2vi.core import HOME_APK_HASH

class Checks:
    def verify(self,adb):return 'verified'
    def _safe(self,adb):
        if adb.flight:raise ValueError('camera')

class Fake:
    def __init__(self,wrong_hash=False,flight=False,failed=False):
        self.wrong_hash=wrong_hash;self.flight=flight;self.failed=failed;self.property='';self.mutations=[]
    def shell(self,command,timeout=20):
        if command.startswith('sha256sum') and 'dev.rclauncher.rc2.debug-' in command:
            from rc2vi.rc_launcher import RC_LAUNCHER_HASH
            return RC_LAUNCHER_HASH+' file'
        if command.startswith('sha256sum'):
            return ('0'*64 if self.wrong_hash else HOME_APK_HASH if 'local.rc2.home-' in command else SERVICES_HASH)+' file'
        if command=='pm path dev.rclauncher.rc2.debug':return 'package:/data/app/dev.rclauncher.rc2.debug-abc/base.apk'
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
        with pytest.raises(ValueError):make_rc_launcher_home(adb,Checks())
        assert adb.mutations==[]

def test_oem_home_route_is_verified():
    adb=Fake();result=make_rc_launcher_home(adb,Checks())
    assert result['status']=='rc_launcher_home' and adb.property==HOME_VALUE
    assert not any('set_fly_home' in s and s.startswith('setprop') for s in adb.mutations)

def test_home_resolution_failure_restores_property():
    adb=Fake(failed=True)
    with pytest.raises(RuntimeError):make_rc_launcher_home(adb,Checks())
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
    make_rc_launcher_home(adb,Checks(),Path(__file__).parents[1]/'assets')
    assert adb.installed and adb.property==HOME_VALUE
    assert not any('uninstall' in str(c) or 'reboot' in str(c) for c in adb.mutations)

def test_corrupted_bridge_asset_is_never_pushed(tmp_path):
    class MissingBridge(Fake):
        def shell(self,command,timeout=20):
            if command=='pm path local.rc2.home':return ''
            return super().shell(command,timeout)
    (tmp_path/'home-bridge.apk').write_bytes(b'not the verified app')
    adb=MissingBridge()
    with pytest.raises(ValueError,match='bị thay đổi'):make_rc_launcher_home(adb,Checks(),tmp_path)
    assert adb.mutations==[]


def test_known_legacy_bridge_is_upgraded_without_removing_data():
    legacy='7e4ecbe3fde296ae006f66be2577194284f002f0d2f914d0eb86e78c28907168'
    class Legacy(Fake):
        digest=legacy
        def command(self,*args,**kwargs):self.mutations.append(args)
        def shell(self,command,timeout=20):
            if command.startswith('sha256sum') and 'local.rc2.home-' in command:return self.digest+' file'
            if command.startswith('pm install'):
                self.mutations.append(command);self.digest=HOME_APK_HASH;return 'Success'
            return super().shell(command,timeout)
    adb=Legacy();make_rc_launcher_home(adb,Checks(),Path(__file__).parents[1]/'assets')
    assert adb.digest==HOME_APK_HASH
    assert any(isinstance(c,str) and c.startswith('pm install -r --user 0 ') for c in adb.mutations)
    assert not any('uninstall' in str(c) or 'clear ' in str(c) for c in adb.mutations)


def test_missing_bridge_readback_mismatch_never_changes_home():
    class FailedReadback(Fake):
        installed=False
        def command(self,*args,**kwargs):self.mutations.append(args)
        def shell(self,command,timeout=20):
            if command=='pm path local.rc2.home' and not self.installed:return ''
            if command.startswith('pm install'):self.installed=True;return 'Success'
            if command.startswith('sha256sum') and 'local.rc2.home-' in command:return '0'*64+' file'
            return super().shell(command,timeout)
    adb=FailedReadback()
    with pytest.raises(RuntimeError,match='khớp'):
        make_rc_launcher_home(adb,Checks(),Path(__file__).parents[1]/'assets')
    assert not any('set-home-activity' in str(c) or str(c).startswith('setprop') for c in adb.mutations)
