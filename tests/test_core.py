import struct
import pytest
from rc2vi.core import PacketBuffer, pack, approve_idmap, validate_target, validate_package_path, transport_conflict, foreground_safe, SUPPORTED_APK

def test_fragmented_packet_roundtrip():
    payload = b"host::test\0"
    wire = pack("CNXN", 0x1000001, 1048576, payload)
    parser = PacketBuffer()
    assert parser.feed(wire[:7]) == []
    assert parser.feed(wire[7:25]) == []
    frame = parser.feed(wire[25:])[0]
    assert frame.command == "CNXN"
    assert frame.payload == payload

def test_multiple_frames_and_bad_magic():
    parser = PacketBuffer()
    assert len(parser.feed(pack("OKAY", 1, 1) + pack("CLSE", 1, 1))) == 2
    bad = bytearray(pack("OKAY", 1, 1)); bad[20] ^= 1
    with pytest.raises(ValueError): PacketBuffer().feed(bytes(bad))

def test_oversized_header_fails_without_body():
    code = int.from_bytes(b"WRTE", "little")
    with pytest.raises(ValueError): PacketBuffer().feed(struct.pack("<6I", code, 1, 1, 1048577, 0, code ^ 0xffffffff))

def header(target, overlay, *, flag=0, version=4):
    return struct.pack("<5IB", 0x504d4449, version, 1, 2, 1, flag) + target.encode().ljust(256,b"\0") + overlay.encode().ljust(256,b"\0") + b"\0"*4

def test_idmap_changes_only_one_verified_byte():
    target='/data/app/dji.go.v5-abc/base.apk'; overlay='/data/app/local.dji.fly.vietnamese-abc/base.apk'
    original=header(target,overlay)
    approved=approve_idmap(original,target,overlay)
    assert [i for i,(a,b) in enumerate(zip(original,approved)) if a!=b] == [20]
    assert original[20] == 0

@pytest.mark.parametrize('variant',['wrong_path','version','flag','short'])
def test_unknown_idmap_is_rejected(variant):
    t='/data/app/dji.go.v5-abc/base.apk'; o='/data/app/local.dji.fly.vietnamese-abc/base.apk'
    raw=header(t,o)
    if variant=='wrong_path': t='/data/app/other/base.apk'
    if variant=='version': raw=header(t,o,version=5)
    if variant=='flag': raw=header(t,o,flag=1)
    if variant=='short': raw=raw[:200]
    with pytest.raises(ValueError): approve_idmap(raw,t,o)

@pytest.mark.parametrize('path',['/system/base.apk','/data/app/x/base.apk;reboot','/data/app/x/../base.apk','/data/app/x/base.apk\n'])
def test_unsafe_package_paths(path):
    with pytest.raises(ValueError): validate_package_path(path)

def test_target_guards():
    validate_target('DJI RC 2','rc331','uid=0(root)','1.21.8',3115809,SUPPORTED_APK)
    for args in [('Phone','other','uid=0(root)','1.21.8',3115809,SUPPORTED_APK),('DJI RC 2','rc331','uid=2000(shell)','1.21.8',3115809,SUPPORTED_APK),('DJI RC 2','rc331','uid=0(root)','1.22.0',3115809,SUPPORTED_APK),('DJI RC 2','rc331','uid=0(root)','1.21.8',3115809,'0'*64)]:
        with pytest.raises(ValueError): validate_target(*args)


def test_installed_hud_build_is_explicitly_allowed():
    validate_target('DJI RC 2', 'rc331', 'uid=0(root)', '1.21.8', 3115809,
                    'abeff2051350dde3dfc524cd1f3ebd63864349e7366cd9f84406cee9778ba750')

def test_other_transports_are_not_interrupted():
    assert not transport_conflict('List of devices attached\nRC2 offline\n','RC2')
    assert transport_conflict('List of devices attached\nRC2 offline\nPHONE device\n','RC2')

def test_flight_and_unknown_fly_activity_block_changes():
    assert foreground_safe('mResumedActivity: dji.go.v5/com.dji.mainpageui.device.DJIDeviceActivity')
    assert foreground_safe('mResumedActivity: app.lawnchair/.LawnchairLauncher')
    assert not foreground_safe('mResumedActivity: dji.go.v5/com.dji.fpv.DJIFpvActivity')
    assert not foreground_safe('mResumedActivity: dji.go.v5/unknown.Activity')
