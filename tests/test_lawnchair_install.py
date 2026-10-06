import hashlib
from pathlib import Path

import pytest

import rc2vi.lawnchair as installer


class FakeAdb:
    def __init__(self, installed=False, model='DJI RC 2', device='rc331', sdk='30',
                 root=True, foreground='app.lawnchair/.LawnchairLauncher',
                 remote_ok=True, install_ok=True, readback_ok=True, component_ok=True,
                 path='/data/app/app.lawnchair-abc/base.apk', cleanup_ok=True):
        self.installed=installed;self.model=model;self.device=device;self.sdk=sdk
        self.root=root;self.foreground=foreground;self.remote_ok=remote_ok
        self.install_ok=install_ok;self.readback_ok=readback_ok
        self.component_ok=component_ok;self.path=path;self.cleanup_ok=cleanup_ok
        self.changes=[];self.pushed=''

    def command(self,*args,**kwargs):
        self.changes.append(args)
        if args[0]=='push':self.pushed=args[-1]
        return ''

    def shell(self,command,timeout=20):
        if command=='getprop ro.product.model':return self.model
        if command=='getprop ro.product.device':return self.device
        if command=='getprop ro.build.version.sdk':return self.sdk
        if command=='id':return 'uid=0(root)' if self.root else 'uid=2000(shell)'
        if command=='pm path app.lawnchair':return 'package:'+self.path if self.installed else ''
        if command.startswith('dumpsys activity'):return self.foreground
        if command.startswith('sha256sum'):
            good=self.remote_ok if self.pushed and self.pushed in command else self.readback_ok
            return (installer.LAWNCHAIR_APK_HASH if good else '0'*64)+'  file'
        if command.startswith('cmd package resolve-activity'):
            return installer.LAWNCHAIR_COMPONENT if self.component_ok else 'No activity found'
        self.changes.append(command)
        if command.startswith('pm install'):
            self.installed=self.install_ok
            return 'Success' if self.install_ok else 'Failure [INSTALL_FAILED_TEST]'
        if command.startswith('rm -f') and not self.cleanup_ok:raise RuntimeError('USB disconnected')
        return ''


@pytest.fixture
def assets(tmp_path,monkeypatch):
    content=b'fixture APK'
    (tmp_path/'lawnchair.apk').write_bytes(content)
    monkeypatch.setattr(installer,'LAWNCHAIR_APK_HASH',hashlib.sha256(content).hexdigest())
    return tmp_path


def install(adb,assets):
    return installer.install_lawnchair(adb,assets,lambda *event:None)


@pytest.mark.parametrize('args',[{'model':'Other'},{'device':'mondrian'},{'sdk':'35'},{'root':False}])
def test_wrong_target_never_writes(args,assets):
    adb=FakeAdb(**args)
    with pytest.raises(ValueError):install(adb,assets)
    assert adb.changes==[]


@pytest.mark.parametrize('foreground',['','dji.go.v5/com.dji.fpv.DJIFpvActivity'])
def test_unknown_or_camera_foreground_never_installs(foreground,assets):
    adb=FakeAdb(foreground=foreground)
    with pytest.raises(ValueError):install(adb,assets)
    assert adb.changes==[]


def test_corrupt_local_apk_never_reaches_device(assets):
    (assets/'lawnchair.apk').write_bytes(b'changed')
    adb=FakeAdb()
    with pytest.raises(ValueError):install(adb,assets)
    assert adb.changes==[]


def test_matching_existing_package_is_read_only_even_on_camera(assets):
    adb=FakeAdb(installed=True,foreground='dji.go.v5/com.dji.fpv.DJIFpvActivity')
    assert install(adb,assets)['status']=='lawnchair_already_installed'
    assert adb.changes==[]


def test_unknown_existing_package_is_never_overwritten(assets):
    adb=FakeAdb(installed=True,readback_ok=False)
    with pytest.raises(ValueError,match='khác'):install(adb,assets)
    assert adb.changes==[]


def test_invalid_installed_path_never_used_in_shell(assets):
    adb=FakeAdb(installed=True,path='/data/app/../../etc/file.apk')
    with pytest.raises(ValueError):install(adb,assets)
    assert adb.changes==[]


def test_push_install_and_verified_readback_do_not_change_home(assets):
    adb=FakeAdb()
    assert install(adb,assets)['status']=='lawnchair_installed'
    assert any(isinstance(c,tuple) and c[0]=='push' for c in adb.changes)
    assert any(isinstance(c,str) and c.startswith('pm install --user 0 ') for c in adb.changes)
    assert any(isinstance(c,str) and c.startswith('rm -f ') for c in adb.changes)
    assert not any(word in str(adb.changes) for word in ['uninstall','setprop','reboot','set-home-activity'])


@pytest.mark.parametrize('args',[{'remote_ok':False},{'install_ok':False},{'readback_ok':False},{'component_ok':False}])
def test_failed_install_checks_never_report_success_and_cleanup(args,assets):
    adb=FakeAdb(**args)
    with pytest.raises((ValueError,RuntimeError)):install(adb,assets)
    assert any(isinstance(c,str) and c.startswith('rm -f ') for c in adb.changes)
    if not adb.remote_ok:assert not any(isinstance(c,str) and c.startswith('pm install') for c in adb.changes)


def test_cleanup_failure_preserves_original_install_error(assets):
    adb=FakeAdb(install_ok=False,cleanup_ok=False);events=[]
    with pytest.raises(RuntimeError,match='cài'):
        installer.install_lawnchair(adb,assets,lambda *event:events.append(event))
    assert events[-1][0]=='warning'


def test_existing_package_without_launcher_never_reports_success(assets):
    adb=FakeAdb(installed=True,component_ok=False)
    with pytest.raises(RuntimeError):install(adb,assets)
    assert adb.changes==[]


def test_install_success_without_package_is_not_success(assets):
    class MissingAfterInstall(FakeAdb):
        def shell(self,command,timeout=20):
            if command=='pm path app.lawnchair':return ''
            return super().shell(command,timeout)
    adb=MissingAfterInstall()
    with pytest.raises(RuntimeError,match='sau khi cài'):install(adb,assets)
    assert any(isinstance(c,str) and c.startswith('rm -f ') for c in adb.changes)


def test_empty_remote_checksum_prevents_install(assets):
    class NoChecksum(FakeAdb):
        def shell(self,command,timeout=20):
            if command.startswith('sha256sum'):return ''
            return super().shell(command,timeout)
    adb=NoChecksum()
    with pytest.raises(RuntimeError,match='mã kiểm tra'):install(adb,assets)
    assert not any(isinstance(c,str) and c.startswith('pm install') for c in adb.changes)
