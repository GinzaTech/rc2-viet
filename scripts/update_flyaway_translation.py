"""Apply the reviewed lost-aircraft wording to RC2 translations and embedded resources."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rc2vi.flyaway_wording import REVISION, TRANSLATIONS as FLYAWAY_TRANSLATIONS, FIRMWARE_TRANSLATIONS
from rc2vi.resource_embed import Table
from rc2vi.translation_complete import _escape, _validate
from rc2vi.translation_catalog import _content

TRANSLATIONS = {**FLYAWAY_TRANSLATIONS, **FIRMWARE_TRANSLATIONS}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_text(row):
    parts = json.loads(row['source'])
    if row['kind'] != 'string' or len(parts) != 1 or parts[0][0] != '' or parts[0][1][1]:
        raise ValueError('Expected a reviewed plain-string source: ' + row['name'])
    return parts[0][1][0]


def update_catalog(raw, expected_sources=None):
    catalog = json.loads(raw)
    rows = {row['name']: row for row in catalog['entries'] if row['kind'] == 'string'}
    if not TRANSLATIONS.keys() <= rows.keys():
        raise ValueError('Catalog is missing a reviewed Flyaway resource')
    sources = {}
    for name, text in TRANSLATIONS.items():
        row = rows[name]
        english = source_text(row)
        if expected_sources is not None and english != expected_sources[name]:
            raise ValueError('Source contract changed: ' + name)
        target = ET.fromstring(row['translation_xml'])
        if target.tag != 'string' or target.get('name') != name or len(target):
            raise ValueError('Unexpected Flyaway XML shape: ' + name)
        original = deepcopy(target)
        original.text = _escape(english)
        target.text = _escape(text)
        _validate(original, target)
        row['translation_xml'] = ET.tostring(target, encoding='unicode')
        sources[name] = english
    return json.dumps(catalog, ensure_ascii=False, separators=(',', ':')).encode(), sources


def table_snapshot(table):
    result = {}
    for key, config, positions in table.entries():
        for slot, (kind, value) in table.values(positions).items():
            if kind == 3:
                result[key, config, slot] = (kind, table.pool.strings[value],
                    tuple((table.pool.strings[tag], first, last) for tag, first, last in table.pool.styles[value]))
            else:
                result[key, config, slot] = (kind, value)
    return result


def update_compiled(raw):
    table = Table(raw)
    before = table_snapshot(table)
    indices, default_seen = {}, set()
    for key, config, positions in table.entries():
        kind, name = key
        if kind != 'string' or name not in TRANSLATIONS:
            continue
        if set(positions) != {None}:
            raise ValueError('Expected one simple compiled string: ' + name)
        position = positions[None]
        value_type, old_index = table.values(positions)[None]
        if value_type != 3 or table.pool.styles[old_index]:
            raise ValueError('Expected an unstyled compiled string: ' + name)
        text = TRANSLATIONS[name]
        if text not in indices:
            try:
                indices[text] = table.pool.strings.index(text)
            except ValueError:
                indices[text] = len(table.pool.strings)
                table.pool.strings.append(text)
                table.pool.styles.append(())
        struct.pack_into('<I', table.data, position + 4, indices[text])
        if not any(config[4:]):
            default_seen.add(name)
    if default_seen != set(TRANSLATIONS):
        raise ValueError('Default compiled translations are incomplete')
    output = table.build()
    after = table_snapshot(Table(output))
    if before.keys() != after.keys():
        raise ValueError('Compiled resource identities or configurations changed')
    changes = 0
    for identity, value in after.items():
        (kind, name), _, slot = identity
        if kind == 'string' and name in TRANSLATIONS:
            if slot is not None or value != (3, TRANSLATIONS[name], ()):
                raise ValueError('Compiled Flyaway wording verification failed: ' + name)
        elif value != before[identity]:
            raise ValueError('An unrelated compiled resource changed: ' + str(identity[:1]))
        changes += value != before[identity]
    return output, changes


def update_overlay(raw):
    text = raw.decode('utf-8')
    for name, value in TRANSLATIONS.items():
        pattern = r'(<string\b[^>]*\bname="' + re.escape(name) + r'"[^>]*>)(.*?)(</string>)'
        text, count = re.subn(pattern, lambda match: match[1] + escape(_escape(value)) + match[3], text, flags=re.S)
        if count != 1:
            raise ValueError('Expected one overlay resource: ' + name)
    observed = {item.get('name'): _content(item)[0] for item in ET.fromstring(text)}
    if any(observed.get(name) != value for name, value in TRANSLATIONS.items()):
        raise ValueError('Overlay wording verification failed')
    return text.encode('utf-8')


def replace_pin(raw, constant, value):
    result, count = re.subn(r"\b" + re.escape(constant) + r" = '[0-9a-f]{64}'",
                           constant + " = '" + value + "'", raw.decode('utf-8'))
    if count != 1:
        raise ValueError('Expected exactly one checksum pin: ' + constant)
    return result.encode('utf-8')


def prepare_updates():
    updates = {}
    path = Path('assets/translation/catalog.json')
    updates[path], sources = update_catalog((ROOT / path).read_bytes())
    path = Path('assets/translation/memory/phone.json')
    updates[path], _ = update_catalog((ROOT / path).read_bytes(), sources)
    path = Path('assets/translation/wording.json')
    corrections = json.loads((ROOT / path).read_bytes())
    for name, english in sources.items():
        corrections[english] = TRANSLATIONS[name]
    updates[path] = (json.dumps(corrections, ensure_ascii=False, indent=2) + '\n').encode()
    path = Path('assets/translation/memories.json')
    manifest = json.loads((ROOT / path).read_bytes())
    for name in ('catalog.json', 'memory/phone.json', 'wording.json'):
        manifest['files'][name]['sha256'] = digest(updates[Path('assets/translation') / name])
    updates[path] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    path = Path('rc2vi/translation_memory.py')
    updates[path] = replace_pin((ROOT / path).read_bytes(), 'MEMORY_MANIFEST_SHA256',
                               digest(updates[Path('assets/translation/memories.json')]))
    for locale in ('values', 'values-en', 'values-en-rUS', 'values-vi'):
        path = Path('translation/review-round2/overlay/res') / locale / 'strings.xml'
        updates[path] = update_overlay((ROOT / path).read_bytes())
    path = Path('assets/auto12110/vietnamese.arsc')
    updates[path], changes = update_compiled((ROOT / path).read_bytes())
    compiled_digest = digest(updates[path])
    manifest_path = path.with_name('manifest.json')
    compiled_manifest = json.loads((ROOT / manifest_path).read_bytes())
    compiled_manifest.update(resource_sha256=compiled_digest, bytes=len(updates[path]),
        translation_revision=REVISION, translation_semantics_match_reviewed_apk=False,
        manual_overrides=sorted(set(compiled_manifest.get('manual_overrides', [])) | set(TRANSLATIONS)))
    updates[manifest_path] = (json.dumps(compiled_manifest, ensure_ascii=False, indent=2) + '\n').encode()
    path = Path('rc2vi/auto_patch.py')
    updates[path] = replace_pin((ROOT / path).read_bytes(), 'TRANSLATION_SHA256', compiled_digest)
    return updates, changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True, help='New backup/report directory')
    args = parser.parse_args()
    updates, changes = prepare_updates()  # Validate every output before changing any input.
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    report = {'revision': REVISION, 'resources': len(TRANSLATIONS),
              'compiled_configurations_changed': changes, 'device_tested': False, 'files': {}}
    for relative, data in updates.items():
        path = ROOT / relative
        original = path.read_bytes()
        backup = work / 'before' / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(original)
        report['files'][relative.as_posix()] = {'before': digest(original), 'after': digest(data)}
    for relative, data in updates.items():
        path = ROOT / relative
        temporary = path.with_name(path.name + '.flyaway.tmp')
        with temporary.open('xb') as stream:
            stream.write(data)
        temporary.replace(path)
        if path.read_bytes() != data:
            raise ValueError('Updated file readback mismatch: ' + str(relative))
    (work / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    main()
