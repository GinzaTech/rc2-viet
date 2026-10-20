"""Desktop integration stays offline until an explicit, guarded device action."""
import json
import threading
import tkinter as tk
from pathlib import Path

import pytest

import auto_patch_app
from rc2vi.desktop_theme import ctk


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    monkeypatch.setattr(auto_patch_app,'discover',lambda: [])
    root=ctk.CTk()
    root.withdraw()
    app=auto_patch_app.App(root,tmp_path/'assets',tmp_path/'work')
    try:
        yield app,root
    finally:
        if app.thread:
            app.cancel.set()
            app.thread.join(timeout=3)
        if app.animation_editor:
            app.animation_editor.close()
        app.progress.stop()
        for callback in root.tk.call('after','info'):
            root.tk.call('after','cancel',callback)
        root.destroy()


def test_editor_opens_without_rc2_and_uses_shared_install_state(desktop):
    app,root=desktop
    editor=app.open_animation()
    root.update()
    assert editor is app.open_animation()
    assert editor.serial_var is app.serial
    assert editor.grounded_var is app.grounded
    assert editor.device_status_var is app.status
    assert editor.get_smoke_state()['layers']==2
    assert editor.window is root and editor.view.winfo_toplevel() is root
    assert editor.embedded and app.active_page == 'animation'
    assert not any(isinstance(child, tk.Toplevel) for child in root.winfo_children())
    assert 'disabled' not in str(app.animation_button['state'])
    assert app.thread is None


def test_back_preserves_draft_raw_input_and_each_page_geometry(desktop):
    app, root = desktop
    root.deiconify(); root.geometry('900x760+40+50'); root.update()
    original_geometry = root.geometry()
    editor = app.open_animation(); root.update()
    assert editor.back_button.winfo_viewable()
    root.geometry('1100x700+60+70'); root.update()
    animation_geometry = root.geometry()
    editor.layer_vars['text'].set('GinzaTech bản đang sửa')
    assert editor._apply_forms()
    editor.layer_vars['font_size'].set('chưa nhập xong')
    editor.time_var.set(.9)
    editor._playing = True
    editor.back_button.invoke(); root.update()
    assert app.active_page == 'patch' and app.patch_page.winfo_viewable()
    assert not editor.view.winfo_viewable() and not editor._playing
    assert root.geometry() == original_geometry and root.wm_minsize() == (800, 680)
    assert 'Tiếng Việt' in root.title()
    assert app.open_animation() is editor
    root.update()
    assert root.geometry() == animation_geometry
    assert editor.layer_vars['text'].get() == 'GinzaTech bản đang sửa'
    assert editor.layer_vars['font_size'].get() == 'chưa nhập xong'
    assert editor.time_var.get() == .9
    assert editor.dirty and editor.selected == 0
    editor.layer_vars['font_size'].set('180')
    assert editor._apply_forms()


def test_back_keeps_export_running_and_close_reveals_invalid_hidden_form(desktop):
    app, root = desktop
    editor = app.open_animation(); root.update()
    finish = threading.Event()
    editor._worker = threading.Thread(target=lambda: finish.wait(3))
    editor._worker.start()
    try:
        editor.layer_vars['font_size'].set('incomplete')
        assert app.show_patch()
        assert editor.busy and not editor._cancel.is_set()
        app.close()
        assert not app.closing and not editor._closing
        assert app.active_page == 'animation' and editor._visible
        assert editor.layer_vars['font_size'].get() == 'incomplete'
        assert root.winfo_exists() and not editor._cancel.is_set()
    finally:
        finish.set(); editor._worker.join(timeout=3)
        editor.layer_vars['font_size'].set('180'); editor._apply_forms()


def test_embedded_editor_close_keeps_root_and_can_reopen(desktop):
    app, root = desktop
    first = app.open_animation(); root.update()
    assert first.close()
    assert root.winfo_exists() and first._destroyed
    second = app.open_animation(); root.update()
    assert second is not first and second._visible
    assert second.window is root and second.view.winfo_exists()
    assert app.show_patch()
    assert not any(isinstance(child, tk.Toplevel) for child in root.winfo_children())


@pytest.mark.parametrize('geometry', ['1050x650', '1240x760'])
def test_embedded_back_and_install_controls_fit_window(desktop, geometry):
    app, root = desktop
    root.deiconify()
    editor = app.open_animation()
    root.geometry(geometry)
    editor.set_device_panel(True)
    root.update()
    left, top = root.winfo_rootx(), root.winfo_rooty()
    right, bottom = left + root.winfo_width(), top + root.winfo_height()
    for widget in (editor.back_button, editor.name_entry, editor.preview_canvas,
                   editor.export_button, editor.install_boot_button,
                   editor.install_shutdown_button, editor.restore_boot_button,
                   editor.restore_shutdown_button, editor.status_label):
        assert widget.winfo_viewable()
        assert left <= widget.winfo_rootx() < widget.winfo_rootx() + widget.winfo_width() <= right
        assert top <= widget.winfo_rooty() < widget.winfo_rooty() + widget.winfo_height() <= bottom


def test_install_requires_selected_controller_and_ground_confirmation(desktop,monkeypatch):
    app,_=desktop
    errors=[]
    monkeypatch.setattr(auto_patch_app.messagebox,'showerror',lambda *a,**kw:errors.append(a))
    assert app.install_animation('not-opened.zip') is False
    app.serial.set('TEST-RC2')
    assert app.install_animation('not-opened.zip') is False
    assert len(errors)==2 and app.thread is None


def test_idle_usb_request_is_available_without_ground_confirmation(desktop, monkeypatch):
    from rc2vi import usb_authorization
    app, root = desktop
    seen = []
    def authorize(assets, serial, **options):
        seen.append((serial, options['cancel'], options['reconnect_event']))
        return {'status':'authorized', 'authorized_verified':True, 'device_modified':False}
    monkeypatch.setattr(usb_authorization, 'authorize_usb', authorize)
    app.serial.set('TEST-RC2'); app.controls()
    assert not app.grounded.get()
    assert app.reconnect_button.cget('state') == 'normal'
    assert app.request_reconnect()
    app.thread.join(timeout=3)
    app.poll()
    assert seen == [('TEST-RC2', app.cancel, app.reconnect_event)]
    assert not app.usb_authorization_job and not app.usb_recovery
    report = json.loads((app.base/'usb-authorization/last-result.json').read_text('utf-8'))
    assert report['authorized_verified'] and report['device_modified'] is False
    assert 'Đã xác minh quyền USB' in app.status.get()


def test_verified_usb_permission_is_not_reported_failed_when_local_report_cannot_save(desktop, monkeypatch):
    from rc2vi import usb_authorization
    app, _root = desktop
    monkeypatch.setattr(usb_authorization, 'authorize_usb', lambda *a, **kw:
                        {'authorized_verified':True, 'device_modified':False})
    def fail_report(*args):
        raise OSError('Không ghi được báo cáo')
    monkeypatch.setattr(auto_patch_app, 'atomic_json', fail_report)
    app.serial.set('TEST-RC2')
    assert app.request_reconnect()
    app.thread.join(timeout=3)
    app.poll()
    assert 'Đã xác minh quyền USB' in app.status.get()
    assert 'chưa lưu được báo cáo' in app.log.get('1.0', 'end')
    assert not app.usb_recovery


def test_waiting_animation_manual_reconnect_uses_same_job_and_both_buttons(desktop):
    app, root = desktop
    app.serial.set('TEST-RC2')
    editor = app.open_animation(); root.update()
    finish = threading.Event()
    app.thread = threading.Thread(target=lambda: finish.wait(3))
    app.thread.start(); app.animation_job = True; app.usb_recovery = True
    try:
        app.controls(); editor._update_controls()
        assert app.reconnect_button.cget('state') == 'normal'
        assert editor.reconnect_button.cget('state') == 'normal'
        worker = app.thread
        editor.reconnect_button.invoke()
        assert app.reconnect_event.is_set() and not app.cancel.is_set()
        assert app.thread is worker
        app.events.put(('connected','Đã kết nối'))
        app.poll(); editor._update_controls()
        assert not app.usb_recovery
        assert app.reconnect_button.cget('state') == 'disabled'
        assert editor.reconnect_button.cget('state') == 'disabled'
        assert app.request_reconnect() is False
    finally:
        finish.set(); app.thread.join(timeout=3)


def test_stop_authorization_never_marks_previous_apk_job_stopped(desktop, monkeypatch):
    from rc2vi import usb_authorization
    app, root = desktop
    previous = app.base/'previous-apk-work'; previous.mkdir(parents=True)
    app.current_work = previous
    started = threading.Event()
    def authorize(assets, serial, **options):
        started.set()
        assert options['cancel'].wait(3)
        raise InterruptedError('Đã dừng xin quyền USB')
    monkeypatch.setattr(usb_authorization, 'authorize_usb', authorize)
    app.serial.set('TEST-RC2')
    assert app.request_reconnect() and started.wait(1)
    app.stop(); app.thread.join(timeout=3); app.poll()
    assert app.cancel.is_set() and not (previous/'STOP').exists()
    assert app.current_work == previous


@pytest.mark.parametrize('geometry', ['900x760', '800x680'])
def test_main_actions_and_log_fit_default_and_compact_window(desktop, geometry):
    app, root = desktop
    root.geometry(geometry)
    root.deiconify()
    root.update()
    root.update_idletasks()
    left, top = root.winfo_rootx(), root.winfo_rooty()
    right, bottom = left + root.winfo_width(), top + root.winfo_height()
    for widget in (app.animation_button, app.selector, app.scan_button,
                   app.ground_check, app.reset_check, app.start_button,
                   app.stop_button, app.reconnect_button, app.log,
                   app.output_button, app.folder_button):
        x, y = widget.winfo_rootx(), widget.winfo_rooty()
        assert widget.winfo_viewable()
        assert left <= x < x + widget.winfo_width() <= right
        assert top <= y < y + widget.winfo_height() <= bottom
    assert app.progress.winfo_height() <= 6


def test_invalid_editor_input_keeps_main_app_usable_on_close(desktop):
    app,root=desktop
    editor=app.open_animation();root.update()
    editor.layer_vars['font_size'].set('chưa nhập xong')
    app.close()
    assert not app.closing
    assert editor.window.winfo_exists() and not editor._closing
    assert 'disabled' not in str(app.animation_button['state'])
    editor.layer_vars['font_size'].set('180')
    assert editor._apply_forms()


def test_exported_package_routes_kind_to_backend_without_resetting_fly(desktop,monkeypatch):
    from rc2vi import animation_install
    app,root=desktop
    seen=[]
    def install(assets,work,serial,package,kind,**options):
        assert options['reconnect_event'] is app.reconnect_event
        seen.append((serial,str(package),kind,options['grounded']))
        work.mkdir(parents=True,exist_ok=True)
        return {'status':'installed','installed_verified':True,'reboot_performed':False}
    monkeypatch.setattr(animation_install,'install_animation',install)
    app.serial.set('TEST-RC2');app.grounded.set(True)
    assert app.install_animation(Path('animation.zip'),'shutdown') is True
    app.thread.join(timeout=3)
    root.update()
    app.poll()
    assert seen==[('TEST-RC2','animation.zip','shutdown',True)]
    result=json.loads((app.current_work/'last-result.json').read_text('utf-8'))
    assert result['installed_verified'] and not result['reboot_performed']
    assert 'animation' in app.status.get()


def test_restoration_does_not_need_a_new_export(desktop,monkeypatch):
    from rc2vi import animation_install
    app,_=desktop
    seen=[]
    def restore(assets,work,serial,kind,**options):
        work.mkdir(parents=True,exist_ok=True);seen.append((serial,kind))
        return {'status':'restored','restored_verified':True}
    monkeypatch.setattr(animation_install,'restore_animation',restore)
    app.serial.set('TEST-RC2');app.grounded.set(True)
    assert app.install_animation(None,'boot',restore=True)
    app.thread.join(timeout=3)
    assert seen==[('TEST-RC2','boot')]


def test_cli_animation_export_never_constructs_gui_or_opens_usb(tmp_path,monkeypatch):
    from rc2vi import animation
    project=animation.new_project('minimal')
    project.update(width=320,height=180,fps=6)
    saved=animation.save_project(project,tmp_path/'source.rc2anim')
    def forbidden(*a,**kw):
        raise AssertionError('Offline animation export must not open GUI/USB')
    monkeypatch.setattr(auto_patch_app.tk,'Tk',forbidden)
    monkeypatch.setattr(auto_patch_app,'discover',forbidden)
    report=tmp_path/'result.json'
    assert auto_patch_app.main(['--animation-export',str(saved),'--work',str(tmp_path/'out'),'--report',str(report)])==0
    result=json.loads(report.read_text('utf-8'))
    assert result['status']=='PASS' and result['usb_opened'] is False
    assert Path(result['zip']).is_file()
