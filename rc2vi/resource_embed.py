"""Embed compiled translations without renumbering or rebuilding app resources.

Format: AOSP androidfw/ResourceTypes.h. Only TYPE_STRING value references and
the global string pool change. Package chunks, configurations and resource IDs
retain their original layout. Styles are copied with their compiled UTF-16 spans.
"""
import struct

NO_ENTRY = 0xffffffff


def u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def chunks(data, start, end):
    while start < end:
        kind, header, size = struct.unpack_from('<HHI', data, start)
        if header < 8 or size < header or start + size > end:
            raise ValueError('Invalid resource chunk bounds')
        yield kind, header, start, start + size
        start += size
    if start != end:
        raise ValueError('Resource chunks are not contiguous')


class Pool:
    def __init__(self, data):
        kind, self.header, size, count, styles, self.flags, strings_at, styles_at = struct.unpack_from('<HH6I', data)
        if kind != 1 or self.header != 28 or size != len(data) or styles > count:
            raise ValueError('Unsupported string pool')
        self.strings = []
        self.styles = []
        for i in range(count):
            at = strings_at + u32(data, self.header + 4 * i)
            if self.flags & 0x100:
                _, at = self._length(data, at, 1)
                n, at = self._length(data, at, 1)
                value = data[at:at+n].decode('utf-8')
                if data[at+n] != 0:
                    raise ValueError('Unterminated UTF-8 resource string')
            else:
                n, at = self._length(data, at, 2)
                value = data[at:at+2*n].decode('utf-16le')
                if data[at+2*n:at+2*n+2] != b'\0\0':
                    raise ValueError('Unterminated UTF-16 resource string')
            self.strings.append(value)
            spans = []
            offset = u32(data, self.header + 4 * (count+i)) if i < styles else NO_ENTRY
            if offset != NO_ENTRY:
                at = styles_at + offset
                while True:
                    name = u32(data, at)
                    if name == NO_ENTRY:
                        break
                    name, first, last = struct.unpack_from('<III', data, at)
                    if name >= count or first > last or last >= len(value.encode('utf-16le')) // 2:
                        raise ValueError('Invalid styled resource span')
                    spans.append((name, first, last)); at += 12
            self.styles.append(tuple(spans))

    @staticmethod
    def _length(data, at, width):
        value = data[at] if width == 1 else struct.unpack_from('<H', data, at)[0]
        high = 1 << (width * 8 - 1)
        at += width
        if value & high:
            low = data[at] if width == 1 else struct.unpack_from('<H', data, at)[0]
            value = ((value & (high-1)) << (width*8)) | low
            at += width
        return value, at

    @staticmethod
    def _encoded_length(n, width):
        limit = 1 << (width*8-1)
        fmt = '<B' if width == 1 else '<H'
        if n < limit:
            return struct.pack(fmt, n)
        if n >= limit << (width*8):
            raise ValueError('Resource string exceeds format limit')
        return struct.pack(fmt, (n >> (width*8)) | limit) + struct.pack(fmt, n & ((1 << (width*8))-1))

    def append_from(self, other, index, memo):
        if index in memo:
            return memo[index]
        spans = tuple((self.append_from(other, name, memo), first, last)
                      for name, first, last in other.styles[index])
        new = len(self.strings)
        self.strings.append(other.strings[index]); self.styles.append(spans)
        memo[index] = new
        return new

    def build(self):
        offsets = []; raw = bytearray(); style_offsets = []; style_raw = bytearray()
        for value in self.strings:
            offsets.append(len(raw)); utf16 = value.encode('utf-16le')
            if self.flags & 0x100:
                utf8 = value.encode('utf-8')
                raw += self._encoded_length(len(utf16)//2, 1) + self._encoded_length(len(utf8), 1) + utf8 + b'\0'
            else:
                raw += self._encoded_length(len(utf16)//2, 2) + utf16 + b'\0\0'
        raw += b'\0' * (-len(raw) % 4)
        style_count = max((i+1 for i, s in enumerate(self.styles) if s), default=0)
        for spans in self.styles[:style_count]:
            style_offsets.append(len(style_raw) if spans else NO_ENTRY)
            if spans:
                for span in spans:
                    style_raw += struct.pack('<III', *span)
                style_raw += struct.pack('<III', NO_ENTRY, NO_ENTRY, NO_ENTRY)
        start = 28 + 4 * (len(offsets) + len(style_offsets))
        styles_at = start + len(raw) if style_count else 0
        header = struct.pack('<HH6I', 1, 28, start+len(raw)+len(style_raw), len(offsets),
                             style_count, self.flags & ~1, start, styles_at)
        return header + struct.pack('<'+'I'*len(offsets), *offsets) + struct.pack('<'+'I'*len(style_offsets), *style_offsets) + raw + style_raw


class Table:
    def __init__(self, data):
        self.data = bytearray(data)
        if len(data) > 128*1024*1024 or data[:2] != b'\x02\x00' or u32(data, 4) != len(data):
            raise ValueError('Invalid compiled resource table')
        self.header = struct.unpack_from('<H', data, 2)[0]
        self.top = list(chunks(data, self.header, len(data)))
        pools = [c for c in self.top if c[0] == 1]
        if len(pools) != 1:
            raise ValueError('Exactly one global resource string pool is required')
        self.pool_chunk = pools[0]
        self.pool = Pool(data[pools[0][2]:pools[0][3]])

    def entries(self):
        for kind, header, package_at, end in self.top:
            if kind != 0x200:
                continue
            package = self.data[package_at:end]
            if header < 284:
                raise ValueError('Unsupported resource package header')
            type_at, key_at = u32(package, 268), u32(package, 276)
            types = Pool(package[type_at:type_at+u32(package, type_at+4)])
            keys = Pool(package[key_at:key_at+u32(package, key_at+4)])
            for tag, h, at, stop in chunks(package, header, len(package)):
                if tag != 0x201:
                    continue
                type_id, flags = package[at+8:at+10]
                count, entries_at = u32(package, at+12), u32(package, at+16)
                config = bytes(package[at+20:at+h])
                if flags & ~3:
                    raise ValueError('Unsupported resource entry index format')
                for i in range(count):
                    if flags & 1:
                        _, offset = struct.unpack_from('<HH', package, at+h+4*i)
                        offset *= 4
                    elif flags & 2:
                        offset = struct.unpack_from('<H', package, at+h+2*i)[0]
                        offset = NO_ENTRY if offset == 0xffff else offset*4
                    else:
                        offset = u32(package, at+h+4*i)
                    if offset == NO_ENTRY:
                        continue
                    entry = at+entries_at+offset
                    size, entry_flags, key = struct.unpack_from('<HHI', package, entry)
                    if entry_flags & 8:
                        raise ValueError('Compact resource entries are not supported')
                    name = (types.strings[type_id-1], keys.strings[key])
                    values = {}
                    if entry_flags & 1:
                        for j in range(u32(package, entry+12)):
                            value = entry+size+12*j
                            values[u32(package, value)] = package_at+value+4
                    else:
                        values[None] = package_at+entry+size
                    for pos in values.values():
                        if pos+8 > package_at+stop or struct.unpack_from('<H', self.data, pos)[0] != 8:
                            raise ValueError('Invalid resource value bounds')
                    yield name, config, values

    def values(self, positions):
        return {key: (self.data[pos+3], u32(self.data, pos+4)) for key, pos in positions.items()}

    def build(self):
        output = bytearray(self.data[:self.header])
        for kind, _, at, stop in self.top:
            output += self.pool.build() if kind == 1 else self.data[at:stop]
        struct.pack_into('<I', output, 4, len(output))
        return bytes(output)


def embed(base_bytes, translated_bytes):
    base, translated = Table(base_bytes), Table(translated_bytes)
    translations = {}
    for key, config, positions in translated.entries():
        # Overlay's default configuration is the authoritative translated value.
        if not any(config[4:]):
            translations[key] = translated.values(positions)
    if not translations or any(k[0] not in {'string', 'array', 'plurals'} for k in translations):
        raise ValueError('Expected only compiled string/array/plural translations')
    memo = {}; matched = set(); changed = 0; configs = 0
    def selected(key, bag_key):
        result = translations[key].get(bag_key)
        # Vietnamese uses the compiled "other" form. Existing Russian/Arabic
        # configurations may have extra few/many/zero/two slots.
        if result is None and key[0] == 'plurals':
            result = translations[key].get(0x01000004)
        return result
    for key, _, positions in base.entries():
        if key not in translations:
            continue
        matched.add(key); configs += 1
        for bag_key, pos in positions.items():
            old_type = base.data[pos+3]
            value = selected(key, bag_key)
            if old_type != 3:  # Keep references and non-string values intact.
                continue
            if value is None or value[0] != 3:
                raise ValueError('Missing translated string value for '+str((key, bag_key)))
            index = base.pool.append_from(translated.pool, value[1], memo)
            struct.pack_into('<I', base.data, pos+4, index); changed += 1
    if matched != set(translations):
        raise ValueError('Translation names missing from target resource table')
    result = base.build()
    # Parse it again and check every replaced value and styled span semantically.
    rebuilt = Table(result)
    for key, _, positions in rebuilt.entries():
        if key not in translations:
            continue
        for bag_key, (kind, index) in rebuilt.values(positions).items():
            if kind != 3:
                continue
            expected = selected(key, bag_key)[1]
            assert rebuilt.pool.strings[index] == translated.pool.strings[expected]
            spans = lambda pool, n: [(pool.strings[tag], first, last) for tag, first, last in pool.styles[n]]
            assert spans(rebuilt.pool, index) == spans(translated.pool, expected)
    return result, {'embedded_resources': len(matched), 'translated_configurations': configs,
                    'translated_string_values': changed, 'appended_pool_strings': len(memo),
                    'all_existing_locale_variants_translated': True}
