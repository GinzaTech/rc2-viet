import tkinter as tk
from types import SimpleNamespace
from app import App
from rc2vi.phone import parse_devices, inspect_phone


def test_phone_parser_keeps_offline_and_unauthorized_visible():
    devices=parse_devices('List of devices attached\nA device product:mondrian model:23013PC75G device:mondrian transport_id:1\nB unauthorized\nC offline\n')
    assert [(d.serial,d.state) for d in devices]==[('A','device'),('B','unauthorized'),('C','offline')]
    assert devices[0].model=='23013PC75G'


def test_inspection_absent_fly_never_requests_root_or_writes():
    calls=[]
    def shell(command,**kwargs):
        calls.append(command)
        return {'getprop ro.product.model':'Phone','getprop ro.product.device':'mondrian',
                'getprop ro.build.version.sdk':'35','pm path dji.go.v5':''}[command]
    result=inspect_phone(SimpleNamespace(shell=shell))
    assert result['status']=='fly_missing'
    assert calls[-1]=='pm path dji.go.v5'


def test_black_ui_routes_each_platform_to_its_own_worker(tmp_path):
    root=tk.Tk();root.withdraw()
    try:
        app=App(root,tmp_path,tmp_path,start_worker=False)
        rc=[];phone=[]
        app.worker=SimpleNamespace(request=lambda *a:rc.append(a))
        app.phone_worker=SimpleNamespace(request=lambda *a:phone.append(a))
        assert root.cget('background')=='#000000'
        app.set_mode('phone');app.send('apply')
        app.set_mode('rc');app.send('apply')
        assert phone==[('apply',None)]
        assert rc==[('apply',None)]
        app.set_mode('phone')
        assert not app.rc_actions.winfo_ismapped()
        assert app.phone_actions.winfo_manager()=='pack'
    finally:root.destroy()


def test_inactive_platform_events_do_not_replace_active_status(tmp_path):
    root=tk.Tk();root.withdraw()
    try:
        app=App(root,tmp_path,tmp_path,start_worker=False)
        app.set_mode('phone')
        app.emit_for('phone','ready','Điện thoại sẵn sàng')
        app.emit_for('rc','waiting','Cắm RC 2')
        app.poll()
        assert app.status.get()=='Điện thoại sẵn sàng'
        assert any('RC 2' in line for line in app.entries)
    finally:root.destroy()
