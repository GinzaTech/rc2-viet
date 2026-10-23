"""Reviewed lost-aircraft wording, build contracts and motion-label regressions."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET

import pytest

from rc2vi import translation_catalog as tc, translation_memory
from rc2vi.resource_embed import Table
from rc2vi.translation_complete import _escape, _validate, compose_complete
from scripts.update_flyaway_translation import TRANSLATIONS, update_compiled


ROOT = Path(__file__).resolve().parents[1]
CATALOGS = ('assets/translation/catalog.json', 'assets/translation/memory/phone.json')
OVERLAYS = tuple(f'translation/review-round2/overlay/res/{locale}/strings.xml'
                 for locale in ('values', 'values-en', 'values-en-rUS', 'values-vi'))
COMPILED = ROOT / 'assets/auto12110/vietnamese.arsc'
BUTTON = 'me_device_info_value_added_loss_certification_btn'
SUCCESS = 'ABCfly_device_loss_certification_success_tips_content'
TERMS = 'ABCfly_device_aircraft_flyaway_terms_content_v2'
MOTION = {
    'wifi_mode_dolly_zoom_fpv_setting_pull_back_first': 'Bay đi đầu tiên',
    'wifi_mode_dolly_zoom_setting_combo_zoom_des':
        'Khi bật, máy bay sẽ bay một khoảng cách nhất định và bắt đầu phóng to',
    'wifi_mode_dolly_zoom_setting_combo_zoom_title': 'Bay đi trước khi phóng to',
}


def _catalog(path):
    rows = json.loads((ROOT / path).read_bytes())['entries']
    selected = [row for row in rows if row['kind'] == 'string']
    assert len({row['name'] for row in selected}) == len(selected)
    return {row['name']: row for row in selected}


def _english(row):
    parts = json.loads(row['source'])
    assert len(parts) == 1 and parts[0][0] == '' and parts[0][1][1] == []
    return parts[0][1][0]


def _plain(element):
    # Decode Android escapes; itertext alone would miss collapsed raw newlines.
    return tc._content(element)[0]


def _xml_values(path):
    elements = [node for node in ET.parse(ROOT / path).getroot() if node.tag == 'string']
    assert len({node.get('name') for node in elements}) == len(elements)
    return {node.get('name'): _plain(node) for node in elements}


def _resource_values(table):
    values = {}
    for key, config, positions in table.entries():
        for slot, (kind, value) in table.values(positions).items():
            content = value
            if kind == 3:
                content = (table.pool.strings[value], tuple(
                    (table.pool.strings[tag], first, last)
                    for tag, first, last in table.pool.styles[value]))
            values[key, config, slot] = kind, content
    return values


@pytest.fixture(scope='module')
def compiled_values():
    return _resource_values(Table(COMPILED.read_bytes()))


def test_user_label_and_consequences_describe_reporting_loss_not_camera_motion():
    assert TRANSLATIONS[BUTTON] == 'Báo mất flycam'
    confirmed = TRANSLATIONS['ABCfly_device_loss_certification_confirm_tips_cont']
    assert 'Sau khi xác nhận' in confirmed
    assert 'không được phép sử dụng tiếp' in confirmed
    assert 'không thể hủy báo cáo đã gửi' in confirmed
    assert 'không thể sử dụng' in TRANSLATIONS[
        'ABCfly_device_loss_certification_confirm_triple_check_secondary_content']
    assert 'Sau khi xác nhận, flycam bị cấm bay' in TRANSLATIONS[SUCCESS]
    assert 'Không thể cất cánh' in TRANSLATIONS['fpv_checklist_app_general_lock_drone']
    assert 'báo mất' in TRANSLATIONS['fpv_capsule_app_general_lock_drone'].lower()


def test_firmware_available_title_uses_the_requested_wording_in_both_entry_points():
    for name in ('firmware_update_click_check_upgrade_device_is_not_latest_version_dialog_content',
                 'firmware_update_detail_new_firmware_version_title'):
        assert TRANSLATIONS[name] == 'Phần mềm mới đã sẵn sàng'


def test_terms_keep_conditional_cancellation_ownership_and_information_categories():
    text = TRANSLATIONS[TERMS]
    assert re.findall(r'(?m)^([123])\. ', text) == ['1', '2', '3']
    unused, used = text.split('1) ', 1)[1].split('2) ', 1)
    used = used.split('\n\n3. ', 1)[0]
    assert 'chưa sử dụng' in unused and 'liên hệ bộ phận hỗ trợ DJI để hủy báo cáo' in unused
    assert 'sử dụng flycam bình thường' in unused
    assert 'đã sử dụng' in used and 'quyền sở hữu' in used and 'chuyển sang DJI' in used
    assert 'không thể hủy báo cáo' in used
    assert 'tài khoản DJI' in text and 'thông tin phần cứng' in text
    assert 'tay điều khiển hoặc kính' in text
    # Keep the absolute confirmation warning separate from these source terms.
    assert 'DJI Care' in text
    assert 'DJI Care Refresh' in TRANSLATIONS['ABCfly_device_unbind_device_terms_warning']
    bound = TRANSLATIONS['ABCfly_aircraft_bound_to_rc_or_gls_terms_content']
    assert 'Bộ điều khiển chuyển động không thể dùng làm thiết bị liên kết' in bound
    assert 'chưa liên kết với tay điều khiển' in bound


def test_success_link_placeholder_and_all_source_contracts_are_preserved():
    rows = _catalog(CATALOGS[0])
    assert TRANSLATIONS[SUCCESS].count('%1$s') == 1
    assert '%1$s' in _english(rows[SUCCESS])
    for name, approved in TRANSLATIONS.items():
        source = ET.fromstring(rows[name]['translation_xml'])
        source.text = _escape(_english(rows[name]))
        target = deepcopy(source)
        target.text = _escape(approved)
        _validate(source, target, strict=True)
        assert _plain(target) == approved, name
    flyaway_sources = {name for name, row in rows.items()
                       if re.search(r'\bflyaway\b', row['source'], re.I)}
    assert flyaway_sources <= TRANSLATIONS.keys()


@pytest.mark.parametrize('path', CATALOGS + OVERLAYS)
def test_every_active_catalog_and_xml_uses_approved_android_text(path):
    if path in CATALOGS:
        rows = _catalog(path)
        observed = {name: _plain(ET.fromstring(rows[name]['translation_xml']))
                    for name in TRANSLATIONS}
    else:
        values = _xml_values(path)
        observed = {name: values[name] for name in TRANSLATIONS}
    assert observed == TRANSLATIONS


def test_every_compiled_locale_and_default_uses_the_same_approved_text(compiled_values):
    found, defaults = set(), set()
    for (key, config, slot), (kind, value) in compiled_values.items():
        resource_type, name = key
        if resource_type != 'string' or name not in TRANSLATIONS:
            continue
        found.add(name)
        if not any(config[4:]):
            defaults.add(name)
        assert slot is None and kind == 3
        assert value == (TRANSLATIONS[name], ()), (name, config.hex())
    assert found == defaults == set(TRANSLATIONS)


def test_corrections_are_loaded_through_both_hash_pins():
    manifest_raw = (ROOT / 'assets/translation/memories.json').read_bytes()
    manifest = json.loads(manifest_raw)
    wording_raw = (ROOT / 'assets/translation/wording.json').read_bytes()
    assert hashlib.sha256(manifest_raw).hexdigest() == translation_memory.MEMORY_MANIFEST_SHA256
    assert manifest['files']['wording.json']['sha256'] == hashlib.sha256(wording_raw).hexdigest()
    rows = _catalog(CATALOGS[0])
    corrections = translation_memory.load_corrections(ROOT / 'assets')
    assert {name: corrections[_english(rows[name])] for name in TRANSLATIONS} == TRANSLATIONS
    assert all(_english(rows[name]) not in corrections for name in MOTION)


@pytest.mark.parametrize('changed_file', ['memories.json', 'wording.json'])
def test_modified_wording_or_manifest_is_not_silently_trusted(tmp_path, changed_file):
    folder = tmp_path / 'translation'
    folder.mkdir()
    for name in ('memories.json', 'wording.json'):
        (folder / name).write_bytes((ROOT / 'assets/translation' / name).read_bytes())
    (folder / changed_file).write_bytes(b'{}\n')
    with pytest.raises(ValueError):
        translation_memory.load_corrections(tmp_path)


def test_pinned_wording_beats_valid_stale_memory_but_does_not_touch_quickshot(tmp_path):
    rows = _catalog(CATALOGS[0])
    root = ET.Element('resources')
    stale_rows = []
    for name in (BUTTON, SUCCESS, *MOTION):
        source = ET.Element('string', name=name)
        source.text = _escape(_english(rows[name]))
        root.append(source)
        target = deepcopy(source)
        target.text = _escape(TRANSLATIONS[name].replace('mất flycam', 'bay đi')
                              if name in TRANSLATIONS else MOTION[name])
        _validate(source, target)
        stale_rows.append({'kind': 'string', 'name': name, 'source': tc._canonical(source),
                           'translation_xml': ET.tostring(target, encoding='unicode')})
    res = tmp_path / 'res'
    (res / 'values').mkdir(parents=True)
    (res / 'values/strings.xml').write_bytes(ET.tostring(root, encoding='utf-8'))
    values, report = compose_complete(res, [{'schema': 1, 'entries': stale_rows}],
        lambda texts: pytest.fail('Exact reviewed wording/memory must not call the model'),
        corrections=translation_memory.load_corrections(ROOT / 'assets'))
    observed = {node.get('name'): _plain(node) for node in values}
    assert report['complete']
    assert observed == {BUTTON: TRANSLATIONS[BUTTON], SUCCESS: TRANSLATIONS[SUCCESS], **MOTION}


def test_quickshot_flyaway_movement_remains_the_original_translation_everywhere(compiled_values):
    assert MOTION.keys().isdisjoint(TRANSLATIONS)
    for path in CATALOGS:
        rows = _catalog(path)
        assert {name: _plain(ET.fromstring(rows[name]['translation_xml']))
                for name in MOTION} == MOTION
    for path in OVERLAYS:
        values = _xml_values(path)
        assert {name: values[name] for name in MOTION} == MOTION
    found = set()
    for ((resource_type, name), _, slot), (kind, value) in compiled_values.items():
        if resource_type == 'string' and name in MOTION:
            found.add(name)
            assert slot is None and kind == 3 and value[0] == MOTION[name]
    assert found == set(MOTION)


def test_compiled_update_changes_only_reviewed_resources_and_is_byte_idempotent():
    table = Table(COMPILED.read_bytes())
    old_text = 'Flyaway cũ dùng chung'
    shared = len(table.pool.strings)
    table.pool.strings.append(old_text)
    table.pool.styles.append(())
    unrelated = None
    for (kind, name), config, positions in table.entries():
        if kind != 'string' or set(positions) != {None}:
            continue
        value_type, _ = table.values(positions)[None]
        if value_type != 3:
            continue
        if name in TRANSLATIONS:
            struct.pack_into('<I', table.data, positions[None] + 4, shared)
        elif unrelated is None and name in MOTION:
            # A shared string-pool index must not let a reviewed update alter
            # a different resource using the same old string.
            struct.pack_into('<I', table.data, positions[None] + 4, shared)
            unrelated = (('string', name), config, None)
    assert unrelated is not None
    baseline = table.build()
    before = _resource_values(Table(baseline))
    updated, count = update_compiled(baseline)
    after = _resource_values(Table(updated))
    assert before.keys() == after.keys()
    changed = {key for key in before if before[key] != after[key]}
    reviewed = {key for key in before if key[0][0] == 'string' and key[0][1] in TRANSLATIONS}
    assert changed == reviewed and count == len(reviewed)
    assert after[unrelated] == before[unrelated] == (3, (old_text, ()))
    assert all(after[key] == (3, (TRANSLATIONS[key[0][1]], ())) for key in reviewed)
    repeated, changes = update_compiled(updated)
    assert repeated == updated and changes == 0
