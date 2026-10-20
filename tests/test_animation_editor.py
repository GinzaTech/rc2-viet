"""Real Tk regressions for project editing and export lifetime management."""
import io
import json
import os
import threading
import time
import tkinter as tk
import zipfile

import pytest
from PIL import Image

import rc2vi.animation_editor as studio
from rc2vi.animation import load_project


def animation_zip(path, color='#80e1bf'):
    data = io.BytesIO()
    Image.new('RGB', (160, 90), color).save(data, format='PNG')
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('desc.txt', '160 90 12\np 0 0 part0\n')
        archive.writestr('part0/0000.png', data.getvalue())
    return path


def pump(root, predicate=lambda: False, timeout=.35):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if predicate():
            return True
        time.sleep(.01)
    return bool(predicate())


@pytest.fixture
def editor(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f'Tk display is unavailable: {error}')
    root.withdraw()
    view = studio.AnimationEditor(root, tmp_path, device_status_var=tk.StringVar(root, 'Bật RC2, nối USB và giữ tay ở Launcher / Settings.'))
    view.window.geometry('1050x650')
    root.update()
    yield view, root
    if not view._destroyed and not view._closing:
        view._sync_all()
    view.close()
    pump(root, lambda: view._destroyed, timeout=3)
    # CTk's appearance and DPI trackers belong to the application root, while
    # each test intentionally creates and tears down an independent Tk app.
    for token in root.tk.splitlist(root.tk.call('after', 'info')):
        root.after_cancel(token)
    root.destroy()


def test_real_editor_import_edit_and_portable_project(editor, tmp_path, monkeypatch):
    view, root = editor
    source = tmp_path / 'logo.png'
    Image.new('RGBA', (80, 40), '#80e1bf').save(source)
    monkeypatch.setattr(view, '_image_path', lambda _: str(source))
    view.import_image()
    assert len(view.project['layers']) == 3
    assert view.project['layers'][-1]['kind'] == 'image'
    view.add_text()
    view.layer_vars['text'].set('GinzaTech thử nghiệm')
    view.layer_vars['effect'].set(studio.EFFECTS['typewriter'])
    view.layer_vars['start'].set('2.2')
    view.layer_vars['font_size'].set('75')
    assert view._apply_forms()
    view.duplicate_layer()
    assert view.project['layers'][-1]['text'] == 'GinzaTech thử nghiệm'
    assert view.project['layers'][-1]['id'] != view.project['layers'][-2]['id']
    view.move_layer(-1)
    view.remove_layer()
    assert len(view.project['layers']) == 4
    assert view.save()
    source.unlink()
    reloaded = load_project(view.project_path, tmp_path / 'reopened')
    imported = next(layer for layer in reloaded['layers'] if layer['kind'] == 'image')
    assert Image.open(imported['image']).size == (80, 40)
    assert reloaded['layers'][-1]['text'] == 'GinzaTech thử nghiệm'
    pump(root)
    state = view.get_smoke_state()
    assert state['preview_ready']
    assert state['preview_size'][0] <= 768
    assert view.export_button.winfo_rooty() + view.export_button.winfo_height() <= view.window.winfo_rooty() + view.window.winfo_height()


def test_loop_preview_uses_local_phase_and_invalid_form_cannot_export(editor, monkeypatch):
    view, _ = editor
    calls = []
    def render(project, seconds, *, size, phase):
        calls.append((seconds, phase))
        return Image.new('RGB', size)
    monkeypatch.setattr(studio, 'render_frame', render)
    view.time_var.set(view.project['intro'] + .4)
    view._render_preview()
    assert calls[-1][1] == 'loop'
    assert calls[-1][0] == pytest.approx(.4)
    old_project = view.project.copy()
    view.scene_vars['width'].set('invalid')
    assert view._apply_forms() is False
    assert view.project == old_project
    assert view.export_to('ignored.zip') is False


def test_selected_export_installs_despite_design_changes_or_invalid_draft(editor, tmp_path):
    view, root = editor
    installed = []
    view.install_callback = lambda path, kind, restore=False: installed.append((path, kind, restore)) or True
    for key, value in (('width', '320'), ('height', '180'), ('fps', '12'), ('intro', '.3'), ('loop', '.2')):
        view.scene_vars[key].set(value)
    for layer in view.project['layers']:
        layer.update(start=0, duration=.1)
    view._sync_layer()
    assert view._apply_forms()
    assert view.export_to(tmp_path / 'animation.zip')
    assert pump(root, lambda: view.current_export is not None and view._package_state == 'valid', timeout=15)
    view.layer_vars['font_size'].set('invalid')
    assert not view._apply_forms()
    view._update_controls()
    assert view.install_boot_button.cget('state') == 'normal'
    assert view.install_shutdown_button.cget('state') == 'normal'
    # The explicit file selection remains installable while the draft is invalid.
    pump(root, timeout=.2)
    assert view.install_boot_button.cget('state') == 'normal'
    view.install('boot')
    assert pump(root, lambda: len(installed) == 1)
    assert installed[-1][0] == tmp_path / 'animation.zip'
    view.layer_vars['text'].set('Đã thay đổi')
    view.install('boot')
    assert pump(root, lambda: len(installed) == 2)
    assert installed[-1][0] == tmp_path / 'animation.zip'
    view.install('shutdown', restore=True)
    assert installed[-1] == (None, 'shutdown', True)


def test_close_cancels_and_waits_for_worker_before_destroying_tk(editor, tmp_path, monkeypatch):
    view, root = editor
    started = threading.Event()
    stopped = threading.Event()
    def export(project, destination, cancel, progress):
        started.set()
        assert cancel.wait(3)
        time.sleep(.08)
        stopped.set()
        raise RuntimeError('cancelled')
    monkeypatch.setattr(studio, 'export_animation', export)
    assert view.export_to(tmp_path / 'cancelled.zip')
    assert started.wait(1)
    assert view.close() is False
    assert view.window.winfo_exists()
    assert pump(root, lambda: view._destroyed, timeout=3)
    assert stopped.is_set()
    assert view.close() is True


@pytest.mark.parametrize('geometry', ['1050x650', '1240x760'])
def test_install_controls_and_footer_fit_window(editor, geometry):
    view, root = editor
    view.window.geometry(geometry)
    view.set_device_panel(True)
    root.update()
    bottom = view.window.winfo_rooty() + view.window.winfo_height()
    right = view.window.winfo_rootx() + view.window.winfo_width()
    for widget in (view.preview_canvas, view.install_boot_button, view.install_shutdown_button,
                   view.restore_boot_button, view.restore_shutdown_button, view.status_label,
                   view.package_path_entry, view.package_browse_button, view.reconnect_button):
        assert widget.winfo_ismapped()
        assert widget.winfo_height() > 0
        assert widget.winfo_rooty() + widget.winfo_height() <= bottom
        assert widget.winfo_rootx() + widget.winfo_width() <= right


def test_device_controls_expand_on_demand_without_displacing_export(editor):
    view, root = editor
    view.window.geometry('1240x760')
    root.update()
    collapsed_height = view.preview_canvas.winfo_height()
    assert not view.install_boot_button.winfo_ismapped()
    assert view.export_button.winfo_ismapped()
    view.device_toggle_button.invoke()
    root.update()
    assert view.install_boot_button.winfo_ismapped()
    assert view.restore_shutdown_button.winfo_ismapped()
    assert view.grounded_check.winfo_ismapped()
    assert view.preview_canvas.winfo_height() < collapsed_height - 80
    assert view.export_button.winfo_ismapped()
    view.toggle_device_panel()
    root.update()
    assert not view.install_boot_button.winfo_ismapped()
    assert view.preview_canvas.winfo_height() == collapsed_height


@pytest.mark.parametrize('scrub_first', [False, True])
def test_first_play_shows_entrance_but_preserves_deliberate_scrub(editor, monkeypatch, scrub_first):
    view, _ = editor
    assert view.time_var.get() > 0
    monkeypatch.setattr(view, '_tick', lambda: None)
    if scrub_first:
        view.time_var.set(1.25)
        view._scrub()
    view.toggle_play()
    assert view._play_offset == (1.25 if scrub_first else 0)
    view.toggle_play()
    view.time_var.set(.6)
    view._scrub()
    view.toggle_play()
    assert view._play_offset == .6


def test_new_designs_and_recovery_do_not_overwrite_previous_projects(editor):
    view, _ = editor
    assert view.save()
    original = view.project_path
    view.create_project('metal')
    assert view.save()
    assert view.project_path != original
    assert original.exists()
    view.layer_vars['text'].set('Unsaved draft one')
    assert view._apply_forms()
    view.create_project('neon')
    first_recovery = next(view.library.glob('Tự lưu*.rc2anim'))
    view.layer_vars['text'].set('Unsaved draft two')
    assert view._apply_forms()
    view.create_project('minimal')
    assert first_recovery.exists()
    assert len(list(view.library.glob('Tự lưu*.rc2anim'))) == 2


def test_invalid_fields_keep_raw_text_when_switching_layer_or_closing(editor):
    view, root = editor
    view.layer_vars['text'].set('Do not lose this draft')
    view.layer_vars['font_size'].set('invalid')
    assert view._apply_forms() is False
    assert view._form_job is None
    view.layer_list.selection_clear(0, 'end')
    view.layer_list.selection_set(1)
    view._select_layer()
    assert view.selected == 0
    assert view.layer_list.curselection() == (0,)
    assert view.layer_vars['text'].get() == 'Do not lose this draft'
    assert view.layer_vars['font_size'].get() == 'invalid'
    assert view.close() is False
    assert view.window.winfo_exists()
    assert 'Chưa thể đóng' in view.status.get()
    view.layer_vars['font_size'].set('180')
    assert view._apply_forms()
    assert view.project['layers'][0]['text'] == 'Do not lose this draft'


def test_selected_zip_survives_asset_changes_but_rejects_damaged_replacement(editor, tmp_path, monkeypatch):
    view, root = editor
    source = tmp_path / 'external.png'
    Image.new('RGB', (40, 40), 'red').save(source)
    monkeypatch.setattr(view, '_image_path', lambda _: str(source))
    view.import_image()
    installed = []
    view.install_callback = lambda path, kind, restore=False: installed.append(path) or True
    for key, value in (('width', '320'), ('height', '180'), ('fps', '12'), ('intro', '.3'), ('loop', '.2')):
        view.scene_vars[key].set(value)
    for layer in view.project['layers']:
        layer.update(start=0, duration=.1)
    view._sync_layer()
    assert view._apply_forms()
    destination = tmp_path / 'freshness.zip'
    assert view.export_to(destination)
    assert pump(root, lambda: view.current_export is not None and view._package_state == 'valid', timeout=15)
    Image.new('RGB', (40, 40), 'blue').save(source)
    view.install('boot')
    assert pump(root, lambda: installed == [destination])
    # An explicit click revalidates content off-thread, even if an external
    # editor preserves size and modification time when replacing the file.
    original_stat = destination.stat()
    destination.write_bytes(b'\0' * original_stat.st_size)
    os.utime(destination, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    view.install('boot')
    assert pump(root, lambda: view._package_state == 'invalid')
    assert installed == [destination]
    assert view.install_boot_button.cget('state') == 'disabled'


def test_close_and_reopen_on_same_tk_root_cancels_all_owned_callbacks(editor, tmp_path):
    initial, root = editor
    errors = []
    root.tk.createcommand('bgerror', lambda message: errors.append(message))
    assert initial.close()
    for index in range(5):
        view = studio.AnimationEditor(root, tmp_path / f'reopen-{index}')
        root.update()
        view.layer_vars['text'].set(f'Pending preview {index}')
        view.toggle_play()
        view.layer_vars['text'].set(f'Pending form {index}')
        assert view._after
        pending = set(view._after)
        assert view.close()
        assert not view._after
        remaining = set(root.tk.splitlist(root.tk.call('after', 'info')))
        assert pending.isdisjoint(remaining)
        pump(root, timeout=.3)
    assert errors == []


def test_continuous_typing_paints_intermediate_text_before_the_last_key(editor, monkeypatch):
    view, root = editor
    pump(root, timeout=.08)
    paints = []
    text = 'Realtime'

    def render(project, seconds, *, size, phase):
        paints.append(project['layers'][0]['text'])
        return Image.new('RGB', size)

    monkeypatch.setattr(studio, 'render_frame', render)
    for index in range(len(text)):
        root.after(index * 50, lambda length=index + 1: view.layer_vars['text'].set(text[:length]))
    assert pump(root, lambda: bool(paints and paints[-1] == text), timeout=3)
    intermediate = {value for value in paints if value != text and value in {text[:i] for i in range(1, len(text))}}
    assert len(intermediate) >= 3
    assert view.project['layers'][0]['text'] == text


def test_preview_reuses_canvas_item_and_preserves_the_last_frame_on_render_failure(editor, monkeypatch):
    view, root = editor
    pump(root, lambda: view._preview_photo is not None)
    original_item = view.preview_canvas.find_all()
    assert len(original_item) == 1
    for value in ('Mới', 'Tiếng Việt trực tiếp', 'GinzaTech'):
        view.layer_vars['text'].set(value)
        assert view._apply_forms()
        view._render_preview()
        assert view.preview_canvas.find_all() == original_item
    photo = view._preview_photo
    bounds = view._preview_bounds

    def failed(*args, **kwargs):
        raise ValueError('image temporarily unavailable')

    monkeypatch.setattr(studio, 'render_frame', failed)
    view._render_preview()
    assert view._preview_photo is photo
    assert view._preview_bounds == bounds
    assert view.preview_canvas.find_all() == original_item


def test_unchanged_layer_labels_and_idle_install_controls_do_not_repaint(editor, monkeypatch):
    view, root = editor
    view.install_callback = lambda *args, **kwargs: True
    view.set_device_panel(True)
    pump(root, timeout=.1)
    deleted_rows = []
    original_delete = view.layer_list.delete

    def delete(*args):
        deleted_rows.append(args)
        return original_delete(*args)

    monkeypatch.setattr(view.layer_list, 'delete', delete)
    view.layer_vars['text'].set('New text with the same layer name')
    assert view._apply_forms()
    assert deleted_rows == []
    pump(root, timeout=.1)
    draws = []
    for button in (view.install_boot_button, view.install_shutdown_button,
                   view.restore_boot_button, view.restore_shutdown_button):
        original = button._draw

        def draw(*args, original=original, **kwargs):
            draws.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(button, '_draw', draw)
    pump(root, timeout=.45)
    assert draws == []


def test_external_quoted_unicode_zip_is_independent_of_the_editor_draft(editor, tmp_path):
    view, root = editor
    selected = animation_zip(tmp_path / 'GinzaTech tiếng Việt có khoảng trắng.zip')
    installed = []
    view.install_callback = lambda path, kind, restore=False: installed.append((path, kind, restore)) or True
    view.package_path_var.set(f'"{selected}"')
    assert pump(root, lambda: view._package_state == 'valid', timeout=3)
    assert view.current_export is None
    view.layer_vars['font_size'].set('not a number')
    assert not view._apply_forms()
    assert view.install_shutdown_button.cget('state') == 'normal'
    view.install('shutdown')
    assert pump(root, lambda: bool(installed), timeout=3)
    assert installed == [(selected, 'shutdown', False)]
    assert view.layer_vars['font_size'].get() == 'not a number'
    settings = json.loads((view.work / 'animation-package.json').read_text(encoding='utf-8'))
    assert settings == {'package_path': str(selected)}


def test_last_valid_package_path_is_restored_and_revalidated_after_restart(editor, tmp_path, monkeypatch):
    original, root = editor
    selected = animation_zip(tmp_path / 'previous-session.zip')
    original.package_path_var.set(str(selected))
    assert pump(root, lambda: original._package_state == 'valid', timeout=3)
    assert original.close()
    calls = []
    validator = studio._validate_zip

    def validate(path, cancel=None):
        calls.append((path, threading.get_ident()))
        return validator(path, cancel=cancel)

    monkeypatch.setattr(studio, '_validate_zip', validate)
    reopened = studio.AnimationEditor(root, original.work, install_callback=lambda *a, **k: True)
    try:
        assert reopened.package_path_var.get() == str(selected)
        assert reopened._package_state == 'checking'
        assert reopened.install_boot_button.cget('state') == 'disabled'
        assert pump(root, lambda: reopened._package_state == 'valid', timeout=3)
        assert len(calls) == 1
        assert calls[0][1] != threading.get_ident()
        assert reopened.install_boot_button.cget('state') == 'normal'
    finally:
        reopened.close()


def test_missing_or_invalid_zip_blocks_then_corrected_file_enables_without_reselection(editor, tmp_path):
    view, root = editor
    view.install_callback = lambda *a, **k: True
    selected = tmp_path / 'replace-me.zip'
    selected.write_bytes(b'not an animation ZIP')
    view.package_path_var.set(str(selected))
    assert pump(root, lambda: view._package_state == 'invalid', timeout=3)
    assert view.install_boot_button.cget('state') == 'disabled'
    animation_zip(selected)
    assert pump(root, lambda: view._package_state == 'valid', timeout=3)
    assert view.install_boot_button.cget('state') == 'normal'
    assert 'chưa hợp lệ' not in view.package_status_var.get()
    selected.unlink()
    assert pump(root, lambda: view._package_state == 'invalid', timeout=3)
    assert view.install_boot_button.cget('state') == 'disabled'
    assert not view.install('boot')


def test_replaced_valid_zip_is_revalidated_and_unchanged_idle_polls_do_not_rehash(editor, tmp_path, monkeypatch):
    view, root = editor
    selected = animation_zip(tmp_path / 'selected.zip')
    validator = studio._validate_zip
    calls, installed = [], []

    def validate(path, cancel=None):
        calls.append(threading.get_ident())
        return validator(path, cancel=cancel)

    monkeypatch.setattr(studio, '_validate_zip', validate)
    view.install_callback = lambda path, kind, restore=False: installed.append(path) or True
    view.package_path_var.set(str(selected))
    assert pump(root, lambda: view._package_state == 'valid', timeout=3)
    first_hash = view._package_details['sha256']
    assert len(calls) == 1
    pump(root, timeout=.5)
    assert len(calls) == 1
    animation_zip(selected, '#ffcc00')
    assert pump(root, lambda: view._package_state == 'valid' and view._package_details['sha256'] != first_hash, timeout=3)
    view.install('boot')
    assert pump(root, lambda: installed == [selected], timeout=3)
    assert len(calls) == 3
    assert all(thread != threading.get_ident() for thread in calls)


def test_stale_validation_cannot_enable_or_install_the_previous_selection(editor, tmp_path, monkeypatch):
    view, root = editor
    previous = animation_zip(tmp_path / 'previous.zip')
    selected = animation_zip(tmp_path / 'selected.zip', '#ffcc00')
    validator = studio._validate_zip
    started, release = threading.Event(), threading.Event()
    installed = []
    view.install_callback = lambda path, kind, restore=False: installed.append(path) or True
    view.package_path_var.set(str(previous))
    assert pump(root, lambda: view._package_state == 'valid', timeout=3)

    def slow_validation(path, cancel=None):
        if path == previous:
            details = validator(path)
            started.set()
            release.wait(3)
            return details
        return validator(path, cancel=cancel)

    monkeypatch.setattr(studio, '_validate_zip', slow_validation)
    view.install('boot')
    assert started.wait(1)
    view.package_path_var.set(str(selected))
    assert pump(root, lambda: view._package_state == 'valid', timeout=3)
    release.set()
    pump(root, timeout=.3)
    assert installed == []
    assert view._package_validated_key[0] == str(selected)
    view.install('boot')
    assert pump(root, lambda: installed == [selected], timeout=3)


def test_close_cancels_local_zip_validation_without_worker_tk_calls(editor, tmp_path, monkeypatch):
    view, root = editor
    selected = animation_zip(tmp_path / 'selected.zip')
    started, stopped = threading.Event(), threading.Event()

    def validation(path, cancel=None):
        started.set()
        assert cancel.wait(3)
        stopped.set()
        raise RuntimeError('cancelled')

    monkeypatch.setattr(studio, '_validate_zip', validation)
    view.package_path_var.set(str(selected))
    assert pump(root, started.is_set, timeout=3)
    assert view.close()
    assert stopped.wait(1)
    pump(root, timeout=.1)
    assert view._destroyed


def test_usb_permission_button_only_routes_when_root_allows_reconnect(editor):
    view, root = editor
    calls = []
    allowed = [False]
    view.reconnect_callback = lambda: calls.append('request')
    view.reconnect_state_callback = lambda: allowed[0]
    view._update_controls()
    assert view.reconnect_button.cget('state') == 'disabled'
    assert not view.request_reconnect()
    allowed[0] = True
    assert pump(root, lambda: view.reconnect_button.cget('state') == 'normal')
    view.reconnect_button.invoke()
    assert calls == ['request']
    allowed[0] = False
    assert pump(root, lambda: view.reconnect_button.cget('state') == 'disabled')
    assert not view.request_reconnect()
    assert calls == ['request']


def test_remembered_package_reads_and_replaces_inside_resolved_physical_directory(editor, tmp_path, monkeypatch):
    view, _ = editor
    selected = animation_zip(tmp_path / 'selected.zip')
    physical = tmp_path / 'resolved-work'
    physical.mkdir()
    original_resolve = studio.Path.resolve
    original_replace = studio.Path.replace
    replacements = []

    def redirected(path, *args, **kwargs):
        return physical if path == view.work else original_resolve(path, *args, **kwargs)

    def replace(path, target):
        replacements.append((path, target))
        return original_replace(path, target)

    monkeypatch.setattr(studio.Path, 'resolve', redirected)
    monkeypatch.setattr(studio.Path, 'replace', replace)
    assert view._remember_package_path(selected)
    assert view._load_package_path() == str(selected)
    assert replacements == [(physical / 'animation-package.json.tmp', physical / 'animation-package.json')]
    assert view._package_path_remembered
    assert view._package_persistence_error is None


def test_persistence_failure_is_visible_and_clears_when_settings_can_be_written(editor, tmp_path, monkeypatch):
    view, root = editor
    selected = animation_zip(tmp_path / 'selected.zip')
    original_replace = studio.Path.replace

    def locked(path, target):
        if path.name == 'animation-package.json.tmp':
            raise PermissionError('settings is temporarily locked')
        return original_replace(path, target)

    monkeypatch.setattr(studio.Path, 'replace', locked)
    view.install_callback = lambda *a, **k: True
    view.package_path_var.set(str(selected))
    assert pump(root, lambda: view._package_state == 'valid', timeout=3)
    assert view.install_boot_button.cget('state') == 'normal'
    assert 'chưa lưu đường dẫn' in view.package_status_var.get()
    assert not view._package_path_remembered
    assert 'temporarily locked' in view._package_persistence_error
    monkeypatch.setattr(studio.Path, 'replace', original_replace)
    view._validate_selected_package(force=True)
    assert pump(root, lambda: view._package_path_remembered, timeout=3)
    assert 'chưa lưu đường dẫn' not in view.package_status_var.get()
    assert view._load_package_path() == str(selected)
    assert view._package_persistence_error is None
