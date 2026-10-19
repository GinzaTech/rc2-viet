import struct
import pytest
from rc2vi.resource_embed import Pool, Table, embed


def pool(strings, styles=None, utf8=True):
    p = Pool.__new__(Pool)
    p.strings = list(strings); p.styles = styles or [()] * len(strings)
    p.flags = 0x100 if utf8 else 0
    return p


def table(kind, keys, strings, variants):
    types = pool([kind]).build(); names = pool(keys).build()
    chunks = []
    for language, entries in variants:
        config = bytearray(64); struct.pack_into('<I', config, 0, 64)
        config[8:10] = language if language else b'\0\0'
        offsets = []; payload = bytearray()
        for entry in entries:
            if entry is None:
                offsets.append(0xffffffff); continue
            key, values = entry; offsets.append(len(payload))
            if kind == 'plurals':
                payload += struct.pack('<HHIII', 16, 1, key, 0, len(values))
                for quantity, index in values.items():
                    payload += struct.pack('<IHBBI', quantity, 8, 0, 3, index)
            else:
                payload += struct.pack('<HHIHBBI', 8, 0, key, 8, 0, 3, values)
        size = 84+4*len(offsets)+len(payload)
        chunks.append(struct.pack('<HHIBBHII', 0x201, 84, size, 1, 0, 0,
                                  len(offsets),84+4*len(offsets)) + config +
                      struct.pack('<'+'I'*len(offsets), *offsets) + payload)
    header = bytearray(288)
    struct.pack_into('<HHII',header,0,0x200,288,288+len(types)+len(names)+sum(map(len,chunks)),0x7f)
    encoded='dji.go.v5'.encode('utf-16le'); header[12:12+len(encoded)] = encoded
    struct.pack_into('<I',header,268,288)
    struct.pack_into('<I',header,276,288+len(types))
    package = header+types+names+b''.join(chunks)
    global_pool = pool(strings).build()
    return struct.pack('<HHII',2,12,12+len(global_pool)+len(package),1)+global_pool+package


@pytest.mark.parametrize('utf8', [True, False])
def test_style_and_non_bmp_characters_survive_pool_append(utf8):
    original=pool(['protocol-token','b'],utf8=utf8)
    translated=pool(['b','Đã hoàn tất 😀'],[(),((0,0,2),)],utf8=not utf8)
    index=original.append_from(translated,1,{})
    read=Pool(original.build())
    assert read.strings[:2]==['protocol-token','b']
    assert read.strings[index]=='Đã hoàn tất 😀'
    assert [(read.strings[tag],a,b) for tag,a,b in read.styles[index]]==[('b',0,2)]


def test_shared_original_string_and_untranslated_resource_remain_intact():
    base=table('string',['visible','protocol'],['Original'],[(b'',[(0,0),(1,0)]),(b'en',[(0,0),(1,0)])])
    translated=table('string',['visible'],['Tiếng Việt'],[(b'',[(0,0)])])
    patched,report=embed(base,translated)
    r=Table(patched)
    for key,_,positions in r.entries():
        index=r.values(positions)[None][1]
        assert r.pool.strings[index]==('Tiếng Việt' if key[1]=='visible' else 'Original')
    assert report['embedded_resources']==1 and report['translated_configurations']==2


def test_existing_plural_quantities_use_vietnamese_other_form():
    other,one,few=0x01000004,0x01000006,0x01000008
    base=table('plurals',['count'],['one','other','few'],[(b'',[(0,{one:0,other:1})]),(b'ru',[(0,{few:2,other:1})])])
    translated=table('plurals',['count'],['%d mục'],[(b'',[(0,{other:0})])])
    result,report=embed(base,translated)
    read=Table(result)
    for _,_,positions in read.entries():
        assert all(read.pool.strings[i]=='%d mục' for _,i in read.values(positions).values())
    assert report['translated_string_values']==4


def test_missing_target_name_fails_before_publication():
    base=table('string',['visible'],['text'],[(b'',[(0,0)])])
    translated=table('string',['unrelated'],['Bản dịch'],[(b'',[(0,0)])])
    with pytest.raises(ValueError,match='missing from target'):
        embed(base,translated)


def test_truncated_table_is_rejected():
    with pytest.raises((ValueError,struct.error)):
        Table(b'\x02\x00bad')
