import tkinter as tk
from pathlib import Path
from unittest.mock import Mock
from tkinter import ttk

import pytest

import app as desktop


def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


@pytest.fixture
def ui(tmp_path):
    root = tk.Tk()
    try:
        window = desktop.App(root, tmp_path, tmp_path, start_worker=False)
        window.worker = Mock()
        window.phone_worker = Mock()
        yield window
    finally:
        # Cancel both App polling and ttk progress timers before destroying Tcl.
        if 'window' in locals():
            window.progress.stop()
        for timer in root.tk.splitlist(root.tk.call('after', 'info')):
            root.after_cancel(timer)
        root.destroy()
        if hasattr(root, '_material_images'):
            root._material_images.clear()


@pytest.mark.parametrize('geometry', ['960x740', '860x580'])
def test_patch_menu_is_compact_primary_rc_control(ui, geometry):
    ui.root.geometry(geometry)
    ui.root.update()
    buttons = {str(w.cget('text')): w for w in widgets(ui.root) if isinstance(w, ttk.Button)}
    button = buttons['Cài / cập nhật menu']
    assert button.winfo_ismapped()
    assert button.winfo_height() <= 36
    assert button.cget('style') == 'Primary.TButton'
    assert {'Tạo APK HUD', 'Cài APK HUD', 'Mở thư mục HUD', 'Chọn APK gốc…'}.isdisjoint(buttons)
    assert button in set(widgets(ui.rc_actions))
    assert button not in set(widgets(ui.phone_actions))
    labels = {str(w.cget('text')): w for w in widgets(ui.rc_actions) if isinstance(w, ttk.Label)}
    assert 'Tự lấy DJI Fly từ RC 2, patch, ký và cài lại.' in labels
    assert 'Nâng cao' not in labels
    assert 'Menu trên tay' in labels
    menu_controls = [w for w in widgets(button.master.master) if isinstance(w, ttk.Button)]
    assert menu_controls == [button]
    ui.tabs['phone'].invoke()
    ui.root.update()
    assert not button.winfo_ismapped()
    ui.tabs['rc'].invoke()
    ui.root.update()
    assert button.winfo_ismapped()


@pytest.mark.parametrize('cached_source', ['none', 'existing', 'missing'])
def test_patch_button_queues_none_without_source_dialog_or_cache(ui, monkeypatch, tmp_path, cached_source):
    source = tmp_path / 'Official Fly RC 2 1.21.8.apk'
    if cached_source == 'existing':
        source.touch()
    if cached_source != 'none':
        ui.hud_source = source
    choose = Mock(return_value=str(source))
    monkeypatch.setattr(desktop.filedialog, 'askopenfilename', choose)
    select = Mock(side_effect=AssertionError('Primary action must not select a source'))
    monkeypatch.setattr(ui, 'select_hud_source', select)
    approve = Mock()
    monkeypatch.setattr(desktop.messagebox, 'askokcancel', approve)
    button = next(w for w in widgets(ui.rc_actions)
                  if isinstance(w, ttk.Button) and w.cget('text') == 'Cài / cập nhật menu')
    button.invoke()
    ui.worker.request.assert_called_once_with('hud_patch_menu', None)
    ui.phone_worker.request.assert_not_called()
    approve.assert_not_called()
    choose.assert_not_called()
    select.assert_not_called()
    assert ui.hud_source == (None if cached_source == 'none' else source)


@pytest.mark.parametrize('handler', ['build_hud', 'choose_hud_source'])
def test_cancel_source_selection_queues_nothing(ui, monkeypatch, handler):
    choose = Mock(return_value='')
    monkeypatch.setattr(desktop.filedialog, 'askopenfilename', choose)
    getattr(ui, handler)()
    ui.worker.request.assert_not_called()
    ui.phone_worker.request.assert_not_called()


@pytest.mark.parametrize('handler', ['patch_menu', 'build_hud', 'choose_hud_source'])
@pytest.mark.parametrize('blocked', ['phone', 'closing'])
def test_hud_handlers_are_rc_only_and_stop_when_closing(ui, monkeypatch, handler, blocked):
    if blocked == 'phone':
        ui.set_mode('phone')
    else:
        ui.closing = True
    choose = Mock()
    monkeypatch.setattr(desktop.filedialog, 'askopenfilename', choose)
    if handler == 'patch_menu':
        button = next(w for w in widgets(ui.rc_actions)
                      if isinstance(w, ttk.Button) and w.cget('text') == 'Cài / cập nhật menu')
        button.invoke()
    else:
        getattr(ui, handler)()
    choose.assert_not_called()
    ui.worker.request.assert_not_called()
    ui.phone_worker.request.assert_not_called()


def test_manual_hud_source_is_reused_in_ui_session(ui, monkeypatch, tmp_path):
    source = tmp_path / 'stock Fly with spaces.apk'
    source.touch()
    choose = Mock(return_value=str(source))
    monkeypatch.setattr(desktop.filedialog, 'askopenfilename', choose)
    ui.build_hud()
    ui.set_mode('phone')
    ui.set_mode('rc')
    ui.build_hud()
    choose.assert_called_once()
    assert [(call.args[0], call.args[1]) for call in ui.worker.request.call_args_list] == [
        ('hud_build', source), ('hud_build', source)]


@pytest.mark.parametrize('invalid', ['missing.apk', 'directory.apk', 'stock.txt'])
def test_invalid_source_is_not_queued_or_remembered(ui, monkeypatch, tmp_path, invalid):
    source = tmp_path / invalid
    if invalid == 'directory.apk':
        source.mkdir()
    elif invalid == 'stock.txt':
        source.touch()
    valid = tmp_path / 'stock.apk'
    valid.touch()
    choose = Mock(side_effect=[str(source), str(valid)])
    monkeypatch.setattr(desktop.filedialog, 'askopenfilename', choose)
    ui.build_hud()
    ui.worker.request.assert_not_called()
    ui.build_hud()
    ui.worker.request.assert_called_once_with('hud_build', valid)
    assert choose.call_count == 2


def test_removed_cached_source_is_chosen_again(ui, monkeypatch, tmp_path):
    source = tmp_path / 'stock.apk'
    source.touch()
    replacement = tmp_path / 'new stock.APK'
    replacement.touch()
    choose = Mock(side_effect=[str(source), '', str(replacement)])
    monkeypatch.setattr(desktop.filedialog, 'askopenfilename', choose)
    ui.build_hud()
    ui.worker.request.reset_mock()
    source.unlink()
    ui.build_hud()
    ui.worker.request.assert_not_called()
    ui.build_hud()
    ui.worker.request.assert_called_once_with('hud_build', replacement)
    assert choose.call_count == 3


def test_choose_another_source_recovers_from_backend_rejection(ui, monkeypatch, tmp_path):
    rejected = tmp_path / 'unsupported.apk'
    rejected.touch()
    supported = tmp_path / 'official stock.apk'
    supported.touch()
    choose = Mock(side_effect=[str(rejected), str(supported)])
    monkeypatch.setattr(desktop.filedialog, 'askopenfilename', choose)
    ui.build_hud()
    ui.emit('error', 'HUD source must be the exact pinned stock Fly APK.')
    ui.poll()
    ui.worker.request.reset_mock()
    ui.choose_hud_source()
    ui.worker.request.assert_not_called()
    ui.build_hud()
    ui.worker.request.assert_called_once_with('hud_build', supported)
    assert choose.call_count == 2
    assert choose.call_args.kwargs['parent'] is ui.root
    assert '1.21.8' in choose.call_args.kwargs['title']
    assert 'chính thức' in choose.call_args.kwargs['title']
    assert choose.call_args.kwargs['filetypes'] == [('Android APK', '*.apk')]


def test_cancel_source_change_retains_previous_session_source(ui, monkeypatch, tmp_path):
    source = tmp_path / 'stock.apk'
    source.touch()
    choose = Mock(side_effect=[str(source), ''])
    monkeypatch.setattr(desktop.filedialog, 'askopenfilename', choose)
    ui.build_hud()
    ui.worker.request.reset_mock()
    ui.choose_hud_source()
    ui.worker.request.assert_not_called()
    ui.build_hud()
    ui.worker.request.assert_called_once_with('hud_build', source)
    assert choose.call_count == 2


@pytest.mark.parametrize('blocked', ['phone', 'closing'])
def test_mode_or_close_change_during_dialog_cannot_dispatch(ui, monkeypatch, tmp_path, blocked):
    source = tmp_path / 'stock.apk'
    source.touch()
    def choose(**kwargs):
        if blocked == 'phone':
            ui.set_mode('phone')
        else:
            ui.closing = True
        return str(source)
    monkeypatch.setattr(desktop.filedialog, 'askopenfilename', choose)
    ui.build_hud()
    ui.worker.request.assert_not_called()
    ui.phone_worker.request.assert_not_called()


def test_patch_menu_leaves_signer_confirmation_to_existing_event(ui, monkeypatch):
    choose = Mock(return_value='')
    monkeypatch.setattr(desktop.filedialog, 'askopenfilename', choose)
    approval = Mock(return_value=False)
    monkeypatch.setattr(desktop.messagebox, 'askokcancel', approval)
    ui.patch_menu()
    choose.assert_not_called()
    approval.assert_not_called()
    plan = {'token': 'one-use', 'serial': 'RC', 'summary': 'Different signer'}
    ui.emit('hud_confirm', plan)
    ui.poll()
    approval.assert_called_once_with(title='Xác nhận thay DJI Fly trên RC 2',
                                    message=plan['summary'], parent=ui.root,
                                    icon='warning', default='cancel')
    assert [call.args for call in ui.worker.request.call_args_list] == [
        ('hud_patch_menu', None), ('hud_cancel', {'token': 'one-use', 'serial': 'RC'})]


def test_menu_control_is_compact_and_rc_only(ui):
    ui.root.update()
    buttons = {str(w.cget('text')): w for w in widgets(ui.root) if isinstance(w, ttk.Button)}
    button = buttons['Cài / cập nhật menu']
    assert button.winfo_ismapped()
    assert button.winfo_height() <= 36
    ui.set_mode('phone')
    ui.root.update()
    assert not button.winfo_ismapped()


def test_hud_source_cancel_never_queues_build(ui, monkeypatch):
    monkeypatch.setattr(desktop.filedialog, 'askopenfilename', lambda **kw: '')
    ui.build_hud()
    ui.worker.request.assert_not_called()


def test_hud_source_is_sent_as_path_off_gui_thread(ui, monkeypatch, tmp_path):
    source = tmp_path / 'APK source with spaces.apk'
    source.touch()
    monkeypatch.setattr(desktop.filedialog, 'askopenfilename', lambda **kw: str(source))
    ui.build_hud()
    ui.worker.request.assert_called_once_with('hud_build', source)
    assert isinstance(ui.worker.request.call_args.args[1], Path)


def test_install_cancel_does_not_approve_replacement(ui, monkeypatch):
    monkeypatch.setattr(desktop.messagebox, 'askokcancel', lambda **kw: False)
    ui.confirm_hud({'token': 'one-use', 'serial': 'RC', 'summary': 'Different signer'})
    assert not any(call.args[0] == 'hud_approve' for call in ui.worker.request.call_args_list)


def test_window_close_routes_to_worker_without_destroying_live_job(ui):
    ui.thread = Mock(is_alive=lambda: True)
    ui.root.tk.call(ui.root.protocol('WM_DELETE_WINDOW'))
    assert ui.closing
    ui.worker.close.assert_called_once()
    assert ui.root.winfo_exists()
