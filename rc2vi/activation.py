"""Resource-only translation: pinned fast path and version-independent RROs."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import tempfile
import uuid
from .core import (OVERLAY_HASH, REVIEWED5_OVERLAY_HASH, HOME_APK_HASH, LAWNCHAIR_APK_HASH, FREEFCC_APK_HASH, INITIAL_OVERLAY_HASH, FIRST_OVERLAY_HASH, PREVIOUS_OVERLAY_HASH, OLDER_OVERLAY_HASH, OVERLAY_PACKAGE, approve_idmap,
                   foreground_safe, validate_package_path)
from .core import SUPPORTED_APK, SUPPORTED_RC_FLY_APKS, validate_rc_device


def verify_bundle(assets: Path) -> None:
    expected=json.loads((assets/'manifest.json').read_text(encoding='utf-8'))
    required={'adb/adb.exe','adb/AdbWinApi.dll','adb/AdbWinUsbApi.dll','vietnamese-resources.apk','home-bridge.apk','lawnchair.apk','freefcc.apk'}
    if (set(expected)!=required or expected['vietnamese-resources.apk']!=OVERLAY_HASH
            or expected['home-bridge.apk']!=HOME_APK_HASH or expected['lawnchair.apk']!=LAWNCHAIR_APK_HASH
            or expected['freefcc.apk']!=FREEFCC_APK_HASH):
        raise ValueError('Danh sách tài nguyên đóng gói không hợp lệ.')
    for name,digest in expected.items():
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
        digest=adb.shell('sha256sum '+shlex.quote(target),timeout=90).split()[0]
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

    def _legacy_supported(self):
        info=self.target_info
        if (info['version'],info['code'])!=('1.21.8',3115809):return False
        if info['digest'] in SUPPORTED_RC_FLY_APKS:return True
        if self.trusted_hud is not None:
            try:
                receipt=self.trusted_hud(info['digest'])
                return receipt.get('digest')==info['digest'] and receipt.get('source_digest')==SUPPORTED_APK
            except (ValueError,OSError):return False
        return False

    def _has_adaptive(self,adb):
        return 'local.dji.fly.vi.auto.' in adb.shell('cmd overlay list --user 0 dji.go.v5')

    def _enabled(self,adb):
        state=adb.shell('cmd overlay dump '+OVERLAY_PACKAGE)
        sample=adb.shell('cmd overlay lookup dji.go.v5 dji.go.v5:string/homepage_connect_drone_btn')
        return 'STATE_ENABLED' in state and sample=='Kết nối máy bay'

    def _safe(self,adb):
        foreground=adb.shell('dumpsys activity activities | grep mResumedActivity')
        if not foreground or not foreground_safe(foreground):
            raise ValueError('Về trang chủ DJI Fly hoặc mở Lawnchair trước khi thay đổi bản dịch.')

    def _run(self,adb,command,timeout=45):
        result=adb.shell(command+' && echo RC2VI_OK',timeout=timeout)
        if 'RC2VI_OK' not in result.splitlines():
            raise RuntimeError('RC 2 không hoàn thành thao tác tài nguyên.')

    def apply(self,adb):
        target=self.verify(adb)
        if not self._legacy_supported() or self._has_adaptive(adb):
            self._safe(adb)
            return self._adaptive().apply(adb,adb,30,lambda:self._safe(adb))
        overlay=self._path(adb,OVERLAY_PACKAGE,required=False)
        upgrade=False
        if overlay:
            digest=adb.shell('sha256sum '+shlex.quote(overlay),timeout=30).split()[0]
            if digest not in {OVERLAY_HASH,REVIEWED5_OVERLAY_HASH,PREVIOUS_OVERLAY_HASH,OLDER_OVERLAY_HASH,FIRST_OVERLAY_HASH,INITIAL_OVERLAY_HASH}:
                raise ValueError('Gói tiếng Việt trên tay khác bản đã kiểm chứng; đã dừng.')
            upgrade=digest!=OVERLAY_HASH
            if not upgrade and self._enabled(adb):
                return {'status':'already_enabled','sample':'Kết nối máy bay'}
        self._safe(adb)
        self.emit('applying','Đang bật tài nguyên tiếng Việt…')
        remote='/data/local/tmp/rc2vi-'+uuid.uuid4().hex
        self._run(adb,'mkdir -m 700 '+remote)
        try:
            if not overlay or upgrade:
                adb.command('push',str(self.assets/'vietnamese-resources.apk'),remote+'/pack.apk',timeout=60)
                self._run(adb,'pm install -r --user 0 '+remote+'/pack.apk',timeout=60)
                overlay=self._path(adb,OVERLAY_PACKAGE)
                digest=adb.shell('sha256sum '+shlex.quote(overlay),timeout=30).split()[0]
                if digest!=OVERLAY_HASH: raise ValueError('APK tiếng Việt cài đặt không khớp.')
            return self._cache(adb,target,overlay,remote)
        finally:
            # Only the exact app-created, random temporary directory is removed.
            self._run(adb,'rm -rf '+remote)

    def _cache(self,adb,target,overlay,remote):
        self._safe(adb)
        cache='/data/resource-cache/'+overlay.lstrip('/').replace('/','@')+'@idmap'
        qcache=shlex.quote(cache)
        self._run(adb,'idmap2 create --target-apk-path '+shlex.quote(target)+
                  ' --overlay-apk-path '+shlex.quote(overlay)+' --idmap-path '+remote+
                  '/map --policy public --ignore-overlayable')
        self.work.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.work) as directory:
            local=Path(directory)/'map'
            adb.command('pull',remote+'/map',str(local),timeout=45)
            local.write_bytes(approve_idmap(local.read_bytes(),target,overlay))
            adb.command('push',str(local),remote+'/map',timeout=45)
        self._run(adb,'if [ -f '+qcache+' ]; then cp '+qcache+' '+remote+'/previous; fi')
        try:
            self._run(adb,'cp '+remote+'/map '+qcache+' && chown root:system '+qcache+
                      ' && chmod 644 '+qcache+' && restorecon '+qcache)
            self._run(adb,'cmd overlay enable --user 0 '+OVERLAY_PACKAGE)
            if not self._enabled(adb):
                raise RuntimeError('Đọc lại tài nguyên chưa xác nhận tiếng Việt.')
        except Exception as exc:
            try:
                self._run(adb,'cmd overlay disable --user 0 '+OVERLAY_PACKAGE)
                self._run(adb,'if [ -f '+remote+'/previous ]; then cp '+remote+'/previous '+
                          qcache+' && restorecon '+qcache+'; else rm -f '+qcache+'; fi')
            except Exception as rollback:
                raise RuntimeError('Bật bản dịch thất bại; phục hồi cache cũng thất bại: '+str(rollback)) from exc
            raise
        return {'status':'enabled','sample':'Kết nối máy bay'}

    def disable(self,adb):
        validate_rc_device(adb.shell('getprop ro.product.model'),adb.shell('getprop ro.product.device'),adb.shell('id'))
        if adb.shell('getprop ro.build.version.sdk')!='30':
            raise ValueError('Công cụ này chỉ hỗ trợ Android 11 đã kiểm chứng.')
        self._safe(adb)
        if self._has_adaptive(adb):
            return self._adaptive().disable(adb,lambda:self._safe(adb))
        self._run(adb,'cmd overlay disable --user 0 '+OVERLAY_PACKAGE)
        if 'STATE_ENABLED' in adb.shell('cmd overlay dump '+OVERLAY_PACKAGE):
            raise RuntimeError('Chưa xác nhận được bản dịch đã tắt.')
        return {'status':'disabled'}
