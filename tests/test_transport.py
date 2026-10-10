from pathlib import Path
from types import SimpleNamespace
import os
import pytest
from rc2vi.transport import UsbLease,Adb,check_standard_server
from rc2vi.transport import Relay
from rc2vi.core import pack

def test_second_instance_cannot_claim_same_controller():
    first=UsbLease('pytest-rc2-exclusive')
    try:
        with pytest.raises(RuntimeError):UsbLease('pytest-rc2-exclusive')
    finally:first.close()
    second=UsbLease('pytest-rc2-exclusive');second.close()

def test_adb_preserves_parent_environment_and_pins_port(monkeypatch):
    monkeypatch.setenv('ADB_SERVER_SOCKET','tcp:unrelated:1234')
    calls=[]
    def run(argv,**kwargs):
        calls.append((argv,kwargs))
        return SimpleNamespace(stdout=b'device\r\n',stderr=b'',returncode=0)
    monkeypatch.setattr('rc2vi.transport.subprocess.run',run)
    assert Adb(Path('adb.exe'),54321,'chosen').command('get-state')=='device'
    assert calls[0][0]==['adb.exe','-P','54321','-s','chosen','get-state']
    assert 'ADB_SERVER_SOCKET' not in calls[0][1]['env']
    assert os.environ['ADB_SERVER_SOCKET']=='tcp:unrelated:1234'


@pytest.mark.parametrize('payload_size', [512, 1024, 65536, 65537])
def test_usb_receiver_reads_the_adb_frame_length_without_waiting_for_a_short_packet(payload_size):
    wire = pack('WRTE', 3, 4, b'x' * payload_size)
    class Link:
        def __init__(self): self.chunks = [wire[:24], wire[24:]]; self.requests = []; self.waits = 0
        def read(self, size=65536):
            self.requests.append(size)
            if not self.chunks: raise EOFError('synthetic end')
            part = self.chunks[0]
            if len(part) % 512 == 0 and size > len(part):
                self.waits += 1
                if self.waits > 1: raise EOFError('full USB packet cannot complete an oversized read')
                raise TimeoutError('no short USB packet')
            out, tail = part[:size], part[size:]
            if tail: self.chunks[0] = tail
            else: self.chunks.pop(0)
            return out
    class Target:
        def __init__(self): self.output = bytearray()
        def sendall(self, data): self.output.extend(data)
    link, target = Link(), Target()
    relay = Relay(link, b'synthetic-public-key', lambda *args: None)
    try:
        relay._receive_usb(target)
        assert bytes(target.output) == wire
        assert link.requests[0] == 24
        assert link.requests[1] == min(payload_size, 65536)
        assert link.waits == 0
    finally:
        relay.listener.close()


@pytest.mark.parametrize('size', [24, 512, 65536])
def test_winusb_read_uses_the_requested_frame_size(monkeypatch, size):
    from rc2vi import usb_windows as backend
    import ctypes
    calls = []
    def read(handle, pipe, buffer, requested, transferred, overlapped):
        calls.append((pipe, requested))
        ctypes.memmove(buffer, b'x' * requested, requested)
        ctypes.cast(transferred, ctypes.POINTER(backend.W.ULONG)).contents.value = requested
        return True
    monkeypatch.setattr(backend.usb, 'WinUsb_ReadPipe', read)
    link = backend.UsbLink.__new__(backend.UsbLink)
    link.handle = backend.W.HANDLE(123)
    assert link.read(size) == b'x' * size
    assert calls == [(0x84, size)]


@pytest.mark.parametrize('size', [0, -1, 65537, True])
def test_winusb_read_rejects_invalid_sizes_without_driver_io(size):
    from rc2vi.usb_windows import UsbLink
    link = UsbLink.__new__(UsbLink)
    with pytest.raises(ValueError):
        link.read(size)

@pytest.mark.parametrize('version,blocked',[(b'0029',False),(b'001f',True)])
def test_protocol_check_prevents_automatic_server_replacement(monkeypatch,version,blocked):
    class Socket:
        def __init__(self):self.pending=b'OKAY0004'+version
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def sendall(self,data):assert data==b'000chost:version'
        def recv(self,size):
            data=self.pending[:size];self.pending=self.pending[size:];return data
    monkeypatch.setattr('rc2vi.transport.socket.create_connection',lambda *a,**k:Socket())
    if blocked:
        with pytest.raises(RuntimeError,match='giao thức khác'):check_standard_server()
    else:check_standard_server()

@pytest.mark.parametrize('listening',[True,False])
def test_absent_server_does_not_block_initial_setup(monkeypatch,listening):
    def absent(*args,**kwargs):raise TimeoutError()
    monkeypatch.setattr('rc2vi.transport.socket.create_connection',absent)
    monkeypatch.setattr('rc2vi.transport.has_standard_listener',lambda:listening)
    if listening:
        with pytest.raises(RuntimeError):check_standard_server()
    else:check_standard_server()


def test_relay_waits_for_device_challenge_before_requesting_authorization(monkeypatch):
    wire = pack('CNXN', 0x01000001, 1048576, b'host::\0')
    class Link:
        def __init__(self): self.writes = []
        def write(self, value): self.writes.append(value)
    class Socket:
        def __init__(self): self.pending = wire
        def settimeout(self, value): pass
        def recv(self, size):
            result, self.pending = self.pending[:size], self.pending[size:]
            return result
    class Listener:
        def accept(self): return Socket(), ('127.0.0.1', 1)
        def close(self): pass
    class Thread:
        def __init__(self, **kwargs): pass
        def start(self): pass
    link = Link()
    relay = Relay(link, b'synthetic-public-key\0', lambda *args: None)
    relay.listener.close()
    relay.listener = Listener()
    monkeypatch.setattr('rc2vi.transport.threading.Thread', Thread)
    relay._accept()
    assert b''.join(link.writes) == wire


def test_relay_requests_public_key_authorization_once_after_challenge():
    from rc2vi.core import PacketBuffer
    challenge = pack('AUTH', 1, 0, b'synthetic-token')
    connected = pack('CNXN', 0x01000001, 1048576, b'device::\0')
    class Link:
        def __init__(self):
            self.pending = challenge + challenge + connected
            self.writes = []
        def read(self, size):
            if not self.pending: raise EOFError('synthetic end')
            result, self.pending = self.pending[:size], self.pending[size:]
            return result
        def write(self, value): self.writes.append(value)
    class Socket:
        def __init__(self): self.output = bytearray()
        def sendall(self, value): self.output.extend(value)
    link, target, events = Link(), Socket(), []
    relay = Relay(link, b'synthetic-public-key\0', lambda *args: events.append(args))
    try:
        relay._receive_usb(target)
        frames = PacketBuffer().feed(b''.join(link.writes))
        assert len(frames) == 1
        assert frames[0].command == 'AUTH' and frames[0].arg0 == 3
        assert bytes(target.output) == connected
        assert relay.connected.is_set()
        assert len(events) == 1 and events[0][0] == 'pairing'
    finally:
        relay.listener.close()


@pytest.mark.parametrize('blocked', ['', 'connected', 'cancelled', 'already_sent'])
def test_delayed_compatibility_pairing_never_duplicates_or_outlives_session(monkeypatch, blocked):
    timers = []
    class Timer:
        def __init__(self, delay, callback):
            self.delay, self.callback, self.cancelled = delay, callback, False
            timers.append(self)
        def start(self): pass
        def cancel(self): self.cancelled = True
    class Link:
        def __init__(self): self.writes = []
        def write(self, value): self.writes.append(value)
        def close(self): pass
    monkeypatch.setattr('rc2vi.transport.threading.Timer', Timer)
    link = Link()
    relay = Relay(link, b'synthetic-public-key\0', lambda *args: None)
    try:
        relay._schedule_pair_fallback()
        assert len(timers) == 1 and timers[0].delay >= 1
        assert not link.writes
        if blocked == 'connected': relay.connected.set()
        if blocked == 'cancelled': relay.close()
        if blocked == 'already_sent': relay._pair()
        before = len(link.writes)
        timers[0].callback()
        assert len(link.writes) == (2 if not blocked else before)
        relay.close()
        assert timers[0].cancelled
    finally:
        relay.listener.close()
