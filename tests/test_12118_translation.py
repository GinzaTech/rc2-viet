"""Exercise the 1.21.18 reuse guards with real binary-XML/resource parsers."""
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from rc2vi.fly_versions import FLY_12118
from rc2vi.resource_embed import Table
from scripts import build_12118_translation as port
from scripts.hud_manifest import ANDROID
from test_resource_embed import pool, table


ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def manifest(package='dji.go.v5', version='1.21.18', code=3132442):
    strings = ['manifest', 'application', 'package', 'versionName', 'versionCode',
               ANDROID, package, version]

    def start(name, attributes=()):
        values = b''.join(struct.pack('<IIIHBBI', ns, key, raw, 8, 0, kind, value)
                          for ns, key, raw, kind, value in attributes)
        return (struct.pack('<HHIii', 0x102, 16, 36 + len(values), 1, -1)
                + struct.pack('<ii6H', -1, name, 20, 20, len(attributes), 0, 0, 0) + values)

    def end(name):
        return struct.pack('<HHIiiii', 0x103, 16, 24, 1, -1, -1, name)

    attributes = [(0xffffffff, 2, 6, 3, 6), (5, 3, 7, 3, 7),
                  (5, 4, 0xffffffff, 16, code)]
    body = pool(strings).build() + start(0, attributes) + start(1) + end(1) + end(0)
    return struct.pack('<HHI', 3, 8, len(body) + 8) + body


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    def create(count=11994):
        names = [f'message_{i}' for i in range(count)]
        entries = [(i, 0) for i in range(count)]
        original = table('string', names, ['Ready'], [(b'', entries), (b'en', entries)])
        translated = table('string', names, ['Sẵn sàng'], [(b'', entries)])
        baseline = tmp_path / 'assets/auto12116'
        baseline.mkdir(parents=True, exist_ok=True)
        (baseline / 'vietnamese.arsc').write_bytes(translated)
        (baseline / 'manifest.json').write_text(json.dumps({
            'semantic_review': {'reviewed_resources': count, 'runtime_visual_validation': False},
            'embedded_resources': count, 'resource_sha256': sha(translated),
            'signed': False, 'installed': False,
        }), encoding='utf-8')
        source = tmp_path / 'stock.apk'

        def write_source(xml=None, resources=None):
            with ZipFile(source, 'w') as archive:
                archive.writestr('AndroidManifest.xml', manifest() if xml is None else xml)
                archive.writestr('resources.arsc', original if resources is None else resources)
            monkeypatch.setattr(port, 'SOURCE_SHA256', sha(source.read_bytes()))

        write_source()
        monkeypatch.setattr(port, 'ROOT', tmp_path)
        monkeypatch.setattr(port, 'RESOURCES_SHA256', sha(original))
        monkeypatch.setattr(port, 'TRANSLATION_SHA256', sha(translated))
        return SimpleNamespace(source=source, baseline=baseline, original=original,
                               translated=translated, write_source=write_source)
    return create


def test_real_profile_and_assets_are_bound_to_the_reviewed_resource_table():
    metadata = json.loads((ROOT / 'assets/auto12118/manifest.json').read_text('utf-8'))
    translated = (ROOT / 'assets/auto12118/vietnamese.arsc').read_bytes()
    assert (metadata['version'], metadata['version_code']) == (FLY_12118.version, FLY_12118.code)
    assert metadata['source_sha256'] == port.SOURCE_SHA256 == FLY_12118.source_sha256
    assert metadata['resource_sha256'] == sha(translated) == port.TRANSLATION_SHA256 == FLY_12118.translation_sha256
    assert translated == (ROOT / 'assets/auto12116/vietnamese.arsc').read_bytes()
    assert len({key for key, _, _ in Table(translated).entries()}) == metadata['embedded_resources'] == 11994
    assert metadata['resource_reuse'] == {
        'baseline_version': '1.21.16', 'source_resources_sha256': port.RESOURCES_SHA256,
        'byte_identical_to_reviewed_stock': True,
        'resource_ids_and_configurations_identical': True, 'host_code_reused': False,
    }
    assert metadata['installed'] is False and metadata['signed'] is False


def test_build_validates_all_11994_binary_resources_and_preserves_review_provenance(inputs, tmp_path):
    current = inputs()
    destination = tmp_path / 'output'
    report = port.build(current.source, destination)
    assert (destination / 'vietnamese.arsc').read_bytes() == current.translated
    assert {p.name for p in destination.iterdir()} == {'manifest.json', 'vietnamese.arsc'}
    metadata = json.loads((destination / 'manifest.json').read_text('utf-8'))
    assert (metadata['version'], metadata['version_code']) == ('1.21.18', 3132442)
    assert metadata['semantic_review'] == {'reviewed_resources': 11994, 'runtime_visual_validation': False}
    assert report['embedded_resources'] == 11994 and report['resource_reuse_proved']
    assert report['device_tested'] is False and metadata['installed'] is False


def test_different_apk_with_the_same_version_is_rejected_before_writing(inputs, tmp_path):
    current = inputs()
    current.source.write_bytes(current.source.read_bytes() + b'changed')
    destination = tmp_path / 'output'
    with pytest.raises(ValueError, match='exact DJI Fly RC'):
        port.build(current.source, destination)
    assert not destination.exists()


@pytest.mark.parametrize('identity', [
    {'package': 'dji.go.phone'}, {'version': '1.21.16'}, {'code': 3132441},
])
def test_identity_is_checked_independently_of_the_source_hash(inputs, tmp_path, identity):
    current = inputs()
    current.write_source(xml=manifest(**identity))
    destination = tmp_path / 'output'
    with pytest.raises(ValueError, match='RC APK identity'):
        port.build(current.source, destination)
    assert not destination.exists()


def test_changed_source_resources_cannot_reuse_the_reviewed_translation(inputs, tmp_path):
    current = inputs()
    current.write_source(resources=current.original + b'changed')
    destination = tmp_path / 'output'
    with pytest.raises(ValueError, match='source resource table differs'):
        port.build(current.source, destination)
    assert not destination.exists()


def test_changed_baseline_translation_is_rejected_before_writing(inputs, tmp_path):
    current = inputs()
    (current.baseline / 'vietnamese.arsc').write_bytes(current.translated + b'changed')
    destination = tmp_path / 'output'
    with pytest.raises(ValueError, match='Vietnamese table differs'):
        port.build(current.source, destination)
    assert not destination.exists()


def test_smaller_valid_resource_tables_cannot_claim_full_coverage(inputs, tmp_path):
    current = inputs(count=1)
    destination = tmp_path / 'output'
    with pytest.raises(ValueError, match='resource count'):
        port.build(current.source, destination)
    assert not destination.exists()
