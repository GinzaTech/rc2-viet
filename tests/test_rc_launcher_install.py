import hashlib
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import pytest
from app import App
from rc2vi import rc_launcher as installer


def test_installer_uses_own_package_and_signed_debug_artifact(tmp_path,monkeypatch):
    payload=b'RC launcher test'
    (tmp_path/'rc-launcher.apk').write_bytes(payload)
    monkeypatch.setattr(installer,'RC_LAUNCHER_HASH',hashlib.sha256(payload).hexdigest())
    calls=[]
    def install(adb,assets,app,emit):calls.append(app);return {'status':'rc_launcher_installed'}
    monkeypatch.setattr(installer,'install_bundled_apk',install)
    assert installer.install_rc_launcher(object(),tmp_path,lambda *a:None)['status']=='rc_launcher_installed'
    assert calls[0].package=='dev.rclauncher.rc2.debug'
    assert calls[0].component=='dev.rclauncher.rc2.debug/dev.rclauncher.rc2.RCLauncher'
    assert calls[0].asset_name=='rc-launcher.apk'


@pytest.mark.parametrize('label,action',[('Cài RC Launcher','install_rc_launcher'),('Mở RC Launcher','rc_launcher')])
def test_desktop_launcher_actions_stay_in_rc_mode(tmp_path,label,action):
    root=tk.Tk();root.withdraw()
    try:
        app=App(root,tmp_path,tmp_path,False);requests=[]
        app.worker=SimpleNamespace(request=lambda *a:requests.append(a))
        def buttons(w):
            for c in w.winfo_children():
                if isinstance(c,ttk.Button):yield c
                yield from buttons(c)
        next(b for b in buttons(root) if b.cget('text')==label).invoke()
        assert requests==[(action,None)]
        app.set_mode('phone');assert not app.rc_actions.winfo_ismapped()
    finally:root.destroy()
