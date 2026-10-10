"""Add an unexported late-init provider without recompiling DJI resources."""
import struct

PROVIDER = 'local.rc2.hud.HudProvider'
AUTHORITY = 'dji.go.v5.rc2hud'


def _chunks(xml: bytes) -> list[tuple[int, int, bytes]]:
    if len(xml) < 8 or struct.unpack_from('<HHI', xml) != (3, 8, len(xml)):
        raise ValueError('Malformed binary XML header')
    result = []
    position = 8
    while position < len(xml):
        if position + 8 > len(xml):
            raise ValueError('Malformed XML chunk')
        kind, header, size = struct.unpack_from('<HHI', xml, position)
        if header < 8 or size < header or position + size > len(xml):
            raise ValueError('Malformed XML chunk length')
        result.append((kind, position, xml[position:position + size]))
        position += size
    return result


def _length(data: bytes, pos: int, width: int) -> tuple[int, int]:
    value = int.from_bytes(data[pos:pos + width], 'little')
    pos += width
    flag = 1 << (width * 8 - 1)
    if value & flag:
        value = ((value & (flag - 1)) << (width * 8)) | int.from_bytes(data[pos:pos + width], 'little')
        pos += width
    return value, pos


def _pool(chunk: bytes) -> tuple[list[str], list[int], int, int]:
    _, header, _, count, styles, flags, start, style_start = struct.unpack_from('<HH6I', chunk)
    if header != 28 or styles != 0 or style_start != 0 or start < 28 + count * 4:
        raise ValueError('Unsupported styled string pool')
    offsets = list(struct.unpack_from('<' + 'I' * count, chunk, 28))
    strings = []
    for offset in offsets:
        pos = start + offset
        units, pos = _length(chunk, pos, 1 if flags & 256 else 2)
        if flags & 256:
            length, pos = _length(chunk, pos, 1)
            strings.append(chunk[pos:pos + length].decode('utf-8'))
        else:
            strings.append(chunk[pos:pos + units * 2].decode('utf-16le'))
    return strings, offsets, flags, start


def inspect_strings(xml: bytes) -> list[str]:
    pools = [chunk for kind, _, chunk in _chunks(xml) if kind == 1]
    if len(pools) != 1:
        raise ValueError('Malformed XML string pool count')
    return _pool(pools[0])[0]


def add_hud_provider(xml: bytes) -> bytes:
    chunks = _chunks(xml)
    strings = inspect_strings(xml)
    if PROVIDER in strings or AUTHORITY in strings:
        raise ValueError('HUD provider already present')
    template = end_provider = None
    for i, (kind, _, chunk) in enumerate(chunks):
        if kind != 0x102 or strings[struct.unpack_from('<I', chunk, 20)[0]] != 'provider':
            continue
        attr_start, attr_size, count = struct.unpack_from('<3H', chunk, 24)
        if attr_size != 20:
            raise ValueError('Malformed provider attributes')
        attributes = {}
        for index in range(count):
            pos = 16 + attr_start + index * attr_size
            name, raw = struct.unpack_from('<2I', chunk, pos + 4)
            attributes[strings[name]] = (pos, raw)
        if 'name' not in attributes:
            continue
        pos, raw = attributes['name']
        name_index = struct.unpack_from('<I', chunk, pos + 16)[0]
        if not strings[name_index].startswith('com.AppGuard.AppGuard.'):
            continue
        if set(attributes) != {'name', 'authorities', 'exported', 'initOrder'}:
            raise ValueError('Unexpected AppGuard provider shape')
        if i + 1 >= len(chunks) or chunks[i + 1][0] != 0x103:
            raise ValueError('Unexpected AppGuard provider children')
        template = bytearray(chunk)
        end_provider = chunks[i + 1][2]
        for attr, new_index in [('name', len(strings)), ('authorities', len(strings) + 1)]:
            offset = attributes[attr][0]
            struct.pack_into('<I', template, offset + 8, new_index)
            struct.pack_into('<HBBI', template, offset + 12, 8, 0, 3, new_index)
        offset = attributes['initOrder'][0]
        struct.pack_into('<I', template, offset + 8, 0xffffffff)
        struct.pack_into('<HBBI', template, offset + 12, 8, 0, 16, 0xfffffff6)
        offset = attributes['exported'][0]
        struct.pack_into('<I', template, offset + 8, 0xffffffff)
        struct.pack_into('<HBBI', template, offset + 12, 8, 0, 18, 0)
        break
    if template is None:
        raise ValueError('AppGuard bootstrap provider not found')
    result = []
    inserted = False
    for kind, _, chunk in chunks:
        if kind == 1:
            _, offsets, flags, start = _pool(chunk)
            data = bytearray(chunk[start:])
            for value in [PROVIDER, AUTHORITY]:
                offsets.append(len(data))
                encoded = value.encode('utf-8' if flags & 256 else 'utf-16le')
                if flags & 256:
                    data.extend(bytes([len(value), len(encoded)]) + encoded + b'\0')
                else:
                    data.extend(struct.pack('<H', len(value)) + encoded + b'\0\0')
            data.extend(bytes((-len(data)) % 4))
            count = len(offsets)
            chunk = struct.pack('<HH6I', 1, 28, 28 + count * 4 + len(data), count, 0, flags, 28 + count * 4, 0)
            chunk += struct.pack('<' + 'I' * count, *offsets) + bytes(data)
        if kind == 0x103 and strings[struct.unpack_from('<I', chunk, 20)[0]] == 'application':
            result.extend([bytes(template), end_provider])
            inserted = True
        result.append(chunk)
    if not inserted:
        raise ValueError('Malformed application ending')
    body = b''.join(result)
    return struct.pack('<HHI', 3, 8, 8 + len(body)) + body
