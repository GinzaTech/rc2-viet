"""Keep the legacy v2 loader input alongside the independently signed v3 candidate.

The selected Android 11 v3 signature must be verified externally after this operation.
This does not claim the retained v2 signature is valid for changed APK content.
"""
import struct

V2 = 0x7109871a


def _parts(data: bytes) -> tuple[int, int, int, list[tuple[int, bytes]]]:
    end = data.rfind(b'PK\x05\x06', max(0, len(data) - 65557))
    if end < 0 or end + 22 > len(data):
        raise ValueError('Malformed ZIP end record')
    if end + 22 + struct.unpack_from('<H', data, end + 20)[0] != len(data):
        raise ValueError('Malformed ZIP comment length')
    central = struct.unpack_from('<I', data, end + 16)[0]
    if central < 24 or central > end or data[central - 16:central] != b'APK Sig Block 42':
        raise ValueError('Malformed APK signing block footer')
    size = struct.unpack_from('<Q', data, central - 24)[0]
    start = central - size - 8
    if start < 0 or struct.unpack_from('<Q', data, start)[0] != size:
        raise ValueError('Malformed APK signing block size')
    position, entries = start + 8, []
    while position < central - 24:
        length = struct.unpack_from('<Q', data, position)[0]
        position += 8
        if length < 4 or position + length > central - 24:
            raise ValueError('Malformed signing block entry')
        identifier = struct.unpack_from('<I', data, position)[0]
        if any(key == identifier for key, _ in entries):
            raise ValueError('Malformed duplicate signing block ID')
        entries.append((identifier, data[position + 4:position + length]))
        position += length
    if position != central - 24:
        raise ValueError('Malformed signing block alignment')
    return start, central, end, entries


def block_entries(data: bytes) -> dict[int, bytes]:
    return dict(_parts(data)[3])


def replace_v2_block(original: bytes, candidate: bytes) -> bytes:
    source = block_entries(original)
    if V2 not in source:
        raise ValueError('Original v2 signing entry missing')
    start, central, end, entries = _parts(candidate)
    if 0xf05368c0 not in dict(entries):
        raise ValueError('Candidate v3 signing entry missing')
    replaced = [(key, source[V2] if key == V2 else value) for key, value in entries]
    if V2 not in dict(replaced):
        replaced.insert(0, (V2, source[V2]))
    pairs = b''.join(struct.pack('<QI', len(value) + 4, key) + value for key, value in replaced)
    size = len(pairs) + 24
    block = struct.pack('<Q', size) + pairs + struct.pack('<Q', size) + b'APK Sig Block 42'
    output = bytearray(candidate[:start] + block + candidate[central:])
    delta = len(block) - (central - start)
    struct.pack_into('<I', output, end + delta + 16, start + len(block))
    return bytes(output)
