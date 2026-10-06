from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import pytest
from app import App

@pytest.mark.parametrize('accepted',[True,False])
def test_developer_button_requires_warning_before_queuing(tmp_path,monkeypatch,accepted):
    root=tk.Tk();root.withdraw()
    try:
        app=App(root,tmp_path,tmp_path,start_worker=False)
        requests=[]
        dialogs=[]
        def confirm(title,message,**kwargs):
            assert len(requests)==(len(dialogs) if accepted else 0)
            dialogs.append((title,message,kwargs))
            return accepted
        monkeypatch.setattr('app.messagebox.askokcancel',confirm)
        app.worker=SimpleNamespace(request=lambda *args:requests.append(args))
        def buttons(widget):
            for child in widget.winfo_children():
                if isinstance(child,ttk.Button):yield child
                yield from buttons(child)
        button=next(b for b in buttons(root) if b.cget('text')=='Bật chế độ nhà phát triển')
        button.invoke()
        assert requests==([('developer',None)] if accepted else [])
        assert len(dialogs)==1
        assert 'KHÔNG TẮT' in dialogs[0][1]
        assert 'USB debugging' in dialogs[0][1]
        assert 'khôi phục cài đặt gốc' in dialogs[0][1]
        assert 'xóa toàn bộ' in dialogs[0][1]
        assert dialogs[0][2]['parent'] is root
        assert dialogs[0][2]['default']=='cancel'
        button.invoke()
        assert len(dialogs)==2
    finally:root.destroy()


@pytest.mark.parametrize('title,action',[('Cài Lawnchair','install_lawnchair'),('Cài FreeFCC','install_freefcc')])
def test_install_button_only_queues_worker_request(tmp_path,title,action):
    root=tk.Tk();root.withdraw()
    try:
        app=App(root,tmp_path,tmp_path,start_worker=False);requests=[]
        app.worker=SimpleNamespace(request=lambda *args:requests.append(args))
        def buttons(widget):
            for child in widget.winfo_children():
                if isinstance(child,ttk.Button):yield child
                yield from buttons(child)
        next(b for b in buttons(root) if b.cget('text')==title).invoke()
        assert requests==[(action,None)]
    finally:root.destroy()
