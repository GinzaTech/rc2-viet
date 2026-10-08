from pathlib import Path
from types import SimpleNamespace
import hashlib
import shlex
import struct
import pytest
from rc2vi import phone_overlay as module


class FakePhone:
    def __init__(self,installed=False,enabled=False):
        self.installed=installed;self.enabled=enabled;self.calls=[];self.fail_enable=False
        self.sdk='35';self.root=True;self.target_hash=module.TARGET_HASH;self.overlay_hash=module.OVERLAY_HASH
        self.foreground='topResumedActivity: ActivityRecord{ u0 com.miui.home/.launcher.Launcher }'
        self.cache_exists=False

    def shell(self,command,**kwargs):
        self.calls.append(command)
        root_command=command.startswith('su -c ')
        if root_command:
            command=shlex.split(command)[2]
            command=command.removesuffix(' && echo PHONEVI_OK')
        if command=='getprop ro.product.model':result='Test phone'
        elif command=='getprop ro.product.device':result='mondrian'
        elif command=='getprop ro.build.version.sdk':result=self.sdk
        elif command=='id':result='uid=0(root)' if self.root else 'permission denied'
        elif command=='dumpsys package dji.go.v5':result='versionName=1.21.12 versionCode=3131451'
        elif command in {'pm path dji.go.v5','(pm path dji.go.v5 || true)'}:result='package:/data/app/fly/base.apk'
        elif command.startswith('(pm path local.'):
            result='package:/data/app/vi/base.apk' if self.installed else ''
        elif command.startswith('sha256sum'):
            result=(self.target_hash if '/fly/' in command else self.overlay_hash)+' file'
        elif command.startswith('dumpsys activity'):result=self.foreground
        elif command.startswith('cmd overlay dump'):result='STATE_ENABLED' if self.enabled else 'STATE_DISABLED'
        elif command.startswith('cmd overlay lookup'):result='Kết nối máy bay'
        elif command.startswith('cmd overlay enable '):self.enabled=not self.fail_enable;result=''
        elif command.startswith('cmd overlay disable '):self.enabled=False;result=''
        elif command.startswith('if [ -f '):result='yes' if self.cache_exists else ''
        elif command.startswith('pm install '):self.installed=True;result='Success'
        else:result=''
        return result+'\nPHONEVI_OK' if root_command else result

    def command(self,*args,**kwargs):
        self.calls.append(args)
        if args[0]=='pull':
            raw=struct.pack('<6I',0x504d4449,9,11,22,1,0)
            for text in ['/data/app/fly/base.apk','/data/app/vi/base.apk','','debug']:
                b=text.encode();raw+=struct.pack('<I',len(b))+b+b'\0'*((-len(b))%4)
            Path(args[2]).write_bytes(raw+b'\0'*80)
        return ''


@pytest.fixture
def setup(tmp_path,monkeypatch):
    assets=tmp_path/'assets';assets.mkdir();(assets/'phone-vietnamese-resources.apk').write_bytes(b'test')
    monkeypatch.setattr(module,'OVERLAY_HASH',hashlib.sha256(b'test').hexdigest())
    events=[];tool=module.PhoneOverlay(assets,tmp_path/'work',lambda *e:events.append(e))
    return tool,FakePhone(),events


def test_install_enable_verified_overlay_and_cleanup(setup):
    tool,adb,events=setup;result=tool.apply(adb)
    assert 'Đã bật' in result['message'] and adb.enabled
    assert any('pm install --user 0 ' in c for c in adb.calls if isinstance(c,str))
    assert any('rm -rf /data/local/tmp/phonevi-' in c for c in adb.calls if isinstance(c,str))
    assert not any('dji.go.v5' in c and ('uninstall' in c or 'pm install' in c) for c in adb.calls if isinstance(c,str))


def test_enabled_noop_is_readonly_even_in_camera(setup):
    tool,adb,_=setup;adb.installed=adb.enabled=True;adb.foreground='dji.go.v5/.Camera'
    assert 'đã bật' in tool.apply(adb)['message']
    assert not any(isinstance(c,tuple) for c in adb.calls)


@pytest.mark.parametrize('change', ['sdk','root','target_hash','overlay_hash','camera','missing_foreground','local_hash'])
def test_incompatible_device_or_foreground_blocks_all_writes(setup,change):
    tool,adb,_=setup
    if change=='sdk':adb.sdk='30'
    elif change=='root':adb.root=False
    elif change=='target_hash':adb.target_hash='unknown'
    elif change=='overlay_hash':adb.installed=True;adb.overlay_hash='unknown'
    elif change=='camera':adb.foreground='topResumedActivity: dji.go.v5/.Camera'
    elif change=='missing_foreground':adb.foreground=''
    else:(tool.assets/'phone-vietnamese-resources.apk').write_bytes(b'changed')
    with pytest.raises(ValueError):tool.apply(adb)
    assert not any(isinstance(c,tuple) for c in adb.calls)


def test_upgrade_only_known_previous_pack(setup):
    tool,adb,_=setup;adb.installed=True;adb.overlay_hash=module.PREVIOUS_OVERLAY_HASH
    original_shell=adb.shell
    def shell(command,**kwargs):
        result=original_shell(command,**kwargs)
        if 'pm install -r' in command:adb.overlay_hash=module.OVERLAY_HASH
        return result
    adb.shell=shell
    tool.apply(adb)
    assert any('pm install -r --user 0' in c for c in adb.calls if isinstance(c,str))


@pytest.mark.parametrize('installed',[True,False])
def test_disable_and_absent_pack(setup,installed):
    tool,adb,_=setup;adb.installed=installed;adb.enabled=installed
    tool.apply(adb,enable=False)
    assert not adb.enabled
    assert not any(isinstance(c,tuple) for c in adb.calls)


@pytest.mark.parametrize('backup',[True,False])
def test_failed_enable_restores_previous_cache_or_removes_new_cache(setup,backup):
    tool,adb,_=setup;adb.installed=True;adb.fail_enable=True;adb.cache_exists=backup
    with pytest.raises(RuntimeError,match='ROM chưa áp dụng'):tool.apply(adb)
    assert not adb.enabled
    calls='\n'.join(c for c in adb.calls if isinstance(c,str))
    assert ('/backup.idmap' in calls) is backup
    if not backup:assert 'rm -f /data/resource-cache/' in calls


def test_root_shell_requires_success_marker():
    with pytest.raises(RuntimeError,match='permission denied'):
        module.RootShell(SimpleNamespace(shell=lambda *a,**k:'permission denied')).shell('id')


def test_missing_package_and_split_packages_fail_clearly():
    fake=SimpleNamespace(shell=lambda *a,**k:'')
    assert module.package_path(fake,'test',required=False) is None
    with pytest.raises(ValueError):module.package_path(fake,'test')


def test_source_matches_exact_installed_phone_profile(setup,monkeypatch):
    tool,adb,_=setup
    monkeypatch.setattr(module,'inspect_phone',lambda a:{'status':'fly_missing','message':'Chưa cài'})
    with pytest.raises(ValueError,match='Chưa cài'):tool.verify(adb)
