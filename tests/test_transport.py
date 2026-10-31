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


def test_private_clients_cannot_implicitly_start_an_unfiltered_daemon(monkeypatch):
    from rc2vi.transport import RELAY_USB_FILTER
    calls=[]
    def run(argv,**kwargs):
        calls.append(argv)
        return SimpleNamespace(stdout=b'device',stderr=b'',returncode=0)
    monkeypatch.setattr('rc2vi.transport.subprocess.run',run)
    adb=Adb(Path('adb.exe'),54321,'127.0.0.1:45000')
    adb.usb_filter=RELAY_USB_FILTER
    for command in [('shell','getprop ro.serialno'),('pull','-Z','remote','local'),
                    ('get-state',),('--one-device',RELAY_USB_FILTER,'start-server')]:
        adb.command(*command)
    for argv in calls[:-1]:
        assert '--one-device' not in argv
        assert argv[argv.index('-H')+1]=='127.0.0.1'
    assert calls[-1].count('--one-device')==1
    assert calls[-1][calls[-1].index('--one-device')+1]==RELAY_USB_FILTER
    with pytest.raises(ValueError):adb.command('--one-device','another-device','start-server')
    assert len(calls)==4


def test_closed_pinned_client_cannot_spawn_an_orphan_adb_server(monkeypatch):
    import threading
    from rc2vi.transport import RELAY_USB_FILTER
    from rc2vi.hud_backup import PinnedAdb,HudTransportError
    calls=[]
    def run(argv,**kwargs):
        calls.append(argv)
        return SimpleNamespace(stdout=b'127.0.0.1:45000 device transport_id:7',stderr=b'',returncode=0)
    monkeypatch.setattr('rc2vi.transport.subprocess.run',run)
    source=Adb(Path('adb.exe'),54321,'127.0.0.1:45000')
    source.usb_filter=RELAY_USB_FILTER;source.closed_event=threading.Event()
    root=PinnedAdb(source,'RC2-A')
    assert root.adb.closed_event is source.closed_event
    assert root.adb.usb_filter==RELAY_USB_FILTER
    source.closed_event.set()
    with pytest.raises(HudTransportError):root.shell('getprop ro.serialno')
    with pytest.raises(HudTransportError):root.command('pull','remote','local')
    assert len(calls)==1  # Only the initial transport binding was dispatched.


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
        def send(self, data): self.output.extend(data); return len(data)
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
    else:assert check_standard_server() is True

@pytest.mark.parametrize('listening',[True,False])
def test_absent_server_does_not_block_initial_setup(monkeypatch,listening):
    def absent(*args,**kwargs):raise TimeoutError()
    monkeypatch.setattr('rc2vi.transport.socket.create_connection',absent)
    monkeypatch.setattr('rc2vi.transport.has_standard_listener',lambda:listening)
    if listening:
        with pytest.raises(RuntimeError):check_standard_server()
    else:assert check_standard_server() is False


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
        def send(self, value): self.output.extend(value); return len(value)
    link, target, events = Link(), Socket(), []
    relay = Relay(link, b'synthetic-public-key\0', lambda *args: events.append(args))
    try:
        relay._receive_usb(target)
        frames = PacketBuffer().feed(b''.join(link.writes))
        assert len(frames) == 1
        assert frames[0].command == 'AUTH' and frames[0].arg0 == 3
        assert bytes(target.output) == connected
        assert relay.connected.is_set()
        pairing=[event for event in events if event[0]=='pairing']
        assert len(pairing) == 1
    finally:
        relay.listener.close()


def test_relay_socket_backpressure_preserves_partial_write_offset():
    import socket
    relay=Relay(SimpleNamespace(),b'public',lambda *args:None)
    wire=pack('WRTE',3,4,bytes(range(256))*512)
    class Target:
        def __init__(self):self.output=bytearray();self.calls=0
        def send(self,data):
            self.calls+=1
            if self.calls in {2,4}:raise socket.timeout('busy ADB reader')
            size=min(len(data),8191)
            self.output.extend(data[:size]);return size
    target=Target()
    try:
        relay._send_socket(target,wire)
        assert bytes(target.output)==wire
        assert not relay.stop_event.is_set()
    finally:relay.listener.close()


def test_relay_socket_backpressure_remains_cancellable():
    import socket
    relay=Relay(SimpleNamespace(),b'public',lambda *args:None)
    class Target:
        def send(self,data):
            relay.stop_event.set()
            raise socket.timeout('busy ADB reader')
    try:
        with pytest.raises(EOFError):relay._send_socket(Target(),b'payload')
    finally:relay.listener.close()


def test_usb_failure_closes_adb_socket_instead_of_leaving_pull_blocked():
    import socket
    class Link:
        def read(self,size):raise OSError('synthetic USB disconnect')
    events=[];relay=Relay(Link(),b'public',lambda *args:events.append(args))
    left,right=socket.socketpair();relay.client=left;right.settimeout(.5)
    try:
        relay._receive_usb(left)
        assert relay.stop_event.is_set()
        assert right.recv(1)==b''
        assert relay.error=='synthetic USB disconnect'
        assert len(events)==1 and 'synthetic USB disconnect' in events[0][1]
        relay._fail(RuntimeError('later error'))
        assert relay.error=='synthetic USB disconnect' and len(events)==1
    finally:left.close();right.close();relay.listener.close()


@pytest.mark.parametrize('server_present',[False,True])
def test_isolated_adb_server_never_reopens_the_relays_physical_usb(monkeypatch,tmp_path,server_present):
    import threading
    from rc2vi import transport as backend
    calls=[]
    class Client:
        def __init__(self,binary,port=5037,serial=''):
            self.binary,self.port,self.serial=binary,port,serial
        def command(self,*args,**kwargs):
            calls.append((self.port,args))
            if args==('devices','-l'):return 'List of devices attached\nRC offline'
            if args==('get-state',):return 'device'
            return ''
    class Wire:
        address='127.0.0.1:45001'
        def __init__(self,*args):
            self.stop_event=threading.Event();self.connected=threading.Event();self.error=''
        def start(self):self.connected.set()
        def close(self):self.stop_event.set()
    keys=tmp_path/'.android';keys.mkdir()
    (keys/'adbkey').write_bytes(b'synthetic-key')
    (keys/'adbkey.pub').write_bytes(b'x'*128)
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    monkeypatch.setattr(backend,'Adb',Client)
    monkeypatch.setattr(backend,'Relay',Wire)
    monkeypatch.setattr(backend,'UsbLink',lambda device:object())
    monkeypatch.setattr(backend,'check_standard_server',lambda:server_present)
    monkeypatch.setattr(backend,'free_port',lambda:45002)
    connection=backend.Connection(SimpleNamespace(serial='RC'),tmp_path,lambda *args:None)
    try:
        adb=connection._open()
        assert adb.serial=='127.0.0.1:45001'
        assert (45002,('--one-device',backend.RELAY_USB_FILTER,'start-server')) in calls
        assert backend.RELAY_USB_FILTER!='RC'
        assert ((5037,('devices','-l')) in calls)==server_present
        assert ((5037,('kill-server',)) in calls)==server_present
    finally:connection.close()


def test_winusb_claims_exclusive_access_before_any_endpoint_io(monkeypatch):
    from rc2vi import usb_windows as backend
    calls=[]
    def create(*args):calls.append(args);return backend.INVALID
    monkeypatch.setattr(backend.kernel,'CreateFileW',create)
    with pytest.raises(OSError):backend.UsbLink(SimpleNamespace(path='synthetic-interface'))
    assert calls[0][2]==0


def test_owned_close_marks_disconnect_expected_before_stopping_adb(monkeypatch,tmp_path):
    from rc2vi import transport as backend
    from unittest.mock import Mock
    events=[]
    link=Mock();relay=backend.Relay(link,b'public',lambda *args:events.append(args))
    connection=backend.Connection(SimpleNamespace(serial='RC'),tmp_path,lambda *args:None)
    connection.relay=relay;connection.adb=SimpleNamespace(binary=Path('adb.exe'),port=45000)
    connection.owned=True
    class Control:
        def __init__(self,*args):pass
        def command(self,*args,**kwargs):
            assert relay.stop_event.is_set()
            relay._fail(EOFError('expected server shutdown'))
    monkeypatch.setattr(backend,'Adb',Control)
    connection.close()
    assert events==[] and relay.error==''


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


@pytest.fixture
def authorization(tmp_path, monkeypatch):
    """No real USB/processes/time: exercise Connection.open's whole lifetime."""
    import threading
    from rc2vi import transport as backend
    rig=SimpleNamespace(now=0.,calls=[],timeline=[],leases=[],links=[],relays=[],clients=[],events=[],
                        state=lambda attempt,now:'unauthorized',sleep_hook=None,
                        server_present=False,listing='List of devices attached\n',server_checks=0,
                        command_hook=None,pending_timeouts=[])
    keys=tmp_path/'.android';keys.mkdir()
    (keys/'adbkey').write_bytes(b'preserve-existing-private-key')
    (keys/'adbkey.pub').write_bytes(b'x'*128)
    class Lease:
        def __init__(self,serial):
            self.closed=False;rig.leases.append(self);rig.timeline.append(('lease',serial))
        def close(self):self.closed=True
    class Link:
        def __init__(self,device):
            assert all(link.closed for link in rig.links)
            self.closed=False;self.number=len(rig.links)+1
            rig.links.append(self);rig.timeline.append(('claim',self.number,rig.now))
        def close(self):
            self.closed=True;rig.timeline.append(('release',self.number,rig.now))
    class Wire:
        def __init__(self,link,public,emit):
            self.link,self.public=link,public
            self.address='127.0.0.1:'+str(45000+link.number)
            self.stop_event=threading.Event();self.connected=threading.Event();self.error=''
            rig.relays.append(self)
        def start(self):pass
        def close(self):self.stop_event.set();self.link.close()
    class Client:
        def __init__(self,binary,port=5037,serial=''):
            self.binary,self.port,self.serial=binary,port,serial
            rig.clients.append(self)
        def command(self,*args,**kwargs):
            if getattr(self,'closed_event',None) is not None and self.closed_event.is_set():
                raise ConnectionError('old client is closed')
            rig.calls.append((self.port,args,rig.now))
            if args and args[0] in ('connect','get-state') and self.port!=5037:
                rig.pending_timeouts.append(kwargs['timeout'])
            if rig.command_hook:rig.command_hook(self,args,kwargs)
            if args==('devices','-l'):return rig.listing
            if args==('kill-server',):rig.timeline.append(('kill',self.port,rig.now))
            if args==('get-state',):
                if self.port==5037:return 'device'
                relay=next(relay for relay in rig.relays if relay.address==self.serial)
                state=rig.state(relay.link.number,rig.now)
                if state=='device':relay.connected.set()
                return state
            return ''
        def shell(self,command,**kwargs):
            if getattr(self,'closed_event',None) is not None and self.closed_event.is_set():
                raise ConnectionError('old client is closed')
            rig.calls.append((self.port,('shell',command),rig.now))
            return 'RC' if command=='getprop ro.serialno' else ''
    def sleep(delay):
        rig.now+=delay
        if rig.sleep_hook:rig.sleep_hook()
    def server():
        rig.server_checks+=1
        return rig.server_present
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    monkeypatch.setattr(backend,'UsbLease',Lease)
    monkeypatch.setattr(backend,'UsbLink',Link)
    monkeypatch.setattr(backend,'Relay',Wire)
    monkeypatch.setattr(backend,'Adb',Client)
    monkeypatch.setattr(backend,'check_standard_server',server)
    monkeypatch.setattr(backend,'free_port',lambda:46000+len(rig.relays))
    monkeypatch.setattr(backend.time,'monotonic',lambda:rig.now)
    monkeypatch.setattr(backend.time,'sleep',sleep)
    rig.connection=backend.Connection(SimpleNamespace(serial='RC'),tmp_path,
                                      lambda *event:rig.events.append(event))
    rig.cancel,rig.reconnect=threading.Event(),threading.Event()
    rig.connection._opening_cancel=rig.cancel
    rig.connection._opening_reconnect_event=rig.reconnect
    yield rig
    rig.connection.close()
    assert all(lease.closed for lease in rig.leases)
    assert all(link.closed for link in rig.links)
    assert (keys/'adbkey').read_bytes()==b'preserve-existing-private-key'
    assert (keys/'adbkey.pub').read_bytes()==b'x'*128
    assert not any('keygen' in command for _,command,_ in rig.calls)


def test_unauthorized_open_retries_after_ten_seconds_under_one_controller_lease(authorization):
    rig=authorization
    rig.state=lambda attempt,now:'device' if attempt==2 else 'unauthorized'
    client=rig.connection.open()
    assert [item[2] for item in rig.timeline if item[0]=='claim']==[0.,10.]
    assert len(rig.leases)==1 and not rig.leases[0].closed
    assert rig.relays[0].public==rig.relays[1].public
    assert rig.timeline.index(('kill',46001,10.))<rig.timeline.index(('release',1,10.))
    assert rig.timeline.index(('release',1,10.))<rig.timeline.index(('claim',2,10.))
    old=next(client for client in rig.clients if getattr(client,'serial','')==rig.relays[0].address)
    assert old.closed_event.is_set() and not client.closed_event.is_set()
    with pytest.raises(ConnectionError):old.command('get-state')
    assert rig.server_checks==1
    assert [state for state,_ in rig.events]==['pairing','reconnecting','pairing','connected']


def test_manual_request_restarts_only_the_pending_session_and_resets_ten_second_timer(authorization):
    rig=authorization
    requested=False
    def request():
        nonlocal requested
        if rig.now>=3 and not requested:
            requested=True;rig.reconnect.set()
    rig.sleep_hook=request
    rig.state=lambda attempt,now:'device' if attempt==3 else 'unauthorized'
    rig.connection.open()
    assert [item[2] for item in rig.timeline if item[0]=='claim']==[0.,3.,13.]
    assert not rig.reconnect.is_set() and not rig.cancel.is_set()
    assert len(rig.leases)==1


def test_manual_request_already_pending_before_open_is_not_erased(authorization):
    rig=authorization;rig.reconnect.set()
    rig.state=lambda attempt,now:'device' if attempt==2 else 'unauthorized'
    rig.connection.open()
    assert [item[2] for item in rig.timeline if item[0]=='claim']==[0.,0.]
    assert not rig.reconnect.is_set()


def test_authorization_wins_over_simultaneous_manual_request_and_retry_deadline(authorization):
    rig=authorization
    def state(attempt,now):
        if now>=10:
            rig.reconnect.set()
            return 'device'
        return 'unauthorized'
    rig.state=state
    client=rig.connection.open()
    assert len(rig.links)==1 and rig.now==10
    assert not rig.reconnect.is_set()
    # No timer/background retry can interrupt a later write on this client.
    rig.reconnect.set();rig.now+=100
    client.shell('echo synthetic critical operation')
    assert len(rig.links)==1 and not rig.links[0].closed


def test_already_authorized_existing_server_is_reused_without_usb_retry(authorization):
    rig=authorization;rig.server_present=True
    rig.listing='List of devices attached\nRC device transport_id:4\nOTHER device transport_id:8'
    rig.reconnect.set()
    client=rig.connection.open()
    assert client.port==5037 and client.serial=='RC'
    assert not rig.links and not rig.relays
    assert not rig.reconnect.is_set()
    assert not any(command in {('kill-server',),('reconnect',)} for _,command,_ in rig.calls)


def test_retry_never_revisits_or_kills_an_unrelated_existing_server(authorization):
    rig=authorization;rig.server_present=True
    rig.listing='List of devices attached\nOTHER device transport_id:8\nRC offline'
    rig.state=lambda attempt,now:'device' if attempt==3 else 'unauthorized'
    rig.connection.open()
    assert rig.server_checks==1
    assert len([call for call in rig.calls if call[:2]==(5037,('devices','-l'))])==1
    assert len([call for call in rig.calls if call[:2]==(5037,('reconnect',))])==1
    assert not any(port==5037 and command==('kill-server',) for port,command,_ in rig.calls)


def test_automatic_authorization_retry_does_not_extend_overall_120_second_deadline(authorization):
    rig=authorization
    with pytest.raises(TimeoutError):rig.connection.open()
    assert rig.now==120
    assert [item[2] for item in rig.timeline if item[0]=='claim']==list(range(0,120,10))
    assert len(rig.leases)==1 and rig.leases[0].closed
    assert rig.connection.closed_event.is_set()


@pytest.mark.parametrize('close_connection',[False,True])
def test_cancel_or_close_while_waiting_never_creates_another_session(authorization,close_connection):
    rig=authorization
    def cancel():
        if rig.now>=3:
            if close_connection:rig.connection.close()
            else:rig.cancel.set()
    rig.sleep_hook=cancel
    with pytest.raises(ConnectionError if close_connection else InterruptedError):rig.connection.open()
    assert rig.now==3 and len(rig.links)==1
    assert rig.links[0].closed and rig.leases[0].closed


def test_cancel_takes_priority_over_a_simultaneous_manual_retry(authorization):
    rig=authorization
    def cancel():
        if rig.now>=3:rig.cancel.set();rig.reconnect.set()
    rig.sleep_hook=cancel
    with pytest.raises(InterruptedError):rig.connection.open()
    assert len(rig.links)==1
    assert not any(state=='reconnecting' for state,_ in rig.events)


def test_pre_cancelled_open_does_not_take_a_lease_or_claim_usb(authorization):
    rig=authorization;rig.cancel.set()
    with pytest.raises(InterruptedError):rig.connection.open()
    assert not rig.leases and not rig.links and not rig.calls


def test_late_get_state_response_does_not_extend_the_total_open_deadline(authorization):
    rig=authorization
    def slow_state(attempt,now):
        if now>=119:
            rig.now=121
            return 'device'
        return 'unauthorized'
    rig.state=slow_state
    with pytest.raises(TimeoutError):rig.connection.open()
    assert len(rig.links)==12
    assert not any(state=='connected' for state,_ in rig.events)
    assert rig.leases[0].closed


def test_cancellation_when_authentication_completes_still_stops_before_return(authorization):
    rig=authorization
    def cancelled_authorization(attempt,now):
        rig.cancel.set()
        return 'device'
    rig.state=cancelled_authorization
    with pytest.raises(InterruptedError):rig.connection.open()
    assert len(rig.links)==1
    assert not any(state=='connected' for state,_ in rig.events)


def test_blocked_connect_and_state_clients_still_retry_after_ten_seconds(authorization):
    import subprocess
    rig=authorization
    def block_first_session(client,args,kwargs):
        if len(rig.relays)==1 and args[0] in ('connect','get-state'):
            rig.now+=kwargs['timeout']
            raise subprocess.TimeoutExpired('synthetic pending authorization',kwargs['timeout'])
    rig.command_hook=block_first_session
    rig.state=lambda attempt,now:'device' if attempt==2 else 'unauthorized'
    rig.connection.open()
    claims=[item[2] for item in rig.timeline if item[0]=='claim']
    assert claims[0]==0 and 10<=claims[1]<=10.051
    assert all(0<timeout<=1 for timeout in rig.pending_timeouts)
    assert len(rig.leases)==1


def test_manual_request_is_observed_between_bounded_blocked_state_clients(authorization):
    import subprocess
    rig=authorization
    def block_state(client,args,kwargs):
        if len(rig.relays)==1 and args==('get-state',):
            rig.now+=kwargs['timeout']
            if rig.now>=2:rig.reconnect.set()
            raise subprocess.TimeoutExpired('synthetic pending authorization',kwargs['timeout'])
    rig.command_hook=block_state
    rig.state=lambda attempt,now:'device' if attempt==2 else 'unauthorized'
    rig.connection.open()
    assert len(rig.links)==2 and rig.now<=3
    assert not rig.reconnect.is_set() and not rig.cancel.is_set()
    assert all(timeout<=1 for timeout in rig.pending_timeouts)


def test_blocked_clients_do_not_extend_the_120_second_authorization_window(authorization):
    import subprocess
    rig=authorization
    def always_block(client,args,kwargs):
        if args[0] in ('connect','get-state'):
            rig.now+=kwargs['timeout']
            raise subprocess.TimeoutExpired('synthetic pending authorization',kwargs['timeout'])
    rig.command_hook=always_block
    with pytest.raises(TimeoutError):rig.connection.open()
    assert rig.now==pytest.approx(120)
    assert all(timeout<=1 for timeout in rig.pending_timeouts)
    assert rig.leases[0].closed and all(link.closed for link in rig.links)


def test_unexpected_state_io_failure_is_not_treated_as_pending_authorization(authorization):
    rig=authorization
    def disconnected(client,args,kwargs):
        if args==('get-state',):raise OSError('synthetic disconnected USB')
    rig.command_hook=disconnected
    with pytest.raises(OSError,match='disconnected USB'):rig.connection.open()
    assert len(rig.links)==1 and rig.links[0].closed


def test_direct_internal_open_failure_still_releases_its_owned_resources(authorization):
    rig=authorization
    def disconnected(client,args,kwargs):
        if args==('get-state',):raise OSError('synthetic disconnected USB')
    rig.command_hook=disconnected
    with pytest.raises(OSError):rig.connection._open()
    assert len(rig.links)==1 and rig.links[0].closed


def test_usb_cnxn_prevents_reset_while_local_adb_state_is_still_catching_up(authorization):
    rig=authorization
    def usb_authorized():
        if rig.now>=3:
            rig.relays[0].connected.set()
            rig.reconnect.set()
    rig.sleep_hook=usb_authorized
    rig.state=lambda attempt,now:'device' if now>=20 else 'offline'
    rig.connection.open()
    assert rig.now==20 and len(rig.links)==1
    assert not rig.reconnect.is_set()
    assert not any(state=='reconnecting' for state,_ in rig.events)
