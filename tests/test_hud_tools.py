"""Offline contracts for pinned HUD tools; all bundled files here are synthetic."""

import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import threading
import traceback
from types import SimpleNamespace
from unittest.mock import Mock
import warnings
import zipfile

import pytest


FILES = {
    'java/bin/java.exe': b'java fixture',
    'java/bin/keytool.exe': b'keytool fixture',
    'java/bin/server/jvm.dll': b'runtime fixture',
    'lib/apktool.jar': b'apktool fixture',
    'lib/apksigner.jar': b'apksigner fixture',
    'lib/hud-tool.jar': b'helper fixture',
    'bin/zipalign.exe': b'zipalign fixture',
    'licenses/tool license.txt': b'license fixture',
}
CERT = 'a1' * 32


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def api():
    return importlib.import_module('rc2vi.hud_tools')


@pytest.fixture
def bundle(tmp_path):
    assets = tmp_path / 'asset folder'
    hud = assets / 'hud'
    hud.mkdir(parents=True)
    work = tmp_path / 'work folder'

    def write(entries=None, declared=None, mutate_archive=None):
        archive = hud / 'toolchain.zip'
        entries = list(FILES.items()) if entries is None else entries
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
                for name, data in entries:
                    output.writestr(name, data)
        if mutate_archive:
            archive.write_bytes(mutate_archive(archive.read_bytes()))
        manifest = {
            'schema': 1,
            'archive_sha256': digest(archive.read_bytes()),
            'files': {name: digest(data) for name, data in
                      (FILES if declared is None else declared).items()},
        }
        (hud / 'toolchain.json').write_text(json.dumps(manifest), encoding='utf-8')
        return manifest

    manifest = write()
    payload = b'dex\n035\0synthetic HUD payload'
    (hud / 'classes23.dex').write_bytes(payload)
    (hud / 'payload.json').write_text(
        json.dumps({'schema': 1, 'sha256': digest(payload)}), encoding='utf-8')
    return SimpleNamespace(assets=assets, hud=hud, work=work, write=write,
                           manifest=manifest, payload=payload)


def update_manifest(bundle, **changes):
    path = bundle.hud / 'toolchain.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    manifest.update(changes)
    path.write_text(json.dumps(manifest), encoding='utf-8')


def test_prepare_extracts_all_files_and_records_exact_pins(api, bundle):
    tools = api.HudTools(bundle.assets, bundle.work)
    root = tools.prepare()
    assert root == bundle.work / 'toolchain' / bundle.manifest['archive_sha256']
    assert tools.archive_sha256 == bundle.manifest['archive_sha256']
    assert tools.manifest_sha256 == digest((bundle.hud / 'toolchain.json').read_bytes())
    assert {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob('*') if path.is_file()} == FILES
    assert tools.prepare() == root
    assert list(root.parent.iterdir()) == [root]


def test_prepare_accepts_explicit_parent_directory_entries(api, bundle):
    bundle.write(entries=[('java/', b''), ('java/bin/', b'')] + list(FILES.items()))
    assert (api.HudTools(bundle.assets, bundle.work).prepare() /
            'java/bin/java.exe').read_bytes() == FILES['java/bin/java.exe']


@pytest.mark.parametrize('name', list(FILES))
def test_every_cached_file_is_rehashed_on_every_prepare(api, bundle, name):
    tools = api.HudTools(bundle.assets, bundle.work)
    root = tools.prepare()
    (root / name).write_bytes(b'tampered')
    with pytest.raises(ValueError):
        tools.prepare()
    assert (root / name).read_bytes() == b'tampered'


@pytest.mark.parametrize('change', ['extra_file', 'extra_dir', 'missing', 'file_as_dir'])
def test_cache_rejects_unlisted_or_missing_entries(api, bundle, change):
    tools = api.HudTools(bundle.assets, bundle.work)
    root = tools.prepare()
    if change == 'extra_file':
        (root / 'injected.exe').write_bytes(b'injected')
    elif change == 'extra_dir':
        (root / 'unlisted').mkdir()
    else:
        (root / 'lib/hud-tool.jar').unlink()
        if change == 'file_as_dir':
            (root / 'lib/hud-tool.jar').mkdir()
    with pytest.raises(ValueError):
        tools.prepare()


@pytest.mark.parametrize('component', ['toolchain', 'cache', 'lib'])
def test_cache_rejects_windows_reparse_points_without_following(api, bundle,
                                                             monkeypatch, component):
    tools = api.HudTools(bundle.assets, bundle.work)
    root = tools.prepare()
    target = {'toolchain': root.parent, 'cache': root, 'lib': root / 'lib'}[component]
    original = Path.lstat

    def reparse(path):
        value = original(path)
        if path == target:
            return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=0x400)
        return value

    monkeypatch.setattr(Path, 'lstat', reparse)
    with pytest.raises(ValueError):
        tools.prepare()


def test_changed_archive_is_rejected_even_when_cache_is_valid(api, bundle):
    tools = api.HudTools(bundle.assets, bundle.work)
    tools.prepare()
    archive = bundle.hud / 'toolchain.zip'
    archive.write_bytes(archive.read_bytes() + b'tampered')
    with pytest.raises(ValueError):
        tools.prepare()


@pytest.mark.parametrize('field,value', [
    ('schema', 2), ('schema', True), ('files', []), ('files', {}),
    ('archive_sha256', 'f' * 63), ('archive_sha256', 'g' * 64),
    ('archive_sha256', 123), ('unexpected', 'field'),
])
def test_invalid_toolchain_manifest_is_rejected(api, bundle, field, value):
    update_manifest(bundle, **{field: value})
    with pytest.raises(ValueError):
        api.HudTools(bundle.assets, bundle.work).prepare()


@pytest.mark.parametrize('name', [
    '../escape.exe', '/absolute.exe', 'C:/escape.exe', 'C:escape.exe',
    'java\\escape.exe', 'dir//evil.exe', 'dir/./evil.exe', 'dir/../evil.exe',
    'CON', 'con.txt', 'dir/CON .exe', 'dir/LPT1 .dll', 'dir/NUL.exe', 'dir/PRN', 'dir/AUX', 'dir/COM1.txt',
    'dir/LPT9', 'dir/COM\u00b2.exe', 'dir/CONIN$', 'dir/CONOUT$',
    'dir/trailing.', 'dir/trailing ', 'dir/bad:stream', 'dir/bad?name',
    'dir/bad*name', 'dir/bad|name', 'dir/bad<name', 'dir/bad"name',
    'dir/bad\x01name',
])
def test_unsafe_archive_paths_are_rejected_before_extraction(api, bundle, name):
    bundle.write(entries=list(FILES.items()) + [(name, b'unsafe')],
                 declared={**FILES, name: b'unsafe'})
    with pytest.raises(ValueError):
        api.HudTools(bundle.assets, bundle.work).prepare()
    assert not (bundle.work.parent / 'escape.exe').exists()
    assert not list(bundle.work.glob('toolchain/*'))


@pytest.mark.parametrize('name', ['../escape', 'C:/evil', 'java\\evil', 'CON'])
def test_manifest_paths_are_validated_independently(api, bundle, name):
    bundle.write(declared={**FILES, name: b'unsafe'})
    with pytest.raises(ValueError):
        api.HudTools(bundle.assets, bundle.work).prepare()


@pytest.mark.parametrize('name', ['java/bin/java.exe', 'JAVA/bin/java.exe',
                                  'java/bin/Java.exe', 'JAVA/additional.dll'])
def test_archive_duplicate_or_casefold_alias_is_rejected(api, bundle, name):
    bundle.write(entries=list(FILES.items()) + [(name, b'duplicate')])
    with pytest.raises(ValueError):
        api.HudTools(bundle.assets, bundle.work).prepare()


def test_manifest_casefold_alias_is_rejected(api, bundle):
    bundle.write(declared={**FILES, 'JAVA/extra.dll': b'alias'})
    with pytest.raises(ValueError):
        api.HudTools(bundle.assets, bundle.work).prepare()


@pytest.mark.parametrize('kind', ['extra', 'missing', 'extra_dir', 'duplicate_dir',
                                  'file_parent', 'symlink', 'fifo', 'encrypted', 'nul'])
def test_archive_inventory_and_metadata_are_checked(api, bundle, kind):
    entries = list(FILES.items())
    declared = dict(FILES)
    mutation = None
    if kind == 'extra':
        entries.append(('extra.dll', b'extra'))
    elif kind == 'missing':
        entries = entries[:-1]
    elif kind == 'extra_dir':
        entries.append(('unlisted/', b''))
    elif kind == 'duplicate_dir':
        entries.extend([('java/', b''), ('java/', b'')])
    elif kind == 'file_parent':
        entries.append(('lib', b'file'))
        declared['lib'] = b'file'
    elif kind in ('symlink', 'fifo'):
        info = zipfile.ZipInfo('extra.dll')
        info.create_system = 3
        info.external_attr = ((stat.S_IFLNK if kind == 'symlink' else stat.S_IFIFO)
                              | 0o777) << 16
        entries.append((info, b'../elsewhere'))
        declared['extra.dll'] = b'../elsewhere'
    elif kind == 'encrypted':
        def mutation(data):
            raw = bytearray(data)
            for signature, offset in [(b'PK\x03\x04', 6), (b'PK\x01\x02', 8)]:
                pos = raw.index(signature) + offset
                struct.pack_into('<H', raw, pos, struct.unpack_from('<H', raw, pos)[0] | 1)
            return raw
    elif kind == 'nul':
        entries.append(('evilXname', b'unsafe'))
        mutation = lambda data: data.replace(b'evilXname', b'evil\0name')
    bundle.write(entries=entries, declared=declared, mutate_archive=mutation)
    with pytest.raises(ValueError):
        api.HudTools(bundle.assets, bundle.work).prepare()
    assert not list(bundle.work.glob('toolchain/*'))


@pytest.mark.parametrize('name', [name for name in FILES if name.endswith(('.exe', '.jar'))])
def test_required_exact_paths_must_exist_in_manifest(api, bundle, name):
    files = {path: data for path, data in FILES.items() if path != name}
    bundle.write(entries=list(files.items()), declared=files)
    with pytest.raises(ValueError):
        api.HudTools(bundle.assets, bundle.work).prepare()


def test_wrong_file_digest_cleans_unique_staging_and_does_not_publish(api, bundle):
    hashes = dict(bundle.manifest['files'])
    hashes['lib/hud-tool.jar'] = '0' * 64
    update_manifest(bundle, files=hashes)
    tools = api.HudTools(bundle.assets, bundle.work)
    with pytest.raises(ValueError):
        tools.prepare()
    assert not list((bundle.work / 'toolchain').iterdir())
    bundle.write()
    assert tools.prepare().is_dir()


def test_cancellation_during_extraction_removes_staging(api, bundle):
    def cancel():
        return any((bundle.work / 'toolchain').glob('.*'))

    with pytest.raises(api.HudCancelled):
        api.HudTools(bundle.assets, bundle.work, cancel).prepare()
    assert not list((bundle.work / 'toolchain').iterdir())


def test_concurrent_cache_publication_validates_winner_and_cleans_own_stage(api, bundle,
                                                                        monkeypatch):
    original = Path.rename

    def winner(path, target):
        if path.parent == bundle.work / 'toolchain':
            shutil.copytree(path, target)
            raise FileExistsError('another builder published first')
        return original(path, target)

    monkeypatch.setattr(Path, 'rename', winner)
    tools = api.HudTools(bundle.assets, bundle.work)
    root = tools.prepare()
    assert (root / 'lib/hud-tool.jar').read_bytes() == FILES['lib/hud-tool.jar']
    assert list(root.parent.iterdir()) == [root]


def test_payload_pin_is_checked_on_each_read(api, bundle):
    tools = api.HudTools(bundle.assets, bundle.work)
    assert tools.payload() == bundle.payload
    (bundle.hud / 'classes23.dex').write_bytes(b'tampered')
    with pytest.raises(ValueError):
        tools.payload()


@pytest.mark.parametrize('restore_hash', [CERT, CERT.upper()])
def test_payload_accepts_optional_restore_owner_pin(api, bundle, restore_hash):
    manifest = {'schema': 1, 'sha256': digest(bundle.payload),
                'restore_owner_sha256': restore_hash}
    (bundle.hud / 'payload.json').write_text(json.dumps(manifest), encoding='utf-8')
    assert api.HudTools(bundle.assets, bundle.work).payload() == bundle.payload


@pytest.mark.parametrize('restore_hash', [None, True, 1, [], {}, '', 'a' * 63,
                                         'a' * 65, 'g' * 64, ' ' + CERT, CERT + '\n'])
def test_payload_rejects_invalid_optional_restore_owner_pin(api, bundle, restore_hash):
    manifest = {'schema': 1, 'sha256': digest(bundle.payload),
                'restore_owner_sha256': restore_hash}
    (bundle.hud / 'payload.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError):
        api.HudTools(bundle.assets, bundle.work).payload()


def test_payload_optional_restore_owner_pin_does_not_allow_unknown_fields(api, bundle):
    manifest = {'schema': 1, 'sha256': digest(bundle.payload),
                'restore_owner_sha256': CERT, 'extra': 'unsupported'}
    (bundle.hud / 'payload.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='Unsupported'):
        api.HudTools(bundle.assets, bundle.work).payload()


def test_payload_optional_restore_owner_pin_still_checks_dex_hash(api, bundle):
    manifest = {'schema': 1, 'sha256': digest(bundle.payload), 'restore_owner_sha256': CERT}
    (bundle.hud / 'payload.json').write_text(json.dumps(manifest), encoding='utf-8')
    (bundle.hud / 'classes23.dex').write_bytes(b'tampered')
    with pytest.raises(ValueError, match='integrity'):
        api.HudTools(bundle.assets, bundle.work).payload()


def test_historical_payload_is_accepted_only_with_explicit_pin_and_matching_bytes(api, bundle, monkeypatch):
    old = b'known-old-hud-for-update-test'
    expected = digest(old)
    monkeypatch.setattr(api, 'LEGACY_HUD_PAYLOADS', frozenset({expected}))
    root = bundle.hud / 'history'
    root.mkdir()
    (root / (expected + '.dex')).write_bytes(old)
    tools = api.HudTools(bundle.assets, bundle.work)
    assert tools.historical_payload(expected) == old
    (root / (expected + '.dex')).write_bytes(b'tampered')
    with pytest.raises(ValueError):
        tools.historical_payload(expected)


def test_historical_payload_does_not_trust_an_arbitrary_receipt_digest(api, bundle):
    with pytest.raises(ValueError):
        api.HudTools(bundle.assets, bundle.work).historical_payload('e' * 64)


@pytest.mark.parametrize('manifest', [
    {'schema': True, 'sha256': CERT}, {'schema': 2, 'sha256': CERT},
    {'schema': 1, 'sha256': 'not hex'}, {'schema': 1},
    {'schema': 1, 'sha256': CERT, 'extra': 'value'},
])
def test_invalid_payload_manifest_is_rejected(api, bundle, manifest):
    (bundle.hud / 'payload.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError):
        api.HudTools(bundle.assets, bundle.work).payload()


@pytest.mark.parametrize('document', ['{"a":1,"a":2}', '{"a":{"x":1,"x":2}}',
                                     '[]', 'null', '{"x":NaN}', '{broken'])
def test_load_json_rejects_duplicate_keys_non_objects_and_invalid_json(api, tmp_path,
                                                                     document):
    path = tmp_path / 'manifest.json'
    path.write_text(document, encoding='utf-8')
    with pytest.raises(ValueError):
        api.load_json(path)


def test_load_json_returns_an_object(api, tmp_path):
    path = tmp_path / 'manifest.json'
    path.write_text('{"schema":1,"files":{"x":"hash"}}', encoding='utf-8')
    assert api.load_json(path) == {'schema': 1, 'files': {'x': 'hash'}}


def test_sha256_file_streams_and_checks_cancellation(api, tmp_path):
    path = tmp_path / 'large file.bin'
    data = b'large streaming fixture' * 180_000
    path.write_bytes(data)
    assert api.sha256_file(path) == digest(data)
    polls = 0

    def cancel():
        nonlocal polls
        polls += 1
        return polls >= 3

    with pytest.raises(api.HudCancelled):
        api.sha256_file(path, cancel)
    assert polls == 3


def test_check_cancel_supports_event_callable_and_none(api):
    assert issubclass(api.HudCancelled, RuntimeError)
    event = threading.Event()
    api.check_cancel(None)
    api.check_cancel(event)
    api.check_cancel(lambda: False)
    event.set()
    for cancel in (event, lambda: True):
        with pytest.raises(api.HudCancelled):
            api.check_cancel(cancel)


def test_run_process_owns_pipes_stdin_flags_and_argument_boundaries(api, monkeypatch):
    process = Mock()
    process.communicate.return_value = (b' output \n', b'ignored stderr')
    process.returncode = 0
    factory = Mock(return_value=process)
    monkeypatch.setattr(api.subprocess, 'Popen', factory)
    environment = {'HUD_SIGN_PASS': 'test password'}
    assert api.run_process(['C:/path with spaces/tool.exe', 'one argument'],
                           env=environment, sensitive=True) == ' output \n'
    args, kwargs = factory.call_args
    assert args[0] == ['C:/path with spaces/tool.exe', 'one argument']
    assert kwargs['stdin'] == subprocess.DEVNULL
    assert kwargs['stdout'] == subprocess.PIPE and kwargs['stderr'] == subprocess.PIPE
    assert kwargs['shell'] is False
    assert kwargs.get('creationflags', 0) == (subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    assert kwargs['env'] == environment and kwargs['env'] is not environment
    assert process.communicate.call_args.kwargs['timeout'] > 0


def test_run_process_drains_large_stdout_and_stderr_across_timeouts(api):
    source = ('import os,time; '
              'os.write(1,b"x"*2000000); os.write(2,b"y"*2000000); '
              'time.sleep(0.35); print("DONE")')
    output = api.run_process([sys.executable, '-I', '-c', source])
    assert output == 'x' * 2_000_000 + 'DONE' + os.linesep


def test_run_process_cancellation_kills_and_reaps_owned_child(api, monkeypatch):
    event = threading.Event()
    children = []
    original = subprocess.Popen

    def capture(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(api.subprocess, 'Popen', capture)
    timer = threading.Timer(0.15, event.set)
    timer.start()
    try:
        with pytest.raises(api.HudCancelled):
            api.run_process([sys.executable, '-I', '-c', 'import time; time.sleep(30)'],
                            cancel=event)
        assert len(children) == 1 and children[0].poll() is not None
        assert children[0].stdout.closed and children[0].stderr.closed
    finally:
        timer.cancel()
        timer.join()
        for child in children:
            if child.poll() is None:
                child.kill()
                child.communicate()


def test_pre_cancelled_process_is_never_spawned(api, monkeypatch):
    factory = Mock()
    monkeypatch.setattr(api.subprocess, 'Popen', factory)
    with pytest.raises(api.HudCancelled):
        api.run_process(['unused.exe'], cancel=lambda: True)
    factory.assert_not_called()


@pytest.mark.parametrize('sensitive', [False, True])
@pytest.mark.parametrize('failure', ['start', 'exit', 'communicate', 'callback'])
def test_process_errors_never_expose_arguments_environment_or_output(api, monkeypatch,
                                                                   sensitive, failure):
    # Synthetic marker for redaction assertions; no account or signing credential.
    fixture_message = 'fixture-password-must-stay-private'
    process = Mock()
    process.poll.return_value = None
    process.returncode = 17 if failure == 'exit' else 0
    process.communicate.return_value = (fixture_message.encode(), fixture_message.encode())
    if failure == 'communicate':
        process.communicate.side_effect = [OSError(fixture_message), (b'', b'')]
    factory = Mock(return_value=process)
    if failure == 'start':
        factory.side_effect = OSError(fixture_message)
    monkeypatch.setattr(api.subprocess, 'Popen', factory)
    cancel = Mock(side_effect=[False, RuntimeError(fixture_message)]) if failure == 'callback' else None
    with pytest.raises(RuntimeError) as caught:
        api.run_process(['command-' + fixture_message], env={'HUD_SIGN_PASS': fixture_message},
                        cancel=cancel, sensitive=sensitive)
    assert fixture_message not in str(caught.value)
    assert fixture_message not in ''.join(traceback.format_exception_only(caught.type, caught.value))
    assert caught.value.__suppress_context__
    if failure in ('communicate', 'callback'):
        process.kill.assert_called_once()
        assert process.communicate.call_count >= 1


def test_communication_cleanup_failure_still_waits_and_closes_pipes(api, monkeypatch):
    process = Mock()
    process.poll.return_value = None
    process.communicate.side_effect = OSError('sensitive fixture detail')
    monkeypatch.setattr(api.subprocess, 'Popen', Mock(return_value=process))
    with pytest.raises(RuntimeError):
        api.run_process(['fixture.exe'])
    process.kill.assert_called_once()
    process.wait.assert_called_once()
    process.stdout.close.assert_called()
    process.stderr.close.assert_called()


def test_wrappers_use_portable_classpath_and_separate_password_environments(api, bundle,
                                                                         monkeypatch):
    tools = api.HudTools(bundle.assets, bundle.work)
    prepare = Mock(wraps=tools.prepare)
    monkeypatch.setattr(tools, 'prepare', prepare)
    runner = Mock(return_value=CERT.upper())
    monkeypatch.setattr(api, 'run_process', runner)
    before = dict(os.environ)
    source = bundle.work / 'input DEX.dex'
    output = bundle.work / 'output DEX.dex'
    stage = bundle.work / 'patch directory'
    key = bundle.work / 'user selected fixture.p12'
    tools.patch(source, output, stage)
    tools.align(source, output)
    tools.sign(source, output, key, 'alias with spaces', 'first password')
    assert tools.verify(output) == CERT
    assert tools.keycert(key, 'alias with spaces', 'second password') == CERT
    tools.generate_key(key, 'alias with spaces', 'third password')
    assert prepare.call_count == 7
    root = bundle.work / 'toolchain' / tools.archive_sha256
    java = [str(root / 'java/bin/java.exe'), '-cp',
            ';'.join(str(root / name) for name in
                     ['lib/hud-tool.jar', 'lib/apktool.jar', 'lib/apksigner.jar']), 'HudTool']
    calls = runner.call_args_list
    assert calls[0].args[0] == java + ['patch', str(source), str(output), str(stage)]
    assert calls[1].args[0] == [str(root / 'bin/zipalign.exe'), '-f', '-p', '4', str(source), str(output)]
    assert calls[2].args[0] == [str(root / 'bin/zipalign.exe'), '-c', '-p', '4', str(output)]
    assert calls[3].args[0] == java + ['sign', str(source), str(output), str(key), 'alias with spaces']
    assert calls[4].args[0] == java + ['verify', str(output)]
    assert calls[5].args[0] == java + ['keycert', str(key), 'alias with spaces']
    key_args = calls[6].args[0]
    assert key_args[0] == str(root / 'java/bin/keytool.exe')
    for option, value in [('-keystore', str(key)), ('-alias', 'alias with spaces'),
                          ('-keyalg', 'RSA'), ('-keysize', '2048'), ('-storetype', 'PKCS12'),
                          ('-storepass:env', 'HUD_SIGN_PASS'), ('-keypass:env', 'HUD_SIGN_PASS')]:
        assert key_args[key_args.index(option) + 1] == value
    assert '-genkeypair' in key_args and '-dname' in key_args and '-noprompt' in key_args
    for index, password in [(3, 'first password'), (5, 'second password'), (6, 'third password')]:
        clean = {name: value for name, value in before.items() if name.upper() not in {
            'HUD_SIGN_PASS', 'JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS', 'CLASSPATH',
        }}
        assert calls[index].kwargs['env'] == {**clean, 'HUD_SIGN_PASS': password}
        assert calls[index].kwargs['sensitive'] is True
        assert password not in calls[index].args[0]
    assert calls[3].kwargs['env'] is not calls[5].kwargs['env']
    assert dict(os.environ) == before
    assert all(call.kwargs['cancel'] is tools.cancel for call in calls)


@pytest.mark.parametrize('method', ['patch', 'align', 'sign', 'verify', 'keycert', 'generate_key'])
def test_tool_execution_rejects_cache_tampering_before_spawning(api, bundle, monkeypatch,
                                                             method):
    tools = api.HudTools(bundle.assets, bundle.work)
    root = tools.prepare()
    (root / 'java/bin/java.exe').write_bytes(b'tampered')
    runner = Mock()
    monkeypatch.setattr(api, 'run_process', runner)
    source, out, key = [bundle.work / name for name in ('source', 'out', 'fixture.p12')]
    args = {'patch': (source, out, bundle.work), 'align': (source, out),
            'sign': (source, out, key, 'alias', 'password'), 'verify': (source,),
            'keycert': (key, 'alias', 'password'), 'generate_key': (key, 'alias', 'password')}
    with pytest.raises(ValueError):
        getattr(tools, method)(*args[method])
    runner.assert_not_called()


def test_align_revalidates_cache_between_alignment_and_verification(api, bundle, monkeypatch):
    tools = api.HudTools(bundle.assets, bundle.work)
    root = tools.prepare()

    def tamper(*args, **kwargs):
        (root / 'bin/zipalign.exe').write_bytes(b'tampered between calls')
        return ''

    runner = Mock(side_effect=tamper)
    monkeypatch.setattr(api, 'run_process', runner)
    with pytest.raises(ValueError):
        tools.align(bundle.work / 'in.apk', bundle.work / 'out.apk')
    assert runner.call_count == 1


@pytest.mark.parametrize('output', ['', 'a' * 63, 'a' * 65, 'z' * 64,
                                   'certificate: ' + CERT, CERT + '\n' + CERT,
                                   ' ' + CERT, CERT + ' ', CERT + '\r',
                                   CERT + '\n\n', CERT + '\r\n\r\n'])
@pytest.mark.parametrize('method', ['verify', 'keycert'])
def test_helper_certificate_output_must_be_only_hex64(api, bundle, monkeypatch, output, method):
    tools = api.HudTools(bundle.assets, bundle.work)
    monkeypatch.setattr(api, 'run_process', Mock(return_value=output))
    args = (bundle.work / 'fixture.apk',) if method == 'verify' else (
        bundle.work / 'fixture.p12', 'alias', 'password')
    with pytest.raises(ValueError):
        getattr(tools, method)(*args)


def test_tool_environments_drop_inherited_password_and_java_injection_options(api, bundle,
                                                                           monkeypatch):
    inherited = {
        'HUD_SIGN_PASS': 'inherited password fixture',
        'JAVA_TOOL_OPTIONS': '-javaagent:ambient.jar',
        'JDK_JAVA_OPTIONS': '--module-path=ambient',
        '_JAVA_OPTIONS': '-Xbootclasspath/a:ambient.jar',
        'CLASSPATH': 'ambient.jar',
    }
    for name, value in inherited.items():
        monkeypatch.setenv(name, value)
    before = dict(os.environ)
    tools = api.HudTools(bundle.assets, bundle.work)
    runner = Mock(return_value=CERT)
    monkeypatch.setattr(api, 'run_process', runner)
    source, out, key = [bundle.work / name for name in ('source', 'out', 'fixture.p12')]
    tools.patch(source, out, bundle.work)
    tools.align(source, out)
    tools.verify(out)
    tools.sign(source, out, key, 'alias', 'sign password fixture')
    tools.keycert(key, 'alias', 'cert password fixture')
    tools.generate_key(key, 'alias', 'key password fixture')
    for index, call in enumerate(runner.call_args_list):
        environment = call.kwargs.get('env')
        assert environment is not None
        assert not (set(inherited) - {'HUD_SIGN_PASS'}) & environment.keys()
        if index < 4:
            assert 'HUD_SIGN_PASS' not in environment
        else:
            assert environment['HUD_SIGN_PASS'] == {
                4: 'sign password fixture', 5: 'cert password fixture',
                6: 'key password fixture',
            }[index]
        assert environment.get('PATH') == before.get('PATH')
    assert len({id(call.kwargs['env']) for call in runner.call_args_list}) == 7
    assert dict(os.environ) == before


def test_process_spawn_failure_suppresses_sensitive_traceback_context(api, monkeypatch):
    detail = 'private fixture detail from operating system'
    monkeypatch.setattr(api.subprocess, 'Popen', Mock(side_effect=OSError(detail)))
    with pytest.raises(RuntimeError) as caught:
        api.run_process(['fixture.exe'], sensitive=True)
    assert detail not in ''.join(traceback.format_exception(caught.value))


@pytest.mark.parametrize('component', ['parent', 'root'])
def test_cache_directories_cannot_be_replaced_by_regular_files(api, bundle, component):
    parent = bundle.work / 'toolchain'
    root = parent / bundle.manifest['archive_sha256']
    parent.mkdir(parents=True)
    if component == 'parent':
        parent.rmdir()
        parent.write_bytes(b'not a directory')
    else:
        root.write_bytes(b'not a directory')
    with pytest.raises(ValueError):
        api.HudTools(bundle.assets, bundle.work).prepare()


def test_malformed_archive_with_valid_pin_is_rejected(api, bundle):
    raw = b'not a ZIP file'
    (bundle.hud / 'toolchain.zip').write_bytes(raw)
    update_manifest(bundle, archive_sha256=digest(raw))
    with pytest.raises(ValueError):
        api.HudTools(bundle.assets, bundle.work).prepare()
    assert not list(bundle.work.glob('toolchain/*'))


@pytest.mark.parametrize('output,valid', [
    (CERT, True), (CERT.upper(), True), (CERT + '\n', True), (CERT + '\r\n', True),
    (' ' + CERT, False), (CERT + ' ', False), (CERT + '\r', False),
    (CERT + '\n\n', False), (CERT + '\r\n\r\n', False),
    ('certificate: ' + CERT + '\n', False),
])
@pytest.mark.parametrize('method', ['verify', 'keycert'])
def test_certificate_boundary_checks_actual_untrimmed_child_stdout(api, bundle, monkeypatch,
                                                                 output, valid, method):
    tools = api.HudTools(bundle.assets, bundle.work)
    original = api.run_process

    def local_helper(args, **kwargs):
        # Exercise the real owned-process runner without executing fake Java.
        source = 'import os; os.write(1, ' + repr(output.encode('ascii')) + ')'
        return original([sys.executable, '-I', '-c', source], **kwargs)

    monkeypatch.setattr(api, 'run_process', local_helper)
    args = (bundle.work / 'fixture.apk',) if method == 'verify' else (
        bundle.work / 'fixture.p12', 'alias', 'password')
    if valid:
        assert getattr(tools, method)(*args) == CERT
    else:
        with pytest.raises(ValueError):
            getattr(tools, method)(*args)
