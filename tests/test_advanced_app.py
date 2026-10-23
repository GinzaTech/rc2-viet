"""Private desktop contract tests; no USB, signing keys, or flight commands."""
import hashlib
import io
import json
from pathlib import Path
import queue
import struct
import threading
from types import SimpleNamespace

import pytest

import advanced_app as app
from rc2vi import advanced_desktop as desktop


def test_offline_stock_check_never_builds_or_opens_usb(tmp_path, monkeypatch):
    result={'status':'hud_device_verified','digest':app.STOCK_SHA256,
            'source_digest':app.STOCK_SHA256,'certificate_sha256':'a'*64}
    builder=SimpleNamespace(verify_device_apk=lambda a,b:result,
                            build=lambda *a:(_ for _ in ()).throw(AssertionError('No build')))
    monkeypatch.setattr(app.tk,'Tk',lambda:(_ for _ in ()).throw(AssertionError('No GUI/USB')))
    report=tmp_path/'stock-check.json'
    assert app.main(['--verify-stock','stock.apk','--report',str(report)],
                    builder_factory=lambda *a,**kw:builder,
                    paths_factory=lambda:(tmp_path/'assets',tmp_path/'work'),space_check=lambda *_:None)==0
    value=json.loads(report.read_text('utf-8'))
    assert value['status']=='hud_device_verified'
    assert value['offline_stock_verification'] is True and value['usb_connected'] is False


class Adb:
    def __init__(self, serial='RC2-A'):
        self.serial = serial
        self.commands = []
        self.values = {
            'getprop ro.serialno': serial, 'getprop ro.product.model': 'DJI RC 2',
            'getprop ro.product.device': 'rc331', 'getprop ro.build.version.sdk': '30',
            'id': 'uid=0(root) gid=0(root)',
            'dumpsys package dji.go.v5': 'versionName=1.21.10 versionCode=3115981',
            'dumpsys activity activities | grep mResumedActivity':
                'mResumedActivity: com.android.settings/.Settings',
            'am start -W -n com.android.settings/.Settings': 'Status: ok',
            'pm path dji.go.v5': 'package:/data/app/fly/base.apk',
            'sha256sum /data/app/fly/base.apk': hashlib.sha256(b'candidate').hexdigest() + '  base.apk',
        }

    def command(self, *args, **kwargs):
        self.commands.append(args)
        assert args == ('get-state',)
        return 'device'

    def shell(self, command, **kwargs):
        self.commands.append(command)
        return self.values.get(command, '')


class Connection:
    def __init__(self, device, assets, emit):
        self.device = device
        self.adb = Adb(device.serial)
        self.closed = False
        self.relay = SimpleNamespace(stop_event=threading.Event())

    def open(self):
        return self.adb

    def alive(self):
        return not self.closed

    def close(self):
        self.closed = True


class Builder:
    def __init__(self, work, trace):
        self.trace = trace
        self.artifact = {
            'status': 'hud_built', 'apk': str(work / 'candidate.apk'),
            'receipt': str(work / 'receipt.json'),
            'digest': hashlib.sha256(b'candidate').hexdigest(),
            'source_digest': app.STOCK_SHA256, 'certificate_sha256': 'a' * 64,
            'source_identity': {'version': '1.21.10', 'code': 3115981},
        }
        Path(self.artifact['apk']).write_bytes(b'candidate')

    def build(self, source):
        self.trace.append(('build', source))
        return dict(self.artifact)

    def verify(self, receipt):
        self.trace.append(('verify', receipt))
        return dict(self.artifact)


class Installer:
    def __init__(self, builder, trace, confirmation=False):
        self.builder, self.trace = builder, trace
        self.confirmation = confirmation
        self.recovery_busy = False
        self.cancel_count = 0
        self.cleanup_threads = []

    def pull_source(self, adb, serial):
        self.trace.append(('pull', serial))
        return Path('automatic-source.apk')

    def prepare(self, adb, serial, receipt):
        self.trace.append(('prepare', receipt))
        if self.confirmation:
            return {'status': 'hud_confirmation_required', 'serial': serial,
                    'token': 'single-use-token', 'digest': self.builder.artifact['digest'],
                    'installed_digest': 'b' * 64, 'backup_path': 'private-backup.tar',
                    'summary': 'Sao lưu dữ liệu; Keystore có thể cần đăng nhập lại.'}
        return self.result(serial)

    def confirm(self, adb, serial, token):
        self.trace.append(('confirm', serial, token))
        return self.result(serial)

    def result(self, serial):
        return {'status': 'hud_installed', 'serial': serial,
                'digest': self.builder.artifact['digest'], 'data_retained': True}

    def cancel_pending(self):
        self.cancel_count += 1

    def cancel_for_close(self):
        self.cancel_pending()
        return not self.recovery_busy

    def trusted_artifact(self, digest):
        return dict(self.builder.artifact)

    def cleanup_pending(self, adb, serial):
        self.cleanup_threads.append(threading.get_ident())


@pytest.fixture
def rig(tmp_path):
    trace, events = [], queue.Queue()
    builder = Builder(tmp_path, trace)
    installer = Installer(builder, trace)

    def translate(adb, before_deploy):
        before_deploy()
        trace.append(('translate', adb.serial))
        return {'status': 'enabled', 'message': 'Đã bật tiếng Việt.'}

    backend = SimpleNamespace(builder=builder, installer=installer, translate=translate)
    worker = app.AdvancedWorker(tmp_path, tmp_path, lambda *e: events.put(e),
                                backend_factory=lambda *a: backend,
                                discover=lambda: [SimpleNamespace(serial='RC2-A')],
                                connection_factory=Connection, pin_factory=lambda adb, serial: adb,
                                space_check=lambda work: None)
    yield SimpleNamespace(worker=worker, backend=backend, trace=trace, events=events)
    worker.close()
    if worker.thread:
        worker.thread.join(3)
    assert not worker.busy


def finish(worker):
    worker.thread.join(3)
    assert not worker.thread.is_alive()


def drain(events):
    result = []
    while not events.empty():
        result.append(events.get_nowait())
    return result


def test_paths_use_private_appdata_and_frozen_assets(monkeypatch, tmp_path):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setattr(app.sys, '_MEIPASS', str(tmp_path / 'frozen'), raising=False)
    assets, work = app.paths()
    assert assets == tmp_path / 'frozen/assets'
    assert work == tmp_path / 'local/RC2Advanced12110'


def test_install_requires_ground_ack_before_any_connection(rig):
    assert not rig.worker.request('install', 'RC2-A', grounded=False)
    assert not rig.trace
    assert rig.worker.connection is None


def test_automatic_workflow_reasserts_settings_after_build(rig):
    assert rig.worker.request('install', 'RC2-A', grounded=True, translate=True)
    finish(rig.worker)
    assert [e[0] for e in rig.trace] == ['pull', 'build', 'verify', 'prepare', 'translate']
    commands = rig.worker.adb.commands
    assert commands.count('am start -W -n com.android.settings/.Settings') >= 3
    assert commands.count('am force-stop dji.go.v5') >= 3
    assert not any(any(banned in str(c).lower() for banned in ('fcc', 'gps', 'tof', 'shutdown'))
                   for c in commands)
    assert any(e[0] == 'ready' and 'giữ dữ liệu' in e[1] for e in drain(rig.events))


@pytest.mark.parametrize('command,value', [
    ('getprop ro.serialno', 'RC2-B'), ('getprop ro.product.model', 'Pixel 9'),
    ('getprop ro.product.device', 'phone'), ('getprop ro.build.version.sdk', '35'),
    ('id', 'uid=2000(shell)'),
    ('dumpsys package dji.go.v5', 'versionName=1.21.8 versionCode=3115809'),
])
def test_connection_guard_rejects_other_serial_model_root_sdk_version(rig, command, value):
    def factory(*args):
        connection = Connection(*args)
        connection.adb.values[command] = value
        return connection
    rig.worker.connection_factory = factory
    assert rig.worker.request('install', 'RC2-A', grounded=True)
    finish(rig.worker)
    assert not rig.trace
    assert any(e[0] == 'error' for e in drain(rig.events))


def test_wrong_workflow_digest_never_prepares(rig):
    build = rig.backend.builder.build
    rig.backend.builder.build = lambda source: {**build(source), 'digest': 'f' * 64}
    rig.worker.request('install', 'RC2-A', grounded=True)
    finish(rig.worker)
    assert not any(e[0] == 'prepare' for e in rig.trace)


def test_confirmation_is_bound_to_exact_serial_digest_and_token(rig):
    rig.backend.installer.confirmation = True
    rig.worker.request('install', 'RC2-A', grounded=True, translate=False)
    while True:
        kind, plan = rig.events.get(timeout=3)
        if kind == 'confirmation':
            break
    assert not rig.worker.answer_confirmation({**plan, 'serial': 'RC2-B'}, True)
    assert not rig.worker.answer_confirmation({**plan, 'digest': 'f' * 64}, True)
    assert not rig.worker.answer_confirmation({**plan, 'token': 'wrong-token'}, True)
    assert rig.worker.answer_confirmation(plan, True)
    assert not rig.worker.answer_confirmation(plan, True)
    finish(rig.worker)
    assert ('confirm', 'RC2-A', 'single-use-token') in rig.trace
    assert not any(e[0] == 'translate' for e in rig.trace)


def test_cancel_confirmation_revokes_and_cleans_on_worker(rig):
    rig.backend.installer.confirmation = True
    rig.worker.request('install', 'RC2-A', grounded=True)
    while rig.events.get(timeout=3)[0] != 'confirmation':
        pass
    rig.worker.cancel()
    finish(rig.worker)
    assert rig.backend.installer.cancel_count
    assert rig.backend.installer.cleanup_threads
    assert threading.get_ident() not in rig.backend.installer.cleanup_threads
    assert not any(e[0] in {'confirm', 'translate'} for e in rig.trace)


def test_one_worker_and_close_keeps_recovery_connection_alive(rig):
    entered, release = threading.Event(), threading.Event()
    installer = rig.backend.installer
    original = installer.prepare
    def recovery(*args):
        installer.recovery_busy = True
        entered.set()
        assert release.wait(3)
        installer.recovery_busy = False
        return original(*args)
    installer.prepare = recovery
    rig.worker.request('install', 'RC2-A', grounded=True)
    assert entered.wait(3)
    assert not rig.worker.request('scan')
    connection = rig.worker.connection
    rig.worker.close()
    assert not connection.relay.stop_event.is_set()
    assert not connection.closed
    release.set()
    finish(rig.worker)
    assert connection.closed
    assert not any(e[0] == 'translate' for e in rig.trace)


def test_cli_offline_build_has_no_usb_or_installer(tmp_path):
    trace = []
    builder = Builder(tmp_path, trace)
    report = tmp_path / 'out/result.json'
    def factory(*args):
        return builder
    assert app.main(['--advanced-build', 'source.apk', '--report', str(report)],
                    builder_factory=factory, paths_factory=lambda: (tmp_path, tmp_path),
                    space_check=lambda p: None) == 0
    value = json.loads(report.read_text('utf-8'))
    assert value['status'] == 'hud_built'
    assert [e[0] for e in trace] == ['build', 'verify']
    assert 'token' not in value


def test_cli_reports_error_when_receipt_does_not_match(tmp_path):
    builder = Builder(tmp_path, [])
    builder.build = lambda source: {**builder.artifact, 'source_digest': 'f' * 64}
    report = tmp_path / 'error.json'
    assert app.main(['--advanced-build', 'wrong.apk', '--report', str(report)],
                    builder_factory=lambda *a: builder,
                    paths_factory=lambda: (tmp_path, tmp_path), space_check=lambda p: None) == 1
    assert json.loads(report.read_text('utf-8'))['status'] == 'error'


def test_rc2_checksums_are_repaired_for_connection_and_every_subsequent_command():
    from rc2vi.core import pack
    sends = []
    class Relay:
        def _send_usb(self, wire):
            sends.append(wire)
    private = app.checksum_relay_class(Relay)
    relay = private()
    frames = [pack('CNXN',0x01000001,1048576,b'host::\0'),
              pack('OPEN',1,0,b'shell:getprop ro.serialno\0'),
              pack('WRTE',1,2,b'x'*1048576),pack('CLSE',1,2),
              pack('OPEN',3,0,b'sync:\0')]
    for wire in frames:
        relay._send_usb(wire[:16] + b'\0' * 4 + wire[20:])
    # Firmware accepts the connection then drops all shell/SYNC requests if
    # only CNXN is repaired. Check complete frames, arguments and payloads.
    assert sends == frames


def test_gui_smoke_buttons_thread_status_no_backend(monkeypatch, tmp_path):
    import tkinter as tk
    calls = []
    class Worker:
        busy = False
        closing = False
        def request(self, *args, **kwargs):
            calls.append((args, kwargs))
            return True
        def cancel(self):
            calls.append(('cancel',))
        def close(self):
            calls.append(('close',))
        def answer_confirmation(self, plan, approved):
            calls.append(('confirm', threading.get_ident(), approved))
    root = tk.Tk()
    root.withdraw()
    try:
        view = app.App(root, tmp_path, tmp_path, start_worker=False, worker=Worker())
        view.emit('devices', ('RC2-A', 'RC2-B'))
        view.poll()
        assert view.selector.get() == ''
        view.selector.set('RC2-A')
        view.on_select()
        assert view.vietnamese.get() is True
        assert str(view.install_button['state']) == 'disabled'
        view.grounded.set(True)
        view.refresh_controls()
        view.install_button.invoke()
        assert calls[-1] == (('install', 'RC2-A'), {'grounded': True, 'translate': True})
        view.worker.busy = True
        view.refresh_controls()
        assert str(view.selector['state']) == 'disabled'
        assert str(view.connect_button['state']) == 'disabled'
        assert str(view.cancel_button['state']) == 'normal'
        view.emit('pairing', 'Bấm Allow USB debugging trên RC 2.')
        view.poll()
        assert 'Allow' in view.status.get()
        monkeypatch.setattr(desktop.messagebox, 'askokcancel', lambda **kw: True)
        view.emit('confirmation', {'serial': 'RC2-A', 'token': 't', 'digest': 'a' * 64,
                                   'backup_path': 'backup.tar', 'summary': 'Sao lưu/Keystore'})
        view.poll()
        assert calls[-1] == ('confirm', threading.get_ident(), True)
        assert 'token' not in view.log.get('1.0', 'end')
        assert root.cget('background') == '#000000'
    finally:
        root.destroy()


def test_gui_smoke_cli_never_initializes_backend(tmp_path):
    report = tmp_path / 'smoke.json'
    assert app.main(['--gui-smoke', '--report', str(report)],
                    paths_factory=lambda: (tmp_path, tmp_path)) == 0
    result = json.loads(report.read_text('utf-8'))
    assert result['status'] == 'PASS'
    assert result['usb_connected'] is False
    assert result['main_button'] == 'Cài menu Nâng cao 1.21.10'


def test_translation_transport_keeps_distinct_pinned_adb_dispatch():
    root = Adb()
    root.adb = SimpleNamespace(serial='')  # Like HUD's immutable -t client.
    direct = app.TranslationTransport(root)
    assert getattr(direct, 'adb', direct) is direct
    assert direct.serial == 'RC2-A'
    bound = direct.bind('RC2-A')
    assert bound.shell('id') == 'uid=0(root) gid=0(root)'
    assert bound.command('get-state') == 'device'
    with pytest.raises(ValueError):
        direct.bind('RC2-B')
    root.serial = 'RC2-B'
    for run in (lambda: direct.bind('RC2-A'), lambda: direct.shell('id'),
                lambda: direct.command('get-state')):
        with pytest.raises(ValueError):
            run()


def test_backend_uses_public_translation_contract_and_settings_hook(monkeypatch, tmp_path):
    from rc2vi import activation, translation_install, translation_build, translation_engine, hud_keys
    calls = []
    class Adaptive:
        def __init__(self, *args, **kwargs):
            calls.append(('adaptive', kwargs['builder']))
        def apply(self, adb, root, sdk, safe):
            assert getattr(root, 'adb', root) is adb
            assert adb.serial == 'RC2-A' and sdk == 30
            return self._deploy(adb, root, {}, safe, {}, tmp_path)
        def _deploy(self, adb, root, before, safe, artifact, local):
            safe()
            calls.append('deploy')
            return {'status': 'enabled', 'message': 'ok'}
    class Activation:
        def __init__(self, *args, **kwargs):
            self.adaptive = kwargs['adaptive']
        def apply(self, adb):
            calls.append(('trusted', self.trusted_hud))
            return self.adaptive.apply(adb, adb, 30, lambda: calls.append('safe'))
    def engine(*args, **kwargs):
        calls.append(('engine', kwargs['payload_roots']))
        return 'pinned-local-engine'
    def builder(*args, **kwargs):
        assert kwargs['sdk'] == 30 and kwargs['engine'] == 'pinned-local-engine'
        return SimpleNamespace(tools='embedded-tools')
    monkeypatch.setattr(activation, 'Activator', Activation)
    monkeypatch.setattr(translation_install, 'AdaptiveTranslation', Adaptive)
    monkeypatch.setattr(translation_build, 'TranslationBuilder', builder)
    monkeypatch.setattr(translation_engine, 'LocalTranslationEngine', engine)
    monkeypatch.setattr(hud_keys, 'HudKeyStore', lambda *a: 'appdata-only-keys')
    monkeypatch.setattr(app, 'paths', lambda: (tmp_path / 'assets', tmp_path / 'appdata'))
    backend = app.Backend.__new__(app.Backend)
    backend.assets, backend.work = tmp_path / 'assets', tmp_path
    backend.emit, backend.cancel = lambda *a: None, threading.Event()
    backend.installer = SimpleNamespace(trusted_artifact=lambda d: {'digest': d})
    root = Adb()
    root.adb = SimpleNamespace(serial='')
    result = backend.translate(root, lambda: calls.append('settings'))
    assert result['status'] == 'enabled'
    assert calls[-4:] == ['settings', 'safe', 'safe', 'deploy']
    assert ('engine', [tmp_path / 'assets/translation-engine', tmp_path / 'translation-engine']) in calls
    assert any(c[0] == 'trusted' and c[1] == backend.installer.trusted_artifact
               for c in calls if isinstance(c, tuple))


def test_close_during_translation_keeps_usb_for_compensation(rig):
    entered, release = threading.Event(), threading.Event()
    def translate(adb, before_deploy):
        before_deploy()
        entered.set()
        assert release.wait(3)
        assert not rig.worker.connection.relay.stop_event.is_set()
        rig.trace.append(('translation-recovered',))
        raise RuntimeError('Đã hủy bản dịch sau phục hồi')
    rig.backend.translate = translate
    rig.worker.request('install', 'RC2-A', grounded=True)
    assert entered.wait(3)
    connection = rig.worker.connection
    rig.worker.close()
    assert not connection.closed and not connection.relay.stop_event.is_set()
    release.set()
    finish(rig.worker)
    assert ('translation-recovered',) in rig.trace
    assert connection.closed


def test_post_consent_settings_failure_revokes_before_cleanup(rig):
    rig.backend.installer.confirmation = True
    rig.worker.request('install', 'RC2-A', grounded=True)
    while True:
        kind, plan = rig.events.get(timeout=3)
        if kind == 'confirmation':
            break
    rig.worker.adb.values['am start -W -n com.android.settings/.Settings'] = 'Error'
    assert rig.worker.answer_confirmation(plan, True)
    finish(rig.worker)
    assert rig.backend.installer.cancel_count
    assert rig.backend.installer.cleanup_threads
    assert not any(e[0] == 'confirm' for e in rig.trace)


def test_independent_translation_requires_verified_installed_menu(rig):
    rig.worker.request('translate', 'RC2-A', grounded=True)
    finish(rig.worker)
    assert [e[0] for e in rig.trace] == ['pull', 'translate']


@pytest.mark.parametrize('digest,trusted', [
    (app.STOCK_SHA256, True), ('', True), ('x' * 64, True), ('f' * 64, False),
])
def test_independent_translation_rejects_stock_unknown_or_invalid_hash(rig, digest, trusted):
    def factory(*args):
        c = Connection(*args)
        c.adb.values['sha256sum /data/app/fly/base.apk'] = digest + '  base.apk'
        return c
    rig.worker.connection_factory = factory
    if not trusted:
        rig.backend.installer.trusted_artifact = lambda d: {'digest': d, 'source_digest': '0' * 64}
    rig.worker.request('translate', 'RC2-A', grounded=True)
    finish(rig.worker)
    assert not any(e[0] == 'translate' for e in rig.trace)
    assert any(e[0] == 'error' for e in drain(rig.events))


def test_disk_check_does_not_attempt_cleanup_or_pull(rig, monkeypatch):
    monkeypatch.setattr(app.shutil, 'disk_usage', lambda path: SimpleNamespace(free=1560 * 1024 ** 2))
    rig.worker.space_check = app.check_space
    rig.worker.request('install', 'RC2-A', grounded=True)
    finish(rig.worker)
    assert not rig.trace
    assert any(e[0] == 'error' and '--work' in e[1] for e in drain(rig.events))


def test_offline_work_override_and_gui_work_override(tmp_path):
    trace = []
    selected = tmp_path / 'other-drive/work'
    builder = Builder(tmp_path, trace)
    seen = []
    def factory(assets, work, emit):
        seen.append(work)
        return builder
    assert app.main(['--advanced-build', 'source.apk', '--work', str(selected)],
                    builder_factory=factory, paths_factory=lambda: (tmp_path, tmp_path),
                    space_check=lambda p: seen.append(p)) == 0
    assert seen == [selected, selected / 'advanced']
    report = tmp_path / 'gui.json'
    assert app.main(['--gui-smoke', '--work-dir', str(selected), '--report', str(report)],
                    paths_factory=lambda: (tmp_path, tmp_path)) == 0
    assert json.loads(report.read_text('utf-8'))['work'] == str(selected)


def test_gui_folder_picker_never_picks_a_source_apk(monkeypatch, tmp_path):
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        view = app.App(root, tmp_path, tmp_path, start_worker=False)
        folder = tmp_path / 'work'
        monkeypatch.setattr(desktop.filedialog, 'askdirectory', lambda **kw: str(folder))
        view.work_button.invoke()
        assert view.work == folder
        assert view.work_label.get() == str(folder)
        assert 'AppData' in view.status.get()
    finally:
        root.destroy()


def test_work_cannot_change_during_operation(rig, tmp_path):
    entered, release = threading.Event(), threading.Event()
    def discover():
        entered.set()
        assert release.wait(3)
        return []
    rig.worker.discover = discover
    rig.worker.request('scan')
    assert entered.wait(3)
    assert not rig.worker.set_work(tmp_path / 'other')
    release.set()
    finish(rig.worker)
    assert rig.worker.set_work(tmp_path / 'other')
    assert rig.worker.work == tmp_path / 'other'


def test_json_console_cp1252_falls_back_without_crashing(monkeypatch, tmp_path):
    data = io.BytesIO()
    stream = io.TextIOWrapper(data, encoding='cp1252')
    monkeypatch.setattr(app.sys, 'stdout', stream)
    report = {'status': 'error', 'message': 'Không đủ dung lượng trống'}
    app.write_report(report, tmp_path / 'utf8.json')
    stream.flush()
    assert json.loads(data.getvalue().decode('cp1252')) == report
    assert json.loads((tmp_path / 'utf8.json').read_text('utf-8')) == report


def test_private_connection_does_not_modify_public_transport_or_generate_keys(monkeypatch, tmp_path):
    from rc2vi import transport, activation
    class BaseAdb:
        def __init__(self, *args):
            pass
        def command(self, *args, **kwargs):
            return args
    class BaseRelay:
        def _send_usb(self, wire):
            return wire
    namespace = {'Adb': BaseAdb, 'Relay': BaseRelay}
    exec('def _open(self):\n self.client = Adb()\n self.private_relay = Relay()\n return self.client', namespace)
    class BaseConnection:
        _open = namespace['_open']
        def __init__(self, *args):
            pass
        def open(self):
            return self._open()
    monkeypatch.setattr(transport, 'Connection', BaseConnection)
    monkeypatch.setattr(transport, 'Relay', BaseRelay)
    monkeypatch.setattr(transport, 'Adb', BaseAdb)
    monkeypatch.setattr(activation, 'verify_bundle', lambda a: None)
    monkeypatch.setattr(app.Path, 'home', lambda: tmp_path)
    private = app.private_connection(SimpleNamespace(serial='RC2-A'), tmp_path, lambda *a: None)
    client = private.open()
    assert transport.Relay is BaseRelay and transport.Adb is BaseAdb
    assert namespace['Relay'] is BaseRelay and namespace['Adb'] is BaseAdb
    assert client.command('get-state') == ('get-state',)
    with pytest.raises(ValueError, match='khóa'):
        client.command('keygen', 'never-create-key')
    assert private.private_relay.__class__ is not BaseRelay


def test_first_usb_key_only_at_expected_absent_path_and_never_overwrites(tmp_path):
    expected = tmp_path / '.android/adbkey'
    expected.parent.mkdir()
    calls = []
    class Adb:
        def command(self, *args, **kwargs):
            calls.append(args)
            if args[0] == 'keygen':
                expected.write_bytes(b'FAKE-TEST-KEY')
                expected.with_suffix('.pub').write_bytes(b'FAKE-TEST-PUBLIC')
            return 'ok'
    client = app.first_key_adb_class(Adb, expected)()
    for args in [('keygen', str(tmp_path / 'other-key')), ('keygen', str(expected), 'extra')]:
        with pytest.raises(ValueError):
            client.command(*args)
    assert not calls
    assert client.command('keygen', str(expected)) == 'ok'
    assert calls == [('keygen', str(expected))]
    prior = (expected.read_bytes(), expected.with_suffix('.pub').read_bytes())
    with pytest.raises(ValueError):
        client.command('keygen', str(expected))
    assert len(calls) == 1
    assert (expected.read_bytes(), expected.with_suffix('.pub').read_bytes()) == prior
    assert client.command('get-state') == 'ok'


def test_partial_usb_keypair_is_preserved(tmp_path):
    expected = tmp_path / 'adbkey'
    expected.with_suffix('.pub').write_bytes(b'FAKE-PUBLIC-ONLY')
    class Adb:
        def command(self, *args, **kwargs):
            pytest.fail('Must not generate over a partial existing keypair')
    with pytest.raises(ValueError):
        app.first_key_adb_class(Adb, expected)().command('keygen', str(expected))
    assert not expected.exists()
    assert expected.with_suffix('.pub').read_bytes() == b'FAKE-PUBLIC-ONLY'


def test_real_core_constructor_contract_with_appdata_signer_and_confirm_adapter(monkeypatch, tmp_path):
    from rc2vi import hud_keys
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local-appdata'))
    monkeypatch.setattr(app, 'paths', lambda: (tmp_path, tmp_path / 'appdata'))
    monkeypatch.setattr(hud_keys, 'HudKeyStore', lambda tools, root=None: SimpleNamespace(root=root or tmp_path/'legacy-signing'))
    backend = app.Backend(tmp_path / 'assets', tmp_path / 'work-d', lambda *e: None, threading.Event())
    assert backend.builder.keys.root == tmp_path / 'appdata/advanced-signing'
    assert backend.installer.builder is backend.builder
    # Validate the core's inherited approve contract without any device I/O.
    from rc2vi.advanced_patch import AdvancedInstaller
    monkeypatch.setattr(AdvancedInstaller, 'approve', lambda self, adb, serial, token: (serial, token))
    assert backend.installer.confirm(None, 'RC2-A', 'confirmed-token') == ('RC2-A', 'confirmed-token')


def test_close_uses_captured_relay_even_when_connection_disappears(tmp_path):
    worker = app.AdvancedWorker(tmp_path, tmp_path, lambda *e: None)
    relay = SimpleNamespace(stop_event=threading.Event())
    class Connection:
        @property
        def relay(self):
            worker.connection = None  # Simulate worker finalization between check/use.
            return relay
    worker.connection = Connection()
    worker.busy = True
    worker.close()
    assert relay.stop_event.is_set()
    worker.busy = False


def test_cancel_uses_captured_backend_even_when_backend_disappears(tmp_path):
    seen = []
    class Worker(app.AdvancedWorker):
        @property
        def backend(self):
            value = self._backend_value
            self._backend_value = None
            return value
        @backend.setter
        def backend(self, value):
            self._backend_value = value
    worker = Worker(tmp_path, tmp_path, lambda *e: None)
    worker.backend = SimpleNamespace(installer=SimpleNamespace(cancel_pending=lambda: seen.append('revoked')))
    worker.cancel()
    assert seen == ['revoked']


def test_cancel_stops_blocked_pairing_and_allows_fresh_retry(rig):
    entered=threading.Event()
    connections=[]
    class Pairing(Connection):
        def open(self):
            entered.set()
            if not self.relay.stop_event.wait(2):
                raise RuntimeError('pairing never cancelled')
            raise RuntimeError('pairing cancelled')
    def factory(*args):
        obj=Pairing(*args) if not connections else Connection(*args)
        connections.append(obj)
        return obj
    rig.worker.connection_factory=factory
    assert rig.worker.request('connect','RC2-A')
    assert entered.wait(1)
    rig.worker.cancel()
    rig.worker.thread.join(1)
    assert not rig.worker.thread.is_alive() and connections[0].closed
    assert connections[0].relay.stop_event.is_set() and not rig.worker.busy
    assert rig.worker.request('connect','RC2-A')
    finish(rig.worker)
    assert rig.worker.adb is connections[1].adb and not connections[1].closed


def test_builder_reuses_existing_pc_signer_for_data_retaining_updates(monkeypatch,tmp_path):
    from rc2vi import hud_keys
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local-appdata'))
    legacy=tmp_path/'legacy-signing'
    legacy.mkdir();(legacy/'signer.json').write_text('{}','utf-8')
    monkeypatch.setattr(hud_keys,'HudKeyStore',lambda tools,root=None:SimpleNamespace(root=root or legacy))
    monkeypatch.setattr(app,'paths',lambda:(tmp_path,tmp_path/'new-private-appdata'))
    builder=app.builder_factory(tmp_path/'assets',tmp_path/'work',lambda *e:None)
    assert builder.keys.root==legacy


def test_translation_adapter_through_real_identity_and_pinned_root():
    from rc2vi.translation_install import _PinnedRoot, _identity
    class Root(Adb):
        def shell(self, command, **kwargs):
            self.commands.append(command)
            if command.endswith(' && echo TRANSLATION_OK'):
                command = command.removesuffix(' && echo TRANSLATION_OK')
                return self.values[command] + '\nTRANSLATION_OK'
            return 'pinned-physical-dispatch'
    root = Root()
    root.adb = SimpleNamespace(serial='')
    direct = app.TranslationTransport(root)
    identity = _identity(direct)
    assert identity == ('RC2-A', 'RC2-A', 30)
    frozen = _PinnedRoot(direct, identity)
    assert frozen.shell('id') == 'pinned-physical-dispatch'
    assert 'getprop ro.serialno' in root.commands[-1]
    assert frozen.adb.serial == 'RC2-A'


def test_checksum_shim_instances_are_independent():
    from rc2vi.core import pack
    class Relay:
        def _send_usb(self, wire):
            return wire
    private = app.checksum_relay_class(Relay)
    a, b = private(), private()
    wire = pack('CNXN', 1, 1024, b'host\0')
    broken = wire[:16] + b'\0' * 4 + wire[20:]
    assert a._send_usb(broken) == wire
    assert b._send_usb(broken) == wire
    assert a._send_usb(broken) == wire


@pytest.mark.parametrize('wire', [b'CNXN', b'x'*24])
def test_usb_checksum_shim_rejects_malformed_frames_before_dispatch(wire):
    from unittest.mock import Mock
    base = type('Base', (), {'_send_usb': Mock()})
    with pytest.raises(ValueError):app.checksum_relay_class(base)()._send_usb(wire)
    base._send_usb.assert_not_called()
