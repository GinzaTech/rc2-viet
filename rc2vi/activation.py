"""Guarded public entry point for adaptive resource-only translation."""
import hashlib
import json
from pathlib import Path
import re
import shlex
from .core import (OVERLAY_HASH, REVIEWED5_OVERLAY_HASH, HOME_APK_HASH, LAWNCHAIR_APK_HASH, FREEFCC_APK_HASH, INITIAL_OVERLAY_HASH, FIRST_OVERLAY_HASH, PREVIOUS_OVERLAY_HASH, OLDER_OVERLAY_HASH, OVERLAY_PACKAGE,
                   foreground_safe, validate_package_path)
from .core import SUPPORTED_APK, SUPPORTED_RC_FLY_APKS, validate_rc_device


def verify_bundle(assets: Path) -> None:
    expected=json.loads((assets/'manifest.json').read_text(encoding='utf-8'))
    required={'adb/adb.exe','adb/AdbWinApi.dll','adb/AdbWinUsbApi.dll','home-bridge.apk','lawnchair.apk','freefcc.apk'}
    # Old manifests may still list the retired RRO; it is never read or trusted.
    if (not isinstance(expected,dict) or set(expected)-{'vietnamese-resources.apk'}!=required
            or expected['home-bridge.apk']!=HOME_APK_HASH or expected['lawnchair.apk']!=LAWNCHAIR_APK_HASH
            or expected['freefcc.apk']!=FREEFCC_APK_HASH):
        raise ValueError('Danh sách tài nguyên đóng gói không hợp lệ.')
    for name in sorted(required):
        digest=expected[name]
        if hashlib.sha256((assets/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Tệp đóng gói bị thay đổi: '+name)


class Activator:
    def __init__(self,assets: Path,work: Path,emit,verify_assets=True,trusted_hud=None,adaptive=None):
        self.assets=assets; self.work=work; self.emit=emit
        self.trusted_hud=trusted_hud
        self.adaptive=adaptive
        self.cancel=None
        self.target_info={}
        if verify_assets: verify_bundle(assets)

    def _path(self,adb,package,required=True):
        output=adb.shell('pm path '+package)
        if not output and not required: return None
        lines=output.splitlines()
        if len(lines)!=1 or not lines[0].startswith('package:'):
            raise ValueError('Không đọc được một APK duy nhất của '+package)
        return validate_package_path(lines[0][8:])

    def verify(self,adb):
        self.emit('checking','Đang kiểm tra phiên bản và quyền trên RC 2…')
        model=adb.shell('getprop ro.product.model')
        device=adb.shell('getprop ro.product.device')
        identity=adb.shell('id')
        if adb.shell('getprop ro.build.version.sdk')!='30':
            raise ValueError('Công cụ này chỉ hỗ trợ Android 11 đã kiểm chứng.')
        info=adb.shell('dumpsys package dji.go.v5')
        version=re.search(r'versionName=([^\s]+)',info)
        code=re.search(r'versionCode=(\d+)',info)
        target=self._path(adb,'dji.go.v5')
        checksum=adb.shell('sha256sum '+shlex.quote(target),timeout=90).split()
        digest=checksum[0] if checksum else ''
        validate_rc_device(model,device,identity)
        if not version or not code or int(code[1])<=0 or not re.fullmatch(r'[0-9a-fA-F]{64}',digest):
            raise ValueError('Không đọc được phiên bản/hash hợp lệ của DJI Fly.')
        self.target_info={'version':version[1],'code':int(code[1]),'digest':digest.lower()}
        return target

    def _adaptive(self):
        if self.adaptive is None:
            from .translation_install import AdaptiveTranslation
            self.adaptive=AdaptiveTranslation(self.assets,self.work/'adaptive',self.emit,cancel=self.cancel)
        return self.adaptive

    def _safe(self,adb):
        foreground=adb.shell('dumpsys activity activities | grep mResumedActivity')
        if not foreground or not foreground_safe(foreground):
            raise ValueError('Về trang chủ DJI Fly hoặc mở Lawnchair trước khi thay đổi bản dịch.')

    def apply(self,adb):
        self.verify(adb)
        self._safe(adb)
        return self._adaptive().apply(adb,adb,30,lambda:self._safe(adb))

    def disable(self,adb):
        validate_rc_device(adb.shell('getprop ro.product.model'),adb.shell('getprop ro.product.device'),adb.shell('id'))
        if adb.shell('getprop ro.build.version.sdk')!='30':
            raise ValueError('Công cụ này chỉ hỗ trợ Android 11 đã kiểm chứng.')
        self._safe(adb)
        return self._adaptive().disable(adb,lambda:self._safe(adb))
