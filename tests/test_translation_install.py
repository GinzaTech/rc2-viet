"""Fake-only deployment tests: never instantiate an ADB client or touch hardware."""
import hashlib
from pathlib import Path
import shlex
import struct
import threading
from types import SimpleNamespace

import pytest

from rc2vi import translation_install as module
from rc2vi.phone_overlay import RootShell


SOURCE = b'fake Fly APK'
PACK = b'fake resource APK'
PACKAGE = 'local.dji.fly.vi.auto.r' + hashlib.sha256(SOURCE).hexdigest()[:16] + 'c' + 'b' * 8 + 's' + 'c' * 8
PREVIOUS = 'local.dji.fly.vi.auto.r' + 'd' * 16 + 'c' + 'e' * 8 + 's' + 'f' * 8
LEGACY = 'local.dji.fly.vietnamese'
FOREIGN = 'other.vendor.translation'
TARGET = '/data/app/fly/base.apk'
OVERLAY = '/data/app/candidate/base.apk'
CACHE = '/data/resource-cache/data@app@candidate@base.apk@idmap'
SAMPLES = [{'name': 'connect_drone', 'value': 'Kết nối máy bay'},
           {'name': 'settings', 'value': 'Cài đặt'}]
COMPLETE_REPORT = {'complete': True, 'eligible_total': 8, 'reviewed': 5, 'machine': 3,
                   'matched': 8, 'unresolved': 0, 'target_untranslated': 0,
                   'preserved': 2, 'skipped': 2, 'total': 10, 'target_total': 10,
                   'machine_meaning_verified': False}


def digest(data):
    return hashlib.sha256(data).hexdigest()


class FakeDevice:
    def __init__(self, sdk=30):
        self.serial = 'selected-transport'
        self.physical = 'physical-RC2'
        self.sdk = sdk
        self.version = '9.99.1'
        self.version_code = 123456
        self.files = {TARGET: SOURCE}
        self.packages = {'dji.go.v5': TARGET}
        self.overlays = {LEGACY: True, PREVIOUS: True, FOREIGN: True}
        self.calls = []
        self.writes = []
        self.hook = lambda command: None
        self.bad_lookup = False
        self.fail_marker = None
        self.fail_write = None
        self.raw_valid = True

    def shell(self, command, **kwargs):
        self.calls.append(command)
        nested = command.startswith('su -c ')
        if nested:
            command = shlex.split(command)[2].removesuffix(' && echo PHONEVI_OK')
        if command.startswith('test "$(getprop ro.serialno)" = '):
            guard, command = command.split(' && ', 1)
            if shlex.split(guard)[-1] != self.physical:
                return ''
        marked = command.endswith(' && echo TRANSLATION_OK')
        if marked:
            command = command.removesuffix(' && echo TRANSLATION_OK')
        self.hook(command)
        output = self._execute(command)
        if command == self.fail_marker:
            return 'TRANSLATION_OK\npermission denied' + ('\nPHONEVI_OK' if nested else '')
        if marked:
            output += '\nTRANSLATION_OK'
        if nested:
            output += '\nPHONEVI_OK'
        return output.strip('\n')

    def _execute(self, command):
        if command == 'getprop ro.serialno':
            return self.physical
        if command == 'getprop ro.build.version.sdk':
            return str(self.sdk)
        if command == 'dumpsys package dji.go.v5':
            return f'versionName={self.version}\nversionCode={self.version_code} minSdk=24'
        if command.startswith('(pm path '):
            path = self.packages.get(command.split()[2])
            return 'package:' + path if path else ''
        if command.startswith('sha256sum '):
            path = shlex.split(command)[1]
            return digest(self.files[path]) + '  ' + path
        if command.startswith('stat -c %s '):
            return str(len(self.files[shlex.split(command)[3]]))
        if command == 'cmd overlay list --user 0 dji.go.v5':
            return 'dji.go.v5\n' + '\n'.join(
                ('[x] ' if enabled else '[ ] ') + package
                for package, enabled in self.overlays.items())
        if command.startswith('cmd overlay lookup --user 0 '):
            name = shlex.split(command)[-1].split('/')[-1]
            if self.bad_lookup or not self.overlays.get(PACKAGE) or self.overlays.get(LEGACY):
                return 'untranslated'
            return next(sample['value'] for sample in SAMPLES if sample['name'] == name)
        if command.startswith('if [ -f '):
            return 'yes' if shlex.split(command)[3] in self.files else ''
        self.writes.append(command)
        if self.fail_write and self.fail_write(command):
            raise RuntimeError('simulated write failure')
        # Only implement the small shell grammar used by the installer.
        for part in command.split(' && '):
            args = shlex.split(part)
            if args[0] in {'mkdir', 'chmod', 'chown', 'restorecon', 'rmdir'}:
                continue
            if args[:2] == ['pm', 'install']:
                assert '-r' not in args
                self.files[OVERLAY] = self.files[args[-1]]
                self.packages[PACKAGE] = OVERLAY
                self.overlays[PACKAGE] = False
            elif args[:2] == ['pm', 'uninstall']:
                assert args == ['pm', 'uninstall', '--user', '0', PACKAGE]
                path = self.packages.pop(PACKAGE, None)
                if path:
                    self.files.pop(path, None)
                self.overlays.pop(PACKAGE, None)
            elif args[:2] == ['idmap2', 'create']:
                destination = args[args.index('--idmap-path') + 1]
                if self.sdk == 30:
                    raw = struct.pack('<5IB', 0x504d4449, 4, 1, 2, 1, 0)
                    raw += TARGET.encode().ljust(256, b'\0') + OVERLAY.encode().ljust(256, b'\0')
                    raw += b'\0' * 80
                else:
                    raw = struct.pack('<6I', 0x504d4449, 9, 1, 2, 1, 0)
                    for value in (TARGET, OVERLAY, '', 'debug'):
                        value = value.encode()
                        raw += struct.pack('<I', len(value)) + value + b'\0' * (-len(value) % 4)
                    raw += b'\0' * 80
                self.files[destination] = raw if self.raw_valid else b'bad idmap'
            elif args[:2] == ['cmd', 'overlay'] and args[2] in {'enable', 'disable'}:
                self.overlays[args[-1]] = args[2] == 'enable'
            elif args[0] == 'cp':
                self.files[args[-1]] = self.files[args[-2]]
            elif args[:2] == ['rm', '-f']:
                for path in args[2:]:
                    self.files.pop(path, None)
            else:
                raise AssertionError('Unexpected or destructive fake command: ' + part)
        return 'Success' if command.startswith(('pm install ', 'pm uninstall ')) else ''

    def command(self, *args, **kwargs):
        self.calls.append(args)
        self.hook(args)
        if args[0] == 'pull':
            Path(args[2]).write_bytes(self.files[args[1]])
        elif args[0] == 'push':
            self.writes.append(args)
            self.files[args[2]] = Path(args[1]).read_bytes()
        else:
            raise AssertionError('Only fake push/pull allowed')
        return ''


@pytest.fixture
def setup(tmp_path):
    work = tmp_path / 'work'
    work.mkdir()
    apk = work / 'candidate.apk'
    apk.write_bytes(PACK)
    artifact = {'apk': apk, 'digest': digest(PACK), 'source_digest': digest(SOURCE),
                'package': PACKAGE, 'version': '9.99.1', 'version_code': 123456,
                'report': dict(COMPLETE_REPORT), 'samples': SAMPLES}
    events, sources = [], []

    def build(source):
        assert source.read_bytes() == SOURCE
        sources.append(source)
        return artifact

    cancel = threading.Event()
    tool = module.AdaptiveTranslation(tmp_path / 'assets', work,
                                     lambda *event: events.append(event), cancel,
                                     SimpleNamespace(build=build))
    return SimpleNamespace(tool=tool, adb=FakeDevice(), artifact=artifact,
                           events=events, sources=sources, cancel=cancel, safe=lambda: None)


@pytest.mark.parametrize('sdk', [30, 35])
def test_success_counts_both_idmap_formats_and_root_nesting(setup, sdk):
    s = setup
    s.adb.sdk = sdk
    root = RootShell(s.adb) if sdk == 35 else s.adb
    result = s.tool.apply(s.adb, root, sdk, s.safe)
    assert result['status'] == 'enabled'
    assert result['report'] == COMPLETE_REPORT
    assert s.adb.overlays == {LEGACY: False, PREVIOUS: False, FOREIGN: True, PACKAGE: True}
    assert s.adb.files[CACHE][20] == 1
    assert any('5 đã duyệt' in e[1] and '3 do máy dịch' in e[1] and '2 tài nguyên kỹ thuật' in e[1] for e in s.events)
    assert 'chỉ được kiểm tra định dạng' in result['message']
    assert not any('một phần' in e[1] for e in s.events)
    assert len([c for c in s.adb.calls if isinstance(c, str) and 'overlay lookup' in c]) == 2
    assert all(not path.exists() for path in s.sources)
    assert not any(path.startswith('/data/local/tmp/') for path in s.adb.files)
    assert s.adb.files[TARGET] == SOURCE


@pytest.mark.parametrize('stage', ['pull', 'build', 'before_write', 'readback'])
def test_source_changed_fails_closed(setup, stage):
    s = setup
    before = dict(s.adb.overlays)

    def change(command):
        if ((stage == 'pull' and isinstance(command, tuple) and command[0] == 'pull') or
                (stage == 'readback' and isinstance(command, str) and command.startswith('cmd overlay enable'))):
            s.adb.files[TARGET] = b'Fly updated during operation'

    s.adb.hook = change
    if stage == 'build':
        build = s.tool.builder.build
        s.tool.builder.build = lambda path: (build(path), s.adb.files.update({TARGET: b'changed'}))[0]
    if stage == 'before_write':
        s.safe = lambda: s.adb.files.update({TARGET: b'changed'})
    with pytest.raises((ValueError, RuntimeError)):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    if stage != 'readback':
        assert not s.adb.writes
    else:
        assert {p: v for p, v in s.adb.overlays.items() if p != PACKAGE} == before
        assert PACKAGE not in s.adb.overlays and PACKAGE not in s.adb.packages


@pytest.mark.parametrize('field,value', [
    ('package', 'local.dji.fly.vi.auto.evil;id'), ('package', 'dji.go.v5'),
    ('digest', 'x' * 64), ('digest', '0' * 64), ('source_digest', '0' * 64),
    ('version', 'wrong'), ('version_code', True), ('version_code', -1),
    ('report', {'matched': 1, 'skipped': 3, 'total': 2}),
    ('samples', []), ('samples', [{'name': 'bad;command', 'value': 'bad'}]),
    ('samples', [{'name': 'valid', 'value': 'line\nbreak'}]),
])
def test_malformed_builder_fields_never_push(setup, field, value):
    setup.artifact[field] = value
    with pytest.raises((ValueError, TypeError)):
        setup.tool.apply(setup.adb, setup.adb, 30, setup.safe)
    assert not setup.adb.writes


@pytest.mark.parametrize('kind', ['missing', 'directory', 'string', 'outside', 'traversal', 'extension'])
def test_malformed_builder_paths_never_push(setup, kind, tmp_path):
    s = setup
    if kind == 'missing':
        s.artifact['apk'] = s.tool.work / 'missing.apk'
    elif kind == 'directory':
        s.artifact['apk'] = s.tool.work
    elif kind == 'string':
        s.artifact['apk'] = str(s.artifact['apk'])
    elif kind == 'outside':
        s.artifact['apk'] = tmp_path / 'foreign.apk'
        s.artifact['apk'].write_bytes(PACK)
    elif kind == 'traversal':
        s.artifact['apk'] = s.tool.work / '..' / 'work' / 'candidate.apk'
    else:
        s.artifact['apk'] = s.tool.work / 'candidate.txt'
        s.artifact['apk'].write_bytes(PACK)
    with pytest.raises((ValueError, OSError, TypeError)):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert not s.adb.writes


@pytest.mark.parametrize('physical', [False, True])
def test_selected_serial_change_during_build_blocks_mutation(setup, physical):
    s = setup
    build = s.tool.builder.build

    def changed(path):
        artifact = build(path)
        setattr(s.adb, 'physical' if physical else 'serial', 'different-device')
        return artifact

    s.tool.builder.build = changed
    with pytest.raises((ValueError, RuntimeError), match='thay đổi|changed|serial|chưa hoàn thành'):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert not s.adb.writes


@pytest.mark.parametrize('old_cache', [None, b'previous cache'])
@pytest.mark.parametrize('candidate_enabled', [False, True])
def test_readback_failure_restores_exact_enabled_set_and_cache(setup, old_cache, candidate_enabled):
    s = setup
    s.adb.packages[PACKAGE] = OVERLAY
    s.adb.files[OVERLAY] = PACK
    s.adb.overlays[PACKAGE] = candidate_enabled
    s.adb.bad_lookup = True
    if old_cache is not None:
        s.adb.files[CACHE] = old_cache
    before = dict(s.adb.overlays)
    with pytest.raises(RuntimeError):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert s.adb.overlays == before
    assert s.adb.files.get(CACHE) == old_cache
    assert not any(path.startswith('/data/local/tmp/') for path in s.adb.files)


def test_existing_foreign_same_package_never_replaced(setup):
    s = setup
    s.adb.packages[PACKAGE] = OVERLAY
    s.adb.files[OVERLAY] = b'foreign pack'
    with pytest.raises(ValueError):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert not s.adb.writes


def test_already_enabled_verifies_every_sample_without_remote_writes(setup):
    s = setup
    s.adb.packages[PACKAGE] = OVERLAY
    s.adb.files[OVERLAY] = PACK
    s.adb.overlays = {PACKAGE: True, FOREIGN: True}
    assert s.tool.apply(s.adb, s.adb, 30, s.safe)['status'] == 'already_enabled'
    assert not s.adb.writes


def test_disable_unknown_updated_fly_does_not_check_version_or_hash(setup):
    s = setup
    s.adb.version = 'future.release'
    s.adb.files[TARGET] = b'new Fly'
    s.adb.overlays[PACKAGE] = True
    s.adb.overlays['local.dji.fly.vi.auto.not-owned'] = True
    result = s.tool.disable(s.adb, s.safe)
    assert result['status'] == 'disabled'
    assert not s.adb.overlays[PACKAGE] and not s.adb.overlays[PREVIOUS]
    assert not s.adb.overlays[LEGACY] and s.adb.overlays[FOREIGN]
    assert s.adb.overlays['local.dji.fly.vi.auto.not-owned']
    assert not any('dumpsys package' in str(c) or 'sha256sum' in str(c) for c in s.adb.calls)


def test_cancellation_before_mutation_and_during_enable_rolls_back(setup):
    s = setup
    s.cancel.set()
    with pytest.raises(RuntimeError):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert not s.adb.writes
    s.cancel.clear()
    before = dict(s.adb.overlays)
    s.adb.hook = lambda c: s.cancel.set() if isinstance(c, str) and c.startswith('cmd overlay enable') else None
    with pytest.raises(RuntimeError):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert all(s.adb.overlays[p] == value for p, value in before.items())
    assert PACKAGE not in s.adb.overlays and PACKAGE not in s.adb.packages
    assert CACHE not in s.adb.files


def test_write_requires_final_completion_marker(setup):
    s = setup
    s.adb.fail_marker = 'cmd overlay enable --user 0 ' + PACKAGE
    with pytest.raises(RuntimeError):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert PACKAGE not in s.adb.overlays and s.adb.overlays[LEGACY]


def test_bad_idmap_never_changes_active_overlays_or_cache(setup):
    s = setup
    s.adb.raw_valid = False
    before = dict(s.adb.overlays)
    with pytest.raises(ValueError):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert all(s.adb.overlays[p] == value for p, value in before.items())
    assert CACHE not in s.adb.files


def test_disable_failure_rolls_back_even_after_cancel(setup):
    s = setup
    s.adb.overlays[PACKAGE] = True
    before = dict(s.adb.overlays)
    s.adb.hook = lambda c: s.cancel.set() if isinstance(c, str) and c.startswith('cmd overlay disable') else None
    with pytest.raises(RuntimeError):
        s.tool.disable(s.adb, s.safe)
    assert s.adb.overlays == before


@pytest.mark.parametrize('sdk', [29, 31, 34, 36, '30', True])
def test_unsupported_sdk_never_mutates(setup, sdk):
    with pytest.raises(ValueError):
        setup.tool.apply(setup.adb, setup.adb, sdk, setup.safe)
    assert not setup.adb.writes


def test_root_and_transfer_transport_must_be_same(setup):
    with pytest.raises(ValueError):
        setup.tool.apply(setup.adb, RootShell(FakeDevice()), 30, setup.safe)
    assert not setup.adb.calls


@pytest.mark.parametrize('change', ['split', 'path', 'serial', 'metadata', 'size', 'sha'])
def test_invalid_snapshot_never_reaches_build(setup, change):
    s = setup
    original = s.adb._execute

    def invalid(command):
        if change == 'split' and command.startswith('(pm path '):
            return 'package:' + TARGET + '\npackage:/data/app/fly/split.apk'
        if change == 'path' and command.startswith('(pm path '):
            return 'package:/data/app/../foreign.apk'
        if change == 'serial' and command == 'getprop ro.serialno':
            return 'unknown'
        if change == 'metadata' and command.startswith('dumpsys package '):
            return 'versionName=1 versionCode=2\nversionName=2 versionCode=3'
        if change == 'size' and command.startswith('stat '):
            return str(module.MAX_APK + 1)
        if change == 'sha' and command.startswith('sha256sum '):
            return digest(SOURCE) + '  wrong-file'
        return original(command)

    s.adb._execute = invalid
    with pytest.raises(ValueError):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert not s.sources and not s.adb.writes


def test_artifact_modified_at_last_guard_never_pushed(setup):
    s = setup
    s.safe = lambda: s.artifact['apk'].write_bytes(b'changed')
    with pytest.raises(ValueError):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert not any(isinstance(c, tuple) and c[0] == 'push' for c in s.adb.calls)


def test_truncated_pulled_source_rejected(setup):
    s = setup
    command = s.adb.command

    def truncated(*args, **kwargs):
        output = command(*args, **kwargs)
        if args[0] == 'pull':
            Path(args[2]).write_bytes(b'truncated')
        return output

    s.adb.command = truncated
    with pytest.raises(ValueError):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert not s.adb.writes


@pytest.mark.parametrize('trigger', ['cp-cache', 'enable', 'disable-prior'])
def test_write_mutates_then_times_out_and_recovers(setup, trigger):
    s = setup
    s.adb.files[CACHE] = b'previous cache'
    before = dict(s.adb.overlays)
    execute = s.adb._execute
    fired = False

    def timeout(command):
        nonlocal fired
        output = execute(command)
        if not fired and ((trigger == 'cp-cache' and command.startswith('cp ') and 'approved.idmap ' in command)
                          or (trigger == 'enable' and command.startswith('cmd overlay enable'))
                          or (trigger == 'disable-prior' and command.startswith('cmd overlay disable'))):
            fired = True
            raise TimeoutError('command applied but acknowledgement lost')
        return output

    s.adb._execute = timeout
    with pytest.raises(TimeoutError):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert fired and s.adb.files[CACHE] == b'previous cache'
    assert all(s.adb.overlays[p] == value for p, value in before.items())
    assert PACKAGE not in s.adb.overlays and PACKAGE not in s.adb.packages


def test_failed_cache_restore_keeps_backup_and_attempts_prior_enables(setup):
    s = setup
    s.adb.files[CACHE] = b'previous cache'
    s.adb.bad_lookup = True
    s.adb.fail_write = lambda command: command.startswith('cp ') and '/previous.idmap ' in command
    with pytest.raises(RuntimeError, match='Phục hồi'):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert s.adb.overlays[LEGACY] and s.adb.overlays[PREVIOUS]
    assert any(path.endswith('/previous.idmap') and data == b'previous cache' for path, data in s.adb.files.items())
    assert any('Giữ' in event[1] for event in s.events)


def test_cleanup_failure_does_not_mask_verified_success(setup):
    s = setup
    s.adb.fail_write = lambda command: command.startswith('rm -f ')
    assert s.tool.apply(s.adb, s.adb, 30, s.safe)['status'] == 'enabled'
    assert any('Không dọn' in event[1] for event in s.events)


def test_corrupt_cache_backup_blocks_switching(setup):
    s = setup
    s.adb.files[CACHE] = b'original cache'
    execute = s.adb._execute

    def corrupt(command):
        result = execute(command)
        if command.startswith('cp ') and command.endswith('/previous.idmap'):
            s.adb.files[shlex.split(command)[-1]] = b'corrupt'
        return result

    s.adb._execute = corrupt
    with pytest.raises(ValueError):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert s.adb.overlays[LEGACY] and s.adb.files[CACHE] == b'original cache'


def test_foreign_prefix_and_disabled_packages_untouched_on_disable(setup):
    s = setup
    s.adb.overlays = {PACKAGE: False, FOREIGN: True, LEGACY: False}
    assert s.tool.disable(s.adb, s.safe)['count'] == 0
    assert not s.adb.writes
    s.adb.overlays = {FOREIGN: True}
    assert s.tool.disable(s.adb, s.safe)['status'] == 'absent'


def test_unsafe_foreground_blocks_all_writes(setup):
    def unsafe():
        raise ValueError('unsafe foreground')

    with pytest.raises(ValueError, match='unsafe foreground'):
        setup.tool.apply(setup.adb, setup.adb, 30, unsafe)
    assert not setup.adb.writes


def test_second_readback_failure_is_not_ignored(setup):
    s = setup
    execute = s.adb._execute

    def fail_second(command):
        result = execute(command)
        return 'wrong' if command.endswith(':string/settings') else result

    s.adb._execute = fail_second
    with pytest.raises(RuntimeError, match='settings'):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert PACKAGE not in s.adb.overlays and PACKAGE not in s.adb.packages


@pytest.mark.parametrize('sdk', [30, 35])
def test_real_builder_is_lazy_and_injected_builder_never_imports_it(setup, monkeypatch, sdk):
    import sys
    s = setup
    calls = []
    injected = s.tool.builder
    fake_module = SimpleNamespace(TranslationBuilder=lambda *args, **kw: (calls.append((args, kw)), injected)[1])
    monkeypatch.setitem(sys.modules, 'rc2vi.translation_build', fake_module)
    s.tool.builder = None
    s.adb.sdk = sdk
    s.tool.disable(s.adb, s.safe)
    assert not calls
    s.tool.apply(s.adb, RootShell(s.adb) if sdk == 35 else s.adb, sdk, s.safe)
    assert len(calls) == 1 and calls[0][1]['cancel'] is s.cancel
    assert calls[0][1]['sdk'] == sdk


@pytest.mark.parametrize('machine', [0, 3, 8])
def test_complete_counts_distinguish_reviewed_machine_and_technical_preservation(setup, machine):
    s = setup
    s.artifact['report'] = {**COMPLETE_REPORT, 'machine': machine, 'reviewed': 8 - machine,
                            'total': 100, 'target_total': 100, 'preserved': 92, 'skipped': 92}
    result = s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert result['report']['target_total'] == 100
    assert result['report']['complete'] is True and result['report']['target_untranslated'] == 0
    assert f'{8 - machine} đã duyệt' in result['message'] and f'{machine} do máy dịch' in result['message']
    assert '92 tài nguyên kỹ thuật giữ nguyên' in result['message']
    assert ('chỉ được kiểm tra định dạng' in result['message']) is (machine > 0)
    assert not any('một phần' in e[1] or e[0] == 'warning' for e in s.events)


@pytest.mark.parametrize('sdk', [30, 35])
@pytest.mark.parametrize('report', [
    'missing-report', None, {}, {'matched': 8, 'skipped': 2, 'total': 10},
    *[{k: v for k, v in COMPLETE_REPORT.items() if k != missing} for missing in COMPLETE_REPORT],
    *[{**COMPLETE_REPORT, field: invalid}
      for field in COMPLETE_REPORT if field not in {'complete', 'machine_meaning_verified'}
      for invalid in (None, True, False, '0', 0.0, -1, 1000001)],
    *[{**COMPLETE_REPORT, 'complete': value} for value in (False, 1, 'true')],
    *[{**COMPLETE_REPORT, 'machine_meaning_verified': value} for value in (True, 0, 'false')],
    *[{**COMPLETE_REPORT, field: value} for field, value in (
        ('eligible_total', 7), ('reviewed', 4), ('machine', 2), ('matched', 7),
        ('unresolved', 1), ('target_untranslated', 1), ('preserved', 3),
        ('skipped', 3), ('total', 11), ('target_total', 11))],
    {**COMPLETE_REPORT, 'matched': 0, 'eligible_total': 0, 'reviewed': 0, 'machine': 0,
     'preserved': 10, 'skipped': 10},
    # Old 0.7 cache: all APK identity/hash fields remain valid, but translation is partial.
    {'matched': 7, 'skipped': 3, 'total': 10, 'target_total': 10, 'target_untranslated': 3},
])
def test_incomplete_or_missing_report_fields_never_reach_deployment(setup, sdk, report):
    s = setup
    s.adb.sdk = sdk
    if report == 'missing-report':
        s.artifact.pop('report')
    else:
        s.artifact['report'] = report
    before = (dict(s.adb.files), dict(s.adb.packages), dict(s.adb.overlays))
    assert digest(s.artifact['apk'].read_bytes()) == s.artifact['digest']
    calls_after_build = []
    build = s.tool.builder.build
    def finish(source):
        artifact = build(source)
        s.adb.hook = calls_after_build.append
        return artifact
    s.tool.builder.build = finish
    with pytest.raises(ValueError, match='bản dịch'):
        s.tool.apply(s.adb, RootShell(s.adb) if sdk == 35 else s.adb, sdk, s.safe)
    assert not s.adb.writes and not calls_after_build and not s.events
    assert (s.adb.files, s.adb.packages, s.adb.overlays) == before
    assert s.sources and all(not path.exists() for path in s.sources)


def test_already_enabled_partial_cache_still_fails_complete_gate(setup):
    s = setup
    s.artifact['report'] = {'matched': 7, 'skipped': 3, 'total': 10}
    s.adb.packages[PACKAGE], s.adb.files[OVERLAY] = OVERLAY, PACK
    s.adb.overlays = {PACKAGE: True}
    with pytest.raises(ValueError, match='bản dịch'):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert not s.adb.writes and s.adb.overlays == {PACKAGE: True}
    assert not any('cmd overlay' in str(c) for c in s.adb.calls)


@pytest.mark.parametrize('native_clone', [False, True])
def test_changed_selection_recovers_original_bound_transport(setup, monkeypatch, native_clone):
    s = setup
    bound = SimpleNamespace(serial=s.adb.serial, shell=s.adb.shell, command=s.adb.command)
    if native_clone:
        s.adb.binary, s.adb.port = Path('unused-fake-adb.exe'), 1234
        monkeypatch.setattr(module.copy, 'copy', lambda value: bound)
    else:
        s.adb.bind = lambda serial: bound
    before = dict(s.adb.overlays)
    s.adb.files[CACHE] = b'original cache'

    def switch(command):
        if isinstance(command, str) and command.startswith('cmd overlay enable'):
            s.adb.serial = 'another-selected-device'

    s.adb.hook = switch
    with pytest.raises(ValueError, match='thay đổi'):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert s.adb.files[CACHE] == b'original cache'
    assert all(s.adb.overlays[p] == enabled for p, enabled in before.items())
    assert PACKAGE not in s.adb.overlays and PACKAGE not in s.adb.packages


def test_changed_physical_device_during_enable_never_receives_rollback_writes(setup):
    s = setup
    s.adb.files[CACHE] = b'original cache'
    execute = s.adb._execute
    write_count = None

    def switch(command):
        nonlocal write_count
        result = execute(command)
        if command == 'cmd overlay enable --user 0 ' + PACKAGE:
            s.adb.physical = 'different-physical-device'
            write_count = len(s.adb.writes)
        return result

    s.adb._execute = switch
    with pytest.raises(RuntimeError, match='Phục hồi'):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert len(s.adb.writes) == write_count
    assert any(p.endswith('/previous.idmap') for p in s.adb.files)


def test_disable_all_recognized_preserves_disabled_legacy_and_foreign(setup):
    s = setup
    phone_legacy = 'local.dji.fly.phone.vietnamese'
    s.adb.overlays.update({PACKAGE: True, phone_legacy: False})
    assert s.tool.disable(s.adb, s.safe)['count'] == 3
    assert s.adb.overlays == {LEGACY: False, PREVIOUS: False, FOREIGN: True,
                              PACKAGE: False, phone_legacy: False}
    assert not any(phone_legacy in str(command) for command in s.adb.writes)


def test_disable_silent_restore_failure_reports_incomplete_recovery(setup):
    s = setup
    execute = s.adb._execute

    def ignored_enable(command):
        if command.startswith('cmd overlay enable'):
            return ''
        result = execute(command)
        if command.startswith('cmd overlay disable'):
            s.cancel.set()
        return result

    s.adb._execute = ignored_enable
    with pytest.raises(RuntimeError, match='Phục hồi trạng thái'):
        s.tool.disable(s.adb, s.safe)


def test_unsafe_foreground_during_switch_retains_backup_without_recovery_writes(setup):
    s = setup
    s.adb.files[CACHE] = b'original cache'

    def safe():
        if not s.adb.overlays[LEGACY]:
            raise ValueError('unsafe foreground')

    with pytest.raises(RuntimeError, match='Phục hồi chưa hoàn tất'):
        s.tool.apply(s.adb, s.adb, 30, safe)
    assert s.adb.overlays[PREVIOUS]
    assert s.adb.files[CACHE] == b'original cache'
    assert any(path.endswith('/previous.idmap') for path in s.adb.files)
    assert s.adb.writes[-1] == 'cmd overlay disable --user 0 ' + LEGACY


@pytest.mark.parametrize('failure', ['idmap', 'approval', 'cancel', 'install_timeout'])
def test_failure_after_new_install_removes_only_owned_overlay(setup, failure):
    s = setup
    execute = s.adb._execute
    before = dict(s.adb.overlays)

    def fail(command):
        if failure == 'idmap' and command.startswith('idmap2 create '):
            raise RuntimeError('idmap failure after install')
        result = execute(command)
        if command.startswith('pm install '):
            if failure == 'cancel':
                s.cancel.set()
            elif failure == 'install_timeout':
                raise TimeoutError('installed but acknowledgement lost')
        return result

    s.adb._execute = fail
    s.adb.raw_valid = failure != 'approval'
    with pytest.raises((ValueError, RuntimeError, TimeoutError)):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert PACKAGE not in s.adb.packages and s.adb.overlays == before
    assert s.adb.packages['dji.go.v5'] == TARGET and s.adb.files[TARGET] == SOURCE
    assert [c for c in s.adb.writes if isinstance(c, str) and c.startswith('pm uninstall ')] == [
        'pm uninstall --user 0 ' + PACKAGE]
    assert not any(path.startswith('/data/local/tmp/') for path in s.adb.files)


@pytest.mark.parametrize('reason', ['digest', 'path', 'identity', 'foreground', 'uninstall'])
def test_new_package_cleanup_refused_or_failed_reports_retained(setup, reason):
    s = setup
    execute = s.adb._execute
    installed = False

    def fail(command):
        nonlocal installed
        if command.startswith('idmap2 create '):
            if reason == 'digest':
                s.adb.files[OVERLAY] = b'foreign replacement'
            elif reason == 'path':
                s.adb.packages[PACKAGE] = '/data/app/foreign/base.apk'
                s.adb.files['/data/app/foreign/base.apk'] = PACK
            elif reason == 'identity':
                s.adb.physical = 'different-physical-device'
            raise RuntimeError('idmap failure')
        result = execute(command)
        if command.startswith('pm install '):
            installed = True
        return result

    def safe():
        if installed and reason == 'foreground':
            raise ValueError('unsafe foreground')

    s.adb._execute = fail
    if reason == 'uninstall':
        s.adb.fail_write = lambda c: c.startswith('pm uninstall ')
    with pytest.raises(RuntimeError, match='giữ|retained|RETAINED'):
        s.tool.apply(s.adb, s.adb, 30, safe)
    assert PACKAGE in s.adb.packages
    assert s.adb.packages['dji.go.v5'] == TARGET and s.adb.files[TARGET] == SOURCE
    assert any(path.startswith('/data/local/tmp/') for path in s.adb.files)
    if reason != 'uninstall':
        assert not any(isinstance(c, str) and c.startswith('pm uninstall ') for c in s.adb.writes)


def test_idmap_failure_never_uninstalls_preexisting_candidate(setup):
    s = setup
    s.adb.packages[PACKAGE], s.adb.files[OVERLAY] = OVERLAY, PACK
    s.adb.overlays[PACKAGE] = False
    s.adb.fail_write = lambda c: c.startswith('idmap2 create ')
    with pytest.raises(RuntimeError):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert s.adb.packages[PACKAGE] == OVERLAY and s.adb.files[OVERLAY] == PACK
    assert not any(isinstance(c, str) and c.startswith('pm uninstall ') for c in s.adb.writes)


@pytest.mark.parametrize('sdk,target_name', [(30, 'DJIFlyLocalTranslation'), (35, 'DJIFlyPhoneTranslation')])
def test_builder_profile_matches_selected_sdk(setup, sdk, target_name):
    s = setup
    s.adb.sdk = sdk
    s.artifact.update(profile_sdk=sdk, target_name=target_name)
    root = RootShell(s.adb) if sdk == 35 else s.adb
    assert s.tool.apply(s.adb, root, sdk, s.safe)['status'] == 'enabled'


@pytest.mark.parametrize('fields', [
    {'profile_sdk': 35}, {'profile_sdk': '30'}, {'profile_sdk': True}, {'profile_sdk': None},
    {'target_name': 'DJIFlyPhoneTranslation'}, {'target_name': None},
    {'profile_sdk': 30, 'target_name': 'wrong'},
])
def test_builder_profile_mismatch_rejected_before_device_writes(setup, fields):
    s = setup
    s.artifact.update(fields)
    with pytest.raises(ValueError, match='Profile SDK/targetName'):
        s.tool.apply(s.adb, s.adb, 30, s.safe)
    assert not s.adb.writes
