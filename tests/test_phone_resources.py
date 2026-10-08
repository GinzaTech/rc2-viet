import xml.etree.ElementTree as ET
import struct
import pytest
from rc2vi.phone_resources import compatible_resources, approve_phone_idmap


def test_only_identical_source_resources_are_reused():
    old=ET.fromstring('<resources><string name="a">Hello %1$s</string><string name="b">Old</string></resources>')
    new=ET.fromstring('<resources><string name="a">Hello %1$s</string><string name="b">New</string><string name="c">Other</string></resources>')
    vi=ET.fromstring('<resources><string name="a">Xin chào %1$s</string><string name="b">Cũ</string></resources>')
    accepted,rejected=compatible_resources(old,new,vi)
    assert [x.get('name') for x in accepted]==['a']
    assert rejected==['b']


def header(version=9,target='/data/app/fly/base.apk',overlay='/data/app/vi/base.apk'):
    data=struct.pack('<6I',0x504d4449,version,111,222,1,0)
    for text in [target,overlay,'','debug']:
        raw=text.encode();data+=struct.pack('<I',len(raw))+raw+b'\0'*((-len(raw))%4)
    return data+b'\0'*100


def test_phone_idmap_validates_v9_length_prefixed_paths_before_changing_flag():
    raw=header();out=approve_phone_idmap(raw,'/data/app/fly/base.apk','/data/app/vi/base.apk')
    assert out[:20]==raw[:20] and out[24:]==raw[24:]
    assert struct.unpack_from('<I',out,20)[0]==1


@pytest.mark.parametrize('raw',[header(version=4),header(target='/system/framework/framework-res.apk'),header()[:29],header()[:16]+struct.pack('<I',16)+header()[20:]])
def test_phone_idmap_rejects_unknown_format_target_or_policy(raw):
    with pytest.raises(ValueError):approve_phone_idmap(raw,'/data/app/fly/base.apk','/data/app/vi/base.apk')
