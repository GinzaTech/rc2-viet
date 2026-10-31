"""Exact-source reuse and Android 15 idmap v9 schema validation."""
import copy
import struct


def identity(element):
    return (element.tag,tuple(sorted(element.attrib.items())),element.text or '',
            tuple(identity(child) for child in element))


def compatible_resources(old,new,translations):
    old_map={e.get('name'):e for e in old};new_map={e.get('name'):e for e in new}
    accepted=[];rejected=[]
    for element in translations:
        name=element.get('name')
        if name in old_map and name in new_map and identity(old_map[name])==identity(new_map[name]):
            accepted.append(copy.deepcopy(element))
        else:rejected.append(name)
    return accepted,rejected


def approve_phone_idmap(raw,target,overlay):
    if len(raw)<64:raise ValueError('Idmap điện thoại bị thiếu dữ liệu.')
    magic,version,_,_,policy,enforce=struct.unpack_from('<6I',raw)
    if (magic,version,policy,enforce)!=(0x504d4449,9,1,0):
        raise ValueError('Chỉ hỗ trợ idmap v9 Android 15 đã kiểm tra; phiên bản/policy không khớp.')
    offset=24;strings=[]
    for _ in range(4):
        if offset+4>len(raw):raise ValueError('Thiếu độ dài trường idmap.')
        size=struct.unpack_from('<I',raw,offset)[0];offset+=4
        if size>65536 or offset+size>len(raw):raise ValueError('Độ dài trường idmap không hợp lệ.')
        strings.append(raw[offset:offset+size].decode('utf-8'));offset+=(size+3)&~3
    if strings[:3]!=[target,overlay,''] or offset+24>len(raw):
        raise ValueError('Đường dẫn/overlay name trong idmap điện thoại không khớp.')
    output=bytearray(raw);struct.pack_into('<I',output,20,1)
    return bytes(output)
