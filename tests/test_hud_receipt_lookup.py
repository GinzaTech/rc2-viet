"""Receipt lookup contracts using retained bytes, without tools or device I/O."""
import hashlib
import json
from pathlib import Path
import stat
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rc2vi import hud_install as backend
from rc2vi.hud_build import HudBuilder
from rc2vi.hud_tools import load_json


class ReceiptBuilder:
    def __init__(self, work):
        self.work = work
        self.receipts = {}
        self.latest_reference = None
        self.verify = Mock(side_effect=self._verify)
        self.verify_historical = Mock(side_effect=self._verify)
        self.latest = Mock(side_effect=self._latest)

    def _latest(self):
        return None if self.latest_reference is None else self.verify(self.latest_reference)

    def _verify(self, reference):
        path = HudBuilder._receipt(self, Path(reference))
        expected, result = self.receipts[str(path)]
        if load_json(path) != expected:
            raise ValueError('Receipt no longer matches the verified recipe.')
        return dict(result)

    def retain(self, index, content=b'installed-hud'):
        directory = self.work / 'builds' / f'{index:032x}'
        directory.mkdir(parents=True)
        apk = directory / 'hud.apk'
        apk.write_bytes(content)
        receipt = directory / 'receipt.json'
        metadata = {'digest': hashlib.sha256(content).hexdigest(),
                    'source_digest': backend.SUPPORTED_APK,
                    'certificate_sha256': 'c' * 64, 'apk': 'hud.apk'}
        receipt.write_text(json.dumps(metadata), encoding='utf-8')
        result = {**metadata, 'apk': str(apk), 'receipt': str(receipt)}
        self.receipts[str(receipt)] = (metadata, result)
        return result


@pytest.fixture
def builder(tmp_path):
    return ReceiptBuilder(tmp_path / 'work with spaces')


def test_scan_of_24_retained_receipts_verifies_and_hashes_only_matching_apk(builder, monkeypatch):
    retained = [builder.retain(index, f'hud-{index}'.encode()) for index in range(24)]
    builder.latest_reference = retained[-1]['receipt']
    target = retained[12]
    byte_hash = Mock(wraps=backend.sha256_file)
    monkeypatch.setattr(backend, 'sha256_file', byte_hash)

    assert backend.verify_trusted_installed_apk(builder, target['digest']) == target

    builder.latest.assert_not_called()
    builder.verify.assert_not_called()
    builder.verify_historical.assert_called_once_with(target['receipt'])
    byte_hash.assert_called_once_with(Path(target['apk']), None)


def test_unknown_digest_never_verifies_unrelated_receipts(builder):
    for index in range(24):
        builder.latest_reference = builder.retain(index, f'hud-{index}'.encode())['receipt']

    with pytest.raises(ValueError):
        backend.verify_trusted_installed_apk(builder, 'f' * 64)

    builder.latest.assert_not_called()
    builder.verify.assert_not_called()
    builder.verify_historical.assert_not_called()


@pytest.mark.parametrize('field', ['source_digest', 'certificate_sha256', 'apk'])
def test_matching_metadata_tampering_still_requires_full_verifier(builder, field):
    target = builder.retain(1)
    path = Path(target['receipt'])
    metadata = load_json(path)
    path.write_text(json.dumps({**metadata, field: 'tampered'}), encoding='utf-8')

    with pytest.raises(ValueError):
        backend.verify_trusted_installed_apk(builder, target['digest'])

    builder.verify_historical.assert_called_once_with(target['receipt'])


def test_matching_receipt_cannot_authorize_tampered_retained_bytes(builder):
    target = builder.retain(1)
    Path(target['apk']).write_bytes(b'tampered-apk')

    with pytest.raises(ValueError):
        backend.verify_trusted_installed_apk(builder, target['digest'])

    builder.verify_historical.assert_called_once_with(target['receipt'])


def test_rejected_matching_receipt_does_not_hide_valid_matching_receipt(builder, monkeypatch):
    rejected = builder.retain(1)
    valid = builder.retain(2)
    Path(rejected['receipt']).write_text(json.dumps({'digest': valid['digest']}), encoding='utf-8')
    monkeypatch.setattr(Path, 'glob', lambda root, pattern: iter([
        Path(rejected['receipt']), Path(valid['receipt']),
    ]))

    assert backend.verify_trusted_installed_apk(builder, valid['digest']) == valid
    assert [call.args[0] for call in builder.verify_historical.call_args_list] == [
        rejected['receipt'], valid['receipt'],
    ]


def test_real_builder_rejects_matching_digest_without_trusted_recipe(builder):
    target = builder.retain(1)
    real = HudBuilder(builder.work / 'unused-assets', builder.work, lambda *event: None)
    historical = Mock(wraps=real.verify_historical)
    real.verify_historical = historical

    # The digest and bytes agree, but these fields are not a valid build receipt.
    with pytest.raises(ValueError):
        backend.verify_trusted_installed_apk(real, target['digest'])
    historical.assert_called_once_with(target['receipt'])


def test_unreadable_receipt_is_skipped_without_verifier(builder, monkeypatch):
    target = builder.retain(1)

    def unreadable(path):
        raise PermissionError('private-receipt-path')

    monkeypatch.setattr(Path, 'read_bytes', unreadable)
    with pytest.raises(ValueError) as error:
        backend.verify_trusted_installed_apk(builder, target['digest'])
    assert 'private-receipt-path' not in str(error.value)
    builder.verify_historical.assert_not_called()


@pytest.mark.parametrize('raw', [
    b'{', b'\xff', b'[]', b'null', b'{}', b'{"digest":null}', b'{"digest":42}',
    b'{"digest":"short"}', b'{"digest":NaN}',
])
def test_malformed_scan_metadata_never_authorizes_or_invokes_verifier(builder, raw):
    target = builder.retain(1)
    Path(target['receipt']).write_bytes(raw)

    with pytest.raises(ValueError):
        backend.verify_trusted_installed_apk(builder, target['digest'])

    builder.verify_historical.assert_not_called()


@pytest.mark.parametrize('nested', [False, True])
def test_duplicate_json_keys_fail_closed_before_verifier(builder, nested):
    target = builder.retain(1)
    digest = json.dumps(target['digest'])
    suffix = ', "changes":{"key":1,"key":2}' if nested else f', "digest":{digest}'
    Path(target['receipt']).write_text('{"digest":' + digest + suffix + '}', encoding='utf-8')

    with pytest.raises(ValueError):
        backend.verify_trusted_installed_apk(builder, target['digest'])

    builder.verify_historical.assert_not_called()


@pytest.mark.parametrize('as_dict', [False, True])
def test_explicit_or_cached_receipt_is_reverified_even_with_scan_duplicate(builder, as_dict):
    target = builder.retain(1)
    reference = target if as_dict else Path(target['receipt'])

    assert backend.verify_trusted_installed_apk(builder, target['digest'], reference) == target
    builder.latest.assert_not_called()
    builder.verify_historical.assert_called_once_with(target['receipt'])

    Path(target['apk']).write_bytes(b'changed-after-cache')
    with pytest.raises(ValueError):
        backend.verify_trusted_installed_apk(builder, target['digest'], reference)
    assert builder.verify_historical.call_count == 2


def test_verifier_returned_digest_must_match_requested_digest(builder):
    target = builder.retain(1)
    other = builder.retain(2, b'other-apk')
    builder.verify_historical.side_effect = lambda reference: dict(other)

    with pytest.raises(ValueError):
        backend.verify_trusted_installed_apk(builder, target['digest'])

    builder.verify_historical.assert_called_once_with(target['receipt'])


@pytest.mark.parametrize('field,value', [
    ('source_digest', 'f' * 64), ('certificate_sha256', 'short'), ('digest', 'short'),
])
def test_matching_receipt_does_not_bypass_verified_metadata_contract(builder, field, value):
    target = builder.retain(1)
    builder.verify_historical.return_value = {**target, field: value}
    builder.verify_historical.side_effect = None

    with pytest.raises(ValueError):
        backend.verify_trusted_installed_apk(builder, target['digest'])


@pytest.mark.parametrize('digest', [None, 42, '', 'a' * 63, 'A' * 64, 'g' * 64])
def test_invalid_input_digest_fails_before_lookup(builder, digest):
    with pytest.raises(ValueError):
        backend.verify_trusted_installed_apk(builder, digest)
    builder.latest.assert_not_called()
    builder.verify_historical.assert_not_called()


def test_cancellation_before_lookup_is_propagated(builder):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(backend.HudCancelled):
        backend.verify_trusted_installed_apk(builder, 'a' * 64, cancel=cancel)
    builder.latest.assert_not_called()
    builder.verify_historical.assert_not_called()


@pytest.mark.parametrize('count', [1, 24])
def test_cancellation_during_unrelated_receipt_scan_is_propagated(builder, monkeypatch, count):
    for index in range(count):
        builder.retain(index, f'hud-{index}'.encode())
    cancel = threading.Event()
    original = Path.read_bytes
    reads = []

    def cancel_after_read(path):
        result = original(path)
        reads.append(path)
        cancel.set()
        return result

    monkeypatch.setattr(Path, 'read_bytes', cancel_after_read)
    with pytest.raises(backend.HudCancelled):
        backend.verify_trusted_installed_apk(builder, 'f' * 64, cancel=cancel)
    assert len(reads) == 1
    builder.verify_historical.assert_not_called()


def test_cancellation_during_matching_verifier_is_propagated(builder):
    target = builder.retain(1)
    cancel = threading.Event()

    def cancel_after_verify(reference):
        result = builder._verify(reference)
        cancel.set()
        return result

    builder.verify_historical.side_effect = cancel_after_verify
    with pytest.raises(backend.HudCancelled):
        backend.verify_trusted_installed_apk(builder, target['digest'], cancel=cancel)


@pytest.mark.parametrize('kind', ['symlink', 'reparse'])
@pytest.mark.parametrize('location', ['root', 'receipt', 'apk'])
def test_lookup_preserves_link_and_reparse_path_guards(builder, monkeypatch, kind, location):
    target = builder.retain(1)
    guarded = (builder.work / 'builds' if location == 'root'
               else Path(target['receipt' if location == 'receipt' else 'apk']))
    original = Path.lstat

    def unsafe_lstat(path, *args, **kwargs):
        if path == guarded:
            return SimpleNamespace(st_mode=stat.S_IFLNK if kind == 'symlink' else stat.S_IFREG,
                                   st_file_attributes=0x400 if kind == 'reparse' else 0)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'lstat', unsafe_lstat)
    with pytest.raises(ValueError):
        backend.verify_trusted_installed_apk(builder, target['digest'])
    if location != 'apk':
        builder.verify_historical.assert_not_called()


def test_explicit_foreign_receipt_is_rejected_by_builder_path_guard(builder, tmp_path):
    target = builder.retain(1)
    foreign = tmp_path / 'receipt.json'
    foreign.write_text(Path(target['receipt']).read_text(), encoding='utf-8')
    Path(target['receipt']).unlink()
    with pytest.raises(ValueError):
        backend.verify_trusted_installed_apk(builder, target['digest'], foreign)
    builder.verify_historical.assert_called_once_with(str(foreign))


@pytest.mark.parametrize('explicit', [False, True])
def test_builder_without_work_keeps_latest_and_verify_fallback(tmp_path, explicit):
    apk = tmp_path / 'hud.apk'
    apk.write_bytes(b'legacy-builder')
    target = {'apk': str(apk), 'receipt': 'opaque-reference',
              'digest': hashlib.sha256(apk.read_bytes()).hexdigest(),
              'source_digest': backend.SUPPORTED_APK, 'certificate_sha256': 'c' * 64}
    builder = SimpleNamespace(latest=Mock(return_value=target), verify=Mock(return_value=target))

    reference = 'opaque-reference' if explicit else None
    assert backend.verify_trusted_installed_apk(builder, target['digest'], reference) == target
    if explicit:
        builder.latest.assert_not_called()
    else:
        builder.latest.assert_called_once_with()
    builder.verify.assert_called_once_with('opaque-reference')


@pytest.mark.parametrize('failure', [OSError, ValueError, RuntimeError])
def test_latest_failure_without_managed_work_fails_closed(failure):
    builder = SimpleNamespace(latest=Mock(side_effect=failure('unavailable')), verify=Mock())
    with pytest.raises(ValueError):
        backend.verify_trusted_installed_apk(builder, 'f' * 64)
    builder.verify.assert_not_called()


def test_latest_failure_does_not_swallow_cancellation():
    cancel = threading.Event()

    def unavailable():
        cancel.set()
        raise RuntimeError('unavailable')

    builder = SimpleNamespace(latest=Mock(side_effect=unavailable), verify=Mock())
    with pytest.raises(backend.HudCancelled):
        backend.verify_trusted_installed_apk(builder, 'f' * 64, cancel=cancel)
    builder.verify.assert_not_called()
