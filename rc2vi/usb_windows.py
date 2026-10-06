"""Windows ADB interface enumeration and descriptor-validated WinUSB IO."""
import ctypes as C
from ctypes import wintypes as W
import uuid
from .core import Device

class GUID(C.Structure):
    _fields_=[('data1',W.DWORD),('data2',W.WORD),('data3',W.WORD),('data4',C.c_ubyte*8)]

class InterfaceData(C.Structure):
    _fields_=[('size',W.DWORD),('guid',GUID),('flags',W.DWORD),('reserved',C.c_size_t)]

class DeviceInfo(C.Structure):
    _fields_=[('size',W.DWORD),('guid',GUID),('devinst',W.DWORD),('reserved',C.c_size_t)]

class Descriptor(C.Structure):
    _pack_=1
    _fields_=[(name,C.c_ubyte) for name in ['length','kind','number','alternate','endpoints','klass','subclass','protocol','index']]

class Pipe(C.Structure):
    _fields_=[('kind',C.c_int),('id',C.c_ubyte),('max_packet',C.c_ushort),('interval',C.c_ubyte)]

setup=C.WinDLL('setupapi',use_last_error=True)
cfg=C.WinDLL('cfgmgr32',use_last_error=True)
kernel=C.WinDLL('kernel32',use_last_error=True)
usb=C.WinDLL('winusb',use_last_error=True)
ADB_GUID=GUID.from_buffer_copy(uuid.UUID('f72fe0d4-cbcb-407d-8814-9ed673d0dd6b').bytes_le)
INVALID=C.c_void_p(-1).value

setup.SetupDiGetClassDevsW.argtypes=[C.POINTER(GUID),W.LPCWSTR,W.HWND,W.DWORD]
setup.SetupDiGetClassDevsW.restype=W.HANDLE
setup.SetupDiEnumDeviceInterfaces.argtypes=[W.HANDLE,C.c_void_p,C.POINTER(GUID),W.DWORD,C.POINTER(InterfaceData)]
setup.SetupDiGetDeviceInterfaceDetailW.argtypes=[W.HANDLE,C.POINTER(InterfaceData),C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.POINTER(DeviceInfo)]
setup.SetupDiDestroyDeviceInfoList.argtypes=[W.HANDLE]
cfg.CM_Get_Parent.argtypes=[C.POINTER(W.DWORD),W.DWORD,W.ULONG]
cfg.CM_Get_Device_IDW.argtypes=[W.DWORD,W.LPWSTR,W.ULONG,W.ULONG]
kernel.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE]
kernel.CreateFileW.restype=W.HANDLE
kernel.CloseHandle.argtypes=[W.HANDLE]
usb.WinUsb_Initialize.argtypes=[W.HANDLE,C.POINTER(W.HANDLE)]
usb.WinUsb_Free.argtypes=[W.HANDLE]
usb.WinUsb_QueryInterfaceSettings.argtypes=[W.HANDLE,C.c_ubyte,C.POINTER(Descriptor)]
usb.WinUsb_QueryPipe.argtypes=[W.HANDLE,C.c_ubyte,C.c_ubyte,C.POINTER(Pipe)]
usb.WinUsb_SetPipePolicy.argtypes=[W.HANDLE,C.c_ubyte,W.ULONG,W.ULONG,C.c_void_p]
usb.WinUsb_ReadPipe.argtypes=[W.HANDLE,C.c_ubyte,C.c_void_p,W.ULONG,C.POINTER(W.ULONG),C.c_void_p]
usb.WinUsb_WritePipe.argtypes=usb.WinUsb_ReadPipe.argtypes

def checked(ok, operation):
    if not ok:
        raise OSError(C.get_last_error(),operation)

def instance_id(devinst):
    buffer=C.create_unicode_buffer(1024)
    if cfg.CM_Get_Device_IDW(devinst,buffer,1024,0)!=0:
        return ''
    return buffer.value

def discover() -> list[Device]:
    handle=setup.SetupDiGetClassDevsW(C.byref(ADB_GUID),None,None,0x12)
    if handle==INVALID:
        raise OSError(C.get_last_error(),'Không đọc được danh sách USB')
    found=[]
    try:
        index=0
        while True:
            iface=InterfaceData(); iface.size=C.sizeof(iface)
            if not setup.SetupDiEnumDeviceInterfaces(handle,None,C.byref(ADB_GUID),index,C.byref(iface)):
                if C.get_last_error()==259:
                    break
                raise OSError(C.get_last_error(),'USB enumeration failed')
            index+=1
            size=W.DWORD()
            setup.SetupDiGetDeviceInterfaceDetailW(handle,C.byref(iface),None,0,C.byref(size),None)
            if size.value<8 or size.value>16384:
                continue
            detail=C.create_string_buffer(size.value)
            C.cast(detail,C.POINTER(W.DWORD))[0]=8 if C.sizeof(C.c_void_p)==8 else 6
            info=DeviceInfo(); info.size=C.sizeof(info)
            checked(setup.SetupDiGetDeviceInterfaceDetailW(handle,C.byref(iface),detail,size,C.byref(size),C.byref(info)),'Interface detail')
            path=C.wstring_at(C.addressof(detail)+4)
            if 'vid_2ca3&pid_1021&mi_02' not in path.lower():
                continue
            parent=W.DWORD()
            if cfg.CM_Get_Parent(C.byref(parent),info.devinst,0)!=0:
                continue
            parent_id=instance_id(parent.value)
            if not parent_id.upper().startswith('USB\\VID_2CA3&PID_1021\\'):
                continue
            serial=parent_id.split('\\')[-1]
            if serial:
                found.append(Device(serial,path))
    finally:
        setup.SetupDiDestroyDeviceInfoList(handle)
    return sorted(found,key=lambda d:d.serial)

class UsbLink:
    def __init__(self, device: Device):
        self.file=None; self.handle=W.HANDLE(); self.closed=False
        self.file=kernel.CreateFileW(device.path,0xc0000000,3,None,3,0x40000000,None)
        if self.file==INVALID:
            self.file=None
            raise OSError(C.get_last_error(),'USB đang được ứng dụng khác giữ hoặc driver chưa sẵn sàng')
        try:
            checked(usb.WinUsb_Initialize(self.file,C.byref(self.handle)),'WinUSB init')
            desc=Descriptor()
            checked(usb.WinUsb_QueryInterfaceSettings(self.handle,0,C.byref(desc)),'USB descriptor')
            if (desc.number,desc.klass,desc.subclass,desc.protocol)!=(2,255,66,1):
                raise ValueError('Giao diện USB không đúng ADB của RC 2')
            pipes=[]
            for index in range(desc.endpoints):
                pipe=Pipe()
                checked(usb.WinUsb_QueryPipe(self.handle,0,index,C.byref(pipe)),'USB endpoint')
                if pipe.kind!=2 or pipe.max_packet!=512:
                    raise ValueError('USB endpoint khác cấu hình đã kiểm chứng')
                pipes.append(pipe.id)
            if set(pipes)!={3,0x84}:
                raise ValueError('Không đúng endpoint RC 2')
            timeout=W.ULONG(1000)
            for pipe in pipes:
                checked(usb.WinUsb_SetPipePolicy(self.handle,pipe,3,4,C.byref(timeout)),'USB timeout')
        except BaseException:
            self.close(); raise

    def write(self,data: bytes):
        if not data:
            return
        buffer=C.create_string_buffer(data)
        actual=W.ULONG()
        checked(usb.WinUsb_WritePipe(self.handle,3,buffer,len(data),C.byref(actual),None),'USB write')
        if actual.value!=len(data):
            raise IOError('USB short write')

    def read(self) -> bytes:
        buffer=C.create_string_buffer(65536); actual=W.ULONG()
        if not usb.WinUsb_ReadPipe(self.handle,0x84,buffer,65536,C.byref(actual),None):
            error=C.get_last_error()
            if error==121:
                raise TimeoutError('USB wait')
            raise OSError(error,'USB bị ngắt')
        return buffer.raw[:actual.value]

    def close(self):
        if self.closed:
            return
        self.closed=True
        if self.handle:
            usb.WinUsb_Free(self.handle); self.handle=W.HANDLE()
        if self.file is not None:
            kernel.CloseHandle(self.file); self.file=None
