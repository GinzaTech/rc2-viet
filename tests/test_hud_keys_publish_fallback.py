"""Redirected-AppData metadata publication faults; every key/secret is synthetic."""
import json
import os
from pathlib import Path

import pytest

from rc2vi import hud_keys


class SyntheticTools:
    cancel = None

    def __init__(self):
        self.generated = 0

    def generate_key(self, path, alias, password):
        self.generated += 1
        path.write_bytes(b'original-synthetic-key')

    def keycert(self, path, alias, password):
        return ('b' if path.read_bytes() == b'imported-synthetic-key' else 'a') * 64


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(hud_keys, 'protect', lambda value: bytes(x ^ 123 for x in value))
    monkeypatch.setattr(hud_keys, 'unprotect', lambda value: bytes(x ^ 123 for x in value))
    tools = SyntheticTools()
    return hud_keys.HudKeyStore(tools, tmp_path / 'private-signing'), tools


def fail_metadata_replace(monkeypatch, destination, code=17):
    original = Path.replace
    calls = []
    def replacement(path, target):
        if Path(target) == destination:
            calls.append(path)
            error = OSError('Synthetic metadata replace failure')
            error.winerror = code
            raise error
        return original(path, target)
    monkeypatch.setattr(Path, 'replace', replacement)
    return calls


def existing_files(root):
    return {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}


def test_first_publish_winerror17_uses_private_verified_file_and_reuses_identity(store, monkeypatch):
    keys, tools = store
    calls = fail_metadata_replace(monkeypatch, keys.root / 'signer.json')
    signer = keys.ensure()
    assert keys.load() == signer == keys.ensure()
    assert signer.certificate_sha256 == 'a' * 64
    assert tools.generated == 1 and len(calls) == 1
    value = json.loads((keys.root / 'signer.json').read_text())
    assert value['keyfile'] == signer.keyfile.name
    assert set(path.name for path in keys.root.iterdir()) == {
        'signer.lock', 'signer.json', signer.keyfile.name, signer.keyfile.stem + '.dpapi'}


def test_winerror17_explicit_import_retains_previous_metadata_and_key_files(store, monkeypatch, tmp_path):
    keys, tools = store
    previous = keys.ensure()
    before = existing_files(keys.root)
    selected = tmp_path / 'explicit-source.keystore'
    selected.write_bytes(b'imported-synthetic-key')
    fail_metadata_replace(monkeypatch, keys.root / 'signer.json')
    imported = keys.import_existing(selected, 'selected', 'fixture-password')
    assert keys.load() == imported
    assert imported.certificate_sha256 == 'b' * 64
    assert imported.keyfile != previous.keyfile
    for name, content in before.items():
        if name != 'signer.json':
            assert (keys.root / name).read_bytes() == content
    retained = list(keys.root.glob('signer-*.previous.json'))
    assert len(retained) == 1 and retained[0].read_bytes() == before['signer.json']
    assert selected.read_bytes() == b'imported-synthetic-key'
    assert tools.generated == 1


@pytest.mark.parametrize('has_previous', [False, True])
def test_publish_write_failure_restores_previous_or_leaves_no_identity(store, monkeypatch, tmp_path, has_previous):
    keys, tools = store
    previous = keys.ensure() if has_previous else None
    before = existing_files(keys.root) if has_previous else {}
    destination = keys.root / 'signer.json'
    fail_metadata_replace(monkeypatch, destination)
    original_fsync = hud_keys.os.fsync
    failed = False
    def fail_destination_flush_once(fd):
        nonlocal failed
        # Fail after new bytes reached the selected destination, rather than in
        # the unrelated backup/staging file. Rollback then uses the real fsync.
        if not failed and destination.exists() and os.fstat(fd).st_ino == destination.stat().st_ino:
            failed = True
            raise OSError('Synthetic destination publication failure')
        return original_fsync(fd)
    monkeypatch.setattr(hud_keys.os, 'fsync', fail_destination_flush_once)
    with pytest.raises(OSError, match='Synthetic destination'):
        if has_previous:
            selected = tmp_path / 'selected.keystore'
            selected.write_bytes(b'imported-synthetic-key')
            keys.import_existing(selected, 'selected', 'fixture-password')
        else:
            keys.ensure()
    assert failed and tools.generated == 1
    if has_previous:
        assert keys.load() == previous
        for name, content in before.items():
            assert (keys.root / name).read_bytes() == content
        retained = list(keys.root.glob('signer-*.previous.json'))
        assert len(retained) == 1 and retained[0].read_bytes() == before['signer.json']
        assert set(existing_files(keys.root)) == set(before) | {retained[0].name}
    else:
        assert not destination.exists()
        assert set(existing_files(keys.root)) == {'signer.lock'}


def test_other_replace_error_never_uses_fallback_and_preserves_existing_identity(store, monkeypatch, tmp_path):
    keys, _ = store
    previous = keys.ensure()
    before = existing_files(keys.root)
    selected = tmp_path / 'selected.keystore'
    selected.write_bytes(b'imported-synthetic-key')
    fail_metadata_replace(monkeypatch, keys.root / 'signer.json', code=5)
    with pytest.raises(OSError, match='Synthetic metadata'):
        keys.import_existing(selected, 'selected', 'fixture-password')
    assert keys.load() == previous
    assert existing_files(keys.root) == before
