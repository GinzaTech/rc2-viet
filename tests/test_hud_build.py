"""Offline builder contracts using synthetic APKs and a deterministic tool boundary."""
import hashlib
import json
import shutil
import struct
import threading
import warnings
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rc2vi import hud_build as backend
from rc2vi.hud_tools import HudCancelled
from scripts.hud_signing_block import V2, block_entries
from test_hud_manifest import binary_manifest


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signing_block(path, entries):
    raw = path.read_bytes()
    end = raw.rfind(b'PK\x05\x06')
    central = struct.unpack_from('<I', raw, end + 16)[0]
    pairs = b''.join(struct.pack('<QI', len(value) + 4, key) + value for key, value in entries)
    size = len(pairs) + 24
    block = struct.pack('<Q', size) + pairs + struct.pack('<Q', size) + b'APK Sig Block 42'
    result = bytearray(raw[:central] + block + raw[central:])
    struct.pack_into('<I', result, end + len(block) + 16, central + len(block))
    path.write_bytes(result)


class FakeTools:
    archive_sha256 = 'a' * 64
    manifest_sha256 = 'b' * 64
    certificate = 'c' * 64
    helper = b'dex\n035\0synthetic-hud'

    def __init__(self, assets, work, cancel=None):
        self.cancel = cancel
        self.patches = 0

    def prepare(self):
        return Path('synthetic-toolchain')

    def payload(self):
        return self.helper

    def historical_payload(self, expected):
        raise ValueError('Historical payload is not pinned unless the test explicitly provides it.')

    def patch(self, source, output, workdir):
        self.patches += 1
        output.write_bytes(source.read_bytes() + b':scoped-hook')

    def align(self, source, output):
        shutil.copyfile(source, output)

    def sign(self, source, output, keyfile, alias, password):
        shutil.copyfile(source, output)
        signing_block(output, [(V2, b'local-v2'), (0xf05368c0, b'local-v3')])

    def verify(self, apk):
        return self.certificate


class FakeKeys:
    def __init__(self, tools):
        self.tools = tools

    def ensure(self):
        return self.load()

    def load(self):
        return SimpleNamespace(keyfile=Path('synthetic.p12'), alias='hud',
                               password='test-only', certificate_sha256='c' * 64)


@pytest.fixture
def project(tmp_path, monkeypatch):
    source = tmp_path / 'source with spaces.apk'
    with zipfile.ZipFile(source, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in {
            'AndroidManifest.xml': binary_manifest(), 'classes.dex': b'bootstrap-five-classes',
            'classes2.dex': b'dji-code', 'resources.arsc': b'resources',
            'lib/arm64-v8a/libAppGuard.so': b'native', 'META-INF/DJI.RSA': b'legacy-cert',
            'META-INF/DJI.SF': b'legacy-signature', 'META-INF/MANIFEST.MF': b'legacy-manifest',
        }.items():
            archive.writestr(name, value)
    signing_block(source, [(V2, b'stock-v2')])
    monkeypatch.setattr(backend, 'SUPPORTED_APK', digest(source))
    monkeypatch.setattr(backend, 'HudTools', FakeTools)
    monkeypatch.setattr(backend, 'HudKeyStore', FakeKeys)
    events = []
    builder = backend.HudBuilder(tmp_path / 'assets', tmp_path / 'work with spaces',
                                 lambda *event: events.append(event))
    return builder, source, events


def test_pinned_hash_is_stock_only():
    assert backend.SUPPORTED_APK == 'cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e'


def test_verify_device_apk_accepts_exact_recipe_without_loading_local_keys(project):
    builder,stock,_=project
    built=builder.build(stock)
    builder.keys.load=Mock(side_effect=AssertionError('Device import must not require PC signing keys'))
    value=builder.verify_device_apk(Path(built['apk']),stock)
    assert value['digest']==built['digest']
    assert value['source_digest']==backend.SUPPORTED_APK
    assert value['certificate_sha256']==builder.tools.certificate
    builder.keys.load.assert_not_called()


def test_verify_device_apk_rejects_changed_recipe(project):
    builder,stock,_=project; built=builder.build(stock)
    from scripts.hud_apk import repack_apk
    candidate=stock.parent/'wrong.apk'
    repack_apk(stock,candidate,b'wrong manifest',builder.tools.payload(),b'wrong bootstrap')
    signing_block(candidate,[(V2,b'stock-v2'),(0xf05368c0,b'local-v3')])
    with pytest.raises(ValueError):builder.verify_device_apk(candidate,stock)


def test_verify_device_apk_rejects_unpinned_helper(project):
    builder,stock,_=project;built=builder.build(stock)
    builder.tools.helper=b'new current payload'
    with pytest.raises(ValueError,match='Historical'):
        builder.verify_device_apk(Path(built['apk']),stock)


def test_verify_device_apk_accepts_verified_foreign_pc_signer(project):
    builder,stock,_=project;built=builder.build(stock)
    builder.tools.certificate='e'*64
    value=builder.verify_device_apk(Path(built['apk']),stock)
    assert value['certificate_sha256']=='e'*64
    with pytest.raises(ValueError):builder.verify(built['receipt'])


def test_existing_receipt_can_be_revalidated_with_an_explicit_verified_historical_payload(project):
    builder, source, _ = project
    result = builder.build(source)
    old = builder.tools.payload()
    builder.tools.helper = b'new-helper-version'
    def historical(expected):
        assert expected == hashlib.sha256(old).hexdigest()
        return old
    builder.tools.historical_payload = historical
    assert builder.verify_historical(result['receipt']) == result
    with pytest.raises(ValueError, match='payload'):
        builder.verify(result['receipt'])


def test_build_preserves_stock_binds_receipt_and_revalidates_latest(project):
    builder, source, events = project
    before = source.read_bytes()
    result = builder.build(source)
    assert result['status'] == 'hud_built'
    assert result['digest'] == digest(Path(result['apk']))
    assert result['source_digest'] == digest(source)
    assert result['certificate_sha256'] == 'c' * 64
    assert source.read_bytes() == before
    assert block_entries(Path(result['apk']).read_bytes())[V2] == b'stock-v2'
    receipt = json.loads(Path(result['receipt']).read_text())
    assert receipt['tool_archive_sha256'] == 'a' * 64
    assert receipt['tool_manifest_sha256'] == 'b' * 64
    assert receipt['payload_sha256'] == hashlib.sha256(FakeTools.helper).hexdigest()
    assert builder.verify(result['receipt']) == result
    assert builder.latest() == result
    assert builder.tools.patches >= 3  # The recipe is reproduced during verification.
    assert len(events) >= 5 and all(event[0] == 'applying' for event in events)
    assert 'test-only' not in Path(result['receipt']).read_text()


def test_latest_returns_none_before_first_build(project):
    assert project[0].latest() is None


def test_rejects_wrong_stock_without_publishing(project):
    builder, source, _ = project
    source.write_bytes(b'wrong-stock')
    with pytest.raises(ValueError, match='stock|source|original'):
        builder.build(source)
    assert builder.latest() is None


@pytest.mark.parametrize('kind', ['duplicate', 'missing', 'malformed', 'existing-hud'])
def test_rejects_invalid_stock_archives_even_with_pinned_test_digest(project, monkeypatch, kind):
    builder, source, _ = project
    if kind == 'malformed':
        source.write_bytes(b'not-a-zip')
    else:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(source, 'a') as archive:
                if kind == 'duplicate':
                    archive.writestr('classes.dex', b'duplicate')
                elif kind == 'existing-hud':
                    archive.writestr('classes23.dex', b'already-patched')
                else:
                    pass
        if kind == 'missing':
            replacement = source.with_suffix('.tmp')
            with zipfile.ZipFile(source) as old, zipfile.ZipFile(replacement, 'w') as new:
                for item in old.infolist():
                    if item.filename != 'classes.dex':
                        new.writestr(item, old.read(item))
            replacement.replace(source)
    monkeypatch.setattr(backend, 'SUPPORTED_APK', digest(source))
    with pytest.raises((ValueError, zipfile.BadZipFile)):
        builder.build(source)
    assert builder.latest() is None


def test_cancel_never_publishes_candidate(project):
    builder, source, _ = project
    builder.cancel = threading.Event()
    builder.cancel.set()
    with pytest.raises(HudCancelled):
        builder.build(source)
    assert builder.latest() is None


def test_failed_build_keeps_previous_verified_latest(project, monkeypatch):
    builder, source, _ = project
    previous = builder.build(source)
    def fail(*args):
        raise RuntimeError('synthetic sign failure')
    monkeypatch.setattr(builder.tools, 'sign', fail)
    with pytest.raises(RuntimeError, match='sign failure'):
        builder.build(source)
    assert builder.latest() == previous


def test_rejects_selected_signature_mismatch(project, monkeypatch):
    builder, source, _ = project
    monkeypatch.setattr(builder.tools, 'verify', lambda _: 'd' * 64)
    with pytest.raises(ValueError, match='certificate|signer'):
        builder.build(source)
    assert builder.latest() is None


@pytest.mark.parametrize('field', ['source_digest', 'tool_archive_sha256', 'tool_manifest_sha256',
                                  'payload_sha256', 'certificate_sha256', 'digest', 'schema'])
def test_verify_rejects_receipt_metadata_tampering(project, field):
    builder, source, _ = project
    result = builder.build(source)
    path = Path(result['receipt'])
    receipt = json.loads(path.read_text())
    receipt[field] = 2 if field == 'schema' else 'f' * 64
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        builder.verify(path)


def test_updated_hash_cannot_authorize_modified_resources(project):
    builder, source, _ = project
    result = builder.build(source)
    candidate = Path(result['apk'])
    replacement = candidate.with_suffix('.tmp')
    with zipfile.ZipFile(candidate) as old, zipfile.ZipFile(replacement, 'w') as new:
        for item in old.infolist():
            new.writestr(item, b'evil-resources' if item.filename == 'resources.arsc' else old.read(item))
    replacement.replace(candidate)
    signing_block(candidate, [(V2, b'stock-v2'), (0xf05368c0, b'local-v3')])
    path = Path(result['receipt'])
    receipt = json.loads(path.read_text())
    receipt['digest'] = digest(candidate)
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='Unexpected'):
        builder.verify(path)


def test_receipt_outside_managed_build_is_rejected(project, tmp_path):
    builder, source, _ = project
    result = builder.build(source)
    foreign = tmp_path / 'foreign.json'
    shutil.copyfile(result['receipt'], foreign)
    with pytest.raises(ValueError, match='receipt|managed'):
        builder.verify(foreign)


def test_latest_pointer_cannot_escape_work(project):
    builder = project[0]
    builder.work.mkdir(parents=True)
    (builder.work / 'latest.json').write_text(json.dumps({'schema': 1, 'receipt': '../foreign.json'}))
    with pytest.raises(ValueError):
        builder.latest()


def test_verify_fails_if_source_snapshot_changed(project):
    builder, source, _ = project
    result = builder.build(source)
    path = Path(result['receipt'])
    receipt = json.loads(path.read_text())
    (path.parent / receipt['source']).write_bytes(b'wrong-snapshot')
    with pytest.raises(ValueError, match='source|stock'):
        builder.verify(path)


def test_verify_rechecks_current_payload_and_tools(project):
    builder, source, _ = project
    result = builder.build(source)
    builder.tools.helper = b'changed-payload'
    with pytest.raises(ValueError, match='payload'):
        builder.verify(result['receipt'])


def test_forged_bootstrap_digest_cannot_replace_reproduced_recipe(project):
    builder, source, _ = project
    result = builder.build(source)
    candidate = Path(result['apk'])
    replacement = candidate.with_suffix('.tmp')
    with zipfile.ZipFile(candidate) as old, zipfile.ZipFile(replacement, 'w') as new:
        for item in old.infolist():
            new.writestr(item, b'forged-hook' if item.filename == 'classes.dex' else old.read(item))
    replacement.replace(candidate)
    signing_block(candidate, [(V2, b'stock-v2'), (0xf05368c0, b'local-v3')])
    receipt_path = Path(result['receipt'])
    receipt = json.loads(receipt_path.read_text())
    receipt['digest'] = digest(candidate)
    receipt['bootstrap_sha256'] = hashlib.sha256(b'forged-hook').hexdigest()
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='bootstrap'):
        builder.verify(receipt_path)


def test_tampered_latest_candidate_does_not_return_trusted_digest(project):
    builder, source, _ = project
    result = builder.build(source)
    Path(result['apk']).write_bytes(b'corrupted-output')
    with pytest.raises(ValueError, match='digest'):
        builder.latest()


def test_tool_manifest_change_invalidates_existing_receipt(project):
    builder, source, _ = project
    result = builder.build(source)
    builder.tools.manifest_sha256 = 'd' * 64
    with pytest.raises(ValueError, match='tool'):
        builder.verify(result['receipt'])


def test_corrupt_latest_and_duplicate_receipt_json_fail_closed(project):
    builder, source, _ = project
    result = builder.build(source)
    receipt = Path(result['receipt'])
    receipt.write_text('{"schema":1,"schema":1}')
    with pytest.raises(ValueError):
        builder.verify(receipt)
    (builder.work / 'latest.json').write_text('not-json')
    with pytest.raises(ValueError):
        builder.latest()


def test_source_changed_during_validation_is_rejected(project, monkeypatch):
    builder, source, _ = project
    result = builder.build(source)
    receipt = Path(result['receipt'])
    original = builder.tools.verify
    def mutate_source(apk):
        (receipt.parent / 'source.apk').write_bytes(b'source-changed-during-verification')
        return original(apk)
    monkeypatch.setattr(builder.tools, 'verify', mutate_source)
    with pytest.raises(ValueError, match='changed'):
        builder.verify(receipt)


def test_cancellation_during_signing_keeps_last_success(project, monkeypatch):
    builder, source, _ = project
    previous = builder.build(source)
    cancellation = threading.Event()
    builder.cancel = cancellation
    original = builder.tools.sign
    def cancel_after_sign(*args):
        original(*args)
        cancellation.set()
    monkeypatch.setattr(builder.tools, 'sign', cancel_after_sign)
    with pytest.raises(HudCancelled):
        builder.build(source)
    cancellation.clear()
    assert builder.latest() == previous
    assert len(list((builder.work / 'builds').iterdir())) == 1


def test_build_guard_checks_junction_metadata_without_following(tmp_path, monkeypatch):
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


def test_public_apk_certificate_inspection_requires_no_receipt_or_signing_key(project, monkeypatch):
    builder, source, _ = project
    verifier = Mock(return_value='c' * 64)
    key_loader = Mock(side_effect=AssertionError('Inspection must not load/create a signer'))
    monkeypatch.setattr(builder.tools, 'verify', verifier)
    monkeypatch.setattr(builder.keys, 'load', key_loader)
    monkeypatch.setattr(builder.keys, 'ensure', key_loader)
    assert builder.verify_apk(source) == 'c' * 64
    verifier.assert_called_once_with(source)
    key_loader.assert_not_called()
    assert builder.latest() is None


def test_public_apk_certificate_inspection_propagates_invalid_signature(project, monkeypatch):
    builder, source, _ = project
    monkeypatch.setattr(builder.tools, 'verify', Mock(side_effect=RuntimeError('HUD tool execution failed.')))
    with pytest.raises(RuntimeError, match='execution failed'):
        builder.verify_apk(source)


def test_public_apk_certificate_inspection_obeys_cancellation(project, monkeypatch):
    builder, source, _ = project
    verifier = Mock()
    monkeypatch.setattr(builder.tools, 'verify', verifier)
    builder.cancel = threading.Event()
    builder.cancel.set()
    with pytest.raises(HudCancelled):
        builder.verify_apk(source)
    verifier.assert_not_called()
