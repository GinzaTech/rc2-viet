"""Guarded phone entry point for adaptive resource-only translation."""
from pathlib import Path
import re
import shlex
from .core import validate_package_path
from .phone import inspect_phone

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
    def __init__(self,assets:Path,work:Path,emit,adaptive=None,cancel=None):
        self.assets=assets;self.work=work;self.emit=emit
        self.adaptive=adaptive;self.cancel=cancel

    def _adaptive(self):
        if self.adaptive is None:
            from .translation_install import AdaptiveTranslation
            self.adaptive=AdaptiveTranslation(self.assets,self.work/'adaptive',self.emit,cancel=self.cancel)
        return self.adaptive

    def verify(self,adb):
        info=inspect_phone(adb)
        if info['status']=='fly_missing':raise ValueError(info['message'])
        if not info['root']:raise ValueError('Việt hóa điện thoại cần quyền root cho ADB. DJI Fly vẫn giữ nguyên chữ ký DJI.')
        if info['sdk']!='35':
            raise ValueError('Đường Việt hóa điện thoại hiện hỗ trợ idmap Android 15. Phiên bản DJI Fly không bị giới hạn.')
        if not info['version'] or info['version_code']<=0:
            raise ValueError('Không đọc được phiên bản DJI Fly.')
        root=RootShell(adb);target=package_path(root,'dji.go.v5')
        checksum=root.shell('sha256sum '+shlex.quote(target),timeout=90).split()
        digest=checksum[0] if checksum else ''
        if not re.fullmatch(r'[0-9a-fA-F]{64}',digest):
            raise ValueError('Không đọc được hash APK DJI Fly.')
        return root,target

    def apply(self,adb,enable=True):
        self.emit('checking','Đang kiểm tra bản DJI Fly điện thoại và quyền root…')
        if not enable:return self.disable(adb)
        root,_=self.verify(adb)
        safe_foreground(root)
        return self._adaptive().apply(adb,root,35,lambda:safe_foreground(root))

    def disable(self,adb):
        model=adb.shell('getprop ro.product.model').lower()
        device=adb.shell('getprop ro.product.device').lower()
        if device=='rc331' or model in {'rc331','dji rc 2'}:
            raise ValueError('Đây là RC 2. Chọn trang Tay DJI RC 2.')
        if adb.shell('getprop ro.build.version.sdk')!='35':
            raise ValueError('Đường Việt hóa điện thoại hiện hỗ trợ Android 15.')
        root=RootShell(adb)
        if not root.shell('id').startswith('uid=0('):
            raise ValueError('Tắt bản dịch điện thoại cần quyền root cho ADB.')
        safe_foreground(root)
        return self._adaptive().disable(root,lambda:safe_foreground(root))
