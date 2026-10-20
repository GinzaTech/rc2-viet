"""Frozen-app diagnostic for installing an existing animation ZIP, offline."""
from __future__ import annotations

import json
from pathlib import Path
import time
import traceback
import tkinter as tk

from . import desktop_theme as theme
from .animation import export_animation, new_project
from .navigation_ui_check import _capture_root, _toplevels


def run_package_ui_check(work) -> dict:
    """Check real CTk controls and asynchronous ZIP checks without touching USB.

    Install and authorization callbacks are local recorders. The real Android
    ZIP validator still decodes every PNG through the editor's normal worker.
    """
    import auto_patch_app as app_module
    from .transport import Connection

    work = Path(work).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    report = {
        'status': 'FAILED', 'single_window': False, 'existing_zip_validated': False,
        'install_without_fresh_project': False, 'invalid_form_does_not_block_zip': False,
        'fresh_validation_before_install': False, 'install_callback_calls': [],
        'back_reopen_path_preserved': False, 'restart_path_remembered': False,
        'restart_revalidated': False, 'missing_zip_disabled': False,
        'invalid_zip_disabled': False, 'usb_request_button_present': False,
        'usb_request_callback_shared': False, 'usb_request_callback_calls': 0,
        'controls_inside_window': False, 'usb_opened': False, 'usb_open_attempts': 0,
        'device_modified': False, 'discovery_calls': 0, 'dialog_attempts': 0,
        'errors': [],
    }
    root = app = editor = None
    original_root_usb_command = None
    editors = []
    callback_originals = []
    original_discover, original_open = app_module.discover, Connection.open
    dialog_originals = []
    started = time.perf_counter()

    def require(condition, message):
        if not condition:
            raise AssertionError(message)

    def pump(seconds=.08):
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            root.update()
            time.sleep(.003)

    def wait_for(predicate, message, timeout=5.):
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            root.update()
            if predicate():
                return
            time.sleep(.003)
        raise AssertionError(message)

    def discover_offline():
        report['discovery_calls'] += 1
        return []

    def forbid_open(*_args, **_kwargs):
        report['usb_open_attempts'] += 1
        raise AssertionError('The package UI diagnostic attempted to open USB.')

    def forbid_dialog(*_args, **_kwargs):
        report['dialog_attempts'] += 1
        raise AssertionError('The package UI diagnostic unexpectedly opened a dialog.')

    def fake_install(path, kind, restore=False):
        report['install_callback_calls'].append(
            {'path': str(path) if path is not None else None, 'kind': kind, 'restore': bool(restore)})
        return True

    def fake_request_usb():
        report['usb_request_callback_calls'] += 1
        return True

    def override(owner, name, value):
        callback_originals.append((owner, name, getattr(owner, name)))
        setattr(owner, name, value)

    def prepare_editor(view):
        editors.append(view)
        override(view, 'install_callback', fake_install)
        override(view, 'busy_callback', lambda: False)
        view._update_controls()

    def install_buttons_enabled(view):
        return all(button.cget('state') == 'normal' for button in
                   (view.install_boot_button, view.install_shutdown_button))

    def install_buttons_disabled(view):
        return all(button.cget('state') == 'disabled' for button in
                   (view.install_boot_button, view.install_shutdown_button))

    try:
        project = new_project('minimal')
        project.update(width=320, height=180, fps=6, intro=1., loop=.5)
        for layer in project['layers']:
            layer.update(start=0., duration=.2)
        exported = export_animation(project, work / 'sample-package' / 'existing-animation.zip')
        valid_zip = Path(exported['zip'])
        invalid_zip = work / 'invalid-animation.zip'
        invalid_zip.write_bytes(b'This is deliberately not an Android animation ZIP.')
        report['package_path'] = str(valid_zip)

        app_module.discover = discover_offline
        Connection.open = forbid_open
        for provider, names in (
            (app_module.filedialog, ('askopenfilename', 'asksaveasfilename', 'askdirectory')),
            (app_module.messagebox, ('showerror', 'showwarning', 'showinfo', 'askyesno',
                                     'askokcancel', 'askyesnocancel', 'askretrycancel', 'askquestion')),
        ):
            for name in names:
                dialog_originals.append((provider, name, getattr(provider, name)))
                setattr(provider, name, forbid_dialog)

        root = theme.ctk.CTk()
        root.withdraw()
        root.report_callback_exception = lambda kind, value, tb: report['errors'].append(
            ''.join(traceback.format_exception(kind, value, tb)))
        assets, _default_work = app_module.locations()
        app = app_module.App(root, assets, work / 'app')
        override(app, 'request_reconnect', fake_request_usb)
        override(app, 'can_request_usb', lambda: True)
        # Both pages receive the same recorder as the root application's action.
        original_root_usb_command = app.reconnect_button.cget('command')
        app.reconnect_button.configure(command=app.request_reconnect)
        app.controls()
        root.geometry('1240x760+32+32')
        root.deiconify()
        editor = app.open_animation()
        prepare_editor(editor)
        editor.set_device_panel(True)
        pump(.18)
        require(editor.embedded and editor.window is root and not _toplevels(root),
                'The package flow opened an extra application window.')
        report['single_window'] = True

        editor.package_path_var.set(str(valid_zip))
        wait_for(lambda: editor._package_state == 'valid' and install_buttons_enabled(editor),
                 'The selected existing ZIP did not validate and enable both install buttons.')
        report['existing_zip_validated'] = True
        require(editor.current_export is None and editor.export_fingerprint is None,
                'The existing-ZIP check unexpectedly depended on a fresh project export.')
        report['install_without_fresh_project'] = True
        editor.layer_vars['font_size'].set('chưa nhập xong')
        pump(.07)
        require(not editor._forms_valid and install_buttons_enabled(editor),
                'An unfinished design field disabled installation of the selected valid ZIP.')
        report['invalid_form_does_not_block_zip'] = True
        editor.install_boot_button.invoke()
        require(not report['install_callback_calls'],
                'Install bypassed the editor asynchronous package revalidation.')
        wait_for(lambda: len(report['install_callback_calls']) == 1,
                 'The verified boot-install click did not reach its local callback.')
        require(report['install_callback_calls'] == [{'path': str(valid_zip), 'kind': 'boot', 'restore': False}],
                'The install callback received the wrong selected package or target.')
        report['fresh_validation_before_install'] = True

        editor.back_button.invoke()
        pump(.07)
        require(app.active_page == 'patch', 'Back did not leave the package page.')
        require(app.open_animation() is editor, 'Back/reopen recreated the package editor.')
        pump(.08)
        require(editor.package_path_var.get() == str(valid_zip) and install_buttons_enabled(editor),
                'Back/reopen lost or invalidated the selected ZIP.')
        report['back_reopen_path_preserved'] = True

        # Recreate the editor against the same work directory to exercise the
        # on-disk remembered path and a new validator/cache, not an old object.
        editor._destroy()
        editor = app.open_animation()
        prepare_editor(editor)
        editor.set_device_panel(True)
        require(editor.package_path_var.get() == str(valid_zip),
                'A new editor did not restore the remembered selected ZIP path.')
        report['restart_path_remembered'] = True
        require(editor._package_validated_key is None,
                'A new editor trusted remembered ZIP validation without checking it again.')
        wait_for(lambda: editor._package_state == 'valid' and install_buttons_enabled(editor),
                 'The remembered ZIP was not revalidated by the new editor.')
        report['restart_revalidated'] = True

        editor.package_path_var.set(str(work / 'missing-animation.zip'))
        wait_for(lambda: editor._package_state == 'invalid' and install_buttons_disabled(editor),
                 'A missing ZIP did not disable both install buttons.')
        report['missing_zip_disabled'] = True
        editor.install_boot_button.invoke()
        require(len(report['install_callback_calls']) == 1, 'A missing ZIP reached installation.')
        editor.package_path_var.set(str(invalid_zip))
        wait_for(lambda: editor._package_state == 'invalid' and install_buttons_disabled(editor),
                 'A malformed ZIP did not disable both install buttons.')
        report['invalid_zip_disabled'] = True
        editor.install_shutdown_button.invoke()
        require(len(report['install_callback_calls']) == 1, 'A malformed ZIP reached installation.')

        editor.package_path_var.set(str(valid_zip))
        wait_for(lambda: editor._package_state == 'valid' and install_buttons_enabled(editor),
                 'Reselecting the good package did not restore the install controls.')
        report['usb_request_button_present'] = bool(editor.reconnect_button.winfo_ismapped())
        report['usb_request_callback_shared'] = editor.reconnect_callback is app.request_reconnect
        require(report['usb_request_button_present'] and report['usb_request_callback_shared']
                and editor.reconnect_button.cget('state') == 'normal',
                'The Animation page did not expose the root USB-request callback.')
        editor.reconnect_button.invoke()
        require(report['usb_request_callback_calls'] == 1,
                'The USB-request button did not invoke the shared local callback exactly once.')
        pump(.18)

        geometry = {}
        rx, ry = root.winfo_rootx(), root.winfo_rooty()
        rw, rh = root.winfo_width(), root.winfo_height()
        for name in ('preview_canvas', 'export_button', 'package_path_entry', 'package_browse_button',
                     'package_status_label', 'device_combo', 'scan_button', 'reconnect_button',
                     'grounded_check', 'install_boot_button', 'install_shutdown_button',
                     'restore_boot_button', 'restore_shutdown_button'):
            widget = getattr(editor, name)
            box = [widget.winfo_rootx() - rx, widget.winfo_rooty() - ry,
                   widget.winfo_width(), widget.winfo_height()]
            geometry[name] = box
            require(widget.winfo_ismapped() and box[2] > 0 and box[3] > 0
                    and box[0] >= 0 and box[1] >= 0
                    and box[0] + box[2] <= rw and box[1] + box[3] <= rh,
                    f'The expanded package/USB controls clipped {name}: {box} in {rw}x{rh}.')
        report['control_geometry'] = geometry
        report['controls_inside_window'] = True
        report['screenshot'] = _capture_root(root, work / 'animation-package-ui.png')
        require(not _toplevels(root) and report['usb_open_attempts'] == 0 and app.thread is None,
                'The package UI flow opened USB, a worker device job, or a second window.')
        report['status'] = 'PASS' if not report['errors'] else 'FAILED'
    except Exception:
        report['errors'].append(traceback.format_exc())
    finally:
        for owner, name, original in reversed(callback_originals):
            setattr(owner, name, original)
        if app is not None:
            app.closing = True
            app.cancel.set()
            if original_root_usb_command is not None:
                app.reconnect_button.configure(command=original_root_usb_command)
        for view in editors:
            if not view._destroyed:
                view._destroy()
            worker = getattr(view, '_package_worker', None)
            if worker is not None and worker.is_alive():
                worker.join(timeout=1.)
        if root is not None:
            try:
                for token in root.tk.splitlist(root.tk.call('after', 'info')):
                    root.after_cancel(token)
                root.destroy()
            except tk.TclError:
                pass
        for provider, name, original in dialog_originals:
            setattr(provider, name, original)
        app_module.discover, Connection.open = original_discover, original_open
        if report['errors']:
            report['status'] = 'FAILED'
        report['duration_ms'] = round((time.perf_counter() - started) * 1000, 2)
        (work / 'animation-package-ui-check.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report
