"""One connection from source capture through verified installation, with resume."""
import json
from pathlib import Path
import re
import threading
import time
import uuid

from .auto_patch import AutoPatchBuilder, atomic_json
from .fly_versions import for_identity
from .embedded_install import Deployment, DeploymentValidationError
from .hud_backup import guard_path, make_private
from .hud_tools import sha256_file, check_cancel
from .transport import UsbLease

HASH = re.compile('[0-9a-f]{64}')


class StopFileWatch:
    """Wake cancellation even inside a pending USB authorization request."""
    def __init__(self, path, cancel):
        self.path, self.cancel = path, cancel
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.run, name='RC2-stop-watch', daemon=True)

    def start(self):
        self.thread.start()

    def run(self):
        while not self.stopping.wait(0.1):
            if self.path.exists():
                self.cancel.set()
                return

    def close(self):
        self.stopping.set()
        self.thread.join(timeout=1)


class IdleHeartbeat:
    """Read identity while PC tools run; no settings or aircraft mutations."""
    def __init__(self, root, serial, cancel, stop_file, emit, interval=2):
        self.root, self.serial, self.cancel = root, serial, cancel
        self.stop_file, self.emit, self.interval = stop_file, emit, interval
        self.stopping = threading.Event()
        self.successes = 0
        self.thread = threading.Thread(target=self.run, name='RC2-build-keepalive', daemon=True)

    def start(self):
        self.thread.start()

    def run(self):
        while not self.stopping.wait(self.interval):
            if self.stop_file.exists():
                self.cancel.set()
            if self.cancel.is_set():
                return
            try:
                if self.root.shell('getprop ro.serialno', timeout=4).strip() != self.serial:
                    raise ValueError('Serial kết nối thay đổi trong lúc dựng APK.')
                self.successes += 1
            except Exception:
                if not self.cancel.is_set():
                    self.emit('warning', 'Phiên USB gián đoạn trong lúc dựng APK; bộ cài sẽ kiểm tra và nối lại trước khi cài.')
                return

    def close(self):
        self.stopping.set()
        self.thread.join(timeout=6)
        if self.thread.is_alive():
            raise RuntimeError('Chưa kết thúc được phiên kiểm tra USB; chưa bắt đầu cài APK.')


class AutoPatchRun:
    def __init__(self, assets, work, serial, emit=lambda *args: None, cancel=None,
                 builder_factory=AutoPatchBuilder, deployment_factory=Deployment,reconnect_event=None):
        if not re.fullmatch('[A-Za-z0-9_.:-]{1,128}', serial):
            raise ValueError('Serial RC 2 không hợp lệ.')
        self.assets, self.work = Path(assets), guard_path(Path(work).absolute())
        self.serial, self.callback = serial, emit
        self.cancel = cancel if cancel is not None else threading.Event()
        self.reconnect_event = reconnect_event if reconnect_event is not None else threading.Event()
        self.builder_factory, self.deployment_factory = builder_factory, deployment_factory
        self.work.mkdir(parents=True, exist_ok=True)
        make_private(self.work, directory=True)
        self.path = self.work / 'auto-result.json'
        self.events = self.work / 'auto-events.jsonl'
        self.state = {'schema': 1, 'serial': serial, 'status': 'preparing', 'phase': 'connect'}
        if self.path.exists():
            if self.path.stat().st_size > 1024 * 1024:
                raise ValueError('Tệp tiến độ vượt giới hạn.')
            previous = json.loads(self.path.read_text('utf-8'))
            if previous.get('schema') != 1 or previous.get('serial') != serial:
                raise ValueError('Thư mục tiến độ thuộc tay khác; chọn thư mục mới.')
            self.state = previous

    def emit(self, state, message):
        with self.events.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'time': time.time(), 'state': state, 'message': message}, ensure_ascii=False) + '\n')
        self.callback(state, message)

    def save(self, **fields):
        self.state.update(fields)
        atomic_json(self.path, self.state)

    def _check(self):
        if (self.work / 'STOP').exists():
            self.cancel.set()
        check_cancel(self.cancel)

    def _capture(self, probe, snapshot):
        raw, source = self.work / 'installed.apk', self.work / 'source.apk'
        if not raw.is_file() or sha256_file(raw, self.cancel) != snapshot['digest']:
            self.emit('capturing', 'Đang lấy APK DJI Fly hiện tại từ RC 2…')
            partial = self.work / 'installed.apk.partial'
            def pull():
                probe.root.command('pull', '-Z', snapshot['path'], str(partial), timeout=300)
                self._check()
                if sha256_file(partial, self.cancel) != snapshot['digest'] or probe.snapshot() != snapshot:
                    raise DeploymentValidationError('APK trên tay đã thay đổi trong lúc lấy; chưa patch hoặc cài.')
                partial.replace(raw)
            probe.retry(pull, 'capture_apk')
        self._check()
        expected = for_identity(snapshot['version'], snapshot['code'])
        builder = self.builder_factory(self.assets, self.work / expected.build_directory, self.emit, self.cancel)
        self.emit('recovering', 'Đang xác minh APK đã lấy và phục hồi nguồn gốc để patch…')
        temporary_source = self.work / ('source-verify-' + uuid.uuid4().hex + '.apk')
        try:
            builder.recover(raw, temporary_source)
            expected = for_identity(snapshot['version'], snapshot['code'])
            if sha256_file(temporary_source, self.cancel) != expected.source_sha256:
                raise ValueError('Nguồn phục hồi không khớp phiên bản RC trên tay; chưa cài.')
            temporary_source.replace(source)
        finally:
            temporary_source.unlink(missing_ok=True)
        self.save(snapshot=snapshot, source_digest=expected.source_sha256, phase='build')
        return source, builder

    def run(self, *, grounded=False, allow_data_reset=False):
        if grounded is not True:
            raise ValueError('Xác nhận đã hạ cánh và động cơ dừng trước khi chạy.')
        self._check()
        lease = UsbLease('autopatch-work-' + str(self.work))
        probe = None
        heartbeat = None
        stop_watch = StopFileWatch(self.work / 'STOP', self.cancel)
        stop_watch.start()
        try:
            self.save(status='running', error=None)
            parent = self
            class Observed(self.deployment_factory):
                def emit(self, state, message):
                    super().emit(state, message)
                    parent.emit(state, message)
            probe = Observed(None, self.assets, self.work / 'connection', self.serial,
                             connect_only=True, cancel=self.cancel, stop_file=self.work / 'STOP',
                             reconnect_event=self.reconnect_event)
            probe.deadline = time.monotonic() + 600
            probe.retry(lambda: None, 'connect_rc2')
            foreground = probe.root.shell('dumpsys activity activities | grep mResumedActivity')
            if 'dji.go.v5/' in foreground:
                if 'dji.go.v5/com.dji.mainpageui.device.DJIDeviceActivity' not in foreground:
                    raise ValueError('Thoát DJI Fly về Launcher/Settings để cài; chưa thay đổi Fly.')
                probe.shell('am start -a android.settings.SETTINGS', mutating=False)
            snapshot = probe.retry(probe.snapshot, 'read_source')
            if snapshot:
                for_identity(snapshot.get('version'), snapshot.get('code'))
            previous = self.state.get('snapshot')
            built = self.state.get('built')
            source = self.work / 'source.apk'
            selected_snapshot = snapshot or previous
            if not selected_snapshot:
                raise ValueError('Chưa thấy DJI Fly hoặc tác vụ có nguồn đã xác minh; chưa cài.')
            expected = for_identity(selected_snapshot['version'], selected_snapshot['code'])
            build_directory = self.work / expected.build_directory
            builder = self.builder_factory(self.assets, build_directory, self.emit, self.cancel)
            resume_install = False
            install_report = self.work / 'install/install-result.json'
            if install_report.is_file() and built:
                saved = json.loads(install_report.read_text('utf-8'))
                resume_install = (saved.get('serial') == self.serial and saved.get('digest') == built.get('digest')
                                  and saved.get('uninstall_authorized_started') is True)
            if snapshot is None:
                if not (resume_install and previous and built and source.is_file()):
                    raise ValueError('Chưa thấy DJI Fly; không có tác vụ đã gỡ để tiếp tục cài.')
                builder.verify(source, build_directory / 'patched.apk', built['digest'])
                snapshot = previous
            elif built and snapshot['digest'] == built.get('digest') and source.is_file():
                expected = for_identity(snapshot['version'], snapshot['code'])
                if sha256_file(source, self.cancel) != expected.source_sha256:
                    raise ValueError('Nguồn tiến độ không khớp phiên bản trên tay; chưa cài.')
                builder.verify(source, build_directory / 'patched.apk', built['digest'])
                self.save(status='complete', phase='complete', installed_verified=True, final=snapshot)
                self.emit('installed', 'RC 2 đã có đúng bản menu local + tiếng Việt; đã đọc lại hash thành công.')
                return self.state
            elif previous and self.state.get('phase') in {'build', 'install'} and snapshot['digest'] != previous.get('digest'):
                raise ValueError('APK trên tay đã đổi giữa tác vụ; giữ tiến độ để kiểm tra, chưa thay Fly.')
            else:
                source, builder = self._capture(probe, snapshot)
            self._check()
            expected = for_identity(snapshot['version'], snapshot['code'])
            if sha256_file(source, self.cancel) != expected.source_sha256:
                raise ValueError('Nguồn tiến độ không khớp phiên bản trên tay; chưa cài.')
            current = getattr(builder, 'current_recovery', None)
            if (isinstance(current, dict) and current.get('digest') == snapshot['digest']
                    and current.get('source_digest') == expected.source_sha256
                    and HASH.fullmatch(current.get('certificate_sha256', ''))):
                # recover() only supplies this after verifying every current
                # recipe byte. Recheck the live package before accepting it.
                if probe.retry(probe.snapshot, 'verify_current_apk') != snapshot:
                    raise DeploymentValidationError('APK trên tay đã thay đổi sau khi kiểm chứng; chưa cài.')
                self.save(status='complete', phase='complete', installed_verified=True, final=snapshot,
                          built=None, verified_current={'digest': current['digest'],
                                 'certificate_sha256': current['certificate_sha256']},
                          already_current=True)
                self.emit('installed', 'RC 2 đã có đúng recipe hiện tại; không cần ký hoặc cài lại.')
                return self.state
            # A pull/retry owns its USB session. Start keepalive only once
            # capture/recovery has finished; never retain its old transport
            # across a reconnect or open shell channels during bulk capture.
            heartbeat = IdleHeartbeat(probe.root, self.serial, self.cancel, self.work / 'STOP', self.emit)
            heartbeat.start()
            value = builder.build(source)
            if not HASH.fullmatch(value.get('digest', '')):
                raise ValueError('Bộ dựng không trả lại hash APK hợp lệ.')
            heartbeat.close()
            keepalives = heartbeat.successes
            heartbeat = None
            self.save(built={'digest': value['digest'], 'certificate_sha256': value['certificate_sha256']},
                      phase='install', usb_keepalives=keepalives)
            self._check()
            deploy = Observed(value['apk'], self.assets, self.work / 'install', self.serial,
                              grounded=True, allow_data_reset=allow_data_reset, expected_digest=value['digest'],
                              source_digest=snapshot['digest'], cancel=self.cancel, cleanup=True,
                              target_version=expected.version, target_code=expected.code,
                              reconnect_event=self.reconnect_event,
                              enable_displayport=value.get('profile',{}).get('displayport_retry')=='hpd-retry-v1',
                              stop_file=self.work / 'STOP')
            deploy.connection, deploy.root = probe.connection, probe.root
            probe.connection = probe.root = None
            self.emit('installing', 'Đang truyền APK mới, kiểm tra từng phần rồi cài và đọc lại…')
            deploy.run()
            if not deploy.status.get('installed_verified'):
                raise RuntimeError('Chưa xác minh được APK sau khi cài.')
            self.save(status='complete', phase='complete', installed_verified=True, final=deploy.status['final'])
            self.emit('installed', 'Đã cài và đọc lại đúng APK: menu local nâng cao + tiếng Việt tích hợp.')
            return self.state
        except BaseException as error:
            stopped = self.cancel.is_set()
            self.save(status='stopped' if stopped else 'failed', error=str(error), installed_verified=False)
            self.emit('stopped' if stopped else 'error', str(error))
            raise
        finally:
            try:
                if heartbeat:
                    heartbeat.close()
            finally:
                try:
                    if probe:
                        probe.close()
                finally:
                    try:
                        lease.close()
                    finally:
                        stop_watch.close()
