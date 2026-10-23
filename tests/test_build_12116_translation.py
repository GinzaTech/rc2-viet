"""Offline regressions for exact-source translation and compiled resource IDs."""
import copy
import json
import struct
import xml.etree.ElementTree as ET

import pytest

from scripts import build_12116_translation as build
from rc2vi import translation_catalog as catalog
from rc2vi.resource_embed import Table, chunks, embed
from rc2vi.translation_complete import IncompleteTranslation
from test_resource_embed import table


def element(name, text):
    item = ET.Element('string', {'name': name})
    item.text = text
    return item


def memory(source, translated):
    return {'schema': 1, 'entries': [{'kind': source.tag, 'name': source.get('name'),
        'source': catalog._canonical(source),
        'translation_xml': ET.tostring(translated, encoding='unicode')}]}


def test_shared_english_from_another_name_never_reuses_translation(tmp_path):
    source = element('new_context', 'Hello')
    other = memory(element('old_context', 'Hello'), element('old_context', 'Xin chào'))
    calls = []
    def unavailable(texts):
        calls.extend(texts)
        return ['' for _ in texts]
    with pytest.raises(IncompleteTranslation) as error:
        build.compose_exact({('string', 'new_context'): source}, [other], unavailable, {}, {}, tmp_path)
    assert calls
    assert error.value.report['reviewed'] == 0
    assert error.value.report['cross_name_memory_reuse'] is False


def test_changed_english_cannot_reuse_old_name_memory(tmp_path):
    old = element('warning', 'Fly higher')
    current = element('warning', 'Fly lower')
    prior = memory(old, element('warning', 'Bay cao hơn'))
    output, report = build.compose_exact({('string', 'warning'): current}, [prior],
        lambda texts: [text.replace('Fly lower', 'Bay thấp hơn') for text in texts], {}, {}, tmp_path)
    assert catalog._content(output[0])[0] == 'Bay thấp hơn'
    assert report['reviewed'] == 0 and report['machine'] == 1


def test_manual_exact_context_has_priority_over_prior_memory(tmp_path):
    source = element('warning', 'Ready')
    reviewed = memory(source, element('warning', 'Sẵn sàng'))
    old = memory(source, element('warning', 'Đã xong'))
    def no_engine(_):
        pytest.fail('An exact reviewed source must not invoke a translator')
    output, report = build.compose_exact({('string', 'warning'): source}, [reviewed, old],
        no_engine, {}, {}, tmp_path)
    assert catalog._content(output[0])[0] == 'Sẵn sàng'
    assert report['exact_selection_provenance'] == {'manual_12116': 1}


def test_manual_raw_compiled_nbsp_contract_survives_xml_whitespace_normalization(tmp_path):
    name = 'copyright_title'
    raw = 'Copyright ©\u00a02026\u00a0DJI Inc.'
    source = element(name, 'Copyright © 2026 DJI Inc.')
    path = tmp_path / 'reviewed.json'
    path.write_text(json.dumps({'source_sha256': build.SOURCE_SHA256, 'entries': [
        {'name': name, 'english': raw, 'vietnamese': 'Bản quyền © 2026 DJI Inc.'}]}), encoding='utf-8')
    selected, errors = build.reviewed_catalog(path, {('string', name): source},
        {('string', name): [[None, 3, {'text': raw, 'spans': []}]]})
    assert not errors and len(selected['entries']) == 1
    _, errors = build.reviewed_catalog(path, {('string', name): source},
        {('string', name): [[None, 3, {'text': raw.replace('2026', '2027'), 'spans': []}]]})
    assert errors[0]['reason'] == 'English text/style contract mismatch'


def test_technical_spoken_command_guards_reject_changed_source():
    targets = {('string', name): element(name, english)
               for name, english in build.PRESERVED_TECHNICAL.items()}
    values = {key: [[None, 3, {'text': item.text, 'spans': []}]] for key, item in targets.items()}
    build.preserve_technical(targets, values)
    assert all(item.get('translatable') == 'false' for item in targets.values())
    changed = copy.deepcopy(values)
    changed['string', 'wifi_fpv_aircraft_voice_ctrl_guide_command'][0][2]['text'] = 'Different command'
    with pytest.raises(ValueError, match='voice command source changed'):
        build.preserve_technical(targets, changed)


def test_resource_id_reader_uses_sparse_entry_index_and_type_id_offset():
    raw = table('string', ['target'], ['Hello'], [(b'', [None, None, None, (0, 0)])])
    parsed = Table(raw)
    _, ph, package_start, package_stop = next(c for c in parsed.top if c[0] == 0x200)
    package = bytearray(parsed.data[package_start:package_stop])
    _, h, start, stop = next(c for c in chunks(package, ph, len(package)) if c[0] == 0x201)
    header = bytearray(package[start:start + h])
    payload = package[start + struct.unpack_from('<I', header, 16)[0]:stop]
    header[9] = 1
    struct.pack_into('<I', header, 4, h + 4 + len(payload))
    struct.pack_into('<II', header, 12, 1, h + 4)
    sparse = header + struct.pack('<HH', 3, 0) + payload
    package[start:stop] = sparse
    struct.pack_into('<I', package, 4, len(package))
    struct.pack_into('<I', package, 284, 5)
    rebuilt = bytearray(raw[:package_start] + package + raw[package_stop:])
    struct.pack_into('<I', rebuilt, 4, len(rebuilt))
    info, identifiers, _ = build.resource_ids(Table(rebuilt))
    assert info['type_id_offset'] == 5
    assert identifiers == {('string', 'target'): 0x7f060003}


def test_reference_contract_compares_names_after_id_renumbering():
    raw = table('string', ['target', 'reference'], ['Text'], [(b'', [(0, 0), (1, 0)])])
    parsed = Table(raw)
    for key, _, positions in parsed.entries():
        if key[1] == 'reference':
            position = positions[None]
            parsed.data[position + 3] = 1
            struct.pack_into('<I', parsed.data, position + 4, 0x7f010000)
            old = build.semantic_values(parsed, positions, {0x7f010000: ('string', 'target')})
            struct.pack_into('<I', parsed.data, position + 4, 0x7f018765)
            new = build.semantic_values(parsed, positions, {0x7f018765: ('string', 'target')})
            assert old == new
            return
    pytest.fail('Fixture must contain a reference resource')


def test_only_integer_lookup_arrays_may_be_excluded_from_text_xml():
    values = {('array', 'indices'): [[0x01000000, 16, {'value': 14}],
                                   [0x01000001, 16, {'value': 15}]]}
    result = build.excluded_integer_arrays({}, values)
    assert result[0]['decoded_kind'] == 'integer-array' and result[0]['items'] == 2
    values['array', 'untranslated_labels'] = [[0x01000000, 3, {'text': 'Hello', 'spans': []}]]
    with pytest.raises(ValueError, match='omitted by XML composition'):
        build.excluded_integer_arrays({}, values)


def test_preservation_check_rejects_changes_to_untranslated_technical_values():
    raw = table('string', ['human', 'protocol'], ['Hello'], [(b'', [(0, 0), (1, 0)])])
    translation = table('string', ['human'], ['Xin chào'], [(b'', [(0, 0)])])
    patched, _ = embed(raw, translation)
    original, rebuilt = Table(raw), Table(patched)
    report = build.verify_untouched_values(original, rebuilt, {('string', 'human')})
    assert report['untouched_values_checked'] == 1
    for key, _, positions in rebuilt.entries():
        if key[1] == 'protocol':
            struct.pack_into('<I', rebuilt.data, positions[None] + 4, len(rebuilt.pool.strings) - 1)
            break
    with pytest.raises(ValueError, match='Untranslated or non-string resource value changed'):
        build.verify_untouched_values(original, rebuilt, {('string', 'human')})
