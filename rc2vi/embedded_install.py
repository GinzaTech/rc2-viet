"""Serial-bound deployment of the reviewed APK, with resumable verified chunks.

Invoked only for the user's authorized install on this RC2. No flight commands,
key replacement, authorisation bypass, firmware edits or broad filesystem cleanup.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys
import threading
import time

from advanced_app import private_connection, discover_rc2, pin_adb, TranslationTransport
from rc2vi.hud_tools import sha256_file
from rc2vi.core import validate_package_path
from rc2vi.fly_versions import for_identity

PACKAGE='dji.go.v5'
SUPPORTED_APK='79161774ff7f404665ee1a5326b9616de23e244962206e00144f8ef58bc45f68'
TARGET_VERSION='1.21.10'
TARGET_CODE=3115981


class DeploymentValidationError(ValueError):
    """A confirmed package/metadata mismatch cannot be repaired by USB retries."""


class DeviceUiWait(RuntimeError):
    """An activity transition/sleep is not a lost USB connection."""


class OpeningCancel:
    """Interrupt a pending Allow wait without marking the whole job stopped."""
    def __init__(self,cancel,reconnect):
        self.cancel,self.reconnect=cancel,reconnect

    def is_set(self):
        return bool((self.cancel is not None and self.cancel.is_set())
                    or (self.reconnect is not None and self.reconnect.is_set()))

    __call__=is_set


class LoggedRoot:
    """Record requests and outcomes, never binary output or authorization keys."""
    def __init__(self,root,trace):self.root,self.trace=root,trace
    def __getattr__(self,name):return getattr(self.root,name)
    def shell(self,command,**kwargs):
        return self.trace('shell',[command],lambda:self.root.shell(command,**kwargs))
    def command(self,*args,**kwargs):
        return self.trace('command',list(args),lambda:self.root.command(*args,**kwargs))


def package_version(dump):
    text=dump.replace('\r\n','\n')
    section=re.search(r'(?ms)^Packages:[ \t]*\n(.*?)(?=^\S|\Z)',text)
    if not section:
        raise DeploymentValidationError('Không đọc được mục Packages của DJI Fly; xem package-version.txt')
    blocks=re.split(r'(?m)^[ \t]+Package \[',section.group(1))[1:]
    matching=[b for b in blocks if b.startswith(PACKAGE+']')]
    if len(matching)!=1:
        raise DeploymentValidationError('Không xác định được gói DJI Fly đang hoạt động; xem package-version.txt')
    names=re.findall(r'(?m)^[ \t]+versionName=([^\n]*)$',matching[0])
    codes=re.findall(r'(?m)^[ \t]+versionCode=(\d+)(?=[ \t]|$)',matching[0])
    if len(names)!=1 or len(codes)!=1 or not names[0].strip() or names[0].strip()=='null':
        raise DeploymentValidationError('Thiếu hoặc mơ hồ thông tin phiên bản DJI Fly; xem package-version.txt')
    return names[0].strip(),int(codes[0])


def emit(state,message):
    if sys.stdout is not None:
        print(json.dumps({'state':state,'message':message},ensure_ascii=True),flush=True)


class Deployment:
    def __init__(self,apk,assets,work,serial,*,grounded=False,allow_data_reset=False,connect_only=False,
                 expected_digest=None,source_digest=None,cancel=None,cleanup=False,stop_file=None,
                 target_version=TARGET_VERSION,target_code=TARGET_CODE,reconnect_event=None,enable_displayport=False):
        if not re.fullmatch('[A-Za-z0-9_.:-]{1,128}',serial):raise ValueError('Serial không hợp lệ')
        if not connect_only and not grounded:
            raise ValueError('Cần xác nhận đã hạ cánh và động cơ dừng')
        self.allow_data_reset=bool(allow_data_reset)
        self.enable_displayport=bool(enable_displayport)
        target=for_identity(target_version,target_code)
        self.target_version,self.target_code=target.version,target.code
        self.serial=serial;self.assets=Path(assets);self.work=Path(work).absolute()
        self.work.mkdir(parents=True,exist_ok=True)
        self.report=self.work/'install-result.json';self.events=self.work/'install-events.jsonl'
        self.trace_path=self.work/'adb-commands.jsonl';self.trace_lock=threading.Lock()
        self.connect_only=connect_only
        self.apk=Path(apk) if apk else None;self.digest=expected_digest or SUPPORTED_APK
        if not re.fullmatch('[0-9a-f]{64}',self.digest):raise ValueError('Hash APK đích không hợp lệ')
        if source_digest is not None and not re.fullmatch('[0-9a-f]{64}',source_digest):raise ValueError('Hash nguồn không hợp lệ')
        self.source_digest=source_digest;self.cancel=cancel;self.cleanup=cleanup
        self.reconnect_event=reconnect_event
        self.needs_reconnect=False
        self.stop_file=Path(stop_file) if stop_file is not None else None
        if not connect_only and sha256_file(self.apk)!=self.digest:
            raise ValueError('APK không đúng bản 2 mục tích hợp tiếng Việt đã kiểm chứng')
        self.remote='/data/local/tmp/rc2vi-embedded-'+self.digest[:16]
        self.connection=None;self.root=None;self.deadline=time.monotonic()+600
        self.status={'apk':str(self.apk),'digest':self.digest,'serial':self.serial,
                     'status':'preparing','chunks_verified':0,'installed_verified':False,
                     'target_version':self.target_version,'target_code':self.target_code}
        if self.report.is_file() and self.report.stat().st_size < 1024*1024:
            previous=json.loads(self.report.read_text('utf-8'))
            if previous.get('digest')==self.digest and previous.get('serial')==self.serial:
                for field in ('original','uninstall_authorized_started'):
                    if field in previous:self.status[field]=previous[field]
        self.parts=[]
        if not connect_only:
            with self.apk.open('rb') as src:
                while data:=src.read(16*1024*1024):
                    self._check_stop()
                    name='part-'+str(len(self.parts)).zfill(4)
                    p=self.work/name;p.write_bytes(data)
                    self.parts.append((name,p,hashlib.sha256(data).hexdigest()))
        self.save()

    def emit(self,state,message):
        with self.events.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'state':state,'message':message},ensure_ascii=False)+'\n')
        emit(state,message)

    def save(self):
        temporary=self.report.with_name(self.report.name+'.tmp')
        with temporary.open('w',encoding='utf-8') as stream:
            json.dump(self.status,stream,ensure_ascii=False,indent=2)
            stream.flush();os.fsync(stream.fileno())
        temporary.replace(self.report)

    def trace(self,kind,args,operation):
        request={'time':time.time(),'thread':threading.current_thread().name,'kind':kind,
                 'arguments':[str(arg)[:2048] for arg in args],'result':'started'}
        def record(value):
            with self.trace_lock,self.trace_path.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(value,ensure_ascii=False)+'\n')
        record(request)
        try:
            value=operation()
        except BaseException as error:
            record({**request,'time':time.time(),'result':'failed','error':type(error).__name__+': '+str(error)[:300]})
            raise
        record({**request,'time':time.time(),'result':'complete'})
        return value

    def close(self):
        connection=self.connection
        self.connection=self.root=None
        if connection:connection.close()

    def _check_stop(self):
        if ((self.work/'STOP').exists() or (self.stop_file is not None and self.stop_file.exists())
                or (self.cancel is not None and self.cancel.is_set())):
            if self.cancel is not None:self.cancel.set()
            raise InterruptedError('Đã dừng trước bước tiếp theo')

    def root_guard(self,mutating=False):
        command=('[ "$(getprop ro.serialno)" = '+shlex.quote(self.serial)+' ] && '
                 '[ "$(getprop ro.product.model | tr _ \' \')" = \'DJI RC 2\' ] && '
                 '[ "$(getprop ro.product.device)" = rc331 ] && '
                 '[ "$(getprop ro.build.version.sdk)" = 30 ] && [ "$(id -u)" = 0 ] || '
                 '{ printf RC2_WRONG_IDENTITY; exit 1; }; ')
        if mutating:
            command+=('rc2fg="$(dumpsys activity activities | grep mResumedActivity)"; '
                      '[ -n "$rc2fg" ] || { printf RC2_FOREGROUND_UNKNOWN; exit 1; }; '
                      'case "$rc2fg" in *dji.go.v5/*) printf RC2_WAIT_ANDROID_SETTINGS_FLY_IS_OPEN; exit 1;; esac; ')
        return command

    def connect(self):
        self._check_stop()
        if self.connection and self.connection.alive():return
        self.close()
        devices=[d for d in discover_rc2() if d.serial==self.serial]
        if len(devices)!=1:raise ConnectionError('RC2 not enumerated by Windows')
        if self.needs_reconnect:
            self.emit('reconnecting','Đã thấy RC 2 trở lại; đang tạo phiên ADB mới để xin quyền USB lại nếu tay yêu cầu.')
        self.status['connection_attempts']=self.status.get('connection_attempts',0)+1
        self.save()
        self.connection=private_connection(devices[0],self.assets,self.emit)
        if hasattr(self.connection,'bind_cancel'):
            if hasattr(self.connection,'bind_reconnect'):
                self.connection.bind_cancel(OpeningCancel(self.cancel,None))
                self.connection.bind_reconnect(self.reconnect_event)
            else:
                self.connection.bind_cancel(OpeningCancel(self.cancel,self.reconnect_event))
        adb=self.connection.open();self.root=LoggedRoot(pin_adb(adb,self.serial),self.trace)
        if self.root.shell(self.root_guard()+'printf RC2_ID_OK',timeout=15).strip()!='RC2_ID_OK':
            raise DeploymentValidationError('Không xác minh được đúng RC 2/model/SDK30/root')
        self.emit('identity','Verified RC2 serial/model/SDK30/root')
        self.needs_reconnect=False
        foreground=self.root.shell('dumpsys activity activities | grep mResumedActivity',timeout=10)
        self.status['foreground']=foreground.strip();self.save()
        if not self.connect_only and 'dji.go.v5/com.dji.mainpageui.device.DJIDeviceActivity' in foreground:
            # Fresh install mode carries explicit grounded consent. Navigate only
            # from Fly's home activity; never take over an FPV/flight activity.
            self.emit('settings','Đang mở Android Settings từ màn hình chính Fly để cài APK')
            self.shell('am start -a android.settings.SETTINGS',mutating=False)

    def shell(self,command,timeout=30,mutating=True):
        self._check_stop()
        marker='RC2_EMBED_COMMAND_OK'
        result=self.root.shell(self.root_guard(mutating)+command+' && printf "\n'+marker+'\n"',timeout=timeout)
        lines=result.strip().splitlines()
        if not lines or lines[-1]!=marker:
            if result.strip() in {'RC2_FOREGROUND_UNKNOWN','RC2_WAIT_ANDROID_SETTINGS_FLY_IS_OPEN'}:
                raise DeviceUiWait(result.strip())
            raise RuntimeError('Command not confirmed: '+result[-400:])
        return '\n'.join(lines[:-1]).strip()

    def retry(self,operation,label):
        while time.monotonic()<self.deadline:
            self._check_stop()
            if self.reconnect_event is not None and self.reconnect_event.is_set():
                self.reconnect_event.clear()
                self.close();self.needs_reconnect=True
                self.deadline=time.monotonic()+600
                self.emit('reconnecting','Đang đóng phiên ADB cũ và yêu cầu kết nối USB lại; giữ nguyên tiến độ.')
            try:
                self.connect();return operation()
            except DeploymentValidationError as error:
                self.status.update(status='blocked',phase=label,last_error=str(error));self.save()
                self.emit('blocked',str(error))
                raise
            except DeviceUiWait as error:
                self._check_stop()
                self.status.update(status='waiting_ui',last_error=str(error),phase=label);self.save()
                self.emit('waiting_ui','Đang chờ Launcher/Settings ổn định trên RC 2; giữ kết nối và tiến độ.')
                if str(error)=='RC2_FOREGROUND_UNKNOWN':
                    # A plain WAKEUP never unlocks the device, accepts USB
                    # authorization or changes persistent power settings. The
                    # next attempt must still pass the full foreground guard.
                    try:
                        power=self.root.shell(self.root_guard(False)+'dumpsys power | grep mWakefulness',timeout=10)
                        if 'mWakefulness=Asleep' in power:
                            self._check_stop()
                            self.root.shell(self.root_guard(False)+'input keyevent 224',timeout=10)
                    except Exception as failure:
                        self._check_stop()
                        self.close();self.needs_reconnect=True
                        self.emit('retry',label+': '+str(failure)[:300])
                if self.cancel is not None:self.cancel.wait(2)
                else:time.sleep(2)
            except Exception as error:
                self._check_stop()
                if self.reconnect_event is not None and self.reconnect_event.is_set():
                    continue
                self.emit('retry',label+': '+type(error).__name__+': '+str(error)[:500])
                self.status.update(status='retry',last_error=str(error)[:500],phase=label);self.save()
                self.close();self.needs_reconnect=True
                if self.cancel is not None:self.cancel.wait(2)
                else:time.sleep(2)
        raise TimeoutError('USB did not remain usable within the bounded install attempt')

    def snapshot(self):
        path=self.shell('pm path '+PACKAGE,mutating=False)
        if not path:return None
        if not path.startswith('package:') or '\n' in path:raise ValueError('Unexpected package APK layout')
        path=validate_package_path(path[8:])
        digest=self.shell('sha256sum '+shlex.quote(path),timeout=45,mutating=False).split()[0]
        if not re.fullmatch('[0-9a-f]{64}',digest):
            raise DeploymentValidationError('Hash APK DJI Fly hiện tại không hợp lệ')
        # Keep section headings to distinguish active and hidden system copies,
        # while transferring only package identity/version fields over USB.
        info=self.shell('dumpsys package '+PACKAGE+
            " | grep -E '^[^[:space:]]|^[[:space:]]+Package \\[|^[[:space:]]+version(Code|Name)='",mutating=False)
        (self.work/'package-version.txt').write_text(info[:256*1024],'utf-8')
        version,code=package_version(info)
        observed={'version':version,'code':code,'digest':digest}
        if self.connect_only:
            # During source discovery there is no selected APK yet. Do not
            # advertise the legacy constructor's default 1.21.10 as a target.
            try:selected=for_identity(version,code)
            except ValueError as error:raise DeploymentValidationError(str(error)) from error
            self.target_version,self.target_code=selected.version,selected.code
            self.status.update(target_version=selected.version,target_code=selected.code)
        if self.status.get('observed_package')!=observed:
            self.status['observed_package']=observed;self.save()
            self.emit('version',f'DJI Fly hiện tại: {version} (code {code}); APK đích: {self.target_version} (code {self.target_code})')
        if digest==self.digest and (version!=self.target_version or code!=self.target_code):
            raise DeploymentValidationError(f'Hash APK đích đúng nhưng phiên bản đọc lại khác: {version} / {code}')
        return {'path':path,'digest':digest,'version':version,'code':code}

    def stage(self):
        remote=self.remote
        return self.shell('[ ! -L /data ] && [ ! -L /data/local ] && [ ! -L /data/local/tmp ] && '
            '[ ! -L '+remote+' ] && ( [ -d '+remote+' ] || (umask 077; mkdir '+remote+') ) && '
            '[ "$(stat -c %u:%a '+remote+')" = 0:700 ] && printf STAGE_OK')

    def push_part(self,name,path,digest):
        self.stage()
        remote=self.remote+'/'+name
        found=self.shell('if [ -f '+remote+' ] && [ ! -L '+remote+' ]; then sha256sum '+remote+'; fi')
        if found.split()[:1]==[digest]:return
        self.shell('[ ! -L '+remote+' ] && [ ! -L '+remote+'.upload ] && printf SAFE')
        # APK entries are already compressed. Avoid SYNC compression negotiation
        # and exercise the ordinary, correctly terminated USB data path.
        self._check_stop()
        self.root.command('push','-Z',str(path),remote+'.upload',timeout=90)
        found=self.shell('sha256sum '+remote+'.upload',timeout=20).split()[0]
        if found!=digest:raise ValueError('Uploaded chunk hash differs')
        self.shell('chmod 600 '+remote+'.upload && mv -f '+remote+'.upload '+remote)

    def assemble(self):
        self.stage();candidate=self.remote+'/candidate.apk'
        found=self.shell('if [ -f '+candidate+' ] && [ ! -L '+candidate+' ]; then sha256sum '+candidate+'; fi',timeout=45)
        if found.split()[:1]==[self.digest]:return
        names=' '.join(self.remote+'/'+n for n,_,_ in self.parts)
        self.shell('[ ! -L '+candidate+' ] && [ ! -L '+candidate+'.tmp ] && cat '+names+
                   ' > '+candidate+'.tmp && chmod 600 '+candidate+'.tmp && mv -f '+candidate+'.tmp '+candidate,timeout=90)
        assert self.shell('sha256sum '+candidate,timeout=45).split()[0]==self.digest

    def install(self):
        current=self.snapshot()
        if current and current['digest']==self.digest:return
        if current is None:
            if not self.status.get('uninstall_authorized_started'):
                raise ValueError('Fly absent before this installer initiated an update')
        elif current['digest']!=self.status['original']['digest']:
            raise ValueError('Fly APK changed since this install started')
        candidate=self.remote+'/candidate.apk'
        assert self.shell('sha256sum '+candidate,timeout=45).split()[0]==self.digest
        result=self.shell('(pm install -r --user 0 '+candidate+' 2>&1; true)',timeout=180)
        if result.strip()!='Success':
            replace_errors=('INSTALL_FAILED_UPDATE_INCOMPATIBLE','INSTALL_FAILED_SHARED_USER_INCOMPATIBLE',
                            'INSTALL_FAILED_VERSION_DOWNGRADE')
            if not any(reason in result for reason in replace_errors):
                raise DeploymentValidationError(result)
            if not self.allow_data_reset:
                raise DeploymentValidationError('Bản Fly cần gỡ/cài lại; chưa được phép xóa dữ liệu. Giữ nguyên bản đang cài. '+result)
            self.status['uninstall_authorized_started']=True;self.save()
            if self.shell('pm uninstall '+PACKAGE,timeout=90).strip()!='Success':raise RuntimeError('Uninstall not confirmed')
            result=self.shell('(pm install --user 0 '+candidate+' 2>&1; true)',timeout=180)
            if result.strip()!='Success':raise RuntimeError(result)
        assert self.snapshot()['digest']==self.digest

    def enable_displayport_if_requested(self):
        if not self.enable_displayport:return
        from .displayport_access import enable_session
        try:
            self.status['displayport_permission']=enable_session(self,self.digest)
        except Exception as error:
            self.status['displayport_permission']={'status':'not_enabled','error':str(error)}
            self.emit('feature_warning','Đã cài APK; chưa kích hoạt quyền nút xuất hình: '+str(error))
        self.save()

    def cleanup_verified_stage(self):
        if not self.status.get('installed_verified') or self.status.get('final',{}).get('digest')!=self.digest:
            raise DeploymentValidationError('Chưa xác minh APK cuối; giữ các phần để tiếp tục.')
        if ((self.cancel is not None and self.cancel.is_set())
                or (self.stop_file is not None and self.stop_file.exists())):
            self.status['staging_cleanup']='DEFERRED';self.save();return
        remote=self.remote
        command=('[ ! -L /data ] && [ ! -L /data/local ] && [ ! -L /data/local/tmp ] && '
                 '[ ! -L '+remote+' ] && if [ -d '+remote+' ]; then '
                 '[ "$(stat -c %u:%a '+remote+')" = 0:700 ] && (cd -- '+remote+
                 ' && rm -f -- candidate.apk candidate.apk.tmp && for rc2part in '+
                 ' '.join(name for name,_,_ in self.parts)+
                 '; do rm -f -- "$rc2part" "$rc2part.upload" || exit 1; done) && rmdir -- '+remote+'; fi')
        self.emit('cleanup','Đang dọn các phần truyền của tác vụ đã cài thành công…')
        try:
            self.shell(command,timeout=20,mutating=False)
            for _,path,_ in self.parts:path.unlink(missing_ok=True)
            self.status['staging_cleanup']='PASS'
        except Exception as error:
            self.status['staging_cleanup']='DEFERRED'
            self.emit('warning','APK đã cài đúng; chưa dọn hết phần truyền tạm: '+str(error)[:250])
        self.save()

    def run(self):
        try:
            if self.connect_only:
                self.deadline=time.monotonic()+120
                self.retry(lambda:None,'request_usb_permission')
                self.status.update(status='usb_connected',usb_permission_and_identity_verified=True)
                self.save();return
            original=self.retry(self.snapshot,'read_original')
            if (original and self.source_digest is not None
                    and original['digest'] not in {self.source_digest,self.digest}):
                raise DeploymentValidationError('APK trên tay đã đổi sau khi lấy nguồn; chưa truyền hoặc thay Fly.')
            if original is None:
                if not self.status.get('uninstall_authorized_started') or not self.status.get('original'):
                    raise ValueError('Fly not installed on initial inspection')
                original=self.status['original']
            if not re.fullmatch('[0-9a-f]{64}',original['digest']):raise ValueError('APK hash không hợp lệ')
            if original['digest']==self.digest:
                self.status.update(status='installed',installed_verified=True,original=original,final=original)
                self.save()
                self.enable_displayport_if_requested()
                if self.cleanup:self.cleanup_verified_stage()
                return
            self.status.update(original=original,status='uploading');self.save()
            for number,(name,path,digest) in enumerate(self.parts,1):
                self.retry(lambda:self.push_part(name,path,digest),'upload_'+name)
                self.status['chunks_verified']=number;self.save()
                self.emit('upload',f'{number}/{len(self.parts)} chunks verified')
            self.retry(self.assemble,'assemble')
            self.status['status']='installing';self.deadline=time.monotonic()+900;self.save()
            self.retry(self.install,'install')
            final=self.retry(self.snapshot,'verify')
            assert final['digest']==self.digest
            self.status.update(status='installed',installed_verified=True,final=final);self.save()
            self.enable_displayport_if_requested()
            if self.cleanup:self.cleanup_verified_stage()
            self.emit('installed',str(final))
        finally:
            self.close();self.save()


