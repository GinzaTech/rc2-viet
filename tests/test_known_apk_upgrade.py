import hashlib
from pathlib import Path
from rc2vi.apk_install import BundledAPK,install_bundled_apk


def test_only_recognized_old_launcher_is_upgraded_with_data_retained(tmp_path):
    payload=b'new launcher';(tmp_path/'rc.apk').write_bytes(payload);new=hashlib.sha256(payload).hexdigest();old='a'*64
    app=BundledAPK('RC','rc.apk','dev.rc','dev.rc/dev.rc.Main',new,'rc',upgrade_hashes=(old,))
    class Adb:
        def __init__(self):self.digest=old;self.commands=[]
        def command(self,*args,**kwargs):self.commands.append(args);return ''
        def shell(self,cmd,**kwargs):
            self.commands.append(cmd)
            if cmd=='getprop ro.product.model':return 'DJI RC 2'
            if cmd=='getprop ro.product.device':return 'rc331'
            if cmd=='getprop ro.build.version.sdk':return '30'
            if cmd=='id':return 'uid=0(root)'
            if cmd.startswith('pm path'):return 'package:/data/app/dev.rc/base.apk'
            if cmd.startswith('sha256sum'):return (new if '/data/local/tmp/' in cmd else self.digest)+' file'
            if cmd.startswith('dumpsys activity'):return 'app.lawnchair/.LawnchairLauncher'
            if cmd.startswith('pm install -r'):self.digest=new;return 'Success'
            if cmd.startswith('cmd package resolve'):return 'dev.rc/dev.rc.Main'
            return ''
    adb=Adb();result=install_bundled_apk(adb,tmp_path,app,lambda *e:None)
    assert result['status']=='rc_installed'
    assert any(isinstance(c,str) and c.startswith('pm install -r --user 0') for c in adb.commands)
    assert not any(isinstance(c,str) and ('uninstall' in c or 'pm clear' in c) for c in adb.commands)
