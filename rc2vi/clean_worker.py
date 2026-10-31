"""Desktop connection owner for durable clean jobs; Stop differs from closing."""
import threading
import subprocess
from pathlib import Path

from advanced_app import AdvancedWorker, paths, friendly_error
from .clean_jobs import Journal, JobError
from .clean_workflow import Coordinator, TaskStopped, TaskSuspended
from .clean_backend import CleanBackend


class CleanWorker(AdvancedWorker):
    clean_workflow=True
    def __init__(self,*args,journal=None,clean_backend_factory=CleanBackend,**kwargs):
        super().__init__(*args,**kwargs)
        self.journal=journal or Journal(paths()[1]/'workflow')
        self.clean_backend_factory=clean_backend_factory
        try:pending=self.journal.load()
        except JobError as error:
            pending=None;self.emit('error',str(error))
        self.can_resume=bool(pending and pending.status=='stopped')
        self.pending_serial=pending.serial if pending and pending.status!='complete' else ''

    def _pending_state(self,job):
        self.pending_serial=job.serial
        self.emit('pending_state',{'serial':job.serial,'work':str(job.work.parent.parent),
                                   'translate':job.translate,'mode':job.mode,'phase':job.phase})

    def _guard(self,serial):
        # Recovery must remain possible while Fly is absent after uninstall.
        self._check()
        if (self.selected!=serial or self.connection is None or self.adb is None
            or self.connection.device.serial!=serial or not self.connection.alive()):
            raise ConnectionError('Chờ kết nối đúng RC 2 đã chọn.')
        root=self.pin_factory(self.adb,serial)
        if (root.command('get-state',timeout=10).strip()!='device'
            or root.shell('getprop ro.serialno').strip()!=serial
            or root.shell('getprop ro.product.model').replace('_',' ').strip()!='DJI RC 2'
            or root.shell('getprop ro.product.device').strip()!='rc331'
            or root.shell('getprop ro.build.version.sdk').strip()!='30'
            or not root.shell('id').startswith('uid=0(')):
            raise ValueError('Cần đúng RC 2 / SDK30 / root / serial đã chọn.')
        self._check();return root

    def _root_provider(self,serial):
        try:
            self._connect(serial)
            return self._guard(serial)
        except (OSError,RuntimeError,ValueError,subprocess.TimeoutExpired):
            self._drop_transport()
            raise

    def _drop_transport(self):
        if self.connection:self.connection.close()
        self.connection=self.adb=None

    def resume_pending(self,automatic=True):
        with self._lock:
            try:job=self.journal.load()
            except JobError as error:self.emit('error',str(error));return False
            if self.busy or self.closing or job is None or job.status=='complete':return False
            if job.status=='stopped' and automatic:
                self.can_resume=True;self._pending_state(job)
                self.emit('stopped','Tác vụ đã Stop; bấm Tiếp tục để chạy lại.');return False
            if not automatic:job=self.journal.resume(job.id)
            self.work=job.work.parent.parent;self.selected=job.serial
            self.pending_serial=job.serial
            self.busy=True;self.stop_event.clear();self.can_resume=False
            self.emit('resume_state',{'serial':job.serial,'work':str(self.work),'translate':job.translate,
                                      'mode':job.mode,'phase':job.phase})
            self.thread=threading.Thread(target=self._run_clean,name='RC2-clean-workflow',daemon=False)
            self.thread.start();return True

    def request(self,operation,serial='',*,grounded=False,translate=True,wipe=False):
        if operation not in {'install','translate','resume'}:
            return super().request(operation,serial,grounded=grounded,translate=translate)
        with self._lock:
            if self.busy or self.closing:return False
            if grounded is not True or wipe is not True:
                self.emit('warning','Xác nhận đã hạ cánh và đồng ý xóa dữ liệu DJI Fly trước khi chạy.');return False
            if operation=='resume':
                job=self.journal.load()
                if job is None or job.serial!=serial:
                    self.emit('warning','Chọn đúng RC 2 của tác vụ đã Stop.');return False
                return self.resume_pending(automatic=False)
            try:
                pending=self.journal.load()
                if pending and pending.status!='complete':
                    self.can_resume=True;self._pending_state(pending)
                    self.emit('warning','Đang có tác vụ trên RC 2 '+pending.serial+'. Bấm Tiếp tục để hoàn tất tác vụ đó.')
                    return False
                self.space_check(self.work)
                self.journal.create(serial,'menu' if operation=='install' else 'language',self.work,
                                    translate=translate if operation=='install' else True,
                                    grounded=grounded,wipe=wipe)
            except Exception as error:
                self.emit('error',friendly_error(error));return False
            return self.resume_pending()

    def _run_clean(self):
        try:
            backend=self.clean_backend_factory(self.assets,self._root_provider,lambda:None,self.emit,self.stop_event)
            runner=Coordinator(self.journal,backend,self.stop_event,self.emit,suspended=lambda:self.closing)
            backend.check=runner.check
            while True:
                runner.check()
                try:
                    with self.journal.lease():result=runner.run()
                    break
                except JobError as error:
                    runner.check();self.emit('retry',str(error)+' Đang chờ và thử lại…');self.stop_event.wait(3)
            self.emit('ready','Đã xóa dữ liệu Fly, hoàn tất patch/cài/đọc lại và dọn tệp tạm của tác vụ.')
            self.pending_serial='';self.can_resume=False
        except TaskStopped:
            self.can_resume=True
            self.emit('stopped','Đã Stop và lưu tiến độ. Tác vụ sẽ không tự chạy lại.')
        except TaskSuspended:
            self.emit('paused','Đã lưu tiến độ; lần mở app sau sẽ kiểm tra và tự tiếp tục.')
        except Exception as error:
            try:
                pending=self.journal.load()
                self.can_resume=bool(pending and pending.status!='complete')
                if self.can_resume:self._pending_state(pending)
            except JobError:self.can_resume=False
            self.emit('error',friendly_error(error))
        finally:
            try:self._drop_transport()
            except Exception as error:self.emit('warning',friendly_error(error))
            with self._lock:self.busy=False
            self.emit('idle','')

    def cancel(self):
        self.stop_event.set()
        try:
            stopped=self.journal.stop();self.can_resume=bool(stopped and stopped.status=='stopped')
        except JobError as error:self.emit('error',str(error));self.can_resume=False
        with self._lock:
            if self._opening_connection and self.connection and getattr(self.connection,'relay',None):
                self.connection.relay.stop_event.set()

    def close(self):
        with self._lock:
            self.closing=True;self.stop_event.set()
            if self._opening_connection and self.connection and getattr(self.connection,'relay',None):
                self.connection.relay.stop_event.set()
            if not self.busy:self._drop_transport()
