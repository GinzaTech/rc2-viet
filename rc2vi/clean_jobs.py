"""One durable, private, serial-bound clean job; contains no Fly user data."""
from contextlib import contextmanager
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import re
import threading
import uuid

from .hud_backup import guard_path, make_private

PHASES=('capture','patch','clear','install','language','verify','cleanup','complete')
STATUSES={'active','stopped','complete'}


class JobError(ValueError):
    pass


@dataclass(frozen=True)
class Job:
    id:str
    serial:str
    mode:str
    translate:bool
    work:Path
    status:str='active'
    phase:str='capture'
    payload:dict=None
    attempts:int=0


class Journal:
    def __init__(self,root):
        self.root=guard_path(root)
        self.root.mkdir(parents=True,exist_ok=True);make_private(self.root,directory=True)
        self.path=self.root/'active.json';self._lock=threading.RLock()

    def _parse(self,record):
        fields={'schema','id','serial','mode','translate','work','status','phase','payload','attempts','wipe','grounded'}
        if (not isinstance(record,dict) or set(record)!=fields or record['schema']!=1
            or type(record['schema']) is not int or not isinstance(record['id'],str)
            or not re.fullmatch('[0-9a-f]{32}',record['id'])
            or not isinstance(record['serial'],str) or not re.fullmatch('[A-Za-z0-9_.:-]{1,128}',record['serial'])
            or record['mode'] not in {'menu','language'} or type(record['translate']) is not bool
            or record['status'] not in STATUSES or record['phase'] not in PHASES
            or not isinstance(record['payload'],dict) or type(record['attempts']) is not int
            or not 0<=record['attempts']<=2147483647 or record['wipe'] is not True or record['grounded'] is not True):
            raise JobError('Tệp tiến độ không hợp lệ; không cấp quyền xóa/cài từ tệp này.')
        work=guard_path(record['work'])
        if not Path(record['work']).is_absolute() or work.name!=record['id'] or work.parent.name!='clean-tasks':
            raise JobError('Thư mục tác vụ không khớp mã tác vụ.')
        if (record['status']=='complete') != (record['phase']=='complete'):
            raise JobError('Trạng thái hoàn thành không khớp tiến độ.')
        payload=record['payload'];hex64=lambda value:isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value)
        if record['phase']!='capture':
            if payload.get('source')!='source.apk' or not hex64(payload.get('source_digest')) or not hex64(payload.get('snapshot',{}).get('digest')):
                raise JobError('Mốc tác vụ thiếu nguồn APK đã lấy từ tay.')
        if record['phase'] not in {'capture','patch'}:
            if record['mode']=='menu' and not hex64(payload.get('menu',{}).get('digest')):raise JobError('Thiếu APK menu đã kiểm chứng.')
            if (record['mode']=='language' or record['translate']) and not hex64(payload.get('overlay',{}).get('digest')):
                raise JobError('Thiếu gói tiếng Việt đã kiểm chứng.')
        if record['phase'] in {'cleanup','complete'}:
            expected=payload['menu']['digest'] if record['mode']=='menu' else payload['snapshot']['digest']
            if payload.get('verified',{}).get('digest')!=expected:raise JobError('Thiếu kết quả cuối; không dọn artifact.')
        return Job(record['id'],record['serial'],record['mode'],record['translate'],work,
                   record['status'],record['phase'],record['payload'],record['attempts'])

    def load(self):
        with self._lock:
            if not self.path.exists():return None
            if self.path.stat().st_size>1024*1024:raise JobError('Tệp tiến độ vượt giới hạn.')
            try:record=json.loads(guard_path(self.path).read_text('utf-8'))
            except (ValueError,UnicodeError):raise JobError('Không đọc được tệp tiến độ; chưa thao tác trên tay.') from None
            job=self._parse(record)
            if job.status!='complete' and (self.root/('stop-'+job.id)).exists():job=replace(job,status='stopped')
            owner=self.root/('owned-'+job.id+'.json')
            if not owner.is_file():raise JobError('Thiếu bằng chứng sở hữu thư mục tác vụ.')
            binding=json.loads(guard_path(owner).read_text('utf-8'))
            if binding!={'id':job.id,'serial':job.serial,'work':str(job.work)}:
                raise JobError('Thư mục tác vụ đã bị đổi; không dọn hoặc thao tác thiết bị.')
            return job

    def _write(self,job):
        record={**job.__dict__,'work':str(job.work),'schema':1,'wipe':True,'grounded':True,'payload':job.payload or {}}
        self._parse(record)
        temporary=guard_path(self.root/('write-'+uuid.uuid4().hex+'.json'))
        try:
            with temporary.open('x',encoding='utf-8') as stream:
                make_private(temporary);json.dump(record,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,guard_path(self.path));make_private(self.path)
        finally:temporary.unlink(missing_ok=True)
        return job

    def create(self,serial,mode,work,*,translate,grounded,wipe):
        with self._lock:
            if grounded is not True or wipe is not True:raise JobError('Cần xác nhận hạ cánh và xóa dữ liệu DJI Fly.')
            current=self.load()
            if current and current.status!='complete':raise JobError('Đang có tác vụ chưa hoàn tất; tiếp tục đúng tác vụ đó.')
            identity=uuid.uuid4().hex
            job=Job(identity,serial,mode,translate,guard_path(work)/'clean-tasks'/identity,payload={})
            job.work.mkdir(parents=True,exist_ok=False);make_private(job.work,directory=True)
            owner=self.root/('owned-'+identity+'.json')
            with owner.open('x',encoding='utf-8') as stream:
                make_private(owner);json.dump({'id':identity,'serial':serial,'work':str(job.work)},stream)
                stream.flush();os.fsync(stream.fileno())
            local_owner=job.work/'.rc2-owner.json'
            local_owner.write_text(json.dumps({'id':identity,'serial':serial,'work':str(job.work)}),'utf-8')
            make_private(local_owner)
            return self._write(job)

    def update(self,job,**changes):
        with self._lock:
            current=self.load()
            if current is None or current.id!=job.id:raise JobError('Tác vụ đang chạy đã thay đổi.')
            if current.status=='stopped':changes={**changes,'status':'stopped'}
            return self._write(replace(current,**changes))

    def stop(self):
        with self._lock:
            job=self.load()
            if job and job.status!='complete':
                marker=guard_path(self.root/('stop-'+job.id))
                with marker.open('w',encoding='ascii') as stream:
                    make_private(marker);stream.write(job.id);stream.flush();os.fsync(stream.fileno())
                return self._write(replace(job,status='stopped'))
            return job

    def resume(self,identity):
        with self._lock:
            job=self.load()
            if job is None or job.id!=identity or job.status=='complete':raise JobError('Không có đúng tác vụ để tiếp tục.')
            guard_path(self.root/('stop-'+identity)).unlink(missing_ok=True)
            return self._write(replace(job,status='active'))

    @contextmanager
    def lease(self):
        import msvcrt
        path=guard_path(self.root/'dispatch.lock')
        with path.open('a+b') as stream:
            make_private(path)
            if stream.tell()==0:stream.write(b'0');stream.flush()
            stream.seek(0)
            try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise JobError('Một phiên app khác đang sở hữu tác vụ; chờ phiên đó đóng.') from None
            try:yield
            finally:
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
