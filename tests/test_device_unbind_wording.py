"""Exact reviewed action labels must not alter other unbinding UI text."""
import xml.etree.ElementTree as ET

import pytest

from rc2vi import device_unbind_wording as wording, translation_catalog as catalog
from scripts import build_12116_translation as build


def source_contracts():
    targets = {('string', name): build.quoted_element('string', name, text)
               for name, text in wording.ENGLISH.items()}
    english = {key: [[None, 3, {'text': text, 'spans': []}]]
               for key, text in ((('string', name), text) for name, text in wording.ENGLISH.items())}
    return targets, english


def test_exact_action_labels_use_requested_spelling_and_leave_same_english_other_context_unchanged(tmp_path):
    targets, english = source_contracts()
    reviewed, errors = build.device_unbind_catalog(targets, english)
    assert not errors
    other_name = 'unrelated_account_action'
    targets['string', other_name] = build.quoted_element('string', other_name, 'Unbind Device')
    old_rows = []
    for key, source in targets.items():
        translated = build.quoted_element('string', key[1],
            'Nhãn của ngữ cảnh khác' if key[1] == other_name else 'Thiết bị chưa kết nối')
        old_rows.append({'kind': 'string', 'name': key[1], 'source': catalog._canonical(source),
                        'translation_xml': ET.tostring(translated, encoding='unicode')})
    def no_engine(_):
        pytest.fail('Reviewed labels must not require machine translation')
    output, report = build.compose_exact(targets,
        [reviewed, {'schema': 1, 'entries': old_rows}], no_engine, {}, {}, tmp_path)
    actual = {item.get('name'): catalog._content(item)[0] for item in output}
    assert actual[other_name] == 'Nhãn của ngữ cảnh khác'
    assert {name: actual[name] for name in wording.TRANSLATIONS} == {
        'fpv_binding_info_delete_dialogue_btn': 'Huỷ kết nối thiết bị',
        'me_device_info_value_added_unbing_rc_btn': 'Huỷ kết nối thiết bị',
    }
    assert report['machine'] == report['unresolved'] == 0


@pytest.mark.parametrize('name', tuple(wording.ENGLISH))
def test_changed_source_label_requires_review_instead_of_reusing_unbind_translation(name):
    targets, english = source_contracts()
    english['string', name][0][2]['text'] = 'Unbind Account'
    _, errors = build.device_unbind_catalog(targets, english)
    assert errors == [{'name': name, 'reason': 'English text/style contract mismatch'}]
