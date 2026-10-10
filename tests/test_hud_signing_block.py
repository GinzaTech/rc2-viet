import struct
import zipfile

import pytest

from scripts.hud_signing_block import block_entries, replace_v2_block


def with_block(path, entries):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('a', b'payload')
    raw = path.read_bytes()
    end = raw.rfind(b'PK\x05\x06')
    cd = struct.unpack_from('<I', raw, end + 16)[0]
    pairs = b''.join(struct.pack('<QI', 4 + len(value), key) + value for key, value in entries)
    size = len(pairs) + 24
    block = struct.pack('<Q', size) + pairs + struct.pack('<Q', size) + b'APK Sig Block 42'
    result = bytearray(raw[:cd] + block + raw[cd:])
    struct.pack_into('<I', result, end + len(block) + 16, cd + len(block))
    return bytes(result)


def test_replaces_v2_and_retains_v3_and_zip_payload(tmp_path):
    original = with_block(tmp_path / 'original.apk', [(0x7109871a, b'original-v2')])
    candidate = with_block(tmp_path / 'new.apk', [(0x7109871a, b'new-v2'), (0xf05368c0, b'local-v3')])
    result = replace_v2_block(original, candidate)
    entries = block_entries(result)
    assert entries[0x7109871a] == b'original-v2'
    assert entries[0xf05368c0] == b'local-v3'
    path = tmp_path / 'result.apk'
    path.write_bytes(result)
    with zipfile.ZipFile(path) as z:
        assert z.read('a') == b'payload'


def test_missing_v2_rejected(tmp_path):
    original = with_block(tmp_path / 'a.apk', [(7, b'not-v2')])
    candidate = with_block(tmp_path / 'b.apk', [(0xf05368c0, b'v3')])
    with pytest.raises(ValueError, match='v2'):
        replace_v2_block(original, candidate)


def test_malformed_footer_rejected():
    with pytest.raises(ValueError, match='Malformed'):
        block_entries(b'not-an-apk')
