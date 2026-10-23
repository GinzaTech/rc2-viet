"""Audit and compile RC2 Fly 1.21.16 Vietnamese resources without signing/device I/O.

Old compiled translations are reused only when both the resource identity and
effective English text/style/reference contract match the pinned 1.21.10 stock.
Resources are compiled independently; embed() retains the target IDs/configs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rc2vi.resource_embed import Table, Pool, chunks, u32, embed, NO_ENTRY
from rc2vi.hud_tools import sha256_file
from rc2vi import translation_catalog as tc
from rc2vi.translation_complete import (compose_complete, IncompleteTranslation, _validate, _escape,
    _technical_reason, _reuse, _sentence, _approved)
from rc2vi.translation_memory import load_memories, load_corrections, with_reviewed_fragments
from rc2vi.translation_build import TranslationBuilder, resource_snapshot
from scripts.hud_manifest import inspect_application
from rc2vi import cellular_wording, device_unbind_wording

SOURCE_SHA256 = '9bec52ed4c43aad6c615b0a7a0650f0d35e842c4bf8a5e59d5da005a50d56b6a'
BASELINE_SHA256 = 'f6c11267d465c303e2aecb737fe4f6b41b54da083368cac497404f4c9a464f98'
PRIOR_TRANSLATION_SHA256 = '552e54ff5b3b4d2e8b70307cf75e4dbbe086838e2aec6b8e7eeec414caa03ddc'
KINDS = {'string', 'array', 'plurals'}
XML_KIND = {'array': 'string-array', 'string': 'string', 'plurals': 'plurals'}
COMPILED_KIND = {v: k for k, v in XML_KIND.items()}
PRESERVED_TECHNICAL = {
    'editor_playback_master_color_mixing_introduce_tab_content1_hg224': 'Vista Pro',
    'editor_playback_master_color_mixing_introduce_tab_content2_hg224': 'Grace Pro',
    'editor_playback_master_color_mixing_introduce_tab_content3_hg224': 'Radiant Pro',
    'editor_playback_master_color_mixing_introduce_tab_content4_hg224': 'Retro Pro',
    'general_playback_editing_export_setting_1080p_title': 'HD',
    'general_playback_editing_export_setting_720p_title': 'SD',
    'general_playback_editing_export_setting_4k_title': 'UHD',
    'general_playback_screenshot_framedphoto_content3': 'Pro',
    'general_playback_screenshot_framedphoto_content_limited3': 'LOVE I',
    'general_playback_single_clip_edit_invisible_stick_title': 'InvisiStick',
    'lct_fly_device_name_d520': 'DJI Avata2',
    'panorama_debug_label_eyez': 'Eyez',
    'panorama_debug_label_fov': 'FOV',
    'wifi_fpv_aircraft_voice_ctrl_guide_command': 'Hey DJI, Follow',
    'wifi_fpv_setting_voice_ctrl_chinese_guid_trigger_title': '小疆小疆',
    'wifi_fpv_setting_voice_ctrl_english_guid_trigger_title': 'Hey DJI',
    'wifi_fpv_setting_voice_ctrl_guid_trigger_title': 'Hey Fly!',
    'wifi_fpv_setting_voice_ctrl_guid_circle': 'Circle',
    'wifi_fpv_setting_voice_ctrl_guid_circle_5m': '2 meter Circle',
    'wifi_fpv_setting_voice_ctrl_guid_dronie': 'Dronie',
    'wifi_fpv_setting_voice_ctrl_guid_dronie_3m': '4 meter Dronie',
    'wifi_fpv_setting_voice_ctrl_guid_land': 'Land',
    'wifi_fpv_setting_voice_ctrl_guid_rocket': 'Rocket',
    'wifi_fpv_setting_voice_ctrl_guid_rocket_8m': '6 meter Rocket',
    'wifi_fpv_setting_voice_ctrl_guid_spotlight': 'Spotlight',
    'wifi_fpv_setting_voice_ctrl_guid_stop1': 'Brake',
    'wifi_fpv_setting_voice_ctrl_guid_stop2': 'Stop!',
    'wifi_fpv_setting_voice_ctrl_guid_track': 'Follow',
    'wifi_fpv_setting_voice_ctrl_guid_track_close': 'Close Follow',
    'wifi_fpv_setting_voice_ctrl_guid_track_front': 'Follow in the front',
    'wifi_fpv_setting_voice_ctrl_guid_track_left': 'Follow on the left',
    'wifi_fpv_setting_voice_ctrl_guid_track_set_closer': 'Closer',
    'wifi_fpv_setting_voice_ctrl_guid_track_set_farther': 'Farther',
    'wifi_fpv_setting_voice_ctrl_guid_track_set_higher': 'Higher',
    'wifi_fpv_setting_voice_ctrl_guid_track_set_lower': 'Lower',
    'fpv_setting_voice_ctrl_audio_popup_guid_track': 'Follow',
    'fpv_setting_voice_ctrl_audio_popup_guid_track_set_height_1': 'Fly higher',
    'fpv_setting_voice_ctrl_audio_popup_guid_track_set_height_2': 'Fly lower',
}


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def resource_ids(table):
    """Read true dense/sparse entry IDs; reject package/name collisions."""
    packages = [c for c in table.top if c[0] == 0x200]
    if len(packages) != 1:
        raise ValueError('Expected exactly one application resource package')
    _, header, start, stop = packages[0]
    package = table.data[start:stop]
    package_id = u32(package, 8)
    package_name = bytes(package[12:268]).decode('utf-16le').split('\0', 1)[0]
    if package_id != 0x7f:
        raise ValueError('Unexpected application resource package ID')
    type_offset = u32(package, 284) if header >= 288 else 0
    type_at, key_at = u32(package, 268), u32(package, 276)
    types = Pool(package[type_at:type_at + u32(package, type_at + 4)])
    keys = Pool(package[key_at:key_at + u32(package, key_at + 4)])
    result, configurations = {}, {}
    for tag, h, at, end in chunks(package, header, len(package)):
        if tag != 0x201:
            continue
        type_id, flags = package[at + 8:at + 10]
        count, entries_at = u32(package, at + 12), u32(package, at + 16)
        config = bytes(package[at + 20:at + h])
        if flags & ~3:
            raise ValueError('Unsupported resource index flags')
        for i in range(count):
            if flags & 1:
                entry_id, off = struct.unpack_from('<HH', package, at + h + 4 * i)
                off *= 4
            elif flags & 2:
                entry_id = i
                off = struct.unpack_from('<H', package, at + h + 2 * i)[0]
                off = NO_ENTRY if off == 0xffff else off * 4
            else:
                entry_id, off = i, u32(package, at + h + 4 * i)
            if off == NO_ENTRY:
                continue
            pos = at + entries_at + off
            size, entry_flags, key = struct.unpack_from('<HHI', package, pos)
            if entry_flags & 8 or pos + size > end or key >= len(keys.strings):
                raise ValueError('Unsupported compact or invalid resource entry')
            name = types.strings[type_id - 1], keys.strings[key]
            identifier = package_id << 24 | (type_id + type_offset) << 16 | entry_id
            if name in result and result[name] != identifier:
                raise ValueError('Resource name/ID collision')
            result[name] = identifier
            configurations.setdefault(name, set()).add(config)
    if len(set(result.values())) != len(result):
        raise ValueError('Resource ID/name collision')
    return {'id': package_id, 'name': package_name, 'type_id_offset': type_offset}, result, configurations


def semantic_values(table, positions, id_names):
    values = []
    for key, (kind, index) in table.values(positions).items():
        if kind == 3:
            content = {'text': table.pool.strings[index], 'spans': [
                [table.pool.strings[tag], first, last] for tag, first, last in table.pool.styles[index]]}
        elif kind in (1, 2, 7, 8) and index in id_names:
            content = {'reference': list(id_names[index])}
        else:
            content = {'value': index}
        values.append([key, kind, content])
    return values


def english(table, id_names):
    selected = {}
    for key, config, positions in table.entries():
        if key[0] not in KINDS:
            continue
        rank = -1
        if not any(config[4:]):
            rank = 0
        elif not any(config[4:8] + config[12:]):
            rank = {b'en\0\0': 1, b'enUS': 2}.get(config[8:12], -1)
        if rank >= 0 and (key not in selected or rank > selected[key][0]):
            selected[key] = rank, semantic_values(table, positions, id_names)
    return {key: row[1] for key, row in selected.items()}


def snapshot(path, expected):
    if sha256_file(path) != expected:
        raise ValueError('Pinned stock APK hash mismatch: ' + str(path))
    with ZipFile(path) as archive:
        identity = inspect_application(archive.read('AndroidManifest.xml'))
        raw = archive.read('resources.arsc')
    table = Table(raw)
    package, ids, configs = resource_ids(table)
    return {'path': str(path), 'sha256': expected, 'identity': identity, 'raw': raw,
            'table': table, 'package': package, 'ids': ids, 'configs': configs,
            'english': english(table, {v: k for k, v in ids.items()})}


def safe_value(name, value):
    # Resource names are useful evidence; credential values are never exported.
    from rc2vi.translation_complete import TECH_NAME
    return {'redacted': 'technical credential resource'} if TECH_NAME.search(name) else value


def audit(before, after):
    a, b = before['english'], after['english']
    added, removed = sorted(b.keys() - a.keys()), sorted(a.keys() - b.keys())
    changed = sorted(k for k in a.keys() & b.keys() if a[k] != b[k])
    common_ids = before['ids'].keys() & after['ids'].keys()
    id_changes = [{'kind': k[0], 'name': k[1], 'old_id': hex(before['ids'][k]),
                   'new_id': hex(after['ids'][k])} for k in sorted(common_ids)
                  if before['ids'][k] != after['ids'][k]]
    configs_changed = [k for k in a.keys() & b.keys()
                       if before['configs'][k] != after['configs'][k]]
    old_types, new_types = {}, {}
    for kind, name in before['ids']:
        old_types.setdefault(name, set()).add(kind)
    for kind, name in after['ids']:
        new_types.setdefault(name, set()).add(kind)
    type_changes = [{'name': n, 'old_types': sorted(old_types[n]), 'new_types': sorted(new_types[n])}
                    for n in sorted(old_types.keys() & new_types.keys()) if old_types[n] != new_types[n]]
    return {'source_sha256': after['sha256'], 'baseline_sha256': before['sha256'],
            'source_package': after['package'], 'baseline_package': before['package'],
            'english_precedence': ['default', 'en', 'en-US'],
            'reference_comparison': 'references resolved by resource name, never raw renumbered IDs',
            'counts': {'old_text_resources': len(a), 'new_text_resources': len(b), 'added': len(added),
                       'removed': len(removed), 'changed_english_contract': len(changed),
                       'renumbered_resource_ids': len(id_changes), 'changed_config_sets': len(configs_changed),
                       'changed_resource_type_sets': len(type_changes)},
            'added': [{'kind': k[0], 'name': k[1], 'english': safe_value(k[1], b[k])} for k in added],
            'removed': [{'kind': k[0], 'name': k[1]} for k in removed],
            'changed': [{'kind': k[0], 'name': k[1], 'old_english': safe_value(k[1], a[k]),
                         'english': safe_value(k[1], b[k])} for k in changed],
            'resource_id_changes': id_changes, 'type_changes': type_changes,
            'configuration_changes': [{'kind': k[0], 'name': k[1],
                'old': sorted(c.hex() for c in before['configs'][k]),
                'new': sorted(c.hex() for c in after['configs'][k])} for k in sorted(configs_changed)]}


def quoted_element(kind, name, text):
    item = ET.Element(kind, {'name': name})
    item.text = '"' + _escape(text) + '"'
    return item


def preserve_technical(targets, compiled_english):
    for name, expected in PRESERVED_TECHNICAL.items():
        key = 'string', name
        if compiled_english.get(key) != [[None, 3, {'text': expected, 'spans': []}]]:
            raise ValueError('Technical name/voice command source changed: ' + name)
        targets[key].set('translatable', 'false')
    if ('string', 'app_name') in targets:
        targets['string', 'app_name'].set('translatable', 'false')


def excluded_integer_arrays(targets, compiled_english):
    exclusions = []
    for (kind, name), values in sorted(compiled_english.items()):
        if (XML_KIND[kind], name) in targets:
            continue
        if kind != 'array' or any(value[1] not in (16, 17) for value in values):
            raise ValueError('Unexpected text resource omitted by XML composition: ' + name)
        exclusions.append({'compiled_kind': kind, 'decoded_kind': 'integer-array', 'name': name,
                           'items': len(values), 'preserved': True,
                           'reason': 'Integer lookup array; contains no translatable string value'})
    return exclusions


def verify_untouched_values(original, rebuilt, translated_keys):
    count = len(original.pool.strings)
    if rebuilt.pool.strings[:count] != original.pool.strings or rebuilt.pool.styles[:count] != original.pool.styles:
        raise ValueError('Existing global string/style pool changed')
    untouched, nonstring, entries = 0, 0, 0
    before_entries, after_entries = list(original.entries()), list(rebuilt.entries())
    if len(before_entries) != len(after_entries):
        raise ValueError('Resource entry count changed')
    for (key, config, before), (new_key, new_config, after) in zip(before_entries, after_entries):
        if (key, config) != (new_key, new_config):
            raise ValueError('Resource identity or configuration order changed')
        old_values, new_values = original.values(before), rebuilt.values(after)
        if old_values.keys() != new_values.keys():
            raise ValueError('Resource bag shape changed')
        entries += 1
        for bag, value in old_values.items():
            if key not in translated_keys or value[0] != 3:
                if new_values[bag] != value:
                    raise ValueError('Untranslated or non-string resource value changed')
                untouched += key not in translated_keys
                nonstring += value[0] != 3
    return {'resource_configurations_checked': entries, 'untouched_values_checked': untouched,
            'nonstring_values_checked': nonstring, 'original_pool_prefix_unchanged': True}


def compare_resource_values(original, rebuilt, allowed_changes):
    """Compare resolved values across all configs, independent of pool indices."""
    old_package, old_ids, old_configs = resource_ids(original)
    new_package, new_ids, new_configs = resource_ids(rebuilt)
    if (old_package, old_ids, old_configs) != (new_package, new_ids, new_configs):
        raise ValueError('Resource identities or configurations changed')
    id_names = {value: key for key, value in old_ids.items()}
    after = {(key, config): positions for key, config, positions in rebuilt.entries()}
    changed = Counter()
    checked = 0
    for key, config, positions in original.entries():
        if (key, config) not in after:
            raise ValueError('Resource entry configurations changed')
        checked += 1
        if semantic_values(original, positions, id_names) != semantic_values(rebuilt, after.pop((key, config)), id_names):
            if key not in allowed_changes:
                raise ValueError('Unrelated resource value changed: ' + key[1])
            changed[key] += 1
    if after:
        raise ValueError('Resource entry configurations changed')
    return {'resource_configurations_checked': checked,
            'unchanged_configurations': checked - sum(changed.values()),
            'changed_configurations': sum(changed.values()),
            'changed_resources': [{'kind': key[0], 'name': key[1], 'configurations': count}
                                  for key, count in sorted(changed.items())],
            'resource_ids_and_configurations_preserved': True,
            'unrelated_values_and_styles_unchanged': True}


def decode_inputs(source, prior, work):
    """Use the existing pinned offline toolchain; never load/create signing keys."""
    work.mkdir(parents=True, exist_ok=True)
    builder = TranslationBuilder(ROOT / 'assets', work / 'utilities')
    java, jar, aapt, framework = builder._utilities(work)
    source_snapshot = work / 'source-resources.apk'
    decoded = work / 'source-decoded'
    if not decoded.exists():
        if not source_snapshot.exists():
            resource_snapshot(source, source_snapshot)
        builder._run(java, '-jar', jar, 'd', '-s', '--no-assets', '-j', '1',
                     '-p', work / 'frameworks', '-o', decoded, source_snapshot)
    prior_apk, prior_decoded = work / 'prior-translation.apk', work / 'prior-decoded'
    if not prior_decoded.exists():
        if not prior_apk.exists():
            with ZipFile(ROOT / 'assets/vietnamese-resources.apk') as original:
                manifest = original.read('AndroidManifest.xml')
            with ZipFile(prior_apk, 'x', ZIP_DEFLATED) as output:
                output.writestr('AndroidManifest.xml', manifest)
                output.writestr('resources.arsc', prior.read_bytes())
        builder._run(java, '-jar', jar, 'd', '-s', '--no-assets', '-j', '1',
                     '-p', work / 'frameworks', '-o', prior_decoded, prior_apk)
    return builder, aapt, framework, decoded / 'res', prior_decoded / 'res'


def prior_catalog(targets, prior_elements, before, after):
    entries, rejected = [], Counter()
    for xml_key, translation in sorted(prior_elements.items()):
        compiled = COMPILED_KIND[xml_key[0]], xml_key[1]
        if (xml_key not in targets or compiled not in before['english']
                or before['english'][compiled] != after['english'].get(compiled)):
            rejected['missing_or_changed_english_contract'] += 1
            continue
        source = targets[xml_key]
        candidate = copy.deepcopy(translation)
        candidate.attrib = dict(source.attrib)
        candidate.tail = None
        try:
            _validate(source, candidate, allow_unchanged=True)
            entries.append({'kind': xml_key[0], 'name': xml_key[1], 'source': tc._canonical(source),
                            'translation_xml': ET.tostring(candidate, encoding='unicode')})
        except (ValueError, UnicodeError):
            rejected['xml_or_format_contract_rejected'] += 1
    return {'schema': 1, 'entries': entries}, dict(rejected)


def reviewed_catalog(path, targets, compiled_english=None):
    if not path or not path.is_file():
        return {'schema': 1, 'entries': []}, []
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('source_sha256') != SOURCE_SHA256 or not isinstance(value.get('entries'), list):
        raise ValueError('Reviewed 1.21.16 wording is not bound to the current source')
    return reviewed_rows(value['entries'], targets, compiled_english)


def cellular_catalog(targets, compiled_english):
    if (cellular_wording.SOURCE_SHA256 != SOURCE_SHA256
            or cellular_wording.ENGLISH.keys() != cellular_wording.TRANSLATIONS.keys()):
        raise ValueError('Cellular wording source or translation inventory differs')
    return reviewed_rows([{'name': name, 'english': english,
                          'vietnamese': cellular_wording.TRANSLATIONS[name]}
                         for name, english in cellular_wording.ENGLISH.items()],
                         targets, compiled_english)


def device_unbind_catalog(targets, compiled_english):
    if (device_unbind_wording.SOURCE_SHA256 != SOURCE_SHA256
            or device_unbind_wording.ENGLISH.keys() != device_unbind_wording.TRANSLATIONS.keys()):
        raise ValueError('Device unbind wording source or translation inventory differs')
    return reviewed_rows([{'name': name, 'english': english,
                          'vietnamese': device_unbind_wording.TRANSLATIONS[name]}
                         for name, english in device_unbind_wording.ENGLISH.items()],
                         targets, compiled_english)


def reviewed_rows(rows, targets, compiled_english=None):
    entries, mismatches = [], []
    for row in rows:
        key = 'string', row['name']
        try:
            source = targets[key]
            expected = [[None, 3, {'text': row['english'], 'spans': []}]]
            actual = (compiled_english.get(key) if compiled_english is not None
                      else [[None, 3, {'text': tc._content(source)[0], 'spans': tc._content(source)[1]}]])
            if actual != expected:
                raise ValueError('English text/style contract mismatch')
            candidate = (copy.deepcopy(source) if tc._content(source) == (row['vietnamese'], [])
                         else quoted_element('string', row['name'], row['vietnamese']))
            _validate(source, candidate, allow_unchanged=True)
            entries.append({'kind': 'string', 'name': row['name'], 'source': tc._canonical(source),
                            'translation_xml': ET.tostring(candidate, encoding='unicode')})
        except (KeyError, ValueError, UnicodeError) as error:
            mismatches.append({'name': row.get('name'), 'reason': str(error)})
    return {'schema': 1, 'entries': entries}, mismatches


def preferred_catalog(catalogs):
    chosen = {}
    for catalog in catalogs:
        for row in catalog['entries']:
            chosen.setdefault((row['kind'], row['name'], row['source']), row)
    return {'schema': 1, 'entries': list(chosen.values())}


def compose_exact(targets, catalogs, translate, overrides, corrections, work):
    """Reuse exact kind/name/English only; shared-text memory is deliberately off."""
    lookup = []
    for catalog in catalogs:
        index = {}
        for row in catalog['entries']:
            index.setdefault((row['kind'], row['name'], row['source']), []).append(row)
        lookup.append(index)
    selected, pending, provenance, preserved = {}, {}, Counter(), Counter()
    for key, source in sorted(targets.items()):
        parts = tc._parts(source)
        technical = (['nontranslatable'] if source.get('translatable') == 'false' else
                     [_technical_reason(item, key[1]) for _, item in parts])
        if all(technical):
            reason = technical[0] if len(set(technical)) == 1 else 'technical_collection'
            preserved[reason] += 1
            continue
        candidate = None
        if source.tag == 'string':
            try:
                candidate = _approved(_sentence(source, source.get('formatted') != 'false'), corrections)
                if candidate is not None:
                    _validate(source, candidate, allow_unchanged=True)
                    provenance['wording_correction'] += 1
            except (ValueError, UnicodeError):
                candidate = None
        if candidate is None:
            try:
                canonical = tc._canonical(source)
            except ValueError:
                canonical = None
            for number, catalog in enumerate(lookup):
                candidate = _reuse(source, catalog.get((*key, canonical), []))
                if candidate is not None:
                    provenance['manual_12116' if number == 0 else
                               'prior_compiled_exact_contract' if number == 1 else 'reviewed_memory_exact_contract'] += 1
                    break
        if candidate is not None:
            selected[key] = candidate
        else:
            pending[key] = source
    partial_elements = []
    machine_report = {'total': 0, 'preserved': 0, 'reviewed': 0, 'machine': 0,
                      'unresolved': 0, 'unresolved_resources': [], 'reasons': {}, 'complete': True}
    if pending:
        folder = work / 'pending-source/values'
        folder.mkdir(parents=True, exist_ok=True)
        xml = ET.Element('resources')
        xml.extend(copy.deepcopy(list(pending.values())))
        ET.ElementTree(xml).write(folder / 'sources.xml', encoding='utf-8', xml_declaration=True)
        try:
            partial_elements, machine_report = compose_complete(folder.parent, [],
                with_reviewed_fragments(translate, overrides), overrides, allow_chinese=True, corrections=corrections)
        except IncompleteTranslation as error:
            machine_report = error.report
    report = {**machine_report, 'total': len(targets), 'target_total': len(targets),
              'preserved': sum(preserved.values()) + machine_report['preserved'],
              'reviewed': len(selected) + machine_report['reviewed'],
              'exact_selection_provenance': dict(provenance),
              'preserved_reasons': dict(preserved), 'cross_name_memory_reuse': False}
    report['eligible_total'] = report['total'] - report['preserved']
    report['matched'] = report['reviewed'] + report['machine']
    report['complete'] = not report['unresolved'] and report['matched'] == report['eligible_total']
    if not report['complete']:
        raise IncompleteTranslation(report)
    elements = list(selected.values()) + partial_elements
    return sorted(elements, key=lambda e: (e.tag, e.get('name'))), report


def pending_details(report, targets):
    result = []
    for row in report.get('unresolved_resources', []):
        key = row['kind'], row['name']
        source = targets.get(key)
        parts = []
        if source is not None:
            for part, item in tc._parts(source):
                try:
                    text, spans = tc._content(item)
                    parts.append({'part': part, 'english': text, 'styled': bool(spans)})
                except ValueError:
                    parts.append({'part': part, 'resource_reference': True})
        result.append({**row, 'source_parts': parts})
    return result


def write_resources(elements, res):
    for qualifier in ('values', 'values-en', 'values-en-rUS', 'values-vi'):
        folder = res / qualifier
        folder.mkdir(parents=True, exist_ok=True)
        root = ET.Element('resources')
        root.extend(copy.deepcopy(elements))
        ET.ElementTree(root).write(folder / 'translations.xml', encoding='utf-8', xml_declaration=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'local-artifacts/fly12116-20261023/DJI-Fly-RC2-1.21.16-stock.apk')
    parser.add_argument('--baseline', type=Path, default=ROOT.parent / 'tham-khao/phone-work-inputs-20261015/stock-inputs/DJI_FLY_RC_1.21.10_stock.apk')
    parser.add_argument('--prior', type=Path, default=ROOT / 'assets/auto12110/vietnamese.arsc')
    parser.add_argument('--work', type=Path, default=ROOT / 'local-artifacts/fly12116-20261023/translation')
    parser.add_argument('--scratch', type=Path, default=Path(tempfile.gettempdir()) / 'rc2vi-12116' /
                        (SOURCE_SHA256[:8] + '-' + PRIOR_TRANSLATION_SHA256[:8]),
                        help='Short host-only tool/decode path for Windows path-length limits')
    parser.add_argument('--output', type=Path, default=ROOT / 'assets/auto12116')
    parser.add_argument('--reviewed', type=Path, default=ROOT / 'local-artifacts/fly12116-20261023/reviewed-wording.json')
    parser.add_argument('--engine-payload-root', type=Path, action='append', default=[])
    parser.add_argument('--machine', action='store_true', help='Translate missing text locally; separately reported as machine output')
    parser.add_argument('--build', action='store_true', help='Compile and publish only after zero unresolved resources')
    args = parser.parse_args(argv)
    args.work.mkdir(parents=True, exist_ok=True)
    before, after = snapshot(args.baseline, BASELINE_SHA256), snapshot(args.source, SOURCE_SHA256)
    if after['identity']['version'] != '1.21.16' or after['identity']['code'] != 3132286:
        raise ValueError('Unexpected RC2 Fly source identity')
    if sha256_file(args.prior) != PRIOR_TRANSLATION_SHA256:
        raise ValueError('Prior compiled Vietnamese table changed')
    diff = audit(before, after)
    atomic_json(args.work / 'resource-audit.json', diff)
    print(json.dumps({'state': 'RESOURCE_AUDIT', **diff['counts']}), flush=True)
    builder, aapt, framework, target_res, prior_res = decode_inputs(args.source, args.prior, args.scratch / 'decode')
    targets = tc.load_resources(target_res)
    exclusions = excluded_integer_arrays(targets, after['english'])
    atomic_json(args.work / 'composition-exclusions.json', {'raw_text_resources': len(after['english']),
        'composition_text_resources': len(targets), 'excluded_technical_arrays': exclusions})
    preserve_technical(targets, after['english'])
    atomic_json(args.work / 'preserved-technical.json', {'source_sha256': SOURCE_SHA256,
        'exact_english_guards': PRESERVED_TECHNICAL, 'app_name': 'preserve source label',
        'all_original_locale_values_retained': True})
    prepared_res = args.work / 'composition-source/values'
    prepared_res.mkdir(parents=True, exist_ok=True)
    source_root = ET.Element('resources')
    source_root.extend(copy.deepcopy(list(targets.values())))
    ET.ElementTree(source_root).write(prepared_res / 'sources.xml', encoding='utf-8', xml_declaration=True)
    old_catalog, rejected = prior_catalog(targets, tc.load_resources(prior_res), before, after)
    reviewed_hash = sha256_file(args.reviewed) if args.reviewed.is_file() else None
    manual, mismatches = reviewed_catalog(args.reviewed, targets, after['english'])
    cellular, cellular_mismatches = cellular_catalog(targets, after['english'])
    unbind, unbind_mismatches = device_unbind_catalog(targets, after['english'])
    mismatches.extend(cellular_mismatches)
    mismatches.extend(unbind_mismatches)
    atomic_json(args.work / 'reviewed-contracts.json', {'accepted': len(manual['entries']),
        'cellular_accepted': len(cellular['entries']), 'device_unbind_accepted': len(unbind['entries']),
        'mismatches': mismatches})
    if mismatches:
        raise ValueError('Reviewed wording mismatched source/format contract; see reviewed-contracts.json')
    memories, overrides, memory_digest = load_memories(ROOT / 'assets')
    corrections = load_corrections(ROOT / 'assets')
    catalogs = [preferred_catalog([unbind, cellular, manual]), old_catalog, *memories]
    atomic_json(args.work / 'selection-inputs.json', {'source_sha256': SOURCE_SHA256,
        'baseline_sha256': BASELINE_SHA256, 'prior_translation_sha256': PRIOR_TRANSLATION_SHA256,
        'prior_compiled_contract_matches': len(old_catalog['entries']), 'prior_rejections': rejected,
        'reviewed_12116': len(manual['entries']), 'memory_digest': memory_digest,
        'reviewed_cellular': len(cellular['entries']), 'cellular_revision': cellular_wording.REVISION,
        'reviewed_device_unbind': len(unbind['entries']), 'device_unbind_revision': device_unbind_wording.REVISION,
        'manual_override_file_sha256': reviewed_hash,
        'app_name_preserved': True})
    translate = lambda texts: ['' for _ in texts]
    engine_stats = {'requested_sentences': 0, 'cache_hits': 0, 'translated_sentences': 0, 'invocations': 0}
    if args.machine:
        from rc2vi.translation_engine import LocalTranslationEngine, ENGINE_MANIFEST_SHA256
        engine = LocalTranslationEngine(ROOT / 'assets', args.work / 'engine',
            lambda state, text: print(json.dumps({'state': state, 'message': text}, ensure_ascii=True), flush=True),
            payload_roots=args.engine_payload_root or None)
        if args.engine_payload_root and not any((p / engine.manifest()['engine_id']).is_dir()
                                                for p in args.engine_payload_root):
            raise ValueError('Explicit offline engine payload is unavailable; no model download attempted')
        cache_path = args.work / 'machine-cache.json'
        cache = {'engine_manifest_sha256': ENGINE_MANIFEST_SHA256, 'translations': {}}
        if cache_path.exists():
            loaded = json.loads(cache_path.read_text(encoding='utf-8'))
            if (loaded.get('engine_manifest_sha256') == ENGINE_MANIFEST_SHA256
                    and isinstance(loaded.get('translations'), dict)):
                cache = loaded
        def translate(texts):
            engine_stats['requested_sentences'] += len(texts)
            hashes = [hashlib.sha256(text.encode('utf-8')).hexdigest() for text in texts]
            missing = [(text, digest) for text, digest in zip(texts, hashes)
                       if digest not in cache['translations']]
            engine_stats['cache_hits'] += len(texts) - len(missing)
            if missing:
                output = engine.translate([text for text, _ in missing])
                for (_, digest), translated in zip(missing, output):
                    cache['translations'][digest] = translated
                atomic_json(cache_path, cache)
                engine_stats['invocations'] += 1
                engine_stats['translated_sentences'] += len(missing)
            return [cache['translations'][digest] for digest in hashes]
    try:
        elements, report = compose_exact(targets, catalogs, translate, overrides, corrections, args.work)
    except IncompleteTranslation as error:
        error.report['local_engine'] = engine_stats
        atomic_json(args.work / 'composition-report.json', error.report)
        atomic_json(args.work / 'unresolved.json', pending_details(error.report, targets))
        print(json.dumps({'state': 'NEEDS_TRANSLATION', 'unresolved': error.report['unresolved'],
                          'reviewed': error.report['reviewed'], 'machine': error.report['machine'],
                          'details': str(args.work / 'unresolved.json')}), flush=True)
        return 2
    report['local_engine'] = engine_stats
    atomic_json(args.work / 'composition-report.json', report)
    atomic_json(args.work / 'unresolved.json', [])
    if not args.build:
        print(json.dumps({'state': 'COMPLETE_SELECTION', 'resources': len(elements), 'reviewed': report['reviewed'],
                          'machine': report['machine'], 'compiled': False}), flush=True)
        return 0
    res = args.work / 'overlay/res'
    write_resources(elements, res)
    manifest = args.work / 'overlay/AndroidManifest.xml'
    manifest.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
        'package="local.dji.fly.vi12116" android:versionCode="1" android:versionName="12116">'
        '<uses-sdk android:minSdkVersion="30" android:targetSdkVersion="30"/>'
        '<application android:hasCode="false" android:label="Tiếng Việt DJI Fly"/></manifest>', encoding='utf-8')
    compiled, unsigned = args.work / 'compiled.zip', args.work / 'unsigned-resources.apk'
    builder._run(aapt, 'compile', '--dir', res, '-o', compiled)
    builder._run(aapt, 'link', '-o', unsigned, '--manifest', manifest, '-I', framework,
                 '--auto-add-overlay', '--no-resource-deduping', '--no-resource-removal', '-R', compiled)
    with ZipFile(unsigned) as archive:
        translation = archive.read('resources.arsc')
    patched, embed_report = embed(after['raw'], translation)
    final_table = Table(patched)
    _, final_ids, final_configs = resource_ids(final_table)
    if final_ids != after['ids'] or final_configs != after['configs']:
        raise ValueError('Resource IDs or configurations changed during embedding')
    translated_keys = {(COMPILED_KIND[item.tag], item.get('name')) for item in elements}
    preservation_report = verify_untouched_values(after['table'], final_table, translated_keys)
    with ZipFile(args.work / 'resource-readback.apk', 'w', ZIP_DEFLATED) as archive:
        with ZipFile(args.source) as source:
            archive.writestr('AndroidManifest.xml', source.read('AndroidManifest.xml'))
        archive.writestr('resources.arsc', patched)
    from scripts.build_feature_candidate import parse_resource_dump
    source_ids = parse_resource_dump(builder._run(aapt, 'dump', 'resources', '--no-values', args.source))
    result_ids = parse_resource_dump(builder._run(aapt, 'dump', 'resources', '--no-values', args.work / 'resource-readback.apk'))
    if not source_ids or source_ids != result_ids:
        raise ValueError('AAPT2 independent resource ID inventory changed')
    if sha256_file(args.source) != SOURCE_SHA256 or sha256_file(args.prior) != PRIOR_TRANSLATION_SHA256:
        raise ValueError('Original input changed during translation build')
    if args.reviewed.is_file() and sha256_file(args.reviewed) != reviewed_hash:
        raise ValueError('Reviewed wording changed during build; rerun using the local machine cache')
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / 'vietnamese.arsc'
    if target.exists() and target.read_bytes() != translation:
        raise FileExistsError('Refusing to replace a different published 1.21.16 table')
    target.write_bytes(translation)
    metadata = {'schema': 1, 'source_sha256': SOURCE_SHA256, 'version': '1.21.16', 'version_code': 3132286,
        'resource_sha256': hashlib.sha256(translation).hexdigest(), 'bytes': len(translation),
        'embedded_resources': embed_report['embedded_resources'], 'separate_overlay_required': False,
        'translation_revision': device_unbind_wording.REVISION, 'source_package': after['package'],
        'prior_translation_sha256': PRIOR_TRANSLATION_SHA256, 'reviewed': report['reviewed'],
        'machine': report['machine'], 'unresolved': 0, 'complete': True,
        'all_machine_output_semantically_reviewed': False if report['machine'] else None,
        'resource_ids_and_configurations_preserved': True, 'aapt2_parse': 'PASS',
        'aapt2_resource_id_inventory_identical': True,
        'raw_text_resources': len(after['english']), 'composition_text_resources': report['total'],
        'preserved_composition_resources': report['preserved'], 'excluded_integer_arrays': len(exclusions),
        'preserved_raw_resources': report['preserved'] + len(exclusions),
        'signed': False, 'installed': False}
    atomic_json(args.output / 'manifest.json', metadata)
    atomic_json(args.work / 'build-report.json', {**metadata, 'embedding': embed_report,
        'preservation_checks': preservation_report, 'composition_exclusions': exclusions,
        'source_unchanged': True, 'baseline_unchanged': sha256_file(args.baseline) == BASELINE_SHA256})
    print(json.dumps({'state': 'BUILT', **metadata}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
