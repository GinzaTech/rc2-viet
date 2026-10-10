"""Strict byte-level checks for locally generated RC2 HUD APK candidates."""
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import copy
import struct


def repack_apk(stock: Path, output: Path, manifest: bytes | None = None, helper: bytes | None = None,
               bootstrap: bytes | None = None) -> None:
    """Copy compressed payloads unchanged; ZipFile generates the new central directory."""
    if stock.resolve() == output.resolve():
        raise ValueError('Output must not overwrite stock')
    with ZipFile(stock) as source, ZipFile(output, 'w') as target:
        _entries(source)
        if 'classes23.dex' in source.namelist():
            raise ValueError('Unexpected existing helper DEX')
        for entry in source.infolist():
            replacement = manifest if entry.filename == 'AndroidManifest.xml' else bootstrap if entry.filename == 'classes.dex' else None
            if replacement is not None:
                target.writestr(copy.copy(entry), replacement)
                continue
            source.fp.seek(entry.header_offset)
            header = source.fp.read(30)
            if len(header) != 30 or header[:4] != b'PK\x03\x04' or entry.flag_bits & 1:
                raise ValueError('Unsupported local ZIP header')
            name_size, extra_size = struct.unpack_from('<HH', header, 26)
            source.fp.seek(name_size + extra_size, 1)
            compressed = source.fp.read(entry.compress_size)
            if len(compressed) != entry.compress_size:
                raise ValueError('Truncated compressed payload')
            # Python 3.11 ZipFile close writes the central directory from these records.
            # Clearing descriptor bit is valid because all sizes and CRCs are known.
            result = copy.copy(entry)
            result.flag_bits &= ~8
            result.header_offset = target.fp.tell()
            target._writecheck(result)
            target._didModify = True
            target.fp.write(result.FileHeader(False))
            target.fp.write(compressed)
            target.filelist.append(result)
            target.NameToInfo[result.filename] = result
            target.start_dir = target.fp.tell()
        if helper is not None:
            info = ZipInfo('classes23.dex')
            info.compress_type = ZIP_DEFLATED
            target.writestr(info, helper)
        target.comment = source.comment


def _entries(archive: ZipFile) -> set[str]:
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError('Duplicate ZIP entry')
    return set(names)


def _compressed_digest(archive: ZipFile, entry: ZipInfo) -> bytes:
    archive.fp.seek(entry.header_offset)
    header = archive.fp.read(30)
    if len(header) != 30 or header[:4] != b'PK\x03\x04':
        raise ValueError('Malformed container header')
    name_size, extra_size = struct.unpack_from('<HH', header, 26)
    archive.fp.seek(name_size + extra_size, 1)
    remaining = entry.compress_size
    digest = sha256()
    while remaining:
        value = archive.fp.read(min(remaining, 1024 * 1024))
        if not value:
            raise ValueError('Truncated container payload')
        digest.update(value)
        remaining -= len(value)
    return digest.digest()


def validate_apk_change(stock: Path, candidate: Path,
                        expected_bootstrap: bytes | None = None,
                        expected_helper: bytes | None = None,
                        expected_manifest: bytes | None = None) -> dict[str, list[str]]:
    expected = {}
    if expected_bootstrap is not None:
        expected['classes.dex'] = expected_bootstrap
    if expected_manifest is not None:
        expected['AndroidManifest.xml'] = expected_manifest
    with ZipFile(stock) as original, ZipFile(candidate) as output:
        old, new = _entries(original), _entries(output)
        if old - new:
            raise ValueError('Removed stock ZIP entries')
        additions = {'classes23.dex'} if expected_helper is not None else set()
        if new - old != additions:
            raise ValueError('Unexpected added ZIP entries')
        if expected_helper is not None and output.read('classes23.dex') != expected_helper:
            raise ValueError('Wrong helper DEX bytes')
        changed = []
        for name in sorted(old):
            with original.open(name) as left, output.open(name) as right:
                different = sha256(left.read()).digest() != sha256(right.read()).digest()
            if not different:
                if name in expected:
                    raise ValueError('Expected modification missing: ' + name)
                left_info, right_info = original.getinfo(name), output.getinfo(name)
                fields = ('compress_type', 'compress_size', 'file_size', 'CRC', 'date_time')
                if any(getattr(left_info, field) != getattr(right_info, field) for field in fields):
                    raise ValueError('Unexpected container metadata: ' + name)
                if _compressed_digest(original, left_info) != _compressed_digest(output, right_info):
                    raise ValueError('Unexpected container recompression: ' + name)
                continue
            if name not in expected or output.read(name) != expected[name]:
                raise ValueError('Unexpected changed ZIP entry: ' + name)
            changed.append(name)
    return {'changed': changed, 'added': sorted(additions)}
