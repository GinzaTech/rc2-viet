import struct

import pytest

from scripts.hud_manifest import add_hud_provider, inspect_strings


def binary_manifest(utf8=True, exported=False):
    strings = ['application', 'provider', 'name', 'authorities', 'exported', 'initOrder',
               'com.AppGuard.AppGuard.TOSQY', 'dji.go.v5.CP']
    data = b''
    offsets = []
    for value in strings:
        offsets.append(len(data))
        encoded = value.encode('utf-8' if utf8 else 'utf-16le')
        data += (bytes([len(value), len(encoded)]) + encoded + b'\0') if utf8 else struct.pack('<H', len(value)) + encoded + b'\0\0'
    data += bytes((-len(data)) % 4)
    pool = struct.pack('<HH7I', 1, 28, 28 + 4 * len(strings) + len(data), len(strings), 0,
                       256 if utf8 else 0, 28 + 4 * len(strings), 0, offsets[0])[:-4]
    pool += struct.pack('<' + 'I' * len(offsets), *offsets) + data
    def start(name, attrs=()):
        values = b''.join(struct.pack('<iiiHBBI', -1, key, raw, 8, 0, kind, value) for key, raw, kind, value in attrs)
        return struct.pack('<HHIii', 0x102, 16, 36 + len(values), 1, -1) + struct.pack('<ii6H', -1, name, 20, 20, len(attrs), 0, 0, 0) + values
    def end(name):
        return struct.pack('<HHIiiii', 0x103, 16, 24, 1, -1, -1, name)
    nodes = start(0) + start(1, [(2, 6, 3, 6), (3, 7, 3, 7), (4, -1, 18, int(exported)), (5, -1, 16, 0x7fffffff)]) + end(1) + end(0)
    return struct.pack('<HHI', 3, 8, 8 + len(pool) + len(nodes)) + pool + nodes


@pytest.mark.parametrize('utf8', [True, False])
def test_provider_added_and_original_strings_preserved(utf8):
    original = binary_manifest(utf8)
    result = add_hud_provider(original)
    before, after = inspect_strings(original), inspect_strings(result)
    assert after[:len(before)] == before
    assert 'local.rc2.hud.HudProvider' in after
    assert 'dji.go.v5.rc2hud' in after
    assert struct.unpack_from('<I', result, 4)[0] == len(result)
    assert len(result) > len(original)


def test_rejects_second_provider_addition():
    result = add_hud_provider(binary_manifest())
    with pytest.raises(ValueError, match='already'):
        add_hud_provider(result)


def test_rejects_truncated_manifest():
    with pytest.raises(ValueError, match='Malformed'):
        add_hud_provider(binary_manifest()[:-1])


def test_rejects_missing_bootstrap_provider():
    original = binary_manifest().replace(b'com.AppGuard.AppGuard.TOSQY', b'com.AppOther.AppOther.TOSQY')
    with pytest.raises(ValueError, match='AppGuard'):
        add_hud_provider(original)


def test_new_provider_is_unexported_even_if_template_was_public():
    result = add_hud_provider(binary_manifest(exported=True))
    strings = inspect_strings(result)
    position = 8
    found = False
    while position < len(result):
        kind, _, size = struct.unpack_from('<HHI', result, position)
        if kind == 0x102 and strings[struct.unpack_from('<I', result, position + 20)[0]] == 'provider':
            attr_start, attr_size, count = struct.unpack_from('<3H', result, position + 24)
            attrs = {}
            for index in range(count):
                offset = position + 16 + attr_start + index * attr_size
                name = strings[struct.unpack_from('<I', result, offset + 4)[0]]
                attrs[name] = struct.unpack_from('<I', result, offset + 16)[0]
            if strings[attrs['name']] == 'local.rc2.hud.HudProvider':
                assert attrs['exported'] == 0
                found = True
        position += size
    assert found
