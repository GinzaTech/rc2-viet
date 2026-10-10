from pathlib import Path
from types import SimpleNamespace
import pytest
from rc2vi import phone as module


@pytest.fixture
def setup(tmp_path,monkeypatch):
    state={'devices':'List of devices attached\nA device model:Phone device:mondrian\n','commands':[],'root':True,'fly':True,'fail':False}
    class Adb:
        def __init__(self,*args,serial=''):self.serial=serial
        def command(self,*args,**kwargs):
            state['commands'].append((self.serial,*args))
            return state['devices']
        def shell(self,command,**kwargs):
            state['commands'].append((self.serial,command))
            if command=='getprop ro.product.model':return 'Phone'
            if command=='getprop ro.product.device':return 'mondrian'
            if command=='getprop ro.build.version.sdk':return '35'
            if command=='pm path dji.go.v5':return 'package:/data/app/fly/base.apk' if state['fly'] else ''
            if command=='dumpsys package dji.go.v5':return 'versionName=1.21.12 versionCode=3131451'
            if command=="su -c 'id'":
                if state['fail']:raise RuntimeError('denied')
                return 'uid=0(root)' if state['root'] else 'uid=2000(shell)'
            if command.startswith('cmd package resolve'):return state.get('component','dji.go.v5/.Main')
            return 'Status: ok'
    events=[]
    worker=module.PhoneWorker(tmp_path,tmp_path,lambda *e:events.append(e),Adb,lambda:None)
    return worker,state,events


def test_sole_phone_is_pinned_and_disconnect_does_not_target_other_phone(setup):
    worker,state,events=setup;worker.step()
    assert worker.selected=='A' and worker.adb.serial=='A'
    state['devices']='B device model:Other device:other'
    worker.request('apply');worker.step()
    assert worker.adb is None and worker.selected=='A'
    assert not any(c[0]=='B' for c in state['commands'])
    assert events[-1][0]=='error'


@pytest.mark.parametrize('devices,status',[('', 'waiting'),('A offline','offline'),('A unauthorized','unauthorized'),
                                        ('A device\nB device','choose'),('RC device model:rc331 device:rc331','waiting')])
def test_unavailable_or_ambiguous_devices_are_not_inspected(setup,devices,status):
    worker,state,events=setup;state['devices']=devices;worker.step()
    assert worker.adb is None and events[-1][0]==status
    assert len(state['commands'])==1


def test_select_refresh_and_open_are_pinned(setup):
    worker,state,events=setup;worker.step();worker.request('select','A');worker.step()
    assert worker.adb is None
    worker.step();worker.execute('fly',None)
    assert ('A','am start -W -n dji.go.v5/.Main') in state['commands']
    worker.execute('refresh',None);assert worker.adb is None
    worker.close();assert worker.stop_event.is_set()


@pytest.mark.parametrize('component',['','other.pkg/.Main','dji.go.v5/.Main;id'])
def test_open_component_validates_package_and_shell_syntax(setup,component):
    worker,state,events=setup;worker.step();state['component']=component
    with pytest.raises(ValueError):worker.execute('fly',None)
    assert not any('am start ' in c[-1] for c in state['commands'])


@pytest.mark.parametrize('fail',[True,False])
def test_inspect_fly_root_absent_and_missing_fly(setup,fail):
    worker,state,events=setup;state['root']=False;state['fail']=fail;worker.step()
    assert 'Chưa có quyền root' in events[-1][1]
    state['fly']=False;worker.execute('fly',None)
    assert 'chưa cài' in events[-1][1]


def test_worker_routes_overlay_requests_and_rejects_rc_actions(setup,monkeypatch):
    worker,state,events=setup;worker.step();calls=[]
    class Overlay:
        def __init__(self,*args,cancel=None):
            assert cancel is worker.stop_event
        def apply(self,adb,enable):calls.append((adb.serial,enable));return {'message':'done'}
    monkeypatch.setattr('rc2vi.phone_overlay.PhoneOverlay',Overlay)
    worker.execute('apply',None);worker.execute('disable',None);worker.execute('inspect',None)
    assert calls==[('A',True),('A',False)]
    with pytest.raises(ValueError,match='RC 2'):worker.execute('home',None)


def test_run_exits_cleanly_and_reports_read_errors(setup):
    worker,state,events=setup
    def step():worker.close();raise RuntimeError('read failed')
    worker.step=step;worker.run()
    assert events==[('error','read failed')]


def test_inspector_rejects_rc_before_fly_or_root_access():
    calls=[]
    def shell(command,**kwargs):calls.append(command);return 'rc331'
    with pytest.raises(ValueError,match='RC 2'):module.inspect_phone(SimpleNamespace(shell=shell))
    assert len(calls)==3
