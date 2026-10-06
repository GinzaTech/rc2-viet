import hashlib

import pytest

import rc2vi.freefcc as installer
from test_lawnchair_install import FakeAdb as LawnchairFake


class FakeAdb(LawnchairFake):
    def __init__(self,**kwargs):
        super().__init__(path='/data/app/com.freefcc.app-abc/base.apk',**kwargs)

    def shell(self,command,timeout=20):
        if command=='pm path com.freefcc.app':
            return 'package:'+self.path if self.installed else ''
        if command.startswith('sha256sum'):
            good=self.remote_ok if self.pushed and self.pushed in command else self.readback_ok
            return (installer.FREEFCC_APK_HASH if good else '0'*64)+'  file'
        if command.startswith('cmd package resolve-activity'):
            return 'com.freefcc.app/.MainActivity' if self.component_ok else 'No activity found'
        return super().shell(command,timeout)


@pytest.fixture
def assets(tmp_path,monkeypatch):
    content=b'fixture FreeFCC APK'
    (tmp_path/'freefcc.apk').write_bytes(content)
    monkeypatch.setattr(installer,'FREEFCC_APK_HASH',hashlib.sha256(content).hexdigest())
    return tmp_path


def install(adb,assets):
    return installer.install_freefcc(adb,assets,lambda *event:None)


def test_installs_and_verifies_freefcc_without_launch_or_radio_commands(assets):
    adb=FakeAdb()
    assert install(adb,assets)['status']=='freefcc_installed'
    assert any(isinstance(c,tuple) and c[0]=='push' and 'freefcc' in c[-1] for c in adb.changes)
    assert any(isinstance(c,str) and c.startswith('pm install --user 0 ') for c in adb.changes)
    assert any(isinstance(c,str) and c.startswith('rm -f ') for c in adb.changes)
    assert not any(word in str(adb.changes) for word in ['am start','uninstall','setprop','reboot','settings put','broadcast'])


def test_matching_existing_freefcc_is_read_only(assets):
    adb=FakeAdb(installed=True)
    assert install(adb,assets)['status']=='freefcc_already_installed'
    assert adb.changes==[]


@pytest.mark.parametrize('args',[{'root':False},{'device':'mondrian'},{'foreground':''},
                              {'foreground':'dji.go.v5/com.dji.fpv.DJIFpvActivity'}])
def test_unsupported_or_unsafe_controller_never_installs(args,assets):
    adb=FakeAdb(**args)
    with pytest.raises(ValueError):install(adb,assets)
    assert adb.changes==[]


def test_corrupt_freefcc_asset_never_pushed(assets):
    (assets/'freefcc.apk').write_bytes(b'changed')
    adb=FakeAdb()
    with pytest.raises(ValueError):install(adb,assets)
    assert adb.changes==[]


def test_unknown_existing_freefcc_is_not_overwritten(assets):
    adb=FakeAdb(installed=True,readback_ok=False)
    with pytest.raises(ValueError,match='khác'):install(adb,assets)
    assert adb.changes==[]


@pytest.mark.parametrize('args',[{'remote_ok':False},{'install_ok':False},{'readback_ok':False},{'component_ok':False}])
def test_errors_are_reported_and_temporary_file_is_cleaned(args,assets):
    adb=FakeAdb(**args)
    with pytest.raises((ValueError,RuntimeError)):install(adb,assets)
    assert any(isinstance(c,str) and c.startswith('rm -f ') for c in adb.changes)
