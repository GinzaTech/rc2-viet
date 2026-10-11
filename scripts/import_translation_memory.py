"""Import supplemental plain-string pairs from an older project export.

Existing exact-source pairs win. Legacy catalogs lack markup/plural metadata, so
collections and marked-up strings are excluded rather than reconstructed by guess.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from rc2vi import translation_catalog as tc
from rc2vi.translation_complete import _validate


def import_memory(folder, current_catalogs):
    folder = Path(folder)
    source = folder / 'translation/translation-catalog.json'
    if source.stat().st_size > 32*1024*1024: raise ValueError('Legacy catalog too large')
    rows = json.loads(source.read_text('utf-8'))
    if not isinstance(rows, list) or len(rows) > tc.MAX_ENTRIES:
        raise ValueError('Invalid legacy text catalog')
    translations = tc.load_resources(folder / 'translation/rc-1.21.10/res')
    existing = {(e['kind'], e['name'], e['source']) for c in current_catalogs for e in c['entries']}
    entries, reasons, seen = [], Counter(), set()
    for row in rows:
        if not isinstance(row, dict): raise ValueError('Invalid legacy row')
        name, kind, texts = row.get('name'), row.get('kind'), row.get('texts')
        if not isinstance(name, str) or not tc.NAME.fullmatch(name): raise ValueError('Invalid legacy name')
        if not isinstance(kind,str) or kind not in tc.KINDS: raise ValueError('Invalid legacy resource kind')
        key = kind, name
        if key in seen: raise ValueError('Duplicate legacy identity')
        seen.add(key)
        value = translations.get(key)
        if (kind != 'string' or not isinstance(texts, list) or len(texts) != 1
                or not isinstance(texts[0], str) or len(texts[0]) > tc.MAX_ENTRY_CHARS
                or value is None or len(value)):
            reasons['missing_source_shape_or_translation'] += 1
            continue
        original = ET.Element('string', name=name); original.text = texts[0]
        try:
            _validate(original, value, allow_unchanged=True)
            canonical = tc._canonical(original)
        except ValueError:
            reasons['incompatible_contract'] += 1
            continue
        if (kind, name, canonical) in existing:
            reasons['already_in_current_memory'] += 1
            continue
        clone = copy.deepcopy(value); clone.tail = None
        entries.append({'kind': kind, 'name': name, 'source': canonical,
                        'translation_xml': ET.tostring(clone, encoding='unicode')})
    return {'schema': 1, 'entries': entries, 'report': {
        'matched': len(entries), 'skipped': len(rows)-len(entries),
        'total': len(rows), 'reasons': dict(reasons)}}, {
        'source': 'rc2-viet-codex-initial-release',
        'source_catalog_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'translations': 'translation/rc-1.21.10/res',
        'method': 'exact source text and placeholder contract; current pairs take precedence',
        'runtime_tested': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--current', type=Path, action='append', required=True)
    args = parser.parse_args()
    catalog, provenance = import_memory(args.folder, [json.loads(p.read_text('utf-8')) for p in args.current])
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')), 'utf-8')
    args.output.with_suffix('.provenance.json').write_text(json.dumps(provenance, indent=2)+'\n', 'utf-8')
    print(json.dumps(catalog['report']))


if __name__ == '__main__': main()
