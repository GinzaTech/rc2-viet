from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rc2vi import transport as backend


@pytest.fixture
def ready(monkeypatch,tmp_path):
    calls=[]
    class FakeAdb:
        def __init__(self,binary,port=5037,serial=''):
            self.binary,self.port,self.serial=binary,port,serial
        def command(self,*args,**kwargs):
            calls.append((self.serial,args))
            if args==('devices','-l'):return 'List of devices attached\nRC device model:DJI_RC_2\nPHONE device'
            if args==('get-state',):return 'device'
            raise AssertionError('Unexpected server mutation '+str(args))
        def shell(self,command,**kwargs):
            calls.append((self.serial,command));assert command=='getprop ro.serialno';return 'RC'
    monkeypatch.setattr(backend,'Adb',FakeAdb)
    monkeypatch.setattr(backend,'check_standard_server',lambda:None)
    link=Mock(side_effect=AssertionError('Ready ADB must not open a new USB session'))
    monkeypatch.setattr(backend,'UsbLink',link)
    events=[];connection=backend.Connection(SimpleNamespace(serial='RC'),tmp_path,lambda *e:events.append(e))
    return connection,calls,events,link


def test_ready_adb_is_reused_without_auth_or_key_or_server_changes(ready,monkeypatch):
    connection,calls,events,link=ready
    monkeypatch.setattr(Path,'home',lambda:(_ for _ in ()).throw(AssertionError('No key access needed')))
    adb=connection._open()
    assert adb.port==5037 and adb.serial=='RC' and connection.alive()
    assert not connection.owned and connection.relay is None
    link.assert_not_called()
    assert events[-1][0]=='connected'
    assert not any('kill-server' in str(c) or 'keygen' in str(c) for c in calls)


def test_closing_reused_server_releases_binding_without_killing_server(ready):
    connection,calls,_,_=ready;connection._open();connection.close()
    assert not connection.alive() and connection.adb is None
    assert not any('kill-server' in str(c) for c in calls)


def test_ready_transport_serial_mismatch_rejected(ready,monkeypatch):
    connection,_,_,link=ready
    monkeypatch.setattr(backend.Adb,'shell',lambda *a,**k:'OTHER')
    with pytest.raises(ValueError):connection._open()
    link.assert_not_called()
