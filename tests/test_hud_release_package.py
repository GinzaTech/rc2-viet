"""Release artifact checks plus packaging fixtures that need no built EXE."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from scripts import package_windows as backend


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def release(tmp_path):
    root = tmp_path / 'release project with spaces'
    dist = root / 'dist'
    dist.mkdir(parents=True)
    (root / 'README.md').write_text('Synthetic release instructions.', encoding='utf-8')
    (root / 'THIRD_PARTY_NOTICES.md').write_text('Synthetic public notices.', encoding='utf-8')
    (root / 'docs').mkdir()
    (root / 'docs/HUD_APK.md').write_text('Synthetic public HUD instructions.', encoding='utf-8')
    (root / 'docs/FREEFCC_LICENSE.txt').write_text('Synthetic AGPL notice.', encoding='utf-8')
    (dist / 'RC2-TiengViet.exe').write_bytes(b'MZ-current-synthetic-exe')
    (dist / 'freefcc.apk').write_bytes(b'synthetic-public-apk')
    with zipfile.ZipFile(dist / 'RC2-TiengViet-Source-v0.2.0.zip', 'w') as archive:
        archive.writestr('README.md', b'synthetic-old-source-readme')
    return root


def test_portable_exe_and_checksum_match_final_loose_exe():
    root = Path(__file__).resolve().parents[1]
    if not (root / 'dist/RC2-TiengViet-Portable.zip').is_file():
        pytest.skip('Portable ZIP is an ignored build artifact; run build.ps1 to create it.')
    backend.verify_package(root)


def test_fresh_clone_artifact_check_skips_without_portable_zip(release, monkeypatch):
    monkeypatch.setitem(globals(), '__file__', str(release / 'tests/test_hud_release_package.py'))
    with pytest.raises(pytest.skip.Exception, match='ignored build artifact'):
        test_portable_exe_and_checksum_match_final_loose_exe()


def test_package_uses_current_exe_and_replaces_stale_zip_report_and_checksums(release):
    dist = release / 'dist'
    with zipfile.ZipFile(dist / 'RC2-TiengViet-Portable.zip', 'w') as archive:
        archive.writestr('RC2-TiengViet.exe', b'MZ-stale-synthetic-exe')
    (dist / 'release-verification.json').write_text('{"exe_sha256":"stale"}', encoding='utf-8')
    (dist / 'SHA256SUMS.txt').write_text('stale old.exe\n', encoding='utf-8')
    report = backend.package_windows(release)
    assert report == backend.verify_package(release)
    assert report['version'] == '0.6.3-local'
    assert report['exe_sha256'] == digest(dist / 'RC2-TiengViet.exe')
    assert report['exe_bytes'] == (dist / 'RC2-TiengViet.exe').stat().st_size
    assert report['hud_pipeline_bundled'] is True
    assert report['java_required_on_host'] is False
    assert report['stock_fly_apk_embedded'] is False
    assert report['private_signing_key_embedded'] is False
    assert report['github_published'] is False
    with zipfile.ZipFile(dist / 'RC2-TiengViet-Portable.zip') as archive:
        assert set(archive.namelist()) == {'RC2-TiengViet.exe', 'README.md',
                                          'THIRD_PARTY_NOTICES.md', 'docs/HUD_APK.md', 'docs/FREEFCC_LICENSE.txt', 'release-verification.json'}
        assert archive.read('docs/FREEFCC_LICENSE.txt') == (release / 'docs/FREEFCC_LICENSE.txt').read_bytes()
        assert archive.read('docs/HUD_APK.md') == (release / 'docs/HUD_APK.md').read_bytes()
        assert archive.read('RC2-TiengViet.exe') == (dist / 'RC2-TiengViet.exe').read_bytes()
        assert archive.read('release-verification.json') == (dist / 'release-verification.json').read_bytes()
    records = backend.read_checksums(dist / 'SHA256SUMS.txt')
    assert set(records) == {'RC2-TiengViet.exe', 'RC2-TiengViet-Portable.zip',
                            'RC2-TiengViet-Source-v0.2.0.zip', 'freefcc.apk',
                            'release-verification.json'}
    assert all(records[name] == digest(dist / name) for name in records)


def test_verifier_rejects_exe_changed_after_packaging_then_packager_repairs_it(release):
    backend.package_windows(release)
    exe = release / 'dist/RC2-TiengViet.exe'
    exe.write_bytes(b'MZ-next-synthetic-exe')
    with pytest.raises(ValueError, match='stale|EXE|exe'):
        backend.verify_package(release)
    backend.package_windows(release)
    assert backend.verify_package(release)['exe_sha256'] == digest(exe)


def test_verifier_rejects_stale_exe_inside_zip_even_if_zip_checksum_is_updated(release):
    backend.package_windows(release)
    dist = release / 'dist'
    portable = dist / 'RC2-TiengViet-Portable.zip'
    with zipfile.ZipFile(portable) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    contents['RC2-TiengViet.exe'] = b'MZ-stale-exe-with-forged-zip-checksum'
    with zipfile.ZipFile(portable, 'w') as archive:
        for name, content in contents.items():
            archive.writestr(name, content)
    records = backend.read_checksums(dist / 'SHA256SUMS.txt')
    records[portable.name] = digest(portable)
    (dist / 'SHA256SUMS.txt').write_text(
        ''.join(f'{value}  {name}\n' for name, value in sorted(records.items())), encoding='utf-8')
    with pytest.raises(ValueError, match='stale|EXE|exe'):
        backend.verify_package(release)


def test_packaging_excludes_private_backups_stock_and_nested_files(release, monkeypatch):
    dist = release / 'dist'
    for name in ('signer.json', 'private-signing.p12', 'device-backup.zip',
                 'camera-backup.zip', 'stock.apk', 'input-stock.apk', 'credentials.json'):
        (dist / name).write_bytes(b'synthetic-private-fixture')
    nested = dist / 'device-backups'
    nested.mkdir()
    (nested / 'private.zip').write_bytes(b'synthetic-backup')
    renamed_stock = dist / 'apparently-public.apk'
    renamed_stock.write_bytes(b'synthetic-pinned-stock')
    monkeypatch.setattr(backend, 'STOCK_APK_SHA256', digest(renamed_stock))
    backend.package_windows(release)
    records = backend.read_checksums(dist / 'SHA256SUMS.txt')
    assert set(records) == {'RC2-TiengViet.exe', 'RC2-TiengViet-Portable.zip',
                            'RC2-TiengViet-Source-v0.2.0.zip', 'freefcc.apk',
                            'release-verification.json'}
    with zipfile.ZipFile(dist / 'RC2-TiengViet-Portable.zip') as archive:
        assert len(archive.namelist()) == 6
    assert (nested / 'private.zip').is_file()


@pytest.mark.parametrize('missing', ['dist/RC2-TiengViet.exe', 'README.md', 'THIRD_PARTY_NOTICES.md',
                                    'docs/HUD_APK.md'])
def test_missing_required_input_does_not_replace_existing_release(release, missing):
    backend.package_windows(release)
    portable = release / 'dist/RC2-TiengViet-Portable.zip'
    before = digest(portable)
    (release / missing).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        backend.package_windows(release)
    assert digest(portable) == before


def test_failed_staged_verification_keeps_old_outputs(release, monkeypatch):
    backend.package_windows(release)
    names = ['RC2-TiengViet-Portable.zip', 'release-verification.json', 'SHA256SUMS.txt']
    before = {name: digest(release / 'dist' / name) for name in names}
    original = backend.verify_package
    def reject(*args, **kwargs):
        raise ValueError('Synthetic staged verification failure')
    monkeypatch.setattr(backend, 'verify_package', reject)
    with pytest.raises(ValueError, match='staged'):
        backend.package_windows(release)
    assert before == {name: digest(release / 'dist' / name) for name in names}
    assert original(release)['version'] == '0.6.3-local'
    assert not list((release / 'dist').glob('.package-*'))


def test_checksums_reject_duplicate_or_escaping_entries(tmp_path):
    path = tmp_path / 'SHA256SUMS.txt'
    for content in ('a' * 64 + '  ../private.apk\n',
                    ('a' * 64 + '  same.exe\n') * 2, 'not-a-digest  public.apk\n'):
        path.write_text(content, encoding='utf-8')
        with pytest.raises(ValueError):
            backend.read_checksums(path)


def test_verifier_rejects_report_zip_mismatch_with_updated_checksum(release):
    backend.package_windows(release)
    dist = release / 'dist'
    path = dist / 'release-verification.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    path.write_text(json.dumps(value, separators=(',', ':')), encoding='utf-8')
    records = backend.read_checksums(dist / 'SHA256SUMS.txt')
    records[path.name] = digest(path)
    (dist / 'SHA256SUMS.txt').write_text(
        ''.join(f'{value}  {name}\n' for name, value in sorted(records.items())), encoding='utf-8')
    with pytest.raises(ValueError, match='report'):
        backend.verify_package(release)


def test_verifier_rejects_stale_checksum_for_public_apk(release):
    backend.package_windows(release)
    (release / 'dist/freefcc.apk').write_bytes(b'updated-public-apk')
    with pytest.raises(ValueError, match='checksum|SHA256'):
        backend.verify_package(release)


def test_packaging_cli_runs_without_java_or_external_dependencies(release):
    script = Path(__file__).resolve().parents[1] / 'scripts/package_windows.py'
    result = subprocess.run([sys.executable, '-I', str(script), '--root', str(release)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['exe_sha256'] == digest(release / 'dist/RC2-TiengViet.exe')
    assert backend.verify_package(release)['version'] == '0.6.3-local'
