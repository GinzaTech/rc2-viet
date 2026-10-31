import hashlib
import json

import pytest

from rc2vi import translation_memory as module


def test_composition_does_not_require_any_memory_package(tmp_path):
    catalogs, overrides, fingerprint = module.load_memories(tmp_path)
    assert catalogs == [] and overrides == {}
    assert len(fingerprint) == 64


def test_explicit_no_memory_does_not_read_assets(tmp_path):
    (tmp_path / 'translation').mkdir()
    (tmp_path / 'translation/memories.json').write_text('invalid')
    assert module.load_memories(tmp_path, enabled=False)[:2] == ([], {})


def fixture(tmp_path, monkeypatch):
    root = tmp_path / 'translation'
    root.mkdir()
    source = root / 'reviewed.json'
    source.write_text(json.dumps({'Hello': 'Xin chào'}))
    metadata = {'schema': 1, 'files': {'reviewed.json': {'kind': 'text',
                 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}}}
    manifest = root / 'memories.json'
    manifest.write_text(json.dumps(metadata))
    monkeypatch.setattr(module, 'MEMORY_MANIFEST_SHA256', hashlib.sha256(manifest.read_bytes()).hexdigest())
    return source


def test_missing_optional_reviewed_file_falls_back_to_engine(tmp_path, monkeypatch):
    path = fixture(tmp_path, monkeypatch)
    before = module.load_memories(tmp_path)
    path.unlink()
    after = module.load_memories(tmp_path)
    assert before[1] == {'Hello': 'Xin chào'}
    assert after[1] == {} and before[2] != after[2]


def test_changed_reviewed_file_is_not_silently_trusted(tmp_path, monkeypatch):
    path = fixture(tmp_path, monkeypatch)
    path.write_text(json.dumps({'Hello': 'Wrong value'}))
    with pytest.raises(ValueError):
        module.load_memories(tmp_path)


def test_reviewed_fragment_terms_preserve_edges_and_defer_new_text():
    calls = []
    def engine(texts):
        calls.append(texts)
        return ['Câu mới'] * len(texts)
    translate = module.with_reviewed_fragments(engine, {'Waypoint': 'Điểm bay'})
    assert translate(['Waypoint', '. Waypoint ', 'New sentence']) == ['Điểm bay', '. Điểm bay ', 'Câu mới']
    assert calls == [['New sentence']]


@pytest.mark.parametrize('value', ['- - m', '- - ft', '- - km/h', '- - m/s'])
def test_disconnected_telemetry_quantity_is_preserved(value):
    import xml.etree.ElementTree as ET
    from rc2vi.translation_complete import _technical
    element = ET.Element('string', name='unknown_measurement')
    element.text = value
    assert _technical(element)
