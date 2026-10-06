"""Pure protocol and compatibility guards; independent of Windows/ADB."""
from dataclasses import dataclass
import re
import struct

SUPPORTED_APK = 'cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e'
OVERLAY_HASH = '2561aad5899e690abafb576841ffd6c716bdd2a42a73636f7fcb006e17f0a4ac'
PREVIOUS_OVERLAY_HASH = 'cc3ee8af5b1ce71fc4f22252881e0fc4dc536d26523f0e497b03858f138f4f38'
OLDER_OVERLAY_HASH = 'aaf1e5921070a4e6eb5fbf2d27c8e0842854ec9574963dad660b4f08b17980ed'
FIRST_OVERLAY_HASH = '350469acd1131e4f89af28094aa315bfed37c58afb54118b97699433ab1cb109'
INITIAL_OVERLAY_HASH = '064dea472f29ccd1406f9987df793d73346d44b0c77453cb22082f452fc0e519'
HOME_APK_HASH = '7e4ecbe3fde296ae006f66be2577194284f002f0d2f914d0eb86e78c28907168'
LAWNCHAIR_APK_HASH = 'd4200d0985169fd79ba1bd225d653f2a2fe7b50aa07cb0d05ca64c7623f86059'
FREEFCC_APK_HASH = 'da2c7dd3ce389d3bd04334188e5ec0fe060070d9c4ff9cf1127aadecf133f1e4'
OVERLAY_PACKAGE = 'local.dji.fly.vietnamese'
MAX_PAYLOAD = 1048576
COMMANDS = {'CNXN','AUTH','OPEN','OKAY','WRTE','CLSE','SYNC','STLS'}

@dataclass(frozen=True)
class Device:
    serial: str
    path: str

@dataclass(frozen=True)
class Frame:
    command: str
    arg0: int
    arg1: int
    payload: bytes
    wire: bytes

def pack(command: str, arg0: int, arg1: int, payload: bytes=b'') -> bytes:
    if command not in COMMANDS or len(payload)>MAX_PAYLOAD:
        raise ValueError('Unsupported ADB frame')
    code=int.from_bytes(command.encode('ascii'),'little')
    return struct.pack('<6I',code,arg0,arg1,len(payload),sum(payload)&0xffffffff,code^0xffffffff)+payload

class PacketBuffer:
    def __init__(self):
        self.pending=bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        self.pending.extend(data)
        frames=[]
        while len(self.pending)>=24:
            code,a0,a1,size,checksum,magic=struct.unpack_from('<6I',self.pending)
            try:
                command=code.to_bytes(4,'little').decode('ascii')
            except UnicodeDecodeError as exc:
                raise ValueError('Invalid ADB header') from exc
            if command not in COMMANDS or magic!=code^0xffffffff or size>MAX_PAYLOAD:
                raise ValueError('Invalid or oversized ADB header')
            if len(self.pending)<24+size:
                break
            wire=bytes(self.pending[:24+size])
            del self.pending[:24+size]
            frames.append(Frame(command,a0,a1,wire[24:],wire))
        return frames

def validate_package_path(path: str) -> str:
    if not re.fullmatch(r'/data/app/[A-Za-z0-9_~+=./-]+\.apk',path) or '..' in path.split('/'):
        raise ValueError('Đường dẫn APK không hợp lệ; công cụ đã dừng.')
    return path

def approve_idmap(raw: bytes, target: str, overlay: str) -> bytes:
    validate_package_path(target); validate_package_path(overlay)
    if len(raw)<537:
        raise ValueError('Cache tài nguyên bị thiếu dữ liệu.')
    magic,version,_,_,policy,enforce=struct.unpack_from('<5IB',raw)
    if (magic,version,policy,enforce)!=(0x504d4449,4,1,0):
        raise ValueError('Cấu trúc idmap khác Android 11 đã kiểm chứng.')
    if raw[21:277].split(b'\0')[0].decode('utf-8')!=target or raw[277:533].split(b'\0')[0].decode('utf-8')!=overlay:
        raise ValueError('Cache tài nguyên không thuộc hai ứng dụng đã chọn.')
    return raw[:20]+b'\x01'+raw[21:]

def validate_target(model: str, device: str, identity: str, version: str, code: int, digest: str) -> None:
    if model.replace('_',' ').strip()!='DJI RC 2' or device.strip()!='rc331':
        raise ValueError('Thiết bị không phải DJI RC 2 đã hỗ trợ.')
    if not identity.startswith('uid=0('):
        raise ValueError('Tay điều khiển chưa cung cấp shell root; công cụ không tự root thiết bị.')
    if version!='1.21.8' or code!=3115809 or digest.lower()!=SUPPORTED_APK:
        raise ValueError('Bản DJI Fly khác 1.21.8 đã kiểm chứng; chưa áp dụng bản dịch.')

def transport_conflict(output: str, serial: str) -> bool:
    for line in output.splitlines():
        parts=line.split()
        if len(parts)>=2 and parts[0] not in {'List','*'} and parts[0]!=serial:
            return True
    return False

def foreground_safe(output: str) -> bool:
    if 'dji.go.v5/' not in output:
        return True
    return 'dji.go.v5/com.dji.mainpageui.device.DJIDeviceActivity' in output
