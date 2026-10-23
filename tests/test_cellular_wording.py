"""Cellular product wording and narrow compiled-table update regressions."""
import copy
import xml.etree.ElementTree as ET

import pytest

from rc2vi import cellular_wording as wording, translation_catalog as catalog
from rc2vi.resource_embed import Table
from scripts import build_12116_translation as build
from test_resource_embed import table


def source_contracts():
    targets, english = {}, {}
    for name, text in wording.ENGLISH.items():
        element = build.quoted_element('string', name, text)
        targets['string', name] = element
        english['string', name] = [[None, 3, {'text': text, 'spans': []}]]
    return targets, english


def test_reviewed_cellular_wording_wins_over_bad_exact_memory_without_machine_translation(tmp_path):
    targets, english = source_contracts()
    reviewed, mismatches = build.cellular_catalog(targets, english)
    assert not mismatches
    bad = copy.deepcopy(reviewed)
    for row in bad['entries']:
        item = ET.Element('string', {'name': row['name']})
        item.text = 'DJI Chuyển động Tế bào'
        row['translation_xml'] = ET.tostring(item, encoding='unicode')
    def no_engine(_):
        pytest.fail('Exact reviewed Cellular wording must never use machine translation')
    elements, report = build.compose_exact(targets, [reviewed, bad], no_engine, {}, {}, tmp_path)
    actual = {element.get('name'): catalog._content(element)[0] for element in elements}
    # XML normalizes spaces around line breaks; compare through the same content reader.
    expected = {}
    for name, text in wording.TRANSLATIONS.items():
        expected[name] = catalog._content(build.quoted_element('string', name, text))[0]
    assert actual == expected
    assert report['machine'] == report['unresolved'] == 0
    assert actual['firmware_update_name_dongle'] == 'DJI Cellular'


def test_cellular_exact_source_guard_rejects_new_generation():
    targets, english = source_contracts()
    name = 'me_device_dongle_detail_page_operator_authentication_description_content'
    english['string', name][0][2]['text'] = wording.ENGLISH[name].replace('Dongle 3', 'Dongle 4')
    _, mismatches = build.cellular_catalog(targets, english)
    assert mismatches == [{'name': name, 'reason': 'English text/style contract mismatch'}]


def test_cellular_brand_generation_generic_data_and_troubleshooting_are_distinct():
    assert wording.TRANSLATIONS['firmware_update_name_dongle'] == 'DJI Cellular'
    assert wording.TRANSLATIONS['cellular_data_permission_dialog_title'] == 'Dữ liệu di động'
    auth = wording.TRANSLATIONS['me_device_dongle_detail_page_operator_authentication_description_content']
    assert 'DJI Cellular 3' in auth
    assert 'China Unicom không hỗ trợ' in auth
    assert '"Sui xin fei zhu shou 2" (随心飞助手 2)' in auth
    lte = wording.TRANSLATIONS['fpv_setting_transfer_mode_check_network_content']
    assert lte.count('%1$s') == 1
    assert all('\n' + str(number) + '. ' in lte for number in (2, 3, 4))
    apn = wording.TRANSLATIONS['me_device_info_accessories_management_drone_dongle_apn_content']
    assert 'APN không chính xác có thể làm mất kết nối dữ liệu' in apn
    assert all('\n' + str(number) + '. ' in apn for number in range(1, 7))
    assert not any('tế bào' in text.casefold() or 'DJI Di động' in text
                   for text in wording.TRANSLATIONS.values())


def test_narrow_resource_comparison_allows_pool_reordering_but_rejects_unrelated_value_changes():
    old = Table(table('string', ['protocol', 'product'], ['Keep', 'Old'],
                      [(b'', [(0, 0), (1, 1)])]))
    updated = Table(table('string', ['protocol', 'product'], ['DJI Cellular', 'Keep'],
                          [(b'', [(0, 1), (1, 0)])]))
    report = build.compare_resource_values(old, updated, {('string', 'product')})
    assert report['changed_resources'] == [{'kind': 'string', 'name': 'product', 'configurations': 1}]
    assert report['unchanged_configurations'] == 1
    bad = Table(table('string', ['protocol', 'product'], ['DJI Cellular', 'Changed protocol'],
                      [(b'', [(0, 1), (1, 0)])]))
    with pytest.raises(ValueError, match='Unrelated resource value changed: protocol'):
        build.compare_resource_values(old, bad, {('string', 'product')})
