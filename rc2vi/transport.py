"""Owned, cancellable loopback relay and isolated ADB client."""
from pathlib import Path
import os
import ctypes
from ctypes import wintypes
import hashlib
import struct
import socket
import subprocess
import threading
import time
from .core import PacketBuffer, pack, transport_conflict, Device
from .usb_windows import UsbLink

# This server is a TCP client of our WinUSB relay. It must never claim the
# physical RC USB interface a second time while the relay is reading it.
RELAY_USB_FILTER='RC2-RELAY-NO-PHYSICAL-USB'

class UsbLease:
    def __init__(self,serial):
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype=wintypes.HANDLE
        self.kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        name='Local\\RC2Vietnamese.USB.'+hashlib.sha256(serial.encode()).hexdigest()
        self.handle=self.kernel.CreateMutexW(None,False,name)
        error=ctypes.get_last_error()
        if not self.handle:raise OSError(error,'Không tạo được khóa kết nối RC 2')
        if error==183:
            self.close();raise RuntimeError('Một phiên công cụ khác đang giữ RC 2. Đóng phiên đó trước.')

    def close(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None

def has_standard_listener():
    api=ctypes.WinDLL('iphlpapi',use_last_error=True)
    api.GetExtendedTcpTable.argtypes=[ctypes.c_void_p,ctypes.POINTER(wintypes.DWORD),wintypes.BOOL,wintypes.ULONG,ctypes.c_int,wintypes.ULONG]
    for family,row_size,port_offset in [(2,24,8),(23,56,20)]:
        size=wintypes.DWORD()
        result=api.GetExtendedTcpTable(None,ctypes.byref(size),False,family,3,0)
        if result not in {0,122}:raise OSError(result,'Không kiểm tra được cổng ADB')
        if size.value<4 or size.value>1048576:raise RuntimeError('Bảng TCP không hợp lệ')
        buffer=ctypes.create_string_buffer(size.value)
        result=api.GetExtendedTcpTable(buffer,ctypes.byref(size),False,family,3,0)
        if result:raise OSError(result,'Không kiểm tra được cổng ADB')
        data=buffer.raw;count=struct.unpack_from('<I',data)[0]
        if 4+count*row_size>len(data):raise RuntimeError('Bảng TCP bị thiếu dữ liệu')
        for index in range(count):
            port=struct.unpack_from('<I',data,4+index*row_size+port_offset)[0]
            if socket.ntohs(port&65535)==5037:return True
    return False

def check_standard_server():
    # Check before invoking an ADB client: a protocol mismatch would make
    # the stock client restart an unrelated server automatically.
    try:sock=socket.create_connection(('127.0.0.1',5037),timeout=2)
    except (ConnectionRefusedError,TimeoutError):
        if has_standard_listener():raise RuntimeError('Server ADB hiện tại không phản hồi. Đóng phiên đó trước khi kết nối RC 2.')
        return False
    with sock:
        def read(size):
            result=b''
            while len(result)<size:
                chunk=sock.recv(size-len(result))
                if not chunk:raise RuntimeError('Server ADB hiện tại không trả lời đúng giao thức.')
                result+=chunk
            return result
        request=b'host:version';sock.sendall(f'{len(request):04x}'.encode()+request)
        if read(4)!=b'OKAY':raise RuntimeError('Cổng ADB đang do server khác sử dụng; đã dừng.')
        size=int(read(4),16)
        if size>16:raise RuntimeError('Phiên bản server ADB không hợp lệ.')
        if int(read(size),16)!=41:
            raise RuntimeError('Server ADB hiện tại dùng giao thức khác; đóng phiên đó trước khi kết nối RC 2.')
    return True

def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]

class Adb:
    def __init__(self, binary: Path, port: int=5037, serial: str=''):
        self.binary=binary; self.port=port; self.serial=serial
        self.closed_event=None; self.usb_filter=None; self.no_autostart=False

    def command(self,*args,timeout=20,check=True):
        if self.closed_event is not None and self.closed_event.is_set():
            raise ConnectionError('Phiên ADB đã đóng; cần kết nối và xin quyền USB lại.')
        argv=[str(self.binary),'-P',str(self.port)]
        # ADB only accepts --one-device when starting a daemon. Ordinary
        # clients explicitly target numeric loopback with -H: ADB treats this
        # as a remote server and will NOT implicitly start an unfiltered one
        # if it disappears. The daemon is created only by Connection._open.
        if self.usb_filter is not None:
            if '--one-device' in args:
                index=args.index('--one-device')
                if index+1>=len(args) or args[index+1]!=self.usb_filter:
                    raise ValueError('Không được thay bộ lọc USB của phiên ADB riêng.')
            if args and args[-1]=='start-server':
                if '--one-device' not in args:
                    argv+=['--one-device',self.usb_filter]
            else:
                if '--one-device' in args:
                    raise ValueError('Bộ lọc USB chỉ dùng khi tạo ADB server.')
                argv+=['-H','127.0.0.1']
        elif self.no_autostart:
            argv+=['-H','127.0.0.1']
        if self.serial:
            argv+=['-s',self.serial]
        environment=dict(os.environ)
        environment.pop('ADB_SERVER_SOCKET',None)
        result=subprocess.run(argv+list(args),capture_output=True,timeout=timeout,env=environment,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        output=result.stdout.decode('utf-8',errors='replace').replace('\r','').strip()
        if check and result.returncode:
            error=result.stderr.decode('utf-8',errors='replace').strip()
            raise RuntimeError(error or 'Lệnh ADB không thành công')
        return output

    def shell(self,command,timeout=20):
        return self.command('shell','-x',command,timeout=timeout)

class Relay:
    def __init__(self, link, public_key: bytes, emit):
        self.link=link; self.public_key=public_key; self.emit=emit
        self.stop_event=threading.Event(); self.connected=threading.Event()
        self.error=''; self.client=None; self.threads=[]
        self.write_lock=threading.Lock()
        self.failure_lock=threading.Lock()
        self.pair_lock=threading.Lock(); self.pair_sent=False
        self.pair_timer=None
        self.listener=socket.socket()
        self.listener.bind(('127.0.0.1',0)); self.listener.listen(1); self.listener.settimeout(1)
        self.address='127.0.0.1:'+str(self.listener.getsockname()[1])

    def start(self):
        thread=threading.Thread(target=self._accept,daemon=True)
        self.threads.append(thread); thread.start()

    def _read_exact(self,sock,size):
        out=bytearray()
        while len(out)<size and not self.stop_event.is_set():
            try:
                data=sock.recv(size-len(out))
            except socket.timeout:
                continue
            if not data:
                raise EOFError('Phiên ADB đã đóng')
            out.extend(data)
        if len(out)!=size:
            raise EOFError('Đã hủy kết nối')
        return bytes(out)

    def _send_usb(self,wire):
        with self.write_lock:
            self.link.write(wire[:24]); self.link.write(wire[24:])

    def _send_socket(self,sock,wire):
        # A socket timeout is a polling interval, as in _read_exact. sendall
        # loses the partial-write offset when a busy ADB client times out.
        pending=memoryview(wire)
        while pending:
            if self.stop_event.is_set():
                raise EOFError('Đã hủy kết nối')
            try:
                sent=sock.send(pending)
            except socket.timeout:
                continue
            if not sent:
                raise EOFError('Phiên ADB đã đóng')
            pending=pending[sent:]

    def _fail(self,error):
        with self.failure_lock:
            if self.stop_event.is_set():return
            self.error=str(error) or type(error).__name__
            self.stop_event.set()
        # Wake ADB's outstanding pull/push immediately. Otherwise a dead relay
        # leaves the client blocked until its whole-operation timeout expires.
        shutdown=getattr(self.client,'shutdown',None)
        if shutdown:
            try:shutdown(socket.SHUT_RDWR)
            except OSError:pass
        self.emit('disconnected','Kết nối USB đã gián đoạn: '+self.error)

    def _pair(self):
        # DJI's challenge workaround is AUTH3 after AUTH1, once per USB
        # session. An early/duplicate AUTH3 is not trusted-key authentication.
        with self.pair_lock:
            if self.pair_sent or self.stop_event.is_set() or self.connected.is_set(): return
            self.pair_sent=True
            self.emit('pairing','Chọn Allow USB debugging trên RC 2 nếu có hộp thoại.')
            self._send_usb(pack('AUTH',3,0,self.public_key))

    def _schedule_pair_fallback(self):
        # Preserve the existing RC2 compatibility request for firmware that
        # does not send a token, while allowing normal challenge ordering first.
        def request():
            try:self._pair()
            except (OSError,RuntimeError) as exc:
                self._fail(exc)
        with self.pair_lock:
            if self.stop_event.is_set() or self.pair_timer is not None:return
            self.pair_timer=threading.Timer(2,request)
            self.pair_timer.daemon=True; self.pair_timer.start()

    def _receive_usb(self,sock):
        parser=PacketBuffer()
        deadline=time.monotonic()+120
        try:
            while not self.stop_event.is_set():
                try:
                    pending=len(parser.pending)
                    if pending<24:
                        read_size=24-pending
                    else:
                        payload_size=int.from_bytes(parser.pending[12:16],'little')
                        read_size=min(65536,24+payload_size-pending)
                    data=self.link.read(read_size)
                except TimeoutError:
                    if not self.connected.is_set() and time.monotonic()>deadline:
                        raise TimeoutError('Hết thời gian chờ Allow USB debugging trên RC 2')
                    continue
                for frame in parser.feed(data):
                    if frame.command=='AUTH' and frame.arg0==1:
                        self._pair(); continue
                    if frame.command=='CNXN':
                        self.connected.set()
                    self._send_socket(sock,frame.wire)
        except Exception as exc:
            self._fail(exc)

    def _accept(self):
        try:
            while not self.stop_event.is_set():
                try:
                    sock,_=self.listener.accept(); break
                except socket.timeout:
                    continue
            else:
                return
            self.client=sock; sock.settimeout(1)
            reader=threading.Thread(target=self._receive_usb,args=(sock,),daemon=True)
            self.threads.append(reader); reader.start()
            first=True
            parser=PacketBuffer()
            while not self.stop_event.is_set():
                header=self._read_exact(sock,24)
                # Validate header/length before receiving any payload.
                import struct
                length=struct.unpack_from('<I',header,12)[0]
                if length>1048576:
                    raise ValueError('Gói ADB vượt giới hạn')
                frames=parser.feed(header+self._read_exact(sock,length))
                if len(frames)!=1:
                    raise ValueError('Gói ADB không đầy đủ')
                frame=frames[0]
                if first and frame.command!='CNXN':
                    raise ValueError('Không đúng gói khởi tạo ADB')
                self._send_usb(frame.wire)
                if first:
                    self._schedule_pair_fallback()
                    first=False
        except Exception as exc:
            self._fail(exc)

    def close(self):
        self.stop_event.set()
        with self.pair_lock:
            if self.pair_timer is not None:self.pair_timer.cancel()
        if self.client:
            try: self.client.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            self.client.close()
        self.listener.close()
        for thread in self.threads:
            if thread is not threading.current_thread(): thread.join(timeout=2)
        self.link.close()

class Connection:
    def __init__(self,device: Device,assets: Path,emit):
        self.device=device; self.assets=assets; self.emit=emit
        self.relay=None; self.adb=None; self.owned=False
        self.lease=None
        self.closed_event=threading.Event()

    def open(self):
        if self.closed_event.is_set():
            raise ConnectionError('Tạo phiên kết nối mới sau khi đóng ADB.')
        self.lease=UsbLease(self.device.serial)
        try:return self._open()
        except BaseException:self.close();raise

    def _open(self):
        binary=self.assets/'adb'/'adb.exe'
        server_present=check_standard_server()
        standard=Adb(binary)
        standard.no_autostart=True
        # Do not start a native USB-scanning server just to stop it again before
        # opening WinUSB. The relay owns its independently filtered server.
        devices=standard.command('devices','-l') if server_present else 'List of devices attached\n'
        rows=[line.split() for line in devices.splitlines()]
        ready=[row for row in rows if len(row)>=2 and row[0]==self.device.serial and row[1]=='device']
        if len(ready)==1:
            target=Adb(binary,serial=self.device.serial)
            target.no_autostart=True
            if (target.command('get-state',timeout=5,check=False)!='device'
                    or target.shell('getprop ro.serialno').strip()!=self.device.serial):
                raise ValueError('Phiên ADB sẵn sàng không khớp RC 2 đã chọn.')
            self.adb=target;self.owned=False
            target.closed_event=self.closed_event
            self.emit('connected','Đã dùng phiên ADB sẵn sàng của RC 2.')
            return target
        key_path=Path.home()/'.android'/'adbkey'
        if not key_path.exists():
            key_path.parent.mkdir(parents=True,exist_ok=True)
            standard.command('keygen',str(key_path))
        public_path=key_path.with_suffix('.pub')
        public=public_path.read_bytes().strip()+b'\0'
        if len(public)<100 or len(public)>8192:
            raise ValueError('Khóa ADB hiện tại không hợp lệ; công cụ không xóa hoặc thay khóa.')
        if transport_conflict(devices,self.device.serial):
            target=Adb(binary,serial=self.device.serial)
            target.no_autostart=True
            target.command('reconnect',timeout=8,check=False)
        elif server_present:
            standard.command('kill-server')
        link=None
        for attempt in range(12):
            try:
                link=UsbLink(self.device); break
            except OSError:
                if attempt==11: raise
                time.sleep(.15)
        self.relay=Relay(link,public,self.emit); self.relay.start()
        self.adb=Adb(binary,free_port())
        self.adb.usb_filter=RELAY_USB_FILTER
        self.adb.closed_event=self.closed_event
        self.owned=True
        try:
            self.adb.command('--one-device',RELAY_USB_FILTER,'start-server',timeout=15)
            self.emit('pairing','Đang ghép nối RC 2; chờ xác nhận USB trên tay.')
            self.adb.command('connect',self.relay.address,timeout=12,check=False)
            self.adb.serial=self.relay.address
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                cancel=getattr(self,'_opening_cancel',None)
                if cancel is not None and cancel.is_set():raise InterruptedError('Đã dừng chờ Allow USB debugging.')
                if self.relay.stop_event.is_set():
                    raise RuntimeError(self.relay.error or 'Kết nối USB đã ngắt')
                state=self.adb.command('get-state',timeout=5,check=False)
                if state=='device' and self.relay.connected.is_set():
                    self.emit('connected','Đã kết nối ADB với RC 2.')
                    return self.adb
                time.sleep(.5)
            raise TimeoutError('Chưa được cho phép USB debugging trên tay điều khiển.')
        except BaseException:
            self.close(); raise

    def alive(self):
        if self.relay is not None:return not self.relay.stop_event.is_set()
        if self.adb is None:return False
        try:return self.adb.command('get-state',timeout=3,check=False)=='device'
        except (OSError,RuntimeError,subprocess.TimeoutExpired):return False

    def close(self):
        self.closed_event.set()
        # Mark the expected disconnect before stopping our ADB server. Its
        # socket EOF must not be reported as a new USB failure to the GUI.
        if self.relay:self.relay.stop_event.set()
        if self.adb and self.owned:
            try:
                control=Adb(self.adb.binary,self.adb.port)
                control.usb_filter=RELAY_USB_FILTER
                control.command('kill-server',timeout=5,check=False)
            except (OSError,subprocess.TimeoutExpired): pass
        if self.relay:
            self.relay.close(); self.relay=None
        if self.lease:self.lease.close();self.lease=None
        self.owned=False;self.adb=None
