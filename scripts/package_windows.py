"""Package the current public Windows release without rebuilding any input."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXE = 'RC2-TiengViet.exe'
PORTABLE = 'RC2-TiengViet-Portable.zip'
REPORT = 'release-verification.json'
SUMS = 'SHA256SUMS.txt'
STOCK_APK_SHA256 = 'cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e'
FLAGS = {'version': '0.7.0-local', 'hud_pipeline_bundled': True,
         'hud_menu_patch_one_click': True,
         'translation_version_independent': True, 'translation_device_tested': False,
         'hud_source_from_device': True, 'stock_recovery_template_bundled': True,
         'java_required_on_host': False, 'stock_fly_apk_embedded': False,
         'private_signing_key_embedded': False, 'github_published': False,
         'menu_functionality_verified': False, 'device_acceptance_complete': False}
DOCS = {'README.md': 'README.md', 'THIRD_PARTY_NOTICES.md': 'THIRD_PARTY_NOTICES.md',
        'CHANGELOG.md': 'CHANGELOG.md', 'docs/VIETNAMESE.md': 'docs/VIETNAMESE.md',
        'docs/ANDROID_PHONE.md': 'docs/ANDROID_PHONE.md',
        'docs/HUD_APK.md': 'docs/HUD_APK.md', 'docs/FREEFCC_LICENSE.txt': 'docs/FREEFCC_LICENSE.txt'}
PRIVATE = re.compile(r'private|backup|stock|input|signer|signing|credential|secret|password|cookie|token|camera|account', re.I)


def guard(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        try:
            value = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(value.st_mode) or getattr(value, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Release paths must not contain links or reparse points.')
    return path


def file_digest(path):
    path = guard(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('Release input must be a regular file.')
    with path.open('rb') as source:
        return stream_digest(source)


def stream_digest(source):
    digest = hashlib.sha256()
    for chunk in iter(lambda: source.read(1024 * 1024), b''):
        digest.update(chunk)
    return digest.hexdigest()


def public_artifacts(dist, outputs):
    candidates = {path.name: path for path in dist.iterdir() if path.is_file()}
    candidates.update({name: outputs / name for name in (REPORT, PORTABLE)})
    result = {}
    for name, path in sorted(candidates.items()):
        suffix = path.suffix.lower()
        if PRIVATE.search(name):
            continue
        if not (name == EXE or name == REPORT or suffix == '.apk'
                or (suffix == '.zip' and name.startswith('RC2-TiengViet-'))):
            continue
        digest = file_digest(path)
        if suffix == '.apk' and digest == STOCK_APK_SHA256:
            continue
        result[name] = digest
    return result


def read_checksums(path):
    result = {}
    for line in guard(path).read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9_. -]*)', line)
        if not match or match[2] in result:
            raise ValueError('Invalid, duplicate or escaping SHA256 checksum entry.')
        result[match[2]] = match[1]
    return result


def verify_package(root=ROOT, *, outputs=None):
    root = guard(root)
    dist = guard(root / 'dist')
    outputs = guard(outputs) if outputs is not None else dist
    exe = dist / EXE
    report_path = outputs / REPORT
    report = json.loads(guard(report_path).read_text(encoding='utf-8'))
    expected = {**FLAGS, 'exe_sha256': file_digest(exe), 'exe_bytes': exe.stat().st_size}
    if report != expected or any(type(report.get(key)) is not type(value) for key, value in expected.items()):
        raise ValueError('EXE report is stale or has invalid public flags.')
    with zipfile.ZipFile(guard(outputs / PORTABLE)) as archive:
        expected_names = {EXE, REPORT, *DOCS}
        if len(archive.namelist()) != len(expected_names) or set(archive.namelist()) != expected_names:
            raise ValueError('Portable ZIP must contain only the public release files.')
        with archive.open(EXE) as source:
            if (stream_digest(source) != expected['exe_sha256']
                    or archive.getinfo(EXE).file_size != expected['exe_bytes']):
                raise ValueError('Portable ZIP EXE is stale.')
        if archive.read(REPORT) != report_path.read_bytes():
            raise ValueError('Portable ZIP report does not match the loose report.')
        for name, relative in DOCS.items():
            with archive.open(name) as source:
                if stream_digest(source) != file_digest(root / relative):
                    raise ValueError('Portable ZIP documentation is stale.')
    if read_checksums(outputs / SUMS) != public_artifacts(dist, outputs):
        raise ValueError('Release SHA256 checksums are stale or include unsupported inputs.')
    return report


def package_windows(root=ROOT):
    root = guard(root)
    dist = guard(root / 'dist')
    exe = dist / EXE
    report = {**FLAGS, 'exe_sha256': file_digest(exe), 'exe_bytes': exe.stat().st_size}
    if report['exe_bytes'] == 0:
        raise ValueError('Release EXE is empty.')
    for relative in DOCS.values():
        file_digest(root / relative)
    # Remove only this invocation's unique staging directory, never dist inputs.
    with tempfile.TemporaryDirectory(prefix='.package-', dir=dist) as temporary:
        stage = guard(Path(temporary))
        (stage / REPORT).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        members = {EXE: exe, REPORT: stage / REPORT,
                   **{name: root / relative for name, relative in DOCS.items()}}
        with zipfile.ZipFile(stage / PORTABLE, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, path in members.items():
                archive.write(guard(path), arcname=name)
        records = public_artifacts(dist, stage)
        (stage / SUMS).write_text(''.join(f'{digest}  {name}\n' for name, digest in records.items()),
                                  encoding='utf-8')
        verify_package(root, outputs=stage)
        for name in (REPORT, PORTABLE, SUMS):
            guard(dist / name)
            (stage / name).replace(dist / name)
    return verify_package(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    report = verify_package(args.root) if args.verify else package_windows(args.root)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
