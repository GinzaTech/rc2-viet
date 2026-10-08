"""Phone-only resource overlay for the verified official Android APK."""
import hashlib
from pathlib import Path
import re
import shlex
import tempfile
import uuid
from .core import validate_package_path
from .phone import inspect_phone
from .phone_resources import approve_phone_idmap

PACKAGE='local.dji.fly.phone.vietnamese'
TARGET_HASH='1da8d5b2ee5cdcb6002131b8f6535605e7445080d1ca6f8411067a0d1524ce0b'
OVERLAY_HASH='c1d9198c1abeca5022ee1bbc18c8c333f0619f2b188776878353c3a84edbeebf'
PREVIOUS_OVERLAY_HASH='d40ebab478d1a26856a1321f475f5b1fbf11d121b570301dfba554aac235df82'
OLDER_OVERLAY_HASH='3bfb108235a52838bb3f19380db8b9825604c9449fd04c014249dd168ed81d6d'


class RootShell:
    def __init__(self,adb):self.adb=adb
    def shell(self,command,timeout=30):
        result=self.adb.shell('su -c '+shlex.quote(command+' && echo PHONEVI_OK'),timeout=timeout)
        lines=result.splitlines()
        if not lines or lines[-1]!='PHONEVI_OK':raise RuntimeError('Điện thoại không hoàn thành lệnh root: '+command.split()[0]+' — '+result[-600:])
        return '\n'.join(lines[:-1])


def package_path(root,package,required=True):
    # `pm path` exits 1 when a package is absent. Still validate any output.
    output=root.shell('(pm path '+package+' || true)')
    if not output and not required:return None
    lines=output.splitlines()
    if len(lines)!=1 or not lines[0].startswith('package:'):raise ValueError('Cần APK nguyên khối đã kiểm chứng: '+package)
    return validate_package_path(lines[0][8:])


def safe_foreground(root):
    output=root.shell("dumpsys activity activities | grep -E 'mResumedActivity|topResumedActivity|ResumedActivity'")
    components=re.findall(r'\b([\w.]+/[\w.$]+)',output)
    if not components:raise ValueError('Không xác định được màn hình hiện tại; đã dừng cập nhật.')
    if any(c.startswith('dji.go.v5/') and c!='dji.go.v5/com.dji.mainpageui.device.DJIDeviceActivity' for c in components):
        raise ValueError('Về trang chủ DJI Fly hoặc màn hình chính điện thoại trước khi cập nhật bản dịch.')


class PhoneOverlay:
    def __init__(self,assets:Path,work:Path,emit):self.assets=assets;self.work=work;self.emit=emit

    def verify(self,adb):
        info=inspect_phone(adb)
        if info['status']=='fly_missing':raise ValueError(info['message'])
        if not info['root']:raise ValueError('Việt hóa điện thoại cần quyền root cho ADB. DJI Fly vẫn giữ nguyên chữ ký DJI.')
        if (info['sdk'],info['version'],info['version_code'])!=('35','1.21.12',3131451):
            raise ValueError('Gói điện thoại hiện hỗ trợ Android 15 / DJI Fly chính thức 1.21.12 (3131451). Phiên bản khác cần đối chiếu tài nguyên riêng.')
        root=RootShell(adb);target=package_path(root,'dji.go.v5')
        if root.shell('sha256sum '+shlex.quote(target),timeout=90).split()[0]!=TARGET_HASH:
            raise ValueError('APK DJI Fly khác bản chính thức đã kiểm chứng; đã dừng.')
        if hashlib.sha256((self.assets/'phone-vietnamese-resources.apk').read_bytes()).hexdigest()!=OVERLAY_HASH:
            raise ValueError('Gói tài nguyên điện thoại bị thay đổi; đã dừng.')
        return root,target

    def enabled(self,root):
        state=root.shell('cmd overlay dump '+PACKAGE)
        if 'STATE_ENABLED' not in state:return False
        return root.shell('cmd overlay lookup --user 0 dji.go.v5 dji.go.v5:string/homepage_connect_drone_btn')=='Kết nối máy bay'

    def apply(self,adb,enable=True):
        self.emit('checking','Đang kiểm tra bản DJI Fly điện thoại và quyền root…')
        root,target=self.verify(adb);overlay=package_path(root,PACKAGE,required=False)
        digest=root.shell('sha256sum '+shlex.quote(overlay)).split()[0] if overlay else None
        upgrade=digest in {PREVIOUS_OVERLAY_HASH,OLDER_OVERLAY_HASH}
        if overlay and digest not in {OVERLAY_HASH,PREVIOUS_OVERLAY_HASH,OLDER_OVERLAY_HASH}:
            raise ValueError('Gói Việt hóa điện thoại đã cài khác bản của công cụ; đã dừng.')
        if not enable and not overlay:return {'status':'absent','message':'Điện thoại chưa cài gói tiếng Việt.'}
        if enable and overlay and not upgrade and self.enabled(root):return {'status':'already_enabled','message':'Tiếng Việt điện thoại đã bật và đọc lại thành công.'}
        safe_foreground(root)
        if not enable:
            root.shell('cmd overlay disable --user 0 '+PACKAGE)
            if 'STATE_ENABLED' in root.shell('cmd overlay dump '+PACKAGE):raise RuntimeError('Chưa tắt được bản dịch điện thoại.')
            return {'status':'disabled','message':'Đã tắt bản dịch điện thoại. Mở lại DJI Fly để xem thay đổi.'}
        self.emit('applying','Đang cài gói tài nguyên riêng cho DJI Fly Android 1.21.12…')
        remote='/data/local/tmp/phonevi-'+uuid.uuid4().hex
        root.shell('mkdir -m 755 '+remote+' && chown shell:shell '+remote+' && restorecon '+remote)
        try:
            if not overlay or upgrade:
                adb.command('push',str(self.assets/'phone-vietnamese-resources.apk'),remote+'/pack.apk',timeout=60)
                root.shell('pm install '+('-r ' if upgrade else '')+'--user 0 '+remote+'/pack.apk',timeout=60)
                overlay=package_path(root,PACKAGE)
                if root.shell('sha256sum '+shlex.quote(overlay)).split()[0]!=OVERLAY_HASH:raise ValueError('Hash gói dịch cài trên điện thoại không khớp.')
            self.cache(adb,root,target,overlay,remote)
            return {'status':'enabled','message':'Đã bật tiếng Việt trên điện thoại và kiểm tra tài nguyên. Mở DJI Fly để xem.'}
        finally:
            try:root.shell('rm -rf '+remote)
            except Exception:self.emit('warning','Không dọn được thư mục tạm của gói dịch điện thoại: '+remote)

    def cache(self,adb,root,target,overlay,remote):
        safe_foreground(root)
        cache='/data/resource-cache/'+overlay.lstrip('/').replace('/','@')+'@idmap'
        original=root.shell('if [ -f '+shlex.quote(cache)+' ]; then echo yes; fi')=='yes'
        if original:root.shell('cp '+shlex.quote(cache)+' '+remote+'/backup.idmap')
        root.shell('idmap2 create --target-apk-path '+shlex.quote(target)+' --overlay-apk-path '+shlex.quote(overlay)+
                   ' --idmap-path '+remote+'/raw.idmap --policy public --ignore-overlayable')
        root.shell('chmod 644 '+remote+'/raw.idmap')
        self.work.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='idmap-',dir=self.work) as folder:
            local=Path(folder)/'raw.idmap'
            adb.command('pull',remote+'/raw.idmap',str(local))
            approved=approve_phone_idmap(local.read_bytes(),target,overlay)
            local.write_bytes(approved);adb.command('push',str(local),remote+'/approved.idmap')
        try:
            safe_foreground(root)
            root.shell('cp '+remote+'/approved.idmap '+shlex.quote(cache))
            root.shell('chown root:system '+shlex.quote(cache)+' && chmod 644 '+shlex.quote(cache)+' && restorecon '+shlex.quote(cache))
            root.shell('cmd overlay enable --user 0 '+PACKAGE)
            if not self.enabled(root):raise RuntimeError('ROM chưa áp dụng gói tài nguyên điện thoại.')
        except Exception:
            root.shell('cmd overlay disable --user 0 '+PACKAGE)
            if original:root.shell('cp '+remote+'/backup.idmap '+shlex.quote(cache)+' && restorecon '+shlex.quote(cache))
            else:root.shell('rm -f '+shlex.quote(cache))
            raise
