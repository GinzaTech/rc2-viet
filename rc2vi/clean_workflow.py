"""Durable checkpoints and retries; every side effect is reconciled by the backend."""
from .clean_jobs import PHASES


class TaskStopped(RuntimeError):
    pass


class TaskSuspended(RuntimeError):
    pass


class Coordinator:
    def __init__(self,journal,backend,cancel,emit,*,wait=None,suspended=lambda:False):
        self.journal,self.backend,self.cancel,self.emit=journal,backend,cancel,emit
        self.wait=wait or cancel.wait;self.suspended=suspended

    def check(self):
        job=self.journal.load()
        if job is None:raise TaskStopped('Không còn tác vụ hiện tại.')
        if job.status=='stopped':raise TaskStopped('Đã Stop tác vụ; không tự chạy lại.')
        if self.suspended():raise TaskSuspended('Đóng app; giữ tiến độ để tiếp tục lần mở sau.')
        if self.cancel.is_set():raise TaskStopped('Đã Stop tác vụ.')
        return job

    @staticmethod
    def _next(job):
        phase=PHASES[PHASES.index(job.phase)+1]
        if phase=='install' and job.mode=='language':phase='language'
        if phase=='language' and job.mode=='menu' and not job.translate:phase='verify'
        return phase

    def run(self):
        while True:
            job=self.check()
            if job.status=='complete':return job
            try:
                self.emit('phase',job.phase)
                addition=self.backend.execute(job.phase,job) or {}
                self.check()
                phase=self._next(job)
                result=self.journal.update(job,phase=phase,status='complete' if phase=='complete' else 'active',
                                           payload={**job.payload,**addition},attempts=0)
                if result.status=='complete':return result
            except (TaskStopped,TaskSuspended):raise
            except Exception as error:
                self.check()
                attempt=min(job.attempts+1,2147483647)
                self.journal.update(job,attempts=attempt)
                message=str(error)[:600] or type(error).__name__
                self.emit('retry',f'Bước {job.phase} chưa xong: {message}. Đang kiểm tra lại trạng thái và tiếp tục…')
                self.wait(min(30,2**min(attempt,5)))
