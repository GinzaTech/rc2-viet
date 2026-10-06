from rc2vi.core import Device
from rc2vi.controller import choose_device, Worker

def test_multiple_controllers_need_selection():
    assert choose_device([Device('A','usbA'),Device('B','usbB')],'') is None
    assert choose_device([Device('A','usbA'),Device('B','usbB')],'B').serial=='B'

def test_absent_selected_device_never_falls_back():
    assert choose_device([Device('B','usbB')],'A') is None
    assert choose_device([Device('B','usbB')],'').serial=='B'

class FakeConnection:
    instances=[]
    def __init__(self,device,assets,emit):
        self.device=device;self.closed=False;self.calls=[]; self.instances.append(self)
    def open(self):return self
    def alive(self):return not self.closed
    def close(self):self.closed=True
    def shell(self,cmd):self.calls.append(cmd);return ''

class FakeActivator:
    def __init__(self):self.calls=[]
    def apply(self,adb):self.calls.append(adb.device.serial);return {'status':'enabled'}
    def disable(self,adb):return {'status':'disabled'}

def test_auto_apply_once_and_disconnect_cleanup(tmp_path):
    devices=[Device('A','usbA')];active=FakeActivator(); events=[]
    w=Worker(tmp_path,active,lambda *v:events.append(v),discover=lambda:list(devices),connection_factory=FakeConnection)
    w.step();w.step()
    assert active.calls==['A']
    connection=w.connection
    devices.clear();w.step()
    assert connection.closed and w.connection is None
    assert events[-1][0]=='waiting'

def test_pending_multiple_devices_make_no_connection(tmp_path):
    active=FakeActivator();events=[]
    w=Worker(tmp_path,active,lambda *v:events.append(v),discover=lambda:[Device('A','x'),Device('B','y')],connection_factory=FakeConnection)
    w.step()
    assert w.connection is None and not active.calls
    w.selected='B';w.step();assert active.calls==['B']

def test_manual_disable_is_not_immediately_reenabled(tmp_path):
    active=FakeActivator()
    w=Worker(tmp_path,active,lambda *v:None,discover=lambda:[Device('A','x')],connection_factory=FakeConnection)
    w.step();w.request('disable');w.step();w.step()
    assert active.calls==['A']

def test_manual_modes_and_stop_release(tmp_path):
    active=FakeActivator();events=[]
    w=Worker(tmp_path,active,lambda *v:events.append(v),discover=lambda:[Device('A','x')],connection_factory=FakeConnection)
    w.request('auto',False);w.step();assert active.calls==[]
    w.request('apply');w.step();assert active.calls==['A']
    w.request('lawnchair');w.step();assert any('app.lawnchair' in c for c in w.adb.calls)
    w.request('fly');w.step();assert any('dji.go.v5' in c for c in w.adb.calls)
    connection=w.connection;w.close();w.run();assert connection.closed

def test_selection_and_refresh_release_only_current(tmp_path):
    w=Worker(tmp_path,FakeActivator(),lambda *v:None,discover=lambda:[Device('A','x')],connection_factory=FakeConnection)
    w.step();old=w.connection;w.request('refresh');w.step();assert old.closed
    w.request('select','B');w.step();assert w.connection is None

def test_developer_action_runs_on_connected_worker(monkeypatch,tmp_path):
    calls=[];events=[]
    monkeypatch.setattr('rc2vi.controller.enable_developer_options',lambda adb:calls.append(adb.device.serial))
    w=Worker(tmp_path,FakeActivator(),lambda *e:events.append(e),discover=lambda:[Device('A','x')],connection_factory=FakeConnection)
    w.step();w.request('developer');w.step()
    assert calls==['A']
    assert events[-1]==('ready','Đã bật chế độ nhà phát triển và mở Developer options trên RC 2.')


def test_lawnchair_install_runs_on_connected_worker(monkeypatch,tmp_path):
    calls=[];events=[]
    def install(adb,assets,emit):
        calls.append((adb.device.serial,assets))
        return {'status':'lawnchair_installed'}
    monkeypatch.setattr('rc2vi.controller.install_lawnchair',install)
    w=Worker(tmp_path,FakeActivator(),lambda *e:events.append(e),discover=lambda:[Device('A','x')],connection_factory=FakeConnection)
    w.auto=False;w.step();w.request('install_lawnchair');w.step()
    assert calls==[('A',tmp_path)]
    assert events[-1][0]=='ready' and 'Lawnchair' in events[-1][1]


def test_lawnchair_install_without_connection_does_not_run(monkeypatch,tmp_path):
    calls=[];events=[]
    monkeypatch.setattr('rc2vi.controller.install_lawnchair',lambda *args:calls.append(args))
    w=Worker(tmp_path,FakeActivator(),lambda *e:events.append(e),discover=lambda:[],connection_factory=FakeConnection)
    w._command('install_lawnchair',None)
    assert not calls and events[-1]==('error','Chưa kết nối RC 2.')


def test_freefcc_install_dispatches_only_to_selected_controller(monkeypatch,tmp_path):
    calls=[];events=[]
    def install(adb,assets,emit):
        calls.append((adb.device.serial,assets))
        return {'status':'freefcc_installed'}
    monkeypatch.setattr('rc2vi.controller.install_freefcc',install)
    w=Worker(tmp_path,FakeActivator(),lambda *e:events.append(e),discover=lambda:[Device('A','x'),Device('B','y')],connection_factory=FakeConnection)
    w.selected='B';w.auto=False;w.step();w.request('install_freefcc');w.step()
    assert calls==[('B',tmp_path)]
    assert events[-1][0]=='ready' and 'FreeFCC' in events[-1][1]


def test_freefcc_install_without_connection_never_runs(monkeypatch,tmp_path):
    calls=[];events=[]
    monkeypatch.setattr('rc2vi.controller.install_freefcc',lambda *args:calls.append(args))
    w=Worker(tmp_path,FakeActivator(),lambda *e:events.append(e),discover=lambda:[],connection_factory=FakeConnection)
    w._command('install_freefcc',None)
    assert not calls and events[-1]==('error','Chưa kết nối RC 2.')
