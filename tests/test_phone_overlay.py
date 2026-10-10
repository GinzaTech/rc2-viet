from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
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
def setup(tmp_path):
    assets=tmp_path/'assets';assets.mkdir()
    events=[];adaptive=Mock()
    adaptive.apply.return_value={'status':'enabled','message':'translated'}
    adaptive.disable.return_value={'status':'disabled','message':'disabled'}
    tool=module.PhoneOverlay(assets,tmp_path/'work',lambda *e:events.append(e),adaptive=adaptive)
    return tool,FakePhone(),events


@pytest.mark.parametrize('installed,enabled', [(False,False),(True,False),(True,True)])
def test_known_phone_always_delegates_without_prepared_pack(setup,installed,enabled):
    tool,adb,_=setup;adb.installed=installed;adb.enabled=enabled
    assert not (tool.assets/'phone-vietnamese-resources.apk').exists()
    assert tool.apply(adb) is tool.adaptive.apply.return_value
    args=tool.adaptive.apply.call_args.args
    assert args[0] is adb and args[1].adb is adb and args[2]==35
    args[3]()
    adb.foreground='dji.go.v5/.Camera'
    with pytest.raises(ValueError):args[3]()
    assert not any(isinstance(c,tuple) for c in adb.calls)


@pytest.mark.parametrize('change', ['sdk','root','target_hash','empty_hash','camera','missing_foreground'])
def test_incompatible_device_or_foreground_blocks_adaptive(setup,change):
    tool,adb,_=setup
    if change=='sdk':adb.sdk='30'
    elif change=='root':adb.root=False
    elif change=='target_hash':adb.target_hash='unknown'
    elif change=='empty_hash':adb.target_hash=''
    elif change=='camera':adb.foreground='topResumedActivity: dji.go.v5/.Camera'
    else:adb.foreground=''
    with pytest.raises(ValueError):tool.apply(adb)
    tool.adaptive.apply.assert_not_called()
    assert not any(isinstance(c,tuple) for c in adb.calls)


@pytest.mark.parametrize('info', [
    {'status':'fly_missing','message':'Chưa cài'},
    {'status':'inspected','root':True,'sdk':'35','version':'','version_code':1},
    {'status':'inspected','root':True,'sdk':'35','version':'2.0','version_code':0},
])
def test_phone_requires_installed_fly_with_valid_version(setup,monkeypatch,info):
    tool,adb,_=setup
    monkeypatch.setattr(module,'inspect_phone',lambda a:info)
    with pytest.raises(ValueError):tool.apply(adb)
    tool.adaptive.apply.assert_not_called()


@pytest.mark.parametrize('field,value', [('ro.product.model','DJI RC 2'),('ro.product.device','rc331')])
@pytest.mark.parametrize('enable', [True,False])
def test_rc_identity_never_enters_phone_translation(setup,field,value,enable):
    tool,adb,_=setup
    original=adb.shell
    adb.shell=lambda command,**kw:value if command=='getprop '+field else original(command,**kw)
    with pytest.raises(ValueError,match='RC 2'):tool.apply(adb,enable=enable)
    assert not tool.adaptive.mock_calls


@pytest.mark.parametrize('change', ['sdk','root','camera','missing_foreground'])
def test_phone_disable_keeps_root_sdk_and_foreground_guards(setup,change):
    tool,adb,_=setup
    if change=='sdk':adb.sdk='30'
    elif change=='root':adb.root=False
    elif change=='camera':adb.foreground='dji.go.v5/.Camera'
    else:adb.foreground=''
    with pytest.raises(ValueError):tool.apply(adb,enable=False)
    tool.adaptive.disable.assert_not_called()


def test_root_shell_requires_success_marker():
    with pytest.raises(RuntimeError,match='permission denied'):
        module.RootShell(SimpleNamespace(shell=lambda *a,**k:'permission denied')).shell('id')


@pytest.mark.parametrize('output', ['', 'bad', 'package:/data/app/../../bad.apk',
                                   'package:/data/app/base.apk\npackage:/data/app/split.apk'])
def test_missing_unsafe_or_split_packages_fail_clearly(output):
    fake=SimpleNamespace(shell=lambda *a,**k:output)
    with pytest.raises(ValueError):module.package_path(fake,'test')
    if not output:assert module.package_path(fake,'test',required=False) is None
