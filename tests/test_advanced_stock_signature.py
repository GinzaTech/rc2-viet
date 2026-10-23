"""Signature scheme contracts: original stock V2 is a separate exact-pin path."""
import hashlib
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

CERTIFICATE = '01a42c94aa87020f41e8c252598df98b86a0acf6c05ff61c75f18fa29cad1dd4'
OUTPUT = ('Verifies\nVerified using v2 scheme (APK Signature Scheme v2): true\n'
          'Verified using v3 scheme (APK Signature Scheme v3): false\n'
          'Number of signers: 1\nSigner #1 certificate SHA-256 digest: ' + CERTIFICATE + '\n')


@pytest.fixture
def case(tmp_path, monkeypatch):
    api = importlib.import_module('rc2vi.advanced_stock_signature')
    apk = tmp_path / 'stock with spaces.apk'
    apk.write_bytes(b'fixture-only-stock')
    pinned = hashlib.sha256(apk.read_bytes()).hexdigest()
    tools = SimpleNamespace(prepare=Mock(return_value=tmp_path / 'runtime'), cancel=None)
    runner = Mock(return_value=OUTPUT)
    monkeypatch.setattr(api, 'run_process', runner)
    return api, apk, pinned, tools, runner


def verify(case):
    api, apk, pinned, tools, _ = case
    return api.verify_stock_apk(tools, apk, source_digest=pinned, certificate_digest=CERTIFICATE)


def test_stock_v2_is_cryptographically_checked_at_sdk30(case):
    api, apk, _, tools, runner = case
    assert verify(case) == CERTIFICATE
    command = list(map(str, runner.call_args.args[0]))
    assert command == [str(tools.prepare.return_value / 'java/bin/java.exe'), '-jar',
                       str(tools.prepare.return_value / 'lib/apksigner.jar'), 'verify', '--verbose',
                       '--print-certs', '--min-sdk-version', '30', '--max-sdk-version', '30', str(apk)]
    assert runner.call_args.kwargs['env'] is not None
    assert runner.call_args.kwargs['cancel'] is None


@pytest.mark.parametrize('output', ['', 'DOES NOT VERIFY\n' + OUTPUT,
    OUTPUT.replace('Verifies\n', ''), OUTPUT.replace('v2): true', 'v2): false'),
    OUTPUT.replace('signers: 1', 'signers: 2'), OUTPUT.replace(CERTIFICATE, 'f' * 64),
    OUTPUT + 'Signer #2 certificate SHA-256 digest: ' + CERTIFICATE + '\n',
    OUTPUT + 'Number of signers: 1\n', OUTPUT + 'Verifies\n', 'x' * 65537],
    ids=['empty','not-verified','missing-header','not-v2','two-signers','wrong-certificate',
         'extra-certificate','duplicate-signer-count','duplicate-header','oversized'])
def test_invalid_or_ambiguous_signature_output_is_rejected(case, output):
    *_, runner = case
    runner.return_value = output
    with pytest.raises(ValueError):
        verify(case)


def test_changed_stock_is_rejected_before_tools_run(case):
    _, apk, _, tools, runner = case
    apk.write_bytes(b'tampered')
    with pytest.raises(ValueError):
        verify(case)
    tools.prepare.assert_not_called()
    runner.assert_not_called()


def test_change_during_native_verification_is_rejected(case):
    _, apk, _, _, runner = case
    def change(*args, **kwargs):
        apk.write_bytes(b'tampered-during-verification')
        return OUTPUT
    runner.side_effect = change
    with pytest.raises(ValueError):
        verify(case)


def test_native_failure_has_stock_context_without_raw_exception(case):
    *_, runner = case
    runner.side_effect = RuntimeError('fixture-secret-must-not-be-reported')
    with pytest.raises(ValueError, match='STOCK_V2_VERIFY') as failure:
        verify(case)
    assert 'fixture-secret' not in str(failure.value)
    assert failure.value.__suppress_context__


def test_cancellation_is_preserved(case):
    api, *_, runner = case
    runner.side_effect = api.HudCancelled('cancelled')
    with pytest.raises(api.HudCancelled):
        verify(case)
