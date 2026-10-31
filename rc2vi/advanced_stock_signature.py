"""Cryptographic V2 verification for the caller's exact pinned original stock.

Modified APKs keep HudTool's V3-only verification. This path never trusts a
certificate extracted without verifying the APK at Android SDK30.
"""
from pathlib import Path
import re

from .hud_backup import guard_path
from .hud_tools import HudCancelled, check_cancel, run_process, sha256_file, _tool_environment


def _pin(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('Invalid original-stock signature pin')
    return value


def _certificate(output, expected):
    if not isinstance(output, str) or len(output) > 65536 or '\0' in output:
        raise ValueError('Invalid stock signature output')
    lines = output.splitlines()
    v2 = 'Verified using v2 scheme (APK Signature Scheme v2): true'
    signers = [line for line in lines if line.startswith('Number of signers:')]
    certificates = [line for line in lines if re.match(r'Signer #[0-9]+ certificate SHA-256 digest:', line)]
    if (lines.count('Verifies') != 1 or 'DOES NOT VERIFY' in lines or lines.count(v2) != 1
            or signers != ['Number of signers: 1'] or len(certificates) != 1):
        raise ValueError('Original stock requires one verified V2 signer')
    match = re.fullmatch(r'Signer #1 certificate SHA-256 digest: ([0-9a-fA-F]{64})', certificates[0])
    if match is None or match[1].lower() != expected:
        raise ValueError('Original stock certificate differs from pinned DJI certificate')
    return match[1].lower()


def verify_stock_apk(tools, apk, *, source_digest, certificate_digest):
    """Return the pinned stock signer after native SDK30 V2 and before/after hash checks."""
    source_digest, certificate_digest = _pin(source_digest), _pin(certificate_digest)
    apk = guard_path(Path(apk))
    cancel = tools.cancel
    check_cancel(cancel)
    if not apk.is_file() or sha256_file(apk, cancel) != source_digest:
        raise ValueError('Original stock changed before V2 signature verification')
    root = tools.prepare()
    try:
        output = run_process([
            str(root / 'java/bin/java.exe'), '-jar', str(root / 'lib/apksigner.jar'),
            'verify', '--verbose', '--print-certs', '--min-sdk-version', '30',
            '--max-sdk-version', '30', str(apk),
        ], cancel=cancel, env=_tool_environment())
    except HudCancelled:
        raise
    except RuntimeError:
        raise ValueError('Không kiểm chứng được chữ ký V2 của APK DJI gốc. '
                         'Kiểm tra Java/công cụ APK trên PC. [STOCK_V2_VERIFY]') from None
    certificate = _certificate(output, certificate_digest)
    check_cancel(cancel)
    if sha256_file(guard_path(apk), cancel) != source_digest:
        raise ValueError('Original stock changed during V2 signature verification')
    return certificate
