"""Repeated cable/ADB loss must create new authorization sessions, preserving work."""
import json
from pathlib import Path
from types import SimpleNamespace
import threading
from unittest.mock import Mock

import pytest
from rc2vi import embedded_install as api
from rc2vi.core import PacketBuffer
from rc2vi.transport import Relay
from tests.test_embedded_install import package_dump


@pytest.fixture
def job(tmp_path,monkeypatch):
    value=api.Deployment(None,tmp_path/'assets',tmp_path/'work','RC2-A',connect_only=True,
                         cancel=threading.Event(),reconnect_event=threading.Event())
    monkeypatch.setattr(api.time,'sleep',lambda delay:None)
    return value


def setup_sessions(job,monkeypatch,on_open=None):
    sessions=[]
    class Link:
        def __init__(self):self.writes=[]
        def write(self,value):self.writes.append(value)
        def close(self):pass
    class Connection:
        def __init__(self):
            self.closed=False;self.cancel=None;self.link=Link()
            self.relay=Relay(self.link,b'same-existing-public-key\0',job.emit)
            sessions.append(self)
        def alive(self):return not self.closed
        def bind_cancel(self,cancel):self.cancel=cancel
        def open(self):
            if on_open:on_open(self,len(sessions))
            self.relay._pair()
            return SimpleNamespace(shell=lambda command,**kwargs:
                'RC2_ID_OK' if 'printf RC2_ID_OK' in command else 'com.android.settings/.Settings')
        def close(self):self.closed=True;self.relay.close()
    monkeypatch.setattr(api,'discover_rc2',lambda:[SimpleNamespace(serial=job.serial)])
    monkeypatch.setattr(api,'private_connection',lambda *args:Connection())
    monkeypatch.setattr(api,'pin_adb',lambda adb,serial:adb)
    return sessions


def test_three_usb_drops_each_create_a_fresh_allow_request(job,monkeypatch):
    sessions=setup_sessions(job,monkeypatch)
    count=0
    def pull():
        nonlocal count
        count+=1
        if count<=3:raise ConnectionError('synthetic USB unplug')
        return 'verified full file'
    try:
        assert job.retry(pull,'capture_apk')=='verified full file'
        assert len(sessions)==4 and all(s.closed for s in sessions[:-1])
        assert job.status['connection_attempts']==4
        for session in sessions:
            frames=PacketBuffer().feed(b''.join(session.link.writes))
            assert len(frames)==1 and frames[0].command=='AUTH' and frames[0].arg0==3
            assert frames[0].payload==b'same-existing-public-key\0'
        assert not job.cancel.is_set()
    finally:job.close()


def test_request_again_interrupts_a_pending_allow_wait_without_stopping_job(job,monkeypatch):
    def opening(connection,number):
        if number==1:
            job.reconnect_event.set()
            assert connection.cancel.is_set()
            raise InterruptedError('Reopen authorization session')
    sessions=setup_sessions(job,monkeypatch,on_open=opening)
    try:
        assert job.retry(lambda:'ready','connect_rc2')=='ready'
        assert len(sessions)==2 and sessions[0].closed
        assert not job.cancel.is_set() and not job.reconnect_event.is_set()
    finally:job.close()


def test_new_transport_binds_manual_retry_separately_from_stop(job, monkeypatch):
    def opening(connection, number):
        assert connection.reconnect is job.reconnect_event
        job.reconnect_event.set()
        assert not connection.cancel.is_set()
        connection.reconnect.clear()
    sessions = setup_sessions(job, monkeypatch, on_open=opening)
    factory = api.private_connection
    def modern(*args):
        connection = factory(*args)
        connection.bind_reconnect = lambda event: setattr(connection, 'reconnect', event)
        return connection
    monkeypatch.setattr(api, 'private_connection', modern)
    try:
        assert job.retry(lambda:'ready','connect_rc2') == 'ready'
        assert len(sessions) == 1 and not job.cancel.is_set()
    finally:
        job.close()


def test_missing_windows_device_waits_without_reusing_old_transport(job,monkeypatch):
    sessions=setup_sessions(job,monkeypatch)
    enumerations=0
    def discover():
        nonlocal enumerations
        enumerations+=1
        return [] if enumerations<3 else [SimpleNamespace(serial=job.serial)]
    monkeypatch.setattr(api,'discover_rc2',discover)
    try:
        assert job.retry(lambda:'ready','capture_apk')=='ready'
        assert enumerations==3 and len(sessions)==1
    finally:job.close()


@pytest.mark.parametrize('version,code',[('1.21.8',3115809),('1.21.10',3115981)])
def test_source_probe_labels_target_with_detected_version(job,version,code):
    job.shell=Mock(side_effect=['package:/data/app/fly/base.apk','a'*64+' base.apk',package_dump(version,code)])
    assert job.snapshot()['version']==version
    assert job.status['target_version']==version and job.status['target_code']==code
    events=[json.loads(line) for line in job.events.read_text('utf-8').splitlines()]
    assert 'APK đích: '+version in events[-1]['message']


def test_unsupported_source_probe_does_not_trigger_endless_reauthorization(job):
    job.shell=Mock(side_effect=['package:/data/app/fly/base.apk','a'*64+' base.apk',package_dump('1.21.9',3115900)])
    with pytest.raises(api.DeploymentValidationError):job.snapshot()


def test_usb_loss_during_screen_wake_returns_to_authorization_retry(job,monkeypatch):
    setup_sessions(job,monkeypatch)
    attempts=0
    def operation():
        nonlocal attempts
        attempts+=1
        if attempts==1:
            job.root.shell=Mock(side_effect=ConnectionError('USB gone during wake check'))
            raise api.DeviceUiWait('RC2_FOREGROUND_UNKNOWN')
        return 'ready'
    try:
        assert job.retry(operation,'upload_part-0000')=='ready'
        assert job.status['connection_attempts']==2
    finally:job.close()


def test_command_trace_identifies_failure_without_logging_output(job):
    secret_output=b'private binary contents'
    root=api.LoggedRoot(SimpleNamespace(command=lambda *a,**kw:secret_output),job.trace)
    assert root.command('pull','-Z','remote','local')==secret_output
    def fail(*args,**kwargs):raise ConnectionError('lost USB')
    root.root.command=fail
    with pytest.raises(ConnectionError):root.command('pull','-Z','remote','local')
    events=[json.loads(line) for line in job.trace_path.read_text('utf-8').splitlines()]
    assert [row['result'] for row in events]==['started','complete','started','failed']
    assert all(row['arguments']==['pull','-Z','remote','local'] for row in events)
    assert 'private binary contents' not in job.trace_path.read_text('utf-8')
