"""Signing identity lifecycle; all key material here is synthetic test data."""
import json
import multiprocessing
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import ctypes
import os
import re
import threading

import pytest

from rc2vi import hud_keys as backend


class Tools:
    certificate = 'c' * 64
    generated = []

    def generate_key(self, path, alias, password):
        self.generated.append((path, alias, password))
        path.write_bytes(b'synthetic-p12')

    def keycert(self, path, alias, password):
        if not path.is_file() or password == 'wrong-test-password':
            raise RuntimeError('Certificate inspection failed')
        return self.certificate


@pytest.fixture
def store(tmp_path, monkeypatch):
    # Encryption boundary is mocked for unit tests, with a real DPAPI round trip below.
    monkeypatch.setattr(backend, 'protect', lambda value: b'DPAPI' + bytes(x ^ 123 for x in value))
    monkeypatch.setattr(backend, 'unprotect', lambda value: bytes(x ^ 123 for x in value[5:]))
    tools = Tools()
    tools.generated = []
    return backend.HudKeyStore(tools, root=tmp_path / 'per-user keys'), tools


def test_first_use_generates_p12_reuses_identity_and_keeps_password_out_of_repr_and_disk(store):
    keys, tools = store
    first = keys.ensure()
    second = keys.ensure()
    assert first == second
    assert len(tools.generated) == 1
    assert first.keyfile.suffix == '.p12'
    assert first.certificate_sha256 == 'c' * 64
    assert first.password not in repr(first)
    assert all(first.password.encode() not in path.read_bytes()
               for path in keys.root.iterdir() if path.is_file())
    assert keys.load() == first


def test_load_does_not_generate_when_missing(store):
    keys, tools = store
    with pytest.raises(ValueError, match='signing|identity|key'):
        keys.load()
    assert not tools.generated


def test_explicit_import_copies_only_selected_key_and_preserves_old_on_failure(store, tmp_path):
    keys, tools = store
    old = keys.ensure()
    source = tmp_path / 'user selected.jks'
    source.write_bytes(b'synthetic-import-jks')
    imported = keys.import_existing(source, 'developer', 'import-test-password')
    assert imported.alias == 'developer'
    assert imported.keyfile.read_bytes() == source.read_bytes()
    assert imported.keyfile != source
    assert keys.load() == imported
    with pytest.raises(RuntimeError):
        keys.import_existing(source, 'developer', 'wrong-test-password')
    assert keys.load() == imported
    assert old.keyfile.is_file()
    assert source.read_bytes() == b'synthetic-import-jks'


@pytest.mark.parametrize('alias,password', [('', 'test'), ('-flag', 'test'), ('a\n', 'test'),
                                          ('a', ''), ('a', 'bad\0test')])
def test_import_rejects_invalid_inputs_before_running_tools(store, tmp_path, alias, password):
    keys, _ = store
    source = tmp_path / 'selected.p12'
    source.write_bytes(b'synthetic')
    with pytest.raises(ValueError):
        keys.import_existing(source, alias, password)


def test_metadata_cannot_escape_key_directory(store, tmp_path):
    keys, _ = store
    keys.ensure()
    metadata = keys.root / 'signer.json'
    value = json.loads(metadata.read_text())
    value['keyfile'] = '../outside.p12'
    metadata.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        keys.load()


def test_tampered_key_digest_is_rejected(store):
    keys, _ = store
    identity = keys.ensure()
    identity.keyfile.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='key|signing'):
        keys.load()


def test_tampered_public_certificate_is_rejected(store):
    keys, tools = store
    keys.ensure()
    tools.certificate = 'd' * 64
    with pytest.raises(ValueError, match='certificate|signer'):
        keys.load()


def test_protection_failure_never_publishes_identity(store, monkeypatch):
    keys, _ = store
    def fail(value):
        raise RuntimeError('DPAPI failed')
    monkeypatch.setattr(backend, 'protect', fail)
    with pytest.raises(RuntimeError, match='DPAPI'):
        keys.ensure()
    assert not (keys.root / 'signer.json').exists()


def test_top_level_import_contract_uses_only_explicit_parameters(store, monkeypatch, tmp_path):
    keys, _ = store
    monkeypatch.setattr(backend, '_default_store', lambda: keys)
    source = tmp_path / 'selected.p12'
    source.write_bytes(b'synthetic')
    result = backend.import_existing(source, 'explicit', 'test-import-password')
    assert result.certificate_sha256 == 'c' * 64
    assert result.alias == 'explicit'


def test_dpapi_roundtrip_and_corruption_fail_closed():
    encrypted = backend.protect(b'synthetic-dpapi-test')
    assert b'synthetic-dpapi-test' not in encrypted
    assert backend.unprotect(encrypted) == b'synthetic-dpapi-test'
    with pytest.raises(RuntimeError, match='DPAPI'):
        backend.unprotect(b'corrupt-synthetic-data')


def test_key_guard_checks_junction_metadata_without_following(tmp_path, monkeypatch):
    junction = tmp_path / 'junction'
    junction.mkdir()
    original = Path.lstat
    def nofollow(path):
        value = original(path)
        if path == junction:
            return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=0x400)
        return value
    monkeypatch.setattr(Path, 'lstat', nofollow)
    with pytest.raises(ValueError, match='reparse'):
        backend._guard(junction / 'child')


def test_concurrent_first_use_creates_one_identity(store):
    keys, tools = store
    second = backend.HudKeyStore(tools, root=keys.root)
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(instance.ensure) for instance in (keys, second)]
        identities = [future.result(timeout=5) for future in futures]
    assert identities[0] == identities[1]
    assert len(tools.generated) == 1


@pytest.mark.skipif(os.name != 'nt', reason='Requires actual Windows byte locks')
def test_first_use_initialization_cannot_flush_over_another_handle_lock(store, monkeypatch):
    import msvcrt

    keys, tools = store
    opened = threading.Barrier(2, timeout=5)
    pending_write = threading.Event()
    acquired = threading.Event()
    flushed = threading.Event()
    state_lock = threading.Lock()
    handles = []
    owners = set()
    writes = []
    flushes = []
    original_open = Path.open
    original_locking = msvcrt.locking
    original_generate = tools.generate_key

    class LockStream:
        def __init__(self, stream, delayed):
            self.stream = stream
            self.delayed = delayed

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def write(self, value):
            with state_lock:
                owned = self.fileno() in owners
            if not owned:
                # Both old initializers buffer a byte while the file is
                # empty; delay one until the other has flushed and locked.
                # The corrected path owns its lock before initializing.
                if self.delayed:
                    result = self.stream.write(value)
                    pending_write.set()
                    assert acquired.wait(5), 'Other initializer never acquired its lock'
                    writes.append(owned)
                    return result
                else:
                    assert pending_write.wait(5), 'Delayed initializer never reached write'
            writes.append(owned)
            return self.stream.write(value)

        def flush(self):
            fd = self.fileno()
            with state_lock:
                flushes.append((fd in owners, bool(owners - {fd})))
            try:
                return self.stream.flush()
            finally:
                flushed.set()

    def lock_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        if path.name != 'signer.lock':
            return stream
        with state_lock:
            delayed = not handles
            handles.append(stream.fileno())
        try:
            opened.wait()
        except BaseException:
            stream.close()
            raise
        return LockStream(stream, delayed)

    def tracked_locking(fd, mode, size):
        with state_lock:
            result = original_locking(fd, mode, size)
            if mode == msvcrt.LK_NBLCK:
                owners.add(fd)
                acquired.set()
            elif mode == msvcrt.LK_UNLCK:
                owners.remove(fd)
        return result

    def generate(*args):
        if pending_write.is_set():
            assert flushed.wait(5), 'Delayed initializer never attempted its flush'
        return original_generate(*args)

    monkeypatch.setattr(Path, 'open', lock_open)
    monkeypatch.setattr(msvcrt, 'locking', tracked_locking)
    monkeypatch.setattr(tools, 'generate_key', generate)
    second = backend.HudKeyStore(tools, root=keys.root)
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(instance.ensure) for instance in (keys, second)]
        identities = [future.result(timeout=5) for future in futures]
    assert identities[0] == identities[1]
    assert len(tools.generated) == 1
    assert flushes == [(True, False)], 'Initialization must flush only under its own byte lock'
    assert writes == [True]
    assert not owners


@pytest.mark.parametrize('contents', [b'', b'\0existing-lock-must-survive'])
def test_existing_lock_is_initialized_without_truncation_and_reusable(store, contents):
    keys, _ = store
    keys.root.mkdir()
    lock_path = keys.root / 'signer.lock'
    lock_path.write_bytes(contents)
    identity = keys.ensure()
    assert lock_path.read_bytes() == (contents or b'\0')
    assert backend.HudKeyStore(keys.tools, root=keys.root).load() == identity


def test_generation_failure_releases_lock_for_another_store(store, monkeypatch):
    keys, tools = store
    generate = tools.generate_key
    def fail(*args):
        raise RuntimeError('Synthetic generation failure')
    monkeypatch.setattr(tools, 'generate_key', fail)
    with pytest.raises(RuntimeError, match='Synthetic generation failure'):
        keys.ensure()
    monkeypatch.setattr(tools, 'generate_key', generate)
    second = backend.HudKeyStore(tools, root=keys.root)
    with ThreadPoolExecutor(max_workers=1) as workers:
        identity = workers.submit(second.ensure).result(timeout=5)
    assert keys.load() == identity
    assert len(tools.generated) == 1


def test_initialization_flush_failure_releases_lock_for_another_store(store, monkeypatch):
    keys, tools = store
    original_open = Path.open

    class FailedFlush:
        def __init__(self, stream):
            self.stream = stream

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def flush(self):
            raise OSError('Synthetic initialization flush failure')

    def lock_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        return FailedFlush(stream) if path.name == 'signer.lock' else stream

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'open', lock_open)
        with pytest.raises(OSError, match='Synthetic initialization flush failure'):
            keys.ensure()
    assert not tools.generated
    assert not (keys.root / 'signer.json').exists()
    second = backend.HudKeyStore(tools, root=keys.root)
    with ThreadPoolExecutor(max_workers=1) as workers:
        identity = workers.submit(second.ensure).result(timeout=5)
    assert keys.load() == identity
    assert len(tools.generated) == 1


@pytest.mark.skipif(os.name != 'nt', reason='Requires actual Windows locks, DACL and DPAPI')
@pytest.mark.parametrize('attempt', range(10))
def test_windows_concurrent_threads_first_use_with_real_dpapi(tmp_path, attempt):
    tools = Tools()
    tools.generated = []
    root = tmp_path / f'threads-{attempt}'
    ready = threading.Barrier(4, timeout=5)
    def ensure():
        keys = backend.HudKeyStore(tools, root=root)
        ready.wait()
        return keys.ensure()
    with ThreadPoolExecutor(max_workers=4) as workers:
        futures = [workers.submit(ensure) for _ in range(4)]
        identities = [future.result(timeout=5) for future in futures]
    assert all(identity == identities[0] for identity in identities)
    assert len(tools.generated) == 1
    assert (root / 'signer.lock').read_bytes() == b'\0'
    _assert_private_dacl(root, directory=True)
    for path in root.iterdir():
        _assert_private_dacl(path)
        assert identities[0].password.encode() not in path.read_bytes()


def _process_ensure(root, ready, result):
    """Spawn worker: report public identity metadata only, never credentials."""
    try:
        tools = Tools()
        tools.generated = []
        ready.wait(timeout=5)
        identity = backend.HudKeyStore(tools, root=Path(root)).ensure()
        result.send(('ok', identity.keyfile.name, identity.alias,
                     identity.certificate_sha256, len(tools.generated)))
    except BaseException as error:
        result.send(('error', type(error).__name__))
    finally:
        result.close()


@pytest.mark.skipif(os.name != 'nt', reason='Requires actual Windows locks, DACL and DPAPI')
@pytest.mark.parametrize('attempt', range(5))
def test_windows_concurrent_processes_first_use_creates_one_identity(tmp_path, attempt):
    context = multiprocessing.get_context('spawn')
    root = tmp_path / f'processes-{attempt}'
    ready = context.Barrier(4)
    readers, processes = [], []
    try:
        for _ in range(3):
            reader, writer = context.Pipe(duplex=False)
            process = context.Process(target=_process_ensure, args=(root, ready, writer))
            process.start()
            writer.close()
            readers.append(reader)
            processes.append(process)
        ready.wait(timeout=5)
        results = []
        for reader in readers:
            assert reader.poll(5), 'Signer process did not report a result'
            results.append(reader.recv())
        for process in processes:
            process.join(timeout=5)
            assert process.exitcode == 0
        assert all(result[0] == 'ok' for result in results), results
        assert all(result[1:4] == results[0][1:4] for result in results)
        assert sum(result[4] for result in results) == 1
        tools = Tools()
        tools.generated = []
        identity = backend.HudKeyStore(tools, root=root).load()
        assert (identity.keyfile.name, identity.alias, identity.certificate_sha256) == results[0][1:4]
        assert not tools.generated
        assert len(list(root.glob('*.p12'))) == len(list(root.glob('*.dpapi'))) == 1
        assert (root / 'signer.lock').read_bytes() == b'\0'
        _assert_private_dacl(root, directory=True)
        for path in root.iterdir():
            _assert_private_dacl(path)
            assert identity.password.encode() not in path.read_bytes()
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
            process.close()
        for reader in readers:
            reader.close()


@pytest.mark.skipif(os.name != 'nt', reason='Requires actual Windows byte locks')
def test_closed_handle_releases_uninitialized_lock_for_first_use(store):
    import msvcrt

    keys, tools = store
    keys.root.mkdir()
    lock_path = keys.root / 'signer.lock'
    with lock_path.open('a+b') as abandoned:
        msvcrt.locking(abandoned.fileno(), msvcrt.LK_NBLCK, 1)
        # Simulate exit before initialization, without explicitly unlocking.
    with ThreadPoolExecutor(max_workers=1) as workers:
        identity = workers.submit(keys.ensure).result(timeout=5)
    assert keys.load() == identity
    assert len(tools.generated) == 1
    assert lock_path.read_bytes() == b'\0'


def _process_hold_lock(lock_path, ready):
    import msvcrt

    with Path(lock_path).open('a+b', buffering=0) as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        ready.send('locked')
        ready.recv()  # Parent terminates this worker while its handle owns the lock.


@pytest.mark.skipif(os.name != 'nt', reason='Requires actual Windows byte locks')
@pytest.mark.parametrize('contents', [b'', b'\0retained-lock'])
def test_terminated_process_releases_lock_without_truncation(store, contents):
    keys, tools = store
    keys.root.mkdir()
    lock_path = keys.root / 'signer.lock'
    lock_path.write_bytes(contents)
    context = multiprocessing.get_context('spawn')
    ready, worker = context.Pipe()
    process = context.Process(target=_process_hold_lock, args=(lock_path, worker))
    try:
        process.start()
        worker.close()
        assert ready.poll(5), 'Lock holder did not acquire byte zero'
        assert ready.recv() == 'locked'
        process.terminate()
        process.join(timeout=5)
        assert not process.is_alive()
        with ThreadPoolExecutor(max_workers=1) as workers:
            identity = workers.submit(keys.ensure).result(timeout=5)
        assert keys.load() == identity
        assert len(tools.generated) == 1
        assert lock_path.read_bytes() == (contents or b'\0')
        _assert_private_dacl(lock_path)
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=5)
        process.close()
        ready.close()
        worker.close()


def test_canceled_first_use_does_not_generate_key(store):
    from rc2vi.hud_tools import HudCancelled
    keys, tools = store
    keys.cancel = threading.Event()
    keys.cancel.set()
    with pytest.raises(HudCancelled):
        keys.ensure()
    assert not tools.generated
    assert not (keys.root / 'signer.json').exists()


def test_corrupt_existing_identity_is_not_silently_replaced(store):
    keys, tools = store
    keys.ensure()
    (keys.root / 'signer.json').write_text('{"schema":2}')
    with pytest.raises(ValueError, match='metadata'):
        keys.ensure()
    assert len(tools.generated) == 1


def test_signer_key_swap_during_certificate_check_is_rejected(store, monkeypatch):
    keys, tools = store
    identity = keys.ensure()
    original = tools.keycert
    def tamper(*args):
        result = original(*args)
        identity.keyfile.write_bytes(b'key-changed-during-inspection')
        return result
    monkeypatch.setattr(tools, 'keycert', tamper)
    with pytest.raises(ValueError, match='changed during'):
        keys.load()


def _windows_dacl(path):
    """Read only ACL metadata, never file contents or a developer key."""
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    get_security = advapi.GetNamedSecurityInfoW
    get_security.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    get_security.restype = ctypes.c_uint32
    convert = advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
    convert.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                       ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    convert.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    descriptor, text = ctypes.c_void_p(), ctypes.c_void_p()
    assert get_security(str(path), 1, 4, None, None, None, None, ctypes.byref(descriptor)) == 0
    try:
        assert convert(descriptor, 1, 4, ctypes.byref(text), None)
        return ctypes.wstring_at(text)
    finally:
        if text.value:
            kernel.LocalFree(text)
        if descriptor.value:
            kernel.LocalFree(descriptor)


def _windows_broad_dacl(path, directory=False):
    """Deliberately expose synthetic test files to broad users to test repair."""
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p),
                       ctypes.c_void_p]
    convert.restype = ctypes.c_int
    set_security = advapi.SetFileSecurityW
    set_security.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p]
    set_security.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    inherit = 'OICI' if directory else ''
    sddl = (f'D:P(A;{inherit};FA;;;SY)(A;{inherit};FA;;;OW)'
            f'(A;{inherit};FR;;;BU)(A;{inherit};FR;;;WD)')
    descriptor = ctypes.c_void_p()
    assert convert(sddl, 1, ctypes.byref(descriptor), None)
    try:
        assert set_security(str(path), 0x80000004, descriptor)
    finally:
        kernel.LocalFree(descriptor)


def _assert_private_dacl(path, directory=False):
    sddl = _windows_dacl(path)
    assert sddl.startswith('D:P'), 'DACL must be protected against parent inheritance'
    aces = [ace.split(';') for ace in re.findall(r'\(([^)]*)\)', sddl)]
    # Exactly these two trustees excludes SandboxUsers and all broad/custom SIDs.
    assert len(aces) == 2 and {ace[5] for ace in aces} == {'SY', 'OW'}
    assert all(ace[0] == 'A' and ace[2] == 'FA' for ace in aces)
    assert all(ace[1] == ('OICI' if directory else '') for ace in aces)


@pytest.mark.skipif(os.name != 'nt', reason='Requires actual Windows DACL APIs')
def test_windows_first_use_removes_inherited_broad_read_acl_from_every_signer_file(store):
    keys, _ = store
    keys.root.parent.mkdir(parents=True, exist_ok=True)
    _windows_broad_dacl(keys.root.parent, directory=True)
    keys.ensure()
    _assert_private_dacl(keys.root, directory=True)
    names = {path.name for path in keys.root.iterdir()}
    assert {'signer.lock', 'signer.json'} <= names
    assert any(name.endswith('.p12') for name in names)
    assert any(name.endswith('.dpapi') for name in names)
    for path in keys.root.iterdir():
        _assert_private_dacl(path)


@pytest.mark.skipif(os.name != 'nt', reason='Requires actual Windows DACL APIs')
def test_windows_load_repairs_current_and_retained_files_before_reading_metadata(store, monkeypatch,
                                                                               tmp_path):
    keys, _ = store
    keys.ensure()
    selected = tmp_path / 'selected.jks'
    selected.write_bytes(b'synthetic-legacy-jks')
    keys.import_existing(selected, 'developer', 'synthetic-migration-password')
    _windows_broad_dacl(keys.root, directory=True)
    for path in keys.root.iterdir():
        _windows_broad_dacl(path)
        assert ';;;BU)' in _windows_dacl(path)
    original = backend.load_json
    observed = []
    def checked_metadata(path):
        _assert_private_dacl(keys.root, directory=True)
        for child in keys.root.iterdir():
            _assert_private_dacl(child)
        observed.append(path.name)
        return original(path)
    monkeypatch.setattr(backend, 'load_json', checked_metadata)
    keys.load()
    assert observed == ['signer.json']


@pytest.mark.skipif(os.name != 'nt', reason='Requires actual Windows DACL APIs')
def test_windows_import_protects_copy_without_changing_selected_source_acl(store, tmp_path):
    keys, _ = store
    selected = tmp_path / 'user-selected.jks'
    selected.write_bytes(b'synthetic-selected-key')
    _windows_broad_dacl(selected)
    source_acl = _windows_dacl(selected)
    identity = keys.import_existing(selected, 'developer', 'synthetic-import-password')
    assert _windows_dacl(selected) == source_acl
    _assert_private_dacl(keys.root, directory=True)
    _assert_private_dacl(identity.keyfile)
    for path in keys.root.iterdir():
        _assert_private_dacl(path)


@pytest.mark.skipif(os.name != 'nt', reason='Requires actual Windows DACL APIs')
def test_windows_staged_metadata_is_private_before_json_write(store, monkeypatch):
    keys, _ = store
    original = backend.json.dump
    observed = []
    def checked_dump(value, output, **kwargs):
        _assert_private_dacl(Path(output.name))
        for child in keys.root.iterdir():
            _assert_private_dacl(child)
        observed.append(Path(output.name).name)
        return original(value, output, **kwargs)
    monkeypatch.setattr(backend.json, 'dump', checked_dump)
    keys.ensure()
    assert len(observed) == 1 and observed[0].startswith('signer-')


@pytest.mark.parametrize('failed_name', [None, 'signer.lock'])
def test_acl_failure_blocks_signer_generation_and_metadata_publication(store, monkeypatch,
                                                                      failed_name):
    keys, tools = store
    def failure(path, directory=False):
        if failed_name is None or Path(path).name == failed_name:
            raise RuntimeError('Private signer ACL could not be enforced')
    monkeypatch.setattr(backend, 'make_private', failure, raising=False)
    with pytest.raises(RuntimeError, match='ACL'):
        keys.ensure()
    assert not tools.generated
    assert not (keys.root / 'signer.json').exists()


def test_existing_acl_repair_failure_blocks_metadata_and_secret_reads(store, monkeypatch):
    keys, _ = store
    keys.ensure()
    original = backend.make_private
    def failure(path, directory=False):
        if Path(path).suffix == '.dpapi':
            raise RuntimeError('Private signer ACL repair failed')
        original(path, directory=directory)
    observed = []
    def forbidden_read(path):
        observed.append(path)
        raise AssertionError('Metadata must not be read after ACL repair failure')
    monkeypatch.setattr(backend, 'make_private', failure)
    monkeypatch.setattr(backend, 'load_json', forbidden_read)
    with pytest.raises(RuntimeError, match='ACL repair'):
        keys.load()
    assert not observed


@pytest.mark.skipif(os.name != 'nt', reason='Requires actual Windows DACL APIs')
def test_hardlinked_signer_file_is_rejected_without_changing_external_acl(store, tmp_path):
    keys, tools = store
    selected = tmp_path / 'external-synthetic-key'
    selected.write_bytes(b'synthetic-key-hardlink')
    _windows_broad_dacl(selected)
    source_acl = _windows_dacl(selected)
    keys.root.mkdir()
    os.link(selected, keys.root / 'hud-old.p12')
    with pytest.raises(ValueError, match='one link'):
        keys.ensure()
    assert _windows_dacl(selected) == source_acl
    assert not tools.generated


def test_import_acl_failure_keeps_previous_identity(store, monkeypatch, tmp_path):
    keys, _ = store
    previous = keys.ensure()
    selected = tmp_path / 'user-selected.jks'
    selected.write_bytes(b'synthetic-selected-jks')
    original = backend.make_private
    def failure(path, directory=False):
        if Path(path).suffix == '.keystore':
            raise RuntimeError('Private imported key ACL failed')
        original(path, directory=directory)
    monkeypatch.setattr(backend, 'make_private', failure)
    with pytest.raises(RuntimeError, match='ACL'):
        keys.import_existing(selected, 'developer', 'synthetic-import-password')
    assert keys.load() == previous
    assert not list(keys.root.glob('*.keystore'))
