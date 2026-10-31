import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import threading
from dataclasses import replace

import pytest

from rc2vi import auto_workflow as api


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture(params=[('1.21.8', 3115809), ('1.21.10', 3115981), ('1.21.16', 3132286)],
                ids=['rc1218', 'rc12110', 'rc12116'])
def case(tmp_path, monkeypatch, request):
    state = SimpleNamespace(raw=b'installed', captured=0, recovered=0, built=0, installed=0,
                            verified=0, version=request.param[0], code=request.param[1], changed=False,
                            build_error=False, recover_error=False, install_error=False,
                            remove_on_install=False)
    state.snapshot = {'path': '/data/app/fly/base.apk', 'digest': sha(state.raw),
                      'version': state.version, 'code': state.code}
    state.original_snapshot = dict(state.snapshot)
    actual_lookup = api.for_identity
    monkeypatch.setattr(api, 'for_identity', lambda version, code:
                        replace(actual_lookup(version, code), source_sha256=sha(b'stock')))
    monkeypatch.setattr(api, 'UsbLease', lambda name: SimpleNamespace(close=lambda: None))

    class Root:
        def shell(self, command):
            return 'mResumedActivity: com.android.settings/.Settings'
        def command(self, *args, **kwargs):
            assert args[:2] == ('pull', '-Z')
            state.captured += 1
            Path(args[3]).write_bytes(state.raw)
            if state.changed:
                state.snapshot = {**state.snapshot, 'digest': 'f' * 64}

    class Deploy:
        def __init__(self, apk, assets, work, serial, **kwargs):
            self.work = Path(work)
            self.work.mkdir(parents=True, exist_ok=True)
            self.apk, self.args = apk, kwargs
            self.root = Root()
            self.connection = SimpleNamespace(close=lambda: None)
            self.status = {}
        def emit(self, *args): pass
        def close(self): pass
        def retry(self, operation, label): return operation()
        def snapshot(self): return state.snapshot
        def run(self):
            state.installed += 1
            assert self.args['grounded'] is True
            assert type(self.args['allow_data_reset']) is bool
            state.allow_data_reset = self.args['allow_data_reset']
            assert self.args['expected_digest'] == sha(b'patched')
            assert self.args['source_digest'] == sha(b'installed')
            assert self.args['target_version'] == state.version
            assert self.args['target_code'] == state.code
            if state.install_error:
                if state.remove_on_install:
                    (self.work / 'install-result.json').write_text(json.dumps({
                        'serial': 'RC2-A', 'digest': sha(b'patched'),
                        'uninstall_authorized_started': True, 'original': state.original_snapshot}), 'utf-8')
                    state.snapshot = None
                raise ConnectionError('USB disconnected during install')
            state.snapshot = {**(state.snapshot or state.original_snapshot), 'digest': sha(b'patched')}
            self.status = {'installed_verified': True, 'final': state.snapshot}

    class Builder:
        def __init__(self, assets, work, emit, cancel):
            self.work = Path(work)
            self.work.mkdir(parents=True, exist_ok=True)
        def recover(self, raw, output):
            state.recovered += 1
            if state.recover_error or raw.read_bytes() != b'installed':
                raise ValueError('Unsupported input APK')
            output.write_bytes(b'stock')
        def build(self, source):
            state.built += 1
            if state.build_error:
                raise ValueError('Cannot verify patch')
            assert source.read_bytes() == b'stock'
            path = self.work / 'patched.apk'
            path.write_bytes(b'patched')
            return {'apk': str(path), 'digest': sha(b'patched'), 'certificate_sha256': 'c' * 64}
        def verify(self, source, output, expected):
            state.verified += 1
            assert source.read_bytes() == b'stock'
            if sha(output.read_bytes()) != expected:
                raise ValueError('Output tampered')

    def create(serial='RC2-A', cancel=None):
        return api.AutoPatchRun(tmp_path / 'assets', tmp_path / 'work', serial,
                                cancel=cancel, builder_factory=Builder, deployment_factory=Deploy)
    return state, create


def test_fresh_pipeline_captures_actual_apk_and_passes_verified_digest_to_installer(case):
    state, create = case
    result = create().run(grounded=True, allow_data_reset=True)
    assert result['status'] == 'complete' and result['installed_verified']
    assert (state.captured, state.recovered, state.built, state.installed) == (1, 1, 1, 1)


def test_pipeline_preserves_default_no_data_reset_consent(case):
    state, create = case
    result = create().run(grounded=True)
    assert result['installed_verified']
    assert state.allow_data_reset is False


def test_keepalive_never_runs_during_capture_or_across_a_capture_reconnect(case,monkeypatch):
    state,create=case
    active=[]
    class Heartbeat:
        successes=0
        def __init__(self,*args):pass
        def start(self):active.append(True)
        def close(self):active.clear()
    monkeypatch.setattr(api,'IdleHeartbeat',Heartbeat)
    runner=create()
    deployment=runner.deployment_factory
    class Observe(deployment):
        def retry(self,operation,label):
            if label=='capture_apk':assert not active
            return super().retry(operation,label)
    builder=runner.builder_factory
    class ObserveBuild(builder):
        def recover(self,*args):
            assert not active
            return super().recover(*args)
        def build(self,*args):
            assert active
            return super().build(*args)
    runner.deployment_factory=Observe;runner.builder_factory=ObserveBuild
    assert runner.run(grounded=True,allow_data_reset=True)['installed_verified']
    assert not active


def test_stop_file_cancels_a_pending_connection_before_any_capture_or_install(case):
    state, create = case
    runner = create()
    original_factory = runner.deployment_factory
    class Waiting(original_factory):
        def retry(self, operation, label):
            assert self.args['stop_file'] == runner.work / 'STOP'
            (runner.work / 'STOP').write_text('RC2-AUTO-PATCH-STOP', 'utf-8')
            assert self.args['cancel'].wait(2), 'STOP must wake an opening connection'
            raise InterruptedError('Stopped pending USB authorization')
    runner.deployment_factory = Waiting
    with pytest.raises(InterruptedError, match='pending USB'):
        runner.run(grounded=True, allow_data_reset=True)
    assert state.captured == state.built == state.installed == 0
    assert json.loads(runner.path.read_text('utf-8'))['status'] == 'stopped'


def test_stop_watch_is_closed_without_a_late_cancellation(tmp_path):
    cancel = threading.Event()
    path = tmp_path / 'STOP'
    watch = api.StopFileWatch(path, cancel)
    watch.start()
    watch.close()
    path.write_text('RC2-AUTO-PATCH-STOP', 'utf-8')
    assert not watch.thread.is_alive()
    assert not cancel.is_set()


def test_already_installed_output_is_verified_without_reinstall(case):
    state, create = case
    create().run(grounded=True, allow_data_reset=True)
    assert create().run(grounded=True, allow_data_reset=True)['installed_verified']
    assert state.installed == 1 and state.captured == 1 and state.verified == 1


def test_current_recipe_recovered_from_fresh_capture_needs_no_signing_or_reinstall(case):
    state, create = case
    runner = create()
    original = runner.builder_factory
    class Current(original):
        def recover(self, raw, output):
            super().recover(raw, output)
            self.current_recovery = {'digest': state.snapshot['digest'],
                                     'source_digest': sha(b'stock'),
                                     'certificate_sha256': 'c' * 64}
        def build(self, source):
            raise AssertionError('Current verified APK must not be rebuilt or signed')
    runner.builder_factory = Current
    result = runner.run(grounded=True)
    assert result['already_current'] and result['installed_verified']
    assert result['built'] is None
    assert state.captured == state.recovered == 1
    assert state.built == state.installed == 0
    assert runner.run(grounded=True)['already_current']
    assert state.captured == 1 and state.built == state.installed == 0


def test_live_package_change_after_current_recipe_recovery_is_rejected(case):
    state, create = case
    runner = create()
    original = runner.builder_factory
    class Changed(original):
        def recover(self, raw, output):
            super().recover(raw, output)
            self.current_recovery = {'digest': state.snapshot['digest'],
                                     'source_digest': sha(b'stock'),
                                     'certificate_sha256': 'c' * 64}
            state.snapshot = {**state.snapshot, 'digest': 'f' * 64}
    runner.builder_factory = Changed
    with pytest.raises(api.DeploymentValidationError, match='thay đổi'):
        runner.run(grounded=True)
    assert state.built == state.installed == 0


def test_recovered_stock_cache_never_authorizes_an_unrecognized_new_input(case):
    state, create = case
    create().run(grounded=True, allow_data_reset=True)
    state.raw = b'unknown modified APK'
    state.snapshot = {**state.snapshot, 'digest': sha(state.raw)}
    with pytest.raises(ValueError, match='Unsupported'):
        create().run(grounded=True, allow_data_reset=True)
    assert state.installed == 1 and state.recovered == 2


@pytest.mark.parametrize('field', ['build_error', 'recover_error'])
def test_build_or_source_failure_never_starts_install(case, field):
    state, create = case
    setattr(state, field, True)
    runner = create()
    with pytest.raises(ValueError): runner.run(grounded=True, allow_data_reset=True)
    assert state.installed == 0 and runner.state['status'] == 'failed'


def test_apk_changed_during_capture_stops_before_patching(case):
    state, create = case
    state.changed = True
    with pytest.raises(api.DeploymentValidationError):
        create().run(grounded=True, allow_data_reset=True)
    assert state.built == state.installed == 0


def test_unsupported_version_is_rejected_without_transfer_or_package_change(case):
    state, create = case
    state.snapshot = {**state.snapshot, 'version': '1.21.9', 'code': 3115900}
    with pytest.raises(ValueError, match='1.21.10'):
        create().run(grounded=True, allow_data_reset=True)
    assert state.captured == state.installed == 0


def test_other_version_code_cannot_select_the_source_recipe(case):
    state, create = case
    state.snapshot['code'] = 3115981 if state.code == 3115809 else 3115809
    with pytest.raises(ValueError):
        create().run(grounded=True, allow_data_reset=True)
    assert state.captured == state.installed == 0


def test_wrong_recovered_source_never_reaches_build_or_install(case):
    state, create = case
    runner = create()
    original = runner.builder_factory
    class Mismatch(original):
        def recover(self, raw, output):
            output.write_bytes(b'stock from another version')
    runner.builder_factory = Mismatch
    with pytest.raises(ValueError, match='Nguồn phục hồi không khớp'):
        runner.run(grounded=True, allow_data_reset=True)
    assert state.built == state.installed == 0


def test_same_controller_can_start_other_supported_version_in_separate_build_directory(case):
    state, create = case
    runner=create()
    runner.run(grounded=True, allow_data_reset=True)
    original=api.for_identity(state.version,state.code)
    state.version,state.code=('1.21.10',3115981) if state.code==3115809 else ('1.21.8',3115809)
    state.snapshot={**state.snapshot,'digest':sha(state.raw),'version':state.version,'code':state.code}
    other=api.for_identity(state.version,state.code)
    result=create().run(grounded=True, allow_data_reset=True)
    assert result['installed_verified'] and state.installed==2
    assert original.build_directory!=other.build_directory
    for profile in (original,other):
        assert (runner.work/profile.build_directory/'patched.apk').is_file()


def test_workspace_cannot_be_reused_for_another_controller(case):
    state, create = case
    create().run(grounded=True, allow_data_reset=True)
    with pytest.raises(ValueError, match='tay khác'): create('RC2-B')
    assert state.installed == 1


def test_cancelled_start_does_not_open_transport_or_install(case):
    state, create = case
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(RuntimeError):
        create(cancel=cancel).run(grounded=True, allow_data_reset=True)
    assert state.captured == state.installed == 0


@pytest.mark.parametrize('flags', [{}, {'allow_data_reset': True}])
def test_runtime_consent_is_required_even_with_existing_progress(case, flags):
    state, create = case
    with pytest.raises(ValueError, match='Xác nhận'): create().run(**flags)
    assert state.captured == state.installed == 0


def test_install_failure_preserves_verified_source_and_candidate_for_resume(case):
    state, create = case
    state.install_error = True
    runner = create()
    with pytest.raises(ConnectionError): runner.run(grounded=True, allow_data_reset=True)
    assert (runner.work / 'source.apk').read_bytes() == b'stock'
    expected = api.for_identity(state.version, state.code)
    assert (runner.work / expected.build_directory / 'patched.apk').read_bytes() == b'patched'
    state.install_error = False
    result = create().run(grounded=True, allow_data_reset=True)
    assert result['installed_verified']


def test_changed_device_apk_during_pending_install_is_not_silently_replaced(case):
    state, create = case
    state.install_error = True
    with pytest.raises(ConnectionError): create().run(grounded=True, allow_data_reset=True)
    state.snapshot = {**state.snapshot, 'digest': 'f' * 64}
    with pytest.raises(ValueError, match='đổi giữa tác vụ'):
        create().run(grounded=True, allow_data_reset=True)
    assert state.installed == 1


def test_restart_after_uninstall_lost_reply_uses_verified_owned_candidate(case):
    state, create = case
    state.install_error = state.remove_on_install = True
    with pytest.raises(ConnectionError): create().run(grounded=True, allow_data_reset=True)
    assert state.snapshot is None
    state.install_error = False
    assert create().run(grounded=True, allow_data_reset=True)['installed_verified']
    assert state.captured == 1 and state.verified == 1


def test_stop_file_is_durable_and_blocks_connection_on_restart(case):
    state, create = case
    runner = create()
    (runner.work / 'STOP').write_text('RC2-AUTO-PATCH-STOP', 'utf-8')
    with pytest.raises(RuntimeError): runner.run(grounded=True, allow_data_reset=True)
    assert runner.cancel.is_set() and state.captured == state.installed == 0


def test_heartbeat_only_reads_serial_and_checks_identity(tmp_path):
    calls = []
    def shell(command, **kwargs):
        calls.append((command, kwargs))
        beat.stopping.set()
        return 'RC2-A'
    beat = api.IdleHeartbeat(SimpleNamespace(shell=shell), 'RC2-A', threading.Event(),
                             tmp_path / 'STOP', lambda *args: None, interval=0)
    beat.run()
    assert beat.successes == 1 and calls == [('getprop ro.serialno', {'timeout': 4})]


def test_heartbeat_stop_file_sets_cancel_without_sending_commands(tmp_path):
    from unittest.mock import Mock
    stop = tmp_path / 'STOP'; stop.write_text('RC2-AUTO-PATCH-STOP')
    root = Mock(); cancel = threading.Event()
    api.IdleHeartbeat(root, 'RC2-A', cancel, stop, lambda *args: None, interval=0).run()
    assert cancel.is_set();root.shell.assert_not_called()
