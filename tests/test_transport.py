from pathlib import Path
from types import SimpleNamespace
import os
import pytest
from rc2vi.transport import UsbLease,Adb,check_standard_server

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
