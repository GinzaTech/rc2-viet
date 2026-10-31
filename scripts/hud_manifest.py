"""Add an unexported late-init provider without recompiling DJI resources."""
import struct
import re

PROVIDER = 'local.rc2.hud.HudProvider'
AUTHORITY = 'dji.go.v5.rc2hud'
ANDROID = 'http://schemas.android.com/apk/res/android'
# Android API30 android.R.attr, checked against the installed android.jar.
ATTR_IDS = {'name': 16842755, 'authorities': 16842776,
            'exported': 16842768, 'initOrder': 16842778}


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
    if pos < 0 or pos + width > len(data): raise ValueError('Truncated string length')
    value = int.from_bytes(data[pos:pos + width], 'little')
    pos += width
    flag = 1 << (width * 8 - 1)
    if value & flag:
        if pos + width > len(data): raise ValueError('Truncated string length extension')
        value = ((value & (flag - 1)) << (width * 8)) | int.from_bytes(data[pos:pos + width], 'little')
        pos += width
    return value, pos


def _pool(chunk: bytes) -> tuple[list[str], list[int], int, int]:
    if len(chunk) < 28: raise ValueError('Truncated string pool')
    _, header, _, count, styles, flags, start, style_start = struct.unpack_from('<HH6I', chunk)
    if (header != 28 or styles != 0 or style_start != 0 or count > 200000
            or not 28 + count * 4 <= start <= len(chunk)):
        raise ValueError('Unsupported styled string pool')
    offsets = list(struct.unpack_from('<' + 'I' * count, chunk, 28))
    strings = []
    for offset in offsets:
        pos = start + offset
        units, pos = _length(chunk, pos, 1 if flags & 256 else 2)
        if flags & 256:
            length, pos = _length(chunk, pos, 1)
            if pos+length>=len(chunk) or chunk[pos+length]!=0: raise ValueError('Truncated UTF8 pool string')
            strings.append(chunk[pos:pos + length].decode('utf-8'))
        else:
            if pos+units*2+2>len(chunk) or chunk[pos+units*2:pos+units*2+2]!=b'\0\0':
                raise ValueError('Truncated UTF16 pool string')
            strings.append(chunk[pos:pos + units * 2].decode('utf-16le'))
    return strings, offsets, flags, start


def inspect_strings(xml: bytes) -> list[str]:
    pools = [chunk for kind, _, chunk in _chunks(xml) if kind == 1]
    if len(pools) != 1:
        raise ValueError('Malformed XML string pool count')
    return _pool(pools[0])[0]


def _attributes(chunk, strings):
    if len(chunk) < 36:
        raise ValueError('Malformed XML element')
    start, width, count = struct.unpack_from('<3H', chunk, 24)
    if start != 20 or width != 20 or 36 + count * width != len(chunk):
        raise ValueError('Malformed XML attributes')
    result = {}
    for i in range(count):
        ns, name, raw, size, zero, kind, value = struct.unpack_from('<IIIHBBI', chunk, 36+i*20)
        if name >= len(strings) or size != 8 or zero or (ns != 0xffffffff and ns >= len(strings)):
            raise ValueError('Malformed XML attribute index')
        key = ('' if ns == 0xffffffff else strings[ns], strings[name])
        if key in result:
            raise ValueError('Duplicate XML attribute')
        if kind == 3:
            if value >= len(strings) or (raw != 0xffffffff and raw >= len(strings)):
                raise ValueError('Malformed XML string value')
            value = strings[value]
        result[key] = (kind, value)
    return result


def inspect_application(xml: bytes) -> dict:
    """Read identity from binary AXML, without resource recompile or version pins."""
    if len(xml) > 4 * 1024 * 1024:
        raise ValueError('Oversized manifest')
    chunks, strings = _chunks(xml), inspect_strings(xml)
    manifests, applications = [], []
    stack = []
    for kind, _, chunk in chunks:
        if kind not in (0x102, 0x103):
            continue
        if len(chunk) < 24:
            raise ValueError('Malformed element')
        index = struct.unpack_from('<I', chunk, 20)[0]
        if index >= len(strings):
            raise ValueError('Malformed element name')
        tag = strings[index]
        if kind == 0x102:
            attrs = _attributes(chunk, strings)
            if tag == 'manifest' and not stack:
                manifests.append(attrs)
            if tag == 'application' and stack == ['manifest']:
                applications.append(attrs)
            stack.append(tag)
        elif not stack or stack.pop() != tag:
            raise ValueError('Unbalanced manifest')
    if stack or len(manifests) != 1 or len(applications) != 1:
        raise ValueError('Ambiguous manifest/application')
    attrs = manifests[0]
    def string(values, key, default=None):
        kind, value = values.get(key, (3, default))
        if kind != 3 or not isinstance(value, str) or not value:
            raise ValueError('Invalid manifest identity')
        return value
    package = string(attrs, ('', 'package'))
    version = string(attrs, (ANDROID, 'versionName'))
    kind, code = attrs.get((ANDROID, 'versionCode'), (0, 0))
    application = string(applications[0], (ANDROID, 'name'), 'android.app.Application')
    if application.startswith('.'):
        application = package + application
    elif '.' not in application:
        application = package + '.' + application
    pattern = r'[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)+'
    if (not re.fullmatch(pattern, package) or not re.fullmatch(pattern, application)
            or len(application) > 512 or len(version) > 128 or kind not in (16, 17)
            or not 0 < code < 2**31):
        raise ValueError('Invalid package/application/version metadata')
    return {'package': package, 'application': application, 'version': version, 'code': code}


def _append_pool(chunk, values):
    _, offsets, flags, start = _pool(chunk)
    data = bytearray(chunk[start:])
    for value in values:
        offsets.append(len(data))
        encoded = value.encode('utf-8' if flags & 256 else 'utf-16le')
        if flags & 256:
            def length(n): return bytes([n]) if n < 128 else bytes([(n >> 8) | 128, n & 255])
            data.extend(length(len(value.encode('utf-16le'))//2)+length(len(encoded))+encoded+b'\0')
        else:
            data.extend(struct.pack('<H', len(encoded)//2)+encoded+b'\0\0')
    data.extend(bytes(-len(data) % 4))
    count = len(offsets)
    return (struct.pack('<HH6I', 1, 28, 28+count*4+len(data), count, 0, flags & ~1, 28+count*4, 0)
            + struct.pack('<'+'I'*count, *offsets)+data)


def add_adaptive_provider(xml: bytes) -> bytes:
    identity = inspect_application(xml)
    if identity['package'] != 'dji.go.v5':
        raise ValueError('Menu targets dji.go.v5 only')
    strings, chunks = inspect_strings(xml), _chunks(xml)
    if PROVIDER in strings or AUTHORITY in strings:
        raise ValueError('Menu provider already present')
    if ANDROID not in strings:
        raise ValueError('Android namespace missing')
    values = ['provider', 'name', 'authorities', 'exported', 'initOrder', PROVIDER, AUTHORITY]
    index = {v: len(strings)+i for i, v in enumerate(values)}
    ns = strings.index(ANDROID)
    mapping = [chunk for kind, _, chunk in chunks if kind == 0x180]
    if len(mapping) > 1 or (mapping and (len(mapping[0])-8) % 4):
        raise ValueError('Invalid XML resource map')
    ids = list(struct.unpack('<'+'I'*((len(mapping[0])-8)//4), mapping[0][8:])) if mapping else []
    if len(ids) > len(strings):
        raise ValueError('Invalid XML resource map length')
    ids += [0] * (len(strings)+len(values)-len(ids))
    for name, value in ATTR_IDS.items(): ids[index[name]] = value
    resource_map = struct.pack('<HHI', 0x180, 8, 8+len(ids)*4)+struct.pack('<'+'I'*len(ids), *ids)
    attributes = []
    for name, raw, kind, value in [('name', index[PROVIDER], 3, index[PROVIDER]),
                                  ('exported', 0xffffffff, 18, 0),
                                  ('authorities', index[AUTHORITY], 3, index[AUTHORITY]),
                                  ('initOrder', 0xffffffff, 16, 0xfffffff6)]:
        attributes.append((ATTR_IDS[name], struct.pack('<IIIHBBI', ns, index[name], raw, 8, 0, kind, value)))
    provider = struct.pack('<HHIii', 0x102, 16, 116, 0, -1)
    provider += struct.pack('<ii6H', -1, index['provider'], 20, 20, 4, 0, 0, 0)
    provider += b''.join(value for _, value in sorted(attributes))
    end = struct.pack('<HHIiiii', 0x103, 16, 24, 0, -1, -1, index['provider'])
    result, inserted = [], False
    for kind, _, chunk in chunks:
        if kind == 1:
            result.append(_append_pool(chunk, values))
            if not mapping: result.append(resource_map)
            continue
        if kind == 0x180: chunk = resource_map
        if kind == 0x103 and strings[struct.unpack_from('<I', chunk, 20)[0]] == 'application':
            result.extend([provider, end]); inserted = True
        result.append(chunk)
    if not inserted: raise ValueError('Application ending missing')
    body = b''.join(result)
    output = struct.pack('<HHI', 3, 8, 8+len(body))+body
    if inspect_application(output) != identity: raise ValueError('Manifest identity changed')
    return output


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
