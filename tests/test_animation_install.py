"""Host-only fake ADB tests. These tests never enumerate or open real USB."""
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import shlex
import threading
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from PIL import Image
import pytest

from rc2vi import animation_install as module
from rc2vi.core import Device


SERIAL = 'RC2TEST001'
LIBRARY = (b'\x7fELF\x02' + b'\0' * 59 + b'persist.sys.customanim.boot\0'
           + b'persist.sys.customanim.shutdown\0' + b'native reviewed fixture')
OTHER = '/data/local/other/shutdown.zip'


def protobuf_properties(values):
    def field(number, raw):
        result, length = bytearray([number << 3 | 2]), len(raw)
        while length >= 128:
            result.append(length & 127 | 128)
            length >>= 7
        return bytes(result) + bytes([length]) + raw
    return b''.join(field(1, field(1, key.encode()) + field(2, value.encode()))
                    for key, value in values.items())


def zip_package(path, *, compression=ZIP_STORED, desc='1920 1080 24\np 1 0 part0\n',
                image_size=(1920, 1080), extra=None, raw_png=None):
    raw = io.BytesIO()
    Image.new('RGB', image_size, '#102030').save(raw, format='PNG')
    with ZipFile(path, 'w', compression=compression) as archive:
        archive.writestr('desc.txt', desc)
        archive.writestr('part0/00000.png', raw.getvalue() if raw_png is None else raw_png)
        if extra:
            archive.writestr(extra, b'extra')
    return path


class FakeAdb:
    def __init__(self):
        self.props = {'ro.serialno': SERIAL, 'ro.product.model': 'DJI RC 2',
                      'ro.product.device': 'rc331', 'ro.build.version.sdk': '30',
                      module._property('boot'): '', module._property('shutdown'): OTHER}
        self.identity = 'uid=0(root) gid=0(root)'
        self.files = {module.NATIVE_LIBRARY: LIBRARY,
                      '/product/media/bootanimation.zip': b'stock boot never modified',
                      OTHER: b'other shutdown untouched'}
        self.modes = {}
        self.commands = []
        self.transfers = []
        self.fail = None
        self.bad_hash = False
        self.bad_hash_path = False
        self.bad_size = False
        self.bad_mode = False
        self.push_mode = '666'
        self.push_owner = (0, 0)
        self.pushed_modes = []
        self.permission_updates = []
        self.links = set()
        self.after_push = None
        self.after_select = None
        self.persist_fails_for = None
        self.persisted = None
        self.directory_failure = False

    def shell(self, wrapped, timeout=20):
        match = re.fullmatch(r'\((.*)\) && echo (RC2_ANIM_OK_[0-9a-f]{32})', wrapped, re.S)
        assert match, wrapped
        command, marker = match.groups()
        self.commands.append(command)
        result, success = self._run(command)
        if self.fail and self.fail(command):
            success = False
        return (result + '\n' if result else '') + (marker if success else 'remote error')

    def _run(self, command):
        if command.startswith('getprop '):
            return self.props.get(command[8:], ''), True
        if command == 'id':
            return self.identity, True
        if command.startswith('setprop '):
            _, key, value = shlex.split(command)
            self.props[key] = value
            if self.after_select:
                self.after_select(key, value)
            return '', True
        if command.startswith('grep '):
            value = self.props[module._property('boot')]
            shutdown = self.props[module._property('shutdown')]
            failed = self.persist_fails_for is not None and self.persist_fails_for in (value, shutdown)
            return '', not failed
        if command.endswith('&& base64 ' + module.PERSISTENT_PROPERTIES):
            values = self.persisted if self.persisted is not None else {
                key: value for key, value in self.props.items() if key.startswith('persist.')}
            return base64.b64encode(protobuf_properties(values)).decode(), True
        if command.startswith('[ -d /data/local ]'):
            return '', not self.directory_failure
        if command.startswith('(set -C; : > '):
            path = command.split('> ', 1)[1].split(')', 1)[0]
            if path in self.files:
                return '', False
            self.files[path] = b''
            self.modes[path] = (0, 0, '644')
            return '', True
        if command.startswith('mv -n -- '):
            _, _, _, source, target = shlex.split(command)
            if target not in self.files:
                self.files[target] = self.files.pop(source)
                self.modes[target] = self.modes.pop(source)
            return '', True
        if command.startswith('[ -f ') and '&& chmod 0644 ' in command:
            path = command[len('[ -f '):].split(' ]', 1)[0]
            owner = self.modes.get(path, (0, 0, '644'))[:2]
            if path not in self.files or path in self.links or owner != (0, 0):
                return '', False
            self.modes[path] = (0, 0, '644')
            self.permission_updates.append(path)
            return '', True
        if 'rm -f -- ' in command:
            path = command.split('rm -f -- ', 1)[1].split(';', 1)[0]
            if path in self.links or (path in self.files and self.modes.get(path, (0, 0, '644'))[:2] != (0, 0)):
                return '', False
            self.files.pop(path, None)
            self.modes.pop(path, None)
            return '', True
        if command.startswith('if [ ! -e '):
            path = command.split('if [ ! -e ', 1)[1].split(' ]', 1)[0]
            if path in self.links:
                return '', False
            if path not in self.files:
                return module._ABSENT, True
            raw = self.files[path]
            digest = hashlib.sha256(raw).hexdigest()
            size = len(raw)
            uid, gid, mode = self.modes.get(path, (0, 0, '644'))
            printed_path = path
            if '/.upload-' in path:
                if self.bad_hash:
                    digest = '0' * 64
                if self.bad_hash_path:
                    printed_path = '/data/local/unrelated.zip'
                if self.bad_size:
                    size += 1
                if self.bad_mode:
                    mode = '666'
            return f'{digest}  {printed_path}\n{size} {uid} {gid} {mode}', True
        raise AssertionError('Unexpected device command: ' + command)

    def command(self, *args, timeout=20, check=True):
        self.transfers.append(args)
        if args[0] == 'pull':
            _, switch, remote, local = args
            assert switch == '-Z'
            Path(local).write_bytes(self.files[remote])
        elif args[0] == 'push':
            _, switch, local, remote = args
            assert switch == '-Z'
            self.files[remote] = Path(local).read_bytes()
            # A real ADB SEND uses the Windows source mode. Recorded RC2
            # evidence shows push overwrites the reserved upload's 0644 with
            # 0666; the installer must reapply permissions after transfer.
            self.modes[remote] = (*self.push_owner, self.push_mode)
            self.pushed_modes.append(self.push_mode)
            if self.after_push:
                self.after_push()
        else:
            raise AssertionError(args)
        return 'transfer completed'


class FakeLease:
    opened = []

    def __init__(self, name):
        self.name, self.closed = name, False
        self.opened.append(self)

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, device, assets, emit, adb):
        self.device, self.adb = device, adb
        self.closed = False
        self.opened = False

    def open(self):
        self.opened = True
        assert hasattr(self, '_opening_cancel')
        return self.adb

    def close(self):
        self.closed = True


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'REVIEWED_LIBRARY_SHA256', hashlib.sha256(LIBRARY).hexdigest())
    monkeypatch.setattr(module, 'UsbLease', FakeLease)
    FakeLease.opened = []
    adb = FakeAdb()
    device = Device(SERIAL, r'\\?\usb#vid_2ca3&pid_1021&mi_02#test')
    connections, enumerations = [], []

    def factory(device, assets, emit):
        connection = FakeConnection(device, assets, emit, adb)
        connections.append(connection)
        return connection

    def devices():
        enumerations.append(True)
        return [device]

    class Rig:
        def __init__(self):
            self.adb, self.connections, self.enumerations = adb, connections, enumerations
            self.package = zip_package(tmp_path / 'animation.zip')
            self.assets, self.work = tmp_path / 'assets', tmp_path / 'work'
            self.options = {'grounded': True, 'connection_factory': factory, 'discover_fn': devices}

        def install(self, kind='boot', **kwargs):
            return module.install_animation(self.assets, self.work, SERIAL, self.package, kind,
                                            **{**self.options, **kwargs})

        def restore(self, kind='boot', **kwargs):
            return module.restore_animation(self.assets, self.work, SERIAL, kind,
                                            **{**self.options, **kwargs})

    yield Rig()
    assert all(connection.closed for connection in connections)
    assert all(lease.closed for lease in FakeLease.opened)
    # The only deletions are this operation's upload, and no protected path is
    # mutated or service/reboot/remount/verity command is ever issued.
    for command in adb.commands:
        assert not re.search(r'\b(remount|reboot|disable-verity|avbctl|fastboot|stop|start|setenforce)\b', command)
        if 'rm -f -- ' in command:
            assert module.REMOTE_DIRECTORY + '/.upload-' in command


@pytest.mark.parametrize('operation', ['install', 'restore'])
@pytest.mark.parametrize('grounded', [False, None, 1, 'yes'])
def test_requires_exact_grounded_consent_before_usb(rig, operation, grounded):
    with pytest.raises(ValueError, match='hạ cánh'):
        getattr(rig, operation)(grounded=grounded)
    assert not rig.enumerations and not rig.connections and not rig.adb.commands


@pytest.mark.parametrize('serial', ['', 'x;reboot', '../rc2', 'a' * 129, None])
def test_serial_rejected_before_usb(rig, serial):
    with pytest.raises(ValueError, match='Serial'):
        module.install_animation(rig.assets, rig.work, serial, rig.package, **rig.options)
    assert not rig.enumerations


@pytest.mark.parametrize('kind', ['updating', '../../boot', '', None])
def test_only_two_fixed_property_kinds_before_usb(rig, kind):
    with pytest.raises(ValueError, match='Chỉ hỗ trợ'):
        rig.install(kind)
    assert not rig.enumerations


@pytest.mark.parametrize('bad', ['compressed', 'traversal', 'missing_desc', 'wrong_size', 'corrupt_png', 'wrong_desc', 'extra'])
def test_bad_package_fails_before_usb(rig, bad):
    if bad == 'compressed':
        zip_package(rig.package, compression=ZIP_DEFLATED)
    elif bad == 'traversal':
        zip_package(rig.package, extra='../other.txt')
    elif bad == 'missing_desc':
        rig.package.write_bytes(b'not a zip')
    elif bad == 'wrong_size':
        zip_package(rig.package, image_size=(100, 100))
    elif bad == 'corrupt_png':
        zip_package(rig.package, raw_png=b'\x89PNG\r\n\x1a\n')
    elif bad == 'wrong_desc':
        zip_package(rig.package, desc='1920 1080 24\np 1 0 ../part0\n')
    else:
        zip_package(rig.package, extra='unknown.txt')
    with pytest.raises(ValueError):
        rig.install()
    assert not rig.enumerations and not rig.adb.commands


@pytest.mark.parametrize('devices', [[], [Device('OTHER', 'other')], [Device(SERIAL, 'a'), Device(SERIAL, 'b')]])
def test_missing_or_ambiguous_discovered_serial_never_opens(rig, devices):
    with pytest.raises(ValueError, match='đúng một'):
        rig.install(discover_fn=lambda: devices)
    assert not rig.connections


@pytest.mark.parametrize('field,value', [('ro.serialno', 'OTHER'), ('ro.product.model', 'Phone'),
                                        ('ro.product.device', 'rc330'), ('ro.build.version.sdk', '31')])
def test_live_identity_must_match_selected_rc2(rig, field, value):
    rig.adb.props[field] = value
    with pytest.raises(ValueError):
        rig.install()
    assert not rig.adb.transfers and not any(c.startswith('setprop ') for c in rig.adb.commands)


def test_root_identity_required(rig):
    rig.adb.identity = 'uid=2000(shell)'
    with pytest.raises(ValueError, match='shell root'):
        rig.install()
    assert not rig.adb.transfers


def test_unsupported_native_library_fails_without_property_mutation(rig):
    rig.adb.files[module.NATIVE_LIBRARY] += b'future firmware'
    with pytest.raises(ValueError, match='chưa được kiểm chứng'):
        rig.install()
    assert not any(c.startswith('setprop ') for c in rig.adb.commands)
    assert not any(args[0] == 'push' for args in rig.adb.transfers)


def test_reviewed_hash_also_requires_both_exact_native_strings(rig, monkeypatch):
    modified = LIBRARY.replace(b'customanim.shutdown\0', b'customanim.shutdownX')
    rig.adb.files[module.NATIVE_LIBRARY] = modified
    monkeypatch.setattr(module, 'REVIEWED_LIBRARY_SHA256', hashlib.sha256(modified).hexdigest())
    with pytest.raises(ValueError, match='custom animation'):
        rig.install()
    assert not any(c.startswith('setprop ') for c in rig.adb.commands)


def test_selected_device_object_is_exact_discovery_result(rig):
    result = rig.install()
    assert rig.connections[0].device.serial == SERIAL
    assert rig.connections[0].device.path.endswith('#test')
    assert result['status'] == 'installed' and result['installed_verified'] is True
    assert result['persistent_property_file_verified'] is True
    assert result['boot_visual_verified'] is False and result['reboot_performed'] is False
    assert result['other_animation_unchanged'] is True and result['stock_unchanged'] is True
    assert rig.adb.props[module._property('shutdown')] == OTHER
    assert rig.adb.files['/product/media/bootanimation.zip'] == b'stock boot never modified'
    assert hashlib.sha256(rig.adb.files[result['property_value']]).hexdigest() == result['package_sha256']
    assert len(result['property_value']) <= 91
    saved = json.loads(Path(result['receipt']).read_text('utf-8'))
    assert saved['serial'] == SERIAL and saved['previous_property_value'] == ''
    assert not any('/.upload-' in path for path in rig.adb.files)


@pytest.mark.parametrize('failure', ['bad_hash', 'bad_hash_path', 'bad_size', 'bad_mode'])
def test_push_must_match_hash_path_size_and_permissions(rig, failure):
    setattr(rig.adb, failure, True)
    with pytest.raises(ValueError):
        rig.install()
    assert rig.adb.props[module._property('boot')] == ''
    assert not any(c.startswith('setprop ') for c in rig.adb.commands)
    assert not any('/.upload-' in path for path in rig.adb.files)


def test_remote_nonzero_without_marker_is_rejected_even_when_adb_process_succeeds(rig):
    rig.adb.directory_failure = True
    with pytest.raises(RuntimeError, match='không xác nhận'):
        rig.install()
    assert not any(args[0] == 'push' for args in rig.adb.transfers)
    assert rig.adb.props[module._property('boot')] == ''


def test_preexisting_stage_never_overwritten_or_removed(rig):
    digest = hashlib.sha256(rig.package.read_bytes()).hexdigest()
    stage = module.REMOTE_DIRECTORY + '/.upload-' + digest + '.zip'
    rig.adb.files[stage] = b'user preexisting file'
    with pytest.raises(RuntimeError):
        rig.install()
    assert rig.adb.files[stage] == b'user preexisting file'
    assert not any(args[0] == 'push' for args in rig.adb.transfers)


def test_preexisting_final_collision_never_overwritten(rig):
    digest = hashlib.sha256(rig.package.read_bytes()).hexdigest()
    final = module.REMOTE_DIRECTORY + '/bootanimation-' + digest[:16] + '.zip'
    rig.adb.files[final] = b'different preexisting file'
    with pytest.raises(ValueError):
        rig.install()
    assert rig.adb.files[final] == b'different preexisting file'
    assert not any(args[0] == 'push' for args in rig.adb.transfers)


def test_cancel_before_usb(rig):
    event = threading.Event()
    event.set()
    with pytest.raises(module.AnimationCancelled):
        rig.install(cancel=event)
    assert not rig.enumerations


def test_cancel_during_push_cleans_only_new_stage_and_closes_connection(rig):
    event = threading.Event()
    rig.adb.after_push = event.set
    with pytest.raises(module.AnimationCancelled):
        rig.install(cancel=event)
    assert rig.adb.props[module._property('boot')] == ''
    assert not any('/.upload-' in path for path in rig.adb.files)
    assert rig.connections[0]._opening_cancel.is_set()


def test_cancel_after_property_selection_rolls_back_without_success_receipt(rig):
    event = threading.Event()
    rig.adb.after_select = lambda key, value: event.set() if value else None
    with pytest.raises(module.AnimationCancelled):
        rig.install(cancel=event)
    assert rig.adb.props[module._property('boot')] == ''
    assert not list(rig.work.rglob('installation.json'))
    reports = [json.loads(path.read_text('utf-8')) for path in rig.work.rglob('operation-*.json')]
    assert reports[-1]['rollback_verified'] is True and reports[-1]['installed_verified'] is False


def test_persistence_failure_rolls_back_previous_property(rig):
    digest = hashlib.sha256(rig.package.read_bytes()).hexdigest()
    rig.adb.persist_fails_for = module.REMOTE_DIRECTORY + '/bootanimation-' + digest[:16] + '.zip'
    with pytest.raises(RuntimeError):
        rig.install()
    assert rig.adb.props[module._property('boot')] == ''
    assert not list(rig.work.rglob('installation.json'))


def test_lost_setprop_reply_still_triggers_verified_rollback(rig):
    failed = False

    def fail_once(command):
        nonlocal failed
        if command.startswith('setprop ') and not failed:
            failed = True
            return True
        return False

    rig.adb.fail = fail_once
    with pytest.raises(RuntimeError):
        rig.install()
    assert rig.adb.props[module._property('boot')] == ''
    report = json.loads(next(rig.work.rglob('operation-*.json')).read_text('utf-8'))
    assert report['rollback_verified'] is True


def test_restore_preserves_previous_custom_animation_and_other_kind(rig):
    previous = '/data/local/earlier/custom.zip'
    rig.adb.props[module._property('boot')] = previous
    rig.adb.files[previous] = b'earlier animation'
    result = rig.install()
    assert result['previous_property_value'] == previous
    backups = list(Path(result['receipt']).parent.glob('previous-*.zip'))
    assert len(backups) == 1 and backups[0].read_bytes() == b'earlier animation'
    restored = rig.restore()
    assert restored['restored_verified'] is True and restored['changed'] is True
    assert rig.adb.props[module._property('boot')] == previous
    assert rig.adb.props[module._property('shutdown')] == OTHER
    assert result['property_value'] in rig.adb.files
    again = rig.restore()
    assert again['changed'] is False


def test_repeated_install_keeps_original_restore_target_and_last_good_package(rig):
    first = rig.install()
    zip_package(rig.package, desc='1920 1080 25\np 1 0 part0\n')
    second = rig.install()
    assert second['previous_property_value'] == ''
    assert first['property_value'] in rig.adb.files
    assert second['property_value'] in rig.adb.files
    rig.restore()
    assert rig.adb.props[module._property('boot')] == ''


def test_identical_package_reused_without_overwrite(rig):
    first = rig.install()
    pushes = len([args for args in rig.adb.transfers if args[0] == 'push'])
    second = rig.install()
    assert first['property_value'] == second['property_value']
    assert len([args for args in rig.adb.transfers if args[0] == 'push']) == pushes


def test_restoring_default_is_noop_with_no_receipt(rig):
    result = rig.restore()
    assert result['status'] == 'restored' and result['changed'] is False
    assert not any(c.startswith('setprop ') for c in rig.adb.commands)


def test_restore_legacy_owned_install_clears_only_own_property(rig):
    legacy = module.REMOTE_DIRECTORY + '/bootanimation-9cb41cce8c185908.zip'
    rig.adb.props[module._property('boot')] = legacy
    rig.adb.files[legacy] = b'previous hand-installed Ginza package'
    result = rig.restore()
    assert result['restored_verified'] is True
    assert rig.adb.props[module._property('boot')] == ''
    assert rig.adb.props[module._property('shutdown')] == OTHER
    assert rig.adb.files[legacy] == b'previous hand-installed Ginza package'


@pytest.mark.parametrize('current', ['/data/local/other/custom.zip',
                                     module.REMOTE_DIRECTORY + '/shutdownanimation-0123456789abcdef.zip',
                                     module.REMOTE_DIRECTORY + '/bootanimation-invalid.zip'])
def test_restore_without_own_receipt_does_not_overwrite_unrelated_config(rig, current):
    rig.adb.props[module._property('boot')] = current
    with pytest.raises(ValueError):
        rig.restore()
    assert rig.adb.props[module._property('boot')] == current
    assert not any(c.startswith('setprop ') for c in rig.adb.commands)


def test_receipt_cannot_override_configuration_changed_outside_tool(rig):
    rig.install()
    external = '/data/local/other/later.zip'
    rig.adb.props[module._property('boot')] = external
    before = len(rig.adb.commands)
    with pytest.raises(ValueError, match='đổi ngoài'):
        rig.restore()
    assert rig.adb.props[module._property('boot')] == external
    assert not any(c.startswith('setprop ') for c in rig.adb.commands[before:])


def test_restore_rejects_changed_previous_package(rig):
    previous = '/data/local/earlier/custom.zip'
    rig.adb.props[module._property('boot')] = previous
    rig.adb.files[previous] = b'earlier animation'
    installed = rig.install()
    rig.adb.files[previous] = b'altered earlier animation'
    with pytest.raises(ValueError, match='không còn đúng'):
        rig.restore()
    assert rig.adb.props[module._property('boot')] == installed['property_value']


def test_corrupted_receipt_fails_without_property_change(rig):
    result = rig.install()
    receipt = Path(result['receipt'])
    data = json.loads(receipt.read_text('utf-8'))
    data['kind'] = 'shutdown'
    receipt.write_text(json.dumps(data), encoding='utf-8')
    before = len(rig.adb.commands)
    with pytest.raises(ValueError, match='Biên bản'):
        rig.restore()
    assert not any(c.startswith('setprop ') for c in rig.adb.commands[before:])


def test_shutdown_install_is_separate_and_missing_stock_is_allowed(rig):
    rig.adb.props[module._property('shutdown')] = ''
    boot = rig.install()
    shutdown = rig.install('shutdown')
    assert boot['receipt'] != shutdown['receipt']
    assert shutdown['stock_file'] is None
    assert rig.adb.props[module._property('boot')] == boot['property_value']
    assert rig.adb.props[module._property('shutdown')] == shutdown['property_value']
    rig.restore('shutdown')
    assert rig.adb.props[module._property('shutdown')] == ''
    assert rig.adb.props[module._property('boot')] == boot['property_value']


def test_cancelled_restore_rolls_back_to_installed_selection(rig):
    installed = rig.install()
    event = threading.Event()
    rig.adb.after_select = lambda key, value: event.set() if not value else None
    with pytest.raises(module.AnimationCancelled):
        rig.restore(cancel=event)
    assert rig.adb.props[module._property('boot')] == installed['property_value']
    saved = json.loads(Path(installed['receipt']).read_text('utf-8'))
    assert saved['status'] == 'installed'


def test_connection_close_even_when_open_raises(rig):
    class Failed(FakeConnection):
        def open(self):
            raise OSError('USB connection failed')

    created = []

    def factory(device, assets, emit):
        connection = Failed(device, assets, emit, rig.adb)
        created.append(connection)
        return connection

    with pytest.raises(OSError):
        rig.install(connection_factory=factory)
    assert created[0].closed is True


def test_callable_cancel_is_forwarded_to_pending_authorization(rig):
    state = {'cancel': False}

    def factory(device, assets, emit):
        class Authorization(FakeConnection):
            def open(self):
                assert self._opening_cancel.is_set() is False
                state['cancel'] = True
                assert self._opening_cancel.is_set() is True
                raise module.AnimationCancelled('auth canceled')

        connection = Authorization(device, assets, emit, rig.adb)
        rig.connections.append(connection)
        return connection

    with pytest.raises(module.AnimationCancelled):
        rig.install(cancel=lambda: state['cancel'], connection_factory=factory)


@pytest.mark.parametrize('preset', ['minimal', 'metal', 'scifi'])
def test_real_engine_exports_validate_and_install_with_trim_or_full_canvas(rig, tmp_path, preset):
    from rc2vi.animation import export_animation, new_project
    project = new_project(preset)
    project.update(width=320, height=180, fps=6, intro=4, loop=1)
    result = export_animation(project, tmp_path / ('engine-' + preset))
    rig.package = Path(result['zip'])
    validation = module._validate_zip(rig.package)
    assert validation['frames'] == result['frames'] == 30
    assert validation['width'] == 320 and validation['height'] == 180
    assert validation['loop_texture_bytes'] == result['loop_texture_bytes']
    assert validation['loop_texture_padded_estimate_bytes'] == result['loop_texture_padded_estimate_bytes']
    installed = rig.install()
    assert installed['installed_verified'] is True


def test_default_full_hd_scifi_export_fits_native_npot_budget(rig, tmp_path):
    from rc2vi.animation import export_animation, new_project
    project = new_project('scifi')
    exported = export_animation(project, tmp_path / 'default-full-hd')
    rig.package = Path(exported['zip'])
    installed = rig.install()
    assert installed['installed_verified'] is True
    assert installed['package']['width'] == 1920 and installed['package']['height'] == 1080
    assert installed['package']['loop_texture_bytes'] == 1920 * 1080 * 4 * 24
    assert installed['package']['loop_texture_padded_estimate_bytes'] == 2048 * 2048 * 4 * 24
    # Native NPOT textures fit 256 MiB. Padding is an estimate for portability,
    # not a false rejection of this RC2's reviewed GLES implementation.
    assert installed['package']['loop_texture_bytes'] <= module.MAX_LOOP_TEXTURE_BYTES


def trimmed_zip(path, *, trim='80x40+10+20\n', image_size=(80, 40), frames=1):
    raw = io.BytesIO()
    Image.new('RGB', image_size, '#102030').save(raw, format='PNG')
    with ZipFile(path, 'w', compression=ZIP_STORED) as archive:
        archive.writestr('desc.txt', '320 180 6\np 0 0 part0\n')
        for index in range(frames):
            archive.writestr(f'part0/{index:05d}.png', raw.getvalue())
        archive.writestr('part0/trim.txt', trim)
    return path


@pytest.mark.parametrize('trim', ['80x40+300+20\n', '80x40+-1+20\n', '0x40+10+20\n',
                                '80x40+10+20\n80x40+10+20\n', 'not geometry\n',
                                '90x40+10+20\n'])
def test_bad_trim_or_png_geometry_fails_before_usb(rig, trim):
    trimmed_zip(rig.package, trim=trim)
    with pytest.raises(ValueError):
        rig.install()
    assert not rig.enumerations


def test_trim_matches_lexical_png_order(rig):
    small, large = io.BytesIO(), io.BytesIO()
    Image.new('RGB', (30, 20)).save(small, format='PNG')
    Image.new('RGB', (60, 40)).save(large, format='PNG')
    with ZipFile(rig.package, 'w', compression=ZIP_STORED) as archive:
        archive.writestr('desc.txt', '320 180 6\np 0 0 part0\n')
        # Archive order differs from Android's lexical filename order.
        archive.writestr('part0/10.png', large.getvalue())
        archive.writestr('part0/02.png', small.getvalue())
        archive.writestr('part0/trim.txt', '30x20+0+0\n60x40+50+30\n')
    validated = module._validate_zip(rig.package)
    assert validated['loop_texture_bytes'] == (30 * 20 + 60 * 40) * 4


def test_loop_memory_budget_is_checked_on_decoded_trim_sizes(rig, monkeypatch):
    trimmed_zip(rig.package, frames=2, trim='80x40+10+20\n80x40+10+20\n')
    monkeypatch.setattr(module, 'MAX_LOOP_TEXTURE_BYTES', 80 * 40 * 4)
    with pytest.raises(ValueError, match='256 MiB'):
        rig.install()
    assert not rig.enumerations


def test_failed_replacement_retains_prior_good_receipt_and_package(rig):
    first = rig.install()
    receipt_path = Path(first['receipt'])
    original_receipt = receipt_path.read_bytes()
    zip_package(rig.package, desc='1920 1080 25\np 1 0 part0\n')
    event = threading.Event()
    rig.adb.after_select = lambda key, value: event.set() if value != first['property_value'] else None
    with pytest.raises(module.AnimationCancelled):
        rig.install(cancel=event)
    assert rig.adb.props[module._property('boot')] == first['property_value']
    assert receipt_path.read_bytes() == original_receipt
    assert first['property_value'] in rig.adb.files


def test_receipt_commit_failure_rolls_back_without_losing_prior_receipt(rig, monkeypatch):
    first = rig.install()
    receipt_path = Path(first['receipt'])
    prior_receipt = receipt_path.read_bytes()
    zip_package(rig.package, desc='1920 1080 25\np 1 0 part0\n')
    original_write = module._atomic_json

    def fail_commit(path, value):
        if Path(path) == receipt_path:
            raise OSError('disk full during receipt commit')
        return original_write(path, value)

    monkeypatch.setattr(module, '_atomic_json', fail_commit)
    with pytest.raises(OSError, match='disk full'):
        rig.install()
    assert rig.adb.props[module._property('boot')] == first['property_value']
    assert receipt_path.read_bytes() == prior_receipt


def test_duplicate_zip_members_fail_before_usb(rig):
    with ZipFile(rig.package, 'a') as archive:
        with pytest.warns(UserWarning):
            archive.writestr('desc.txt', '320 180 6\np 1 0 part0\n')
    with pytest.raises(ValueError):
        rig.install()
    assert not rig.enumerations


def test_persistent_file_checks_use_fixed_string_grep_for_only_selected_property(rig):
    rig.install()
    grep = [command for command in rig.adb.commands if command.startswith('grep ')]
    assert grep
    assert all('grep -a -F -q -- persist.sys.customanim.boot ' in command for command in grep)
    assert all(module.PERSISTENT_PROPERTIES in command for command in grep)
    assert all('persist.sys.customanim.shutdown' not in command for command in grep)


def test_strict_previous_property_value_cannot_inject_remote_commands(rig):
    rig.adb.props[module._property('boot')] = '/data/local/a.zip; reboot'
    with pytest.raises(ValueError, match='Đường dẫn animation'):
        rig.install()
    assert not any(args[0] == 'push' for args in rig.adb.transfers)
    assert not any(command.startswith('setprop ') for command in rig.adb.commands)


def test_literal_property_value_under_other_record_is_not_persistence_proof(rig):
    digest = hashlib.sha256(rig.package.read_bytes()).hexdigest()
    final = module.REMOTE_DIRECTORY + '/bootanimation-' + digest[:16] + '.zip'
    # Fixed grep would find both the boot key and new path, but the new path
    # belongs to an unrelated property. Exact protobuf binding must fail.
    rig.adb.persisted = {module._property('boot'): '', 'persist.unrelated.animation': final}
    with pytest.raises(ValueError, match='chưa được lưu bền'):
        rig.install()
    assert rig.adb.props[module._property('boot')] == ''
    report = json.loads(next(rig.work.rglob('operation-*.json')).read_text('utf-8'))
    assert report['rollback_verified'] is True


def test_empty_restore_requires_persisted_empty_value_not_just_key_presence(rig):
    first = rig.install()
    rig.adb.persisted = {module._property('boot'): first['property_value']}
    with pytest.raises(ValueError, match='chưa được lưu bền'):
        rig.restore()
    # Old persisted selection remained, so restore rolls the running property
    # back to the installed animation and reports failure truthfully.
    assert rig.adb.props[module._property('boot')] == first['property_value']
    report = json.loads(next(rig.work.rglob('restore-*.json')).read_text('utf-8'))
    assert report['restored_verified'] is False and report['rollback_verified'] is True


@pytest.mark.parametrize('raw', [b'', b'\x0a\xff', b'\x08\x00', b'\x0a\x05\x0a\x01x',
                                protobuf_properties({'persist.other': 'value'})])
def test_malformed_or_missing_persistent_property_is_rejected(raw):
    with pytest.raises(ValueError):
        module._persisted_value(raw, module._property('boot'))


def test_duplicate_persistent_property_records_are_rejected():
    record = protobuf_properties({module._property('boot'): ''})
    with pytest.raises(ValueError, match='đúng một'):
        module._persisted_value(record + record, module._property('boot'))


@pytest.mark.parametrize('push_mode', ['666', '600', '644', '0644'])
def test_adb_send_mode_is_hardened_after_transfer_on_only_owned_upload(rig, push_mode):
    rig.adb.push_mode = push_mode
    installed = rig.install()
    digest = installed['package_sha256']
    stage = module.REMOTE_DIRECTORY + '/.upload-' + digest + '.zip'
    assert rig.adb.pushed_modes == [push_mode]
    assert rig.adb.permission_updates == [stage]
    assert rig.adb.modes[installed['property_value']] == (0, 0, '644')
    assert installed['installed_verified'] is True
    assert not any(command.startswith('[ -f ' + installed['property_value'])
                   for command in rig.adb.commands)


@pytest.mark.parametrize('owner', [(2000, 2000), (0, 2000)])
def test_upload_whose_owner_changed_is_not_chowned_or_removed(rig, owner):
    rig.adb.push_owner = owner
    with pytest.raises(ValueError, match=f'UID:GID {owner[0]}:{owner[1]}, cần 0:0'):
        rig.install()
    assert rig.adb.permission_updates == []
    assert any('/.upload-' in path for path in rig.adb.files)
    assert rig.adb.props[module._property('boot')] == ''
    assert not any(command.startswith('setprop ') for command in rig.adb.commands)


def test_upload_replaced_with_link_after_push_is_not_chmodded_or_removed(rig):
    def replace_with_link():
        stage = rig.adb.transfers[-1][-1]
        rig.adb.links.add(stage)
    rig.adb.after_push = replace_with_link
    with pytest.raises(RuntimeError):
        rig.install()
    assert rig.adb.permission_updates == []
    assert rig.adb.links
    assert rig.adb.props[module._property('boot')] == ''


def test_preexisting_final_with_wrong_permissions_remains_strictly_rejected(rig):
    installed = rig.install()
    final = installed['property_value']
    rig.adb.modes[final] = (0, 0, '666')
    updates = list(rig.adb.permission_updates)
    with pytest.raises(ValueError, match='quyền 0666, cần 0644'):
        rig.install()
    assert rig.adb.modes[final] == (0, 0, '666')
    assert rig.adb.permission_updates == updates
    assert len([transfer for transfer in rig.adb.transfers if transfer[0] == 'push']) == 1


@pytest.mark.parametrize('mode', ['644', '0644'])
def test_package_verification_accepts_both_valid_octal_stat_representations(mode):
    package = {'sha256': 'a' * 64, 'size': 1234}
    remote = {**package, 'path': module.REMOTE_DIRECTORY + '/bootanimation-aaaaaaaaaaaaaaaa.zip',
              'uid': 0, 'gid': 0, 'mode': mode}
    module._verify_package(remote, package)


@pytest.mark.parametrize('field,actual,diagnostic', [
    ('sha256', 'b' * 64, 'SHA-256 trên tay ' + 'b' * 64 + ', cần ' + 'a' * 64),
    ('size', 12, 'kích thước 12 byte, cần 1234 byte'),
    ('uid', 2000, 'UID:GID 2000:0, cần 0:0'),
    ('gid', 2000, 'UID:GID 0:2000, cần 0:0'),
    ('mode', '666', 'quyền 0666, cần 0644'),
])
def test_package_mismatch_diagnostic_identifies_exact_expected_and_actual_values(field, actual, diagnostic):
    package = {'sha256': 'a' * 64, 'size': 1234}
    remote = {**package, 'path': module.REMOTE_DIRECTORY + '/bootanimation-aaaaaaaaaaaaaaaa.zip',
              'uid': 0, 'gid': 0, 'mode': '644', field: actual}
    with pytest.raises(ValueError) as caught:
        module._verify_package(remote, package)
    assert diagnostic in str(caught.value)


def test_reconnect_event_reaches_pending_open_separately_from_cancellation(rig):
    reconnect = threading.Event()
    reconnect.set()
    result = rig.install(reconnect_event=reconnect)
    connection = rig.connections[0]
    assert connection._opening_reconnect_event is reconnect
    assert not connection._opening_cancel.is_set()
    assert result['installed_verified'] and connection.closed


def test_reconnect_after_authorization_does_not_replay_upload_or_property_write(rig):
    reconnect = threading.Event()
    rig.adb.after_push = reconnect.set
    result = rig.install(reconnect_event=reconnect)
    assert result['installed_verified'] and reconnect.is_set()
    assert len(rig.connections) == 1
    assert len([transfer for transfer in rig.adb.transfers if transfer[0] == 'push']) == 1
    assert len([command for command in rig.adb.commands if command.startswith('setprop ')]) == 1
