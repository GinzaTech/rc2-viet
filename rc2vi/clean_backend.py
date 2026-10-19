"""Fresh device APKs, verified patch outputs and clean, idempotent Fly deployment."""
import json
from pathlib import Path
import re
import shlex
import shutil
import tempfile
import sys

from .core import validate_package_path
from .hud_backup import guard_path, make_private
from .hud_tools import sha256_file

PACKAGE='dji.go.v5'
HASH=re.compile('[0-9a-f]{64}')


class CleanBackend:
    def __init__(self,assets,root_provider,check,emit,cancel=None):
        self.assets,self.root_provider,self.check,self.emit,self.cancel=Path(assets),root_provider,check,emit,cancel

    def _root(self,job,mutating=False):
        self.check();root=self.root_provider(job.serial)
        if (root.serial!=job.serial or root.command('get-state').strip()!='device'
            or root.shell('getprop ro.serialno').strip()!=job.serial
            or root.shell('getprop ro.product.model').replace('_',' ').strip()!='DJI RC 2'
            or root.shell('getprop ro.product.device').strip()!='rc331'
            or root.shell('getprop ro.build.version.sdk').strip()!='30'
            or not root.shell('id').startswith('uid=0(')):
            raise ValueError('Chờ đúng RC 2/serial/SDK30/root đã chọn.')
        if mutating:self._safe(root)
        self.check();return root

    def _safe(self,root):
        self.check()
        foreground=root.shell('dumpsys activity activities | grep mResumedActivity')
        if not foreground.strip():raise ValueError('Chưa xác định màn hình đang mở trên RC 2.')
        if re.search(r'\bdji\.go\.v5/',foreground):
            raise ValueError('Giữ tay ở Launcher/Settings khi đã hạ cánh; không can thiệp màn hình DJI Fly đang mở.')
        self.check()

    def _write(self,root,command,timeout=180):
        self._safe(root);self.check()
        prefix=('rc2_fg="$(dumpsys activity activities | grep mResumedActivity)"; '
            '[ -n "$rc2_fg" ] || exit 1; case "$rc2_fg" in *dji.go.v5/*) exit 1;; esac;\n# RC2_CLEAN_WRITE\n')
        return root.shell(prefix+command,timeout=timeout)

    def _snapshot(self,root,required=True):
        lines=root.shell('pm path '+PACKAGE).strip().splitlines()
        if not lines and not required:return None
        if len(lines)!=1 or not lines[0].startswith('package:'):raise ValueError('Cần đúng một APK DJI Fly.')
        path=validate_package_path(lines[0][8:]);info=root.shell('dumpsys package '+PACKAGE)
        version=re.findall(r'\bversionName=([^\s]+)',info);code=re.findall(r'\bversionCode=(\d+)',info)
        checksum=root.shell('sha256sum '+shlex.quote(path),timeout=120).split()
        if len(version)!=1 or len(code)!=1 or not checksum or not HASH.fullmatch(checksum[0]):
            raise ValueError('Không đọc được phiên bản/hash APK hiện tại.')
        return {'path':path,'digest':checksum[0],'version':version[0],'code':int(code[0])}

    def _path(self,job,relative):
        if not isinstance(relative,str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Đường dẫn artifact không thuộc tác vụ.')
        path=guard_path(job.work/relative)
        if not path.is_relative_to(job.work):raise ValueError('Artifact ra ngoài tác vụ.')
        return path

    def _builders(self,job):
        from advanced_app import builder_factory
        from .translation_build import TranslationBuilder
        from .translation_engine import LocalTranslationEngine
        from .hud_keys import HudKeyStore
        from advanced_app import paths
        menu=builder_factory(self.assets,job.work/'advanced',self.emit,self.cancel)
        engine=LocalTranslationEngine(self.assets,paths()[1]/'shared-translation-engine',self.emit,cancel=self.cancel,
            payload_roots=[Path(sys.executable).parent/'translation-engine',
                           self.assets/'translation-engine',self.assets.parent/'translation-engine'])
        overlay=TranslationBuilder(self.assets,job.work/'translation',self.emit,cancel=self.cancel,sdk=30,engine=engine)
        overlay.keys=HudKeyStore(overlay.tools,paths()[1]/'translation-signing')
        return menu,overlay

    def _capture(self,job):
        root=self._root(job);before=self._snapshot(root)
        job.work.mkdir(parents=True,exist_ok=True);make_private(job.work,directory=True)
        raw=self._path(job,'installed.apk');source=self._path(job,'source.apk')
        raw.unlink(missing_ok=True);source.unlink(missing_ok=True)
        root.command('pull',before['path'],str(raw),timeout=300)
        self.check();make_private(raw)
        if sha256_file(raw,self.cancel)!=before['digest'] or self._snapshot(self._root(job))!=before:
            raise ValueError('APK thay đổi trong lúc lấy; sẽ lấy lại APK hiện tại.')
        if job.mode=='menu':
            from .advanced_patch import SOURCE_SHA256
            menu,_=self._builders(job)
            if before['digest']==SOURCE_SHA256:shutil.copyfile(raw,source)
            else:menu.recover_profile(raw,source)
            menu.verify_device_apk(raw,source)
        else:
            from scripts.hud_manifest import inspect_application
            from zipfile import ZipFile
            with ZipFile(raw) as apk:
                if inspect_application(apk.read('AndroidManifest.xml'))['package']!=PACKAGE:
                    raise ValueError('Tệp lấy về không phải DJI Fly.')
            shutil.copyfile(raw,source)
        self.check();make_private(source)
        return {'snapshot':before,'source':'source.apk','source_digest':sha256_file(source,self.cancel)}

    def _patch(self,job):
        source=self._path(job,job.payload['source'])
        if sha256_file(source,self.cancel)!=job.payload['source_digest']:raise ValueError('Nguồn tác vụ đã thay đổi.')
        menu,overlay=self._builders(job);result={};translation_source=source
        if job.mode=='menu':
            found=menu.latest()
            built=found if found else menu.build(source)
            checked=menu.verify(built['receipt'])
            result['menu']={**checked,'apk':str(Path(checked['apk']).relative_to(job.work)),
                            'receipt':str(Path(checked['receipt']).relative_to(job.work))}
            translation_source=Path(checked['apk'])
        if job.mode=='language' or job.translate:
            artifact=overlay.build(translation_source)
            result['overlay']={**artifact,'apk':str(Path(artifact['apk']).relative_to(job.work))}
        self.check();return result

    def _menu(self,job):
        menu,_=self._builders(job)
        value=menu.verify(self._path(job,job.payload['menu']['receipt']))
        if value['digest']!=job.payload['menu']['digest']:raise ValueError('APK menu không khớp tác vụ.')
        return {**value,'apk':Path(value['apk'])}

    def _overlay(self,job):
        declared=job.payload['overlay'];_,builder=self._builders(job)
        source=self._menu(job)['apk'] if job.mode=='menu' else self._path(job,job.payload['source'])
        value=builder.build(source)
        if (value['digest']!=declared['digest'] or value['source_digest']!=declared['source_digest']
            or value['package']!=declared['package'] or value['apk']!=self._path(job,declared['apk'])):
            raise ValueError('Overlay không khớp nguồn, chữ ký hoặc artifact đã kiểm chứng của tác vụ.')
        from .translation_install import AdaptiveTranslation
        before={'identity':(job.serial,job.serial,30),'digest':value['source_digest'],
                'version':job.payload['snapshot']['version'],'version_code':job.payload['snapshot']['code']}
        validator=AdaptiveTranslation(self.assets,job.work/'translation',self.emit,cancel=self.cancel,builder=builder)
        return validator._artifact(value,before)

    def _stage(self,job):
        root=self._root(job,True);remote='/data/local/tmp/rc2vi-clean-'+job.id
        self.check()
        command=('[ ! -L /data ] && [ ! -L /data/local ] && [ ! -L /data/local/tmp ] && '
            '[ ! -L '+remote+' ] && ( [ -d '+remote+' ] || (umask 077 && mkdir '+remote+') ) && '
            '[ "$(stat -c %u:%a '+remote+')" = 0:700 ] && printf STAGE_OK')
        if root.shell(command).strip()!='STAGE_OK':raise ValueError('Staging RC 2 không hợp lệ.')
        return remote

    def _cleared(self,job,root,remote):
        expected=job.id+':'+job.payload['snapshot']['digest']
        value=root.shell('if [ -f '+remote+'/clear.done ]; then [ "$(cat '+remote+'/clear.done)" = '
                         +shlex.quote(expected)+' ] && printf 1; else printf 0; fi').strip()
        if value not in {'0','1'}:raise ValueError('Mốc xóa dữ liệu không khớp tác vụ.')
        return value=='1'

    def _clear(self,job):
        if job.mode=='menu':self._menu(job)
        if job.mode=='language' or job.translate:self._overlay(job)
        root=self._root(job,True);remote=self._stage(job)
        if self._cleared(job,root,remote):return {}
        current=self._snapshot(root)
        if current['digest']!=job.payload['snapshot']['digest']:
            raise ValueError('APK trên tay đã thay đổi; chưa xóa dữ liệu.')
        self._write(root,'am force-stop '+PACKAGE)
        self.check()
        from .hud_backup import safe_roots_command
        sentinel='/data/user/0/'+PACKAGE+'/files/.rc2vi-clean-'+job.id
        public='/data/media/0/DJI/'+PACKAGE
        trash='/data/media/0/DJI/.rc2vi-delete-'+job.id
        checks=' && '.join('[ ! -L '+p+' ]' for p in ['/data/media','/data/media/0','/data/media/0/DJI',public])
        expected=shlex.quote(job.id+':'+current['digest'])
        # The app-data sentinel is deleted by pm clear itself. Its absence after
        # a recorded start proves that a lost reply must not cause another clear.
        command=('('+safe_roots_command()+' && '+checks+' && [ ! -L '+trash+' ] && '
            '[ ! -L /data/user/0/'+PACKAGE+'/files ] && [ ! -L '+sentinel+' ]) || exit 1; '
            'if [ ! -f '+remote+'/clear.app.done ]; then '
            'if [ ! -f '+remote+'/clear.started ]; then mkdir -p /data/user/0/'+PACKAGE+'/files || exit 1; '
            'printf %s '+expected+' > '+sentinel+' || exit 1; chmod 600 '+sentinel+' || exit 1; '
            'printf %s '+expected+' > '+remote+'/clear.started || exit 1; fi; '
            '[ "$(cat '+remote+'/clear.started)" = '+expected+' ] || exit 1; '
            'if [ -f '+sentinel+' ]; then pm clear --user 0 '+PACKAGE+' || exit 1; fi; '
            '[ ! -e '+sentinel+' ] && printf %s '+expected+' > '+remote+'/clear.app.done || exit 1; fi; '
            'if [ ! -f '+remote+'/public.done ]; then '
            'if [ ! -f '+remote+'/public.started ]; then '
            '[ ! -e '+trash+' ] || exit 1; '
            'if [ -d '+public+' ]; then stat -c %d:%i '+public+' > '+remote+'/public.tmp || exit 1; '
            'else printf ABSENT > '+remote+'/public.tmp || exit 1; fi; '
            'mv -f -- '+remote+'/public.tmp '+remote+'/public.started || exit 1; fi; '
            'rc2_old="$(cat '+remote+'/public.started)" || exit 1; '
            'if [ "$rc2_old" != ABSENT ]; then printf %s "$rc2_old" | grep -Eq "^[0-9]+:[1-9][0-9]*$" || exit 1; fi; '
            'if [ ! -f '+remote+'/public.moved ]; then '
            'if [ "$rc2_old" != ABSENT ]; then '
            'if [ ! -e '+trash+' ] && [ -d '+public+' ] && [ "$(stat -c %d:%i '+public+')" = "$rc2_old" ]; '
            'then mv -- '+public+' '+trash+' || exit 1; fi; fi; '
            'printf %s '+expected+' > '+remote+'/moved.tmp || exit 1; '
            'mv -f -- '+remote+'/moved.tmp '+remote+'/public.moved || exit 1; fi; '
            '[ "$(cat '+remote+'/public.moved)" = '+expected+' ] || exit 1; '
            'if [ "$rc2_old" != ABSENT ]; then '
            'if [ -e '+trash+' ]; then [ -d '+trash+' ] && [ "$(stat -c %d:%i '+trash+')" = "$rc2_old" ] || exit 1; '
            'rm -rf -- '+trash+' || exit 1; fi; fi; '
            '[ ! -e '+trash+' ] && printf %s '+expected+' > '+remote+'/public.done || exit 1; fi; '
            'printf %s '+expected+' > '+remote+'/clear.done || exit 1; chmod 600 '+remote+'/clear.done || exit 1; printf CLEARED')
        if not self._write(root,command).strip().endswith('CLEARED'):
            raise RuntimeError('Chưa xác nhận xóa dữ liệu DJI Fly; sẽ kiểm tra lại mốc trên tay.')
        return {}

    def _install(self,job):
        artifact=self._menu(job);root=self._root(job,True);remote=self._stage(job)
        if not self._cleared(job,root,remote):raise ValueError('Chưa có mốc xóa dữ liệu; không cài.')
        current=self._snapshot(root,False)
        if current and current['digest']==artifact['digest']:return {}
        if current and current['digest']!=job.payload['snapshot']['digest']:
            raise ValueError('Có APK khác xuất hiện trong lúc cài; chờ kiểm tra, không gỡ.')
        self.check();root.command('push',str(artifact['apk']),remote+'/candidate.apk',timeout=300)
        self.check()
        if root.shell('sha256sum '+remote+'/candidate.apk').split()[0]!=artifact['digest']:
            raise ValueError('APK gửi sang tay không khớp hash.')
        self._safe(root);self.check()
        result=self._write(root,'pm install -r --user 0 '+remote+'/candidate.apk',timeout=300)
        if result.strip()!='Success':
            if current and ('INSTALL_FAILED_UPDATE_INCOMPATIBLE' in result or 'INSTALL_FAILED_SHARED_USER_INCOMPATIBLE' in result):
                self._safe(root);self.check()
                if self._write(root,'pm uninstall '+PACKAGE).strip()!='Success':raise RuntimeError('Gỡ Fly chưa xong.')
                self.check();self._safe(root)
                result=self._write(root,'pm install --user 0 '+remote+'/candidate.apk',timeout=300)
            if result.strip()!='Success':raise RuntimeError('Cài APK chưa xong; đang đối chiếu trạng thái thực tế.')
        if self._snapshot(self._root(job))['digest']!=artifact['digest']:raise RuntimeError('Chưa đọc lại được APK vừa cài.')
        return {}

    def _language(self,job):
        from advanced_app import TranslationTransport
        from .translation_install import AdaptiveTranslation,known_overlays,_snapshot,_path,_hash
        artifact=self._overlay(job);root=self._root(job,True)
        if self._snapshot(root)['digest']!=artifact['source_digest']:raise ValueError('APK đích đã đổi trước khi dịch.')
        backend=self
        class GuardedWire(TranslationTransport):
            def bind(self,serial):
                if serial!=self.serial:raise ValueError('Serial bản dịch đã đổi.')
                return GuardedWire(self.pinned)
            def shell(self,command,**kwargs):
                backend.check()
                return backend._write(self.pinned,command,timeout=kwargs.get('timeout',90))
        wire=GuardedWire(root);_,builder=self._builders(job)
        backend=self
        class Deployment(AdaptiveTranslation):
            def _recover(self,*args,**kwargs):
                backend.check()
                return super()._recover(*args,**kwargs)
        adaptive=Deployment(self.assets,job.work/'translation',self.emit,cancel=self.cancel,builder=builder)
        before=_snapshot(wire)
        artifact=adaptive._artifact(artifact,before)
        if known_overlays(wire).get(artifact['package']):
            if _hash(wire,_path(wire,artifact['package']))!=artifact['digest']:
                raise ValueError('Gói tiếng Việt trên tay có hash khác tác vụ.')
            adaptive._readback(wire,before,artifact);return {}
        # Remove only recognized Fly translation overlays; no Fly data restoration.
        for package in known_overlays(wire):
            self.check();self._safe(root)
            if self._write(root,'pm uninstall --user 0 '+package,timeout=120).strip()!='Success':
                raise RuntimeError('Gỡ overlay cũ chưa hoàn tất.')
        self.check()
        with tempfile.TemporaryDirectory(prefix='clean-overlay-',dir=job.work) as folder:
            adaptive._deploy(wire,wire,_snapshot(wire),lambda:(self.check(),self._safe(root)),artifact,Path(folder))
        return {}

    def _verify(self,job):
        root=self._root(job)
        expected=job.payload['menu']['digest'] if job.mode=='menu' else job.payload['snapshot']['digest']
        if self._snapshot(root)['digest']!=expected:raise RuntimeError('APK cuối chưa khớp tác vụ.')
        if job.mode=='language' or job.translate:self._language(job)
        return {'verified':{'digest':expected}}

    def _cleanup(self,job):
        root=self._root(job);remote='/data/local/tmp/rc2vi-clean-'+job.id
        expected=job.payload.get('verified',{}).get('digest')
        if not isinstance(expected,str) or not HASH.fullmatch(expected):raise ValueError('Thiếu kết quả cuối đã kiểm chứng; giữ artifact để tiếp tục.')
        current=self._snapshot(root,False)
        if current is None or current['digest']!=expected:raise ValueError('Fly chưa được cài đúng; không xóa artifact khôi phục.')
        self.check()
        command=('[ ! -L /data ] && [ ! -L /data/local ] && [ ! -L /data/local/tmp ] && [ ! -L '+remote+' ] && '
            '( [ ! -e '+remote+' ] || ( [ "$(stat -c %u:%a '+remote+')" = 0:700 ] && rm -f -- '
            +remote+'/candidate.apk '+remote+'/clear.done '+remote+'/clear.started '+remote+'/clear.app.done '
            +remote+'/public.started '+remote+'/public.done '+remote+'/public.moved '+remote+'/public.tmp '
            +remote+'/moved.tmp && rmdir -- '+remote+' ) ) && printf CLEANED')
        if root.shell(command).strip()!='CLEANED':raise RuntimeError('Staging chưa dọn xong.')
        self.check()
        if job.work.exists():
            if job.work.name!=job.id or job.work.parent.name!='clean-tasks':raise ValueError('Phạm vi dọn PC không hợp lệ.')
            owner=guard_path(job.work/'.rc2-owner.json')
            if not owner.is_file() or json.loads(owner.read_text('utf-8'))!={'id':job.id,'serial':job.serial,'work':str(job.work)}:
                raise ValueError('Không có bằng chứng sở hữu thư mục; không xóa.')
            for path in job.work.rglob('*'):guard_path(path)
            shutil.rmtree(guard_path(job.work))
        return {}

    def execute(self,phase,job):
        self.check()
        operations={'capture':self._capture,'patch':self._patch,'clear':self._clear,'install':self._install,
                    'language':self._language,'verify':self._verify,'cleanup':self._cleanup}
        if phase not in operations:raise ValueError('Bước tác vụ không hợp lệ.')
        return operations[phase](job)
