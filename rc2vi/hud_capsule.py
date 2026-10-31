"""Per-input byte-exact recovery data. Recovery alone never approves a mod APK.

The caller must replay the current patch against the recovered source and verify
every unchanged payload, added helper and selected signer before installation.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from .hud_backup import guard_path
from .hud_tools import _json_object, check_cancel, sha256_file
from . import hud_stock as stock

MAX_LITERAL = 96 * 1024 * 1024
CAPSULE_ENTRY = 'assets/rc2-menu/recovery.zip'
PROFILE_ENTRY = 'assets/rc2-menu/profile.json'


def _changed(names):
    if not isinstance(names, (set, frozenset, list, tuple)) or not 1 <= len(names) <= 64:
        raise ValueError('Invalid changed entry inventory')
    values = set(names)
    if len(values) != len(names) or 'AndroidManifest.xml' not in values:
        raise ValueError('Invalid changed manifest inventory')
    for name in values:
        stock.safe_name(name)
        if name not in {'AndroidManifest.xml', 'resources.arsc'} and not re.fullmatch(r'classes(?:[1-9][0-9]*)?\.dex', name):
            raise ValueError('Only DEX, manifest and compiled resources can be recovered from literals')
    return values


def _recipe(archive):
    if archive.namelist() != ['recipe.json', 'literals.bin']:
        raise ValueError('Invalid recovery capsule entries')
    for entry in archive.infolist():
        if entry.flag_bits & 1 or entry.compress_type not in (0, 8):
            raise ValueError('Unsupported recovery capsule compression')
    if archive.getinfo('recipe.json').file_size > 8 * 1024 * 1024:
        raise ValueError('Oversized recovery recipe')
    value = _json_object(archive.read('recipe.json'))
    changed = _changed(value.get('changed'))
    digest = value.get('stock_sha256')
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('Invalid recovery source digest')
    return stock.recipe_value(archive, expected_digest=digest, changed=changed,
                              max_literal=MAX_LITERAL, schema=2)


def build_capsule(source, output, changed, cancel=None):
    source, output = map(guard_path, (source, output))
    changed = _changed(changed)
    if output.exists(): raise FileExistsError('Recovery capsule already exists')
    if not 0 < source.stat().st_size <= 1536 * 1024 * 1024:
        raise ValueError('Source APK size outside recovery limit')
    before = sha256_file(source, cancel)
    literals, rows = bytearray(), []
    def literal(data):
        offset = len(literals)
        if offset + len(data) > MAX_LITERAL: raise ValueError('Recovery literal limit exceeded')
        literals.extend(data)
        return offset
    with ZipFile(source) as archive:
        entries = sorted(stock.entries(archive), key=lambda e: e.header_offset)
        if not changed <= set(archive.namelist()): raise ValueError('Changed input entry missing')
        prefix = entries[0].header_offset
        archive.fp.seek(0); literal(archive.fp.read(prefix))
        for index, entry in enumerate(entries):
            check_cancel(cancel)
            payload = stock.compressed_offset(archive, entry)
            archive.fp.seek(entry.header_offset)
            header = archive.fp.read(payload-entry.header_offset)
            row = {'name': entry.filename, 'header_offset': entry.header_offset,
                   'header_size': len(header), 'header_literal': literal(header),
                   'compressed_size': entry.compress_size, 'file_size': entry.file_size,
                   'crc': entry.CRC, 'method': entry.compress_type,
                   'payload_literal': len(literals) if entry.filename in changed else -1}
            digest, remaining = hashlib.sha256(), entry.compress_size
            while remaining:
                check_cancel(cancel)
                part = archive.fp.read(min(stock.CHUNK, remaining))
                if not part: raise ValueError('Truncated recovery source')
                digest.update(part); remaining -= len(part)
                if entry.filename in changed: literal(part)
            row['compressed_sha256'] = digest.hexdigest()
            end = payload + entry.compress_size
            next_offset = entries[index+1].header_offset if index+1 < len(entries) else source.stat().st_size
            if next_offset < end or next_offset-end > MAX_LITERAL:
                raise ValueError('Overlapping or excessive APK suffix')
            row['suffix_size'] = next_offset-end
            row['suffix_literal'] = literal(archive.fp.read(next_offset-end))
            rows.append(row)
    recipe = {'schema': 2, 'stock_sha256': before, 'stock_size': source.stat().st_size,
              'literal_size': len(literals), 'entries': rows, 'prefix_size': prefix,
              'prefix_literal': 0, 'changed': sorted(changed)}
    if sha256_file(source, cancel) != before: raise ValueError('Source changed while building recovery')
    check_cancel(cancel)
    try:
        with ZipFile(output, 'x', ZIP_DEFLATED) as archive:
            for name, value in [('recipe.json', json.dumps(recipe, sort_keys=True, separators=(',', ':')).encode()),
                                ('literals.bin', bytes(literals))]:
                info = ZipInfo(name, (1980, 1, 1, 0, 0, 0)); info.compress_type = ZIP_DEFLATED
                archive.writestr(info, value, compresslevel=9)
        with ZipFile(output) as archive: _recipe(archive)
        return output
    except BaseException:
        output.unlink(missing_ok=True)
        raise


def recover_capsule(installed, capsule, output, added_names, cancel=None):
    installed, capsule, output = map(guard_path, (installed, capsule, output))
    if output.exists(): raise FileExistsError('Recovery never overwrites files')
    if capsule.stat().st_size > MAX_LITERAL: raise ValueError('Oversized capsule')
    if len(added_names) > 64: raise ValueError('Invalid added inventory')
    added = {stock.safe_name(name) for name in added_names}
    temporary = None
    try:
        with ZipFile(capsule) as archive, ZipFile(installed) as current:
            recipe = _recipe(archive); changed = set(recipe['changed'])
            entries = stock.entries(current)
            expected = {row['name'] for row in recipe['entries']}
            if expected & added or set(current.namelist()) != expected | added:
                raise ValueError('Recovery APK inventory differs')
            spans = sorted((entry.header_offset, stock.compressed_offset(current, entry)+entry.compress_size)
                           for entry in entries)
            if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
                raise ValueError('Overlapping recovery payloads')
            for row in recipe['entries']:
                if row['name'] in changed: continue
                entry = current.getinfo(row['name'])
                if (entry.compress_size, entry.file_size, entry.CRC, entry.compress_type) != (
                        row['compressed_size'], row['file_size'], row['crc'], row['method']):
                    raise ValueError('Changed original payload metadata')
            with tempfile.NamedTemporaryFile(prefix='.menu-recover-', dir=output.parent, delete=False) as target:
                temporary = Path(target.name)
                with archive.open('literals.bin') as literals:
                    stock.stream_copy(literals, target, recipe['prefix_size'], cancel)
                    for row in recipe['entries']:
                        stock.stream_copy(literals, target, row['header_size'], cancel)
                        if row['name'] in changed:
                            stock.stream_copy(literals, target, row['compressed_size'], cancel, row['compressed_sha256'])
                        else:
                            current.fp.seek(stock.compressed_offset(current, current.getinfo(row['name'])))
                            stock.stream_copy(current.fp, target, row['compressed_size'], cancel, row['compressed_sha256'])
                        stock.stream_copy(literals, target, row['suffix_size'], cancel)
                    if literals.read(1): raise ValueError('Trailing recovery literals')
            if (temporary.stat().st_size != recipe['stock_size']
                    or sha256_file(temporary, cancel) != recipe['stock_sha256']):
                raise ValueError('Recovered source checksum mismatch')
            guard_path(output); check_cancel(cancel)
            os.link(temporary, output)
            return output
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
