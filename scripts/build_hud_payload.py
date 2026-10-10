"""Compile the framework-only HUD helper; update only the DEX/payload hash, not the toolchain or keys."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from package_windows import guard

ROOT = Path(__file__).resolve().parents[1]


def run(arguments):
    result = subprocess.run(list(map(str, arguments)), capture_output=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[:3000])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java-home', required=True, type=Path)
    parser.add_argument('--sdk', required=True, type=Path)
    args = parser.parse_args()
    java = guard(args.java_home / 'bin/java.exe')
    compiler = guard(args.java_home / 'bin/javac.exe')
    android = guard(args.sdk / 'platforms/android-30/android.jar')
    r8 = guard(args.sdk / 'build-tools/36.1.0/lib/d8.jar')
    if not r8.is_file():
        r8 = guard(args.sdk / 'build-tools/36.1.0/lib/r8.jar')
    sources = sorted((ROOT / 'android-hud/src').rglob('*.java'))
    if not sources:
        raise ValueError('No HUD source files.')
    for path in [java, compiler, android, r8, *sources]:
        if not guard(path).is_file():
            raise ValueError('Missing HUD build input: ' + str(path))
    builds = guard(ROOT / 'build')
    builds.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hud-payload-', dir=builds) as temporary:
        stage = guard(temporary)
        if stage.parent != builds:
            raise ValueError('HUD staging must stay inside build directory.')
        classes = stage / 'classes'; classes.mkdir()
        dex = stage / 'dex'; dex.mkdir()
        run([compiler, '-source', '8', '-target', '8', '-encoding', 'UTF-8',
             '-cp', android, '-d', classes, *sources])
        run([java, '-cp', r8, 'com.android.tools.r8.D8', '--min-api', '30',
             '--lib', android, '--output', dex, *sorted(classes.rglob('*.class'))])
        if {path.name for path in dex.iterdir()} != {'classes.dex'}:
            raise ValueError('Unexpected HUD DEX output.')
        output = dex / 'classes.dex'
        content = output.read_bytes()
        if not content.startswith(b'dex\n'):
            raise ValueError('Invalid HUD DEX output.')
        hud = guard(ROOT / 'assets/hud')
        retained = guard(ROOT / 'android-hud/dex'); retained.mkdir(exist_ok=True)
        owner = guard(hud / 'restore-owner')
        payload = {'schema': 1, 'sha256': hashlib.sha256(content).hexdigest(),
                   'restore_owner_sha256': hashlib.sha256(owner.read_bytes()).hexdigest()}
        for target in (hud / 'classes23.dex', retained / 'classes.dex'):
            guard(target); shutil.copyfile(output, target)
        metadata = guard(hud / 'payload.json')
        metadata.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'dex_bytes': len(content), 'source_files': len(sources), **payload}))


if __name__ == '__main__':
    main()
