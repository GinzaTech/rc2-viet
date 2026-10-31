"""Reuse the reviewed translation only for byte-identical RC resource tables.

Fly 1.21.18 changes host code, so its menu recipe is built separately. Its
resources.arsc matches the verified 1.21.16 stock exactly; this command proves
that fact before carrying over the reviewed Vietnamese table.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rc2vi.hud_tools import sha256_file
from scripts.hud_manifest import inspect_application
from rc2vi.resource_embed import embed

SOURCE_SHA256 = '9c6b068a43187a2700fb9fc31734ea6107a07ff222dc28482969b0ddb99ca0fe'
RESOURCES_SHA256 = 'fc44abaa822ca846082d7ef9e505d88e038360959fa1f141f8d8b91d53ac599b'
TRANSLATION_SHA256 = '7ae58691f03056aeab336edde3c0e29e383b7eab88592f82f29b6d84beb9b3d9'


def build(source, output):
    source, output = Path(source), Path(output)
    if sha256_file(source) != SOURCE_SHA256:
        raise ValueError('Expected the exact DJI Fly RC 1.21.18 stock APK')
    with ZipFile(source) as archive:
        identity = inspect_application(archive.read('AndroidManifest.xml'))
        resources = archive.read('resources.arsc')
    if (identity['package'] != 'dji.go.v5' or identity['version'] != '1.21.18'
            or identity['code'] != 3132442):
        raise ValueError('Unexpected RC APK identity')
    if hashlib.sha256(resources).hexdigest() != RESOURCES_SHA256:
        raise ValueError('The reviewed source resource table differs')
    baseline = ROOT / 'assets/auto12116'
    translated = baseline / 'vietnamese.arsc'
    if sha256_file(translated) != TRANSLATION_SHA256:
        raise ValueError('The reviewed Vietnamese table differs')
    _, report = embed(resources, translated.read_bytes())
    if report['embedded_resources'] != 11994:
        raise ValueError('Unexpected embedded resource count')
    manifest = json.loads((baseline / 'manifest.json').read_text('utf-8'))
    manifest.update(source_sha256=SOURCE_SHA256, version='1.21.18', version_code=3132442,
                    translation_revision='r14.6.1-12118-reviewed-port-1',
                    resource_reuse={
                        'baseline_version': '1.21.16',
                        'source_resources_sha256': RESOURCES_SHA256,
                        'byte_identical_to_reviewed_stock': True,
                        'resource_ids_and_configurations_identical': True,
                        'host_code_reused': False,
                    })
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(translated, output / 'vietnamese.arsc')
    (output / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    return {'source_sha256': SOURCE_SHA256, 'resource_sha256': RESOURCES_SHA256,
            'translation_sha256': TRANSLATION_SHA256, 'embedded_resources': 11994,
            'resource_reuse_proved': True, 'device_tested': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'assets/auto12118')
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output)))


if __name__ == '__main__':
    main()
