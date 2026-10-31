"""Real-window, offline diagnostic for the embedded Animation page.

The check owns one fresh CTk root. Device discovery and connection opening are
guarded while it exercises the same buttons and variable traces as the user.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import time
import traceback
import tkinter as tk

from PIL import ImageGrab

from . import desktop_theme as theme


def _toplevels(root):
    found = []

    def visit(widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Toplevel):
                found.append(str(child))
            visit(child)

    visit(root)
    return found


def _capture_root(root, destination):
    """Capture this diagnostic's actual native window, even if occluded."""
    root.update_idletasks()
    if sys.platform != 'win32':
        raise RuntimeError('The native-window navigation screenshot requires Windows.')
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    api.GetAncestor.restype = wintypes.HWND
    handle = api.GetAncestor(root.winfo_id(), 2)  # GA_ROOT, including the Tk wrapper.
    if not handle:
        raise OSError(ctypes.get_last_error(), 'Cannot resolve the diagnostic window HWND.')
    with ImageGrab.grab(window=int(handle)) as capture:
        if all(low == high for low, high in capture.getextrema()):
            raise RuntimeError('Windows has not rendered the navigation window yet.')
        capture.save(destination, format='PNG')
        return {'path': str(destination), 'hwnd': int(handle),
                'width': capture.width, 'height': capture.height, 'capture_mode': 'HWND'}


def run_navigation_check(work) -> dict:
    """Open, leave, and reopen Animation without losing an invalid raw draft.

    This never invokes patching, exporting, installing, or a file dialog. A USB
    open attempt is denied and reported. Only the root created here is closed.
    """
    # Keep a normal static import for PyInstaller's dependency analysis.
    import auto_patch_app as app_module
    from .transport import Connection

    work = Path(work).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    report = {
        'status': 'FAILED', 'single_window': False, 'back_button_present': False,
        'roundtrips': 0, 'draft_preserved': False, 'invalid_draft_preserved': False,
        'editor_reused': False, 'playback_paused_on_back': False,
        'hidden_preview_renders': None, 'usb_opened': False, 'usb_open_attempts': 0,
        'device_modified': False, 'discovery_mode': 'offline-empty-list',
        'discovery_calls': 0, 'dialogs_opened': 0, 'dialog_attempts': 0,
        'screenshots': {}, 'errors': [],
    }
    root = app = editor = None
    original_discover = app_module.discover
    original_open = Connection.open
    dialog_guards = []
    started = time.perf_counter()

    def discover_offline():
        report['discovery_calls'] += 1
        return []

    def refuse_connection(*_args, **_kwargs):
        report['usb_open_attempts'] += 1
        raise AssertionError('The navigation diagnostic attempted to open USB.')

    def refuse_dialog(*_args, **_kwargs):
        report['dialog_attempts'] += 1
        raise AssertionError('Navigation unexpectedly requested a modal dialog.')

    def require(condition, message):
        if not condition:
            raise AssertionError(message)

    def pump(seconds=.08):
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            root.update()
            time.sleep(.003)

    def callback_error(exc_type, exc_value, exc_traceback):
        report['errors'].append(''.join(traceback.format_exception(exc_type, exc_value, exc_traceback)))

    try:
        app_module.discover = discover_offline
        Connection.open = refuse_connection
        for provider, names in (
            (app_module.filedialog, ('askopenfilename', 'asksaveasfilename', 'askdirectory')),
            (app_module.messagebox, ('showerror', 'showwarning', 'showinfo', 'askyesno',
                                     'askokcancel', 'askyesnocancel', 'askretrycancel', 'askquestion')),
        ):
            for name in names:
                dialog_guards.append((provider, name, getattr(provider, name)))
                setattr(provider, name, refuse_dialog)
        root = theme.ctk.CTk()
        root.withdraw()
        root.report_callback_exception = callback_error
        # App's constructor scans through our empty stub, never a USB enumerator.
        assets, _default_work = app_module.locations()
        app = app_module.App(root, assets, work / 'app')
        root.geometry('900x760+32+32')
        root.deiconify()
        pump(.16)
        require(app.active_page == 'patch' and app.patch_page.winfo_ismapped(),
                'The desktop application did not start on its patch page.')

        editor = app.open_animation()
        pump(.22)
        require(editor is not None and editor.embedded and editor.window is root,
                'Animation opened outside the existing application window.')
        report['back_button_present'] = bool(getattr(editor, 'back_button', None)
                                             and editor.back_button.winfo_ismapped())
        require(report['back_button_present'], 'The Animation Back button is missing or hidden.')
        require(app.active_page == 'animation' and editor.view.winfo_ismapped()
                and not app.patch_page.winfo_ismapped(), 'The Animation route did not become the only visible page.')
        require(not _toplevels(root), 'Animation created an additional Toplevel window.')
        report['single_window'] = True

        draft = 'GinzaTech — bản nháp điều hướng'
        editor.layer_vars['text'].set(draft)
        pump(.08)
        require(editor.project['layers'][editor.selected]['text'] == draft,
                'The edited text did not reach the current project.')
        valid_font_size = editor.layer_vars['font_size'].get()
        invalid_font_size = 'đang nhập chưa xong'
        editor.layer_vars['font_size'].set(invalid_font_size)
        # Let validation fail before Back, then verify both model and raw fields.
        pump(.07)
        editor.back_button.invoke()
        pump(.10)
        require(app.active_page == 'patch' and app.patch_page.winfo_ismapped()
                and not editor.view.winfo_ismapped(), 'Back did not restore the patch page.')
        require(editor.layer_vars['font_size'].get() == invalid_font_size
                and editor.layer_vars['text'].get() == draft,
                'Back discarded the raw draft containing an unfinished numeric field.')
        reopened = app.open_animation()
        pump(.10)
        report['editor_reused'] = reopened is editor
        report['draft_preserved'] = reopened.layer_vars['text'].get() == draft
        report['invalid_draft_preserved'] = reopened.layer_vars['font_size'].get() == invalid_font_size
        require(report['editor_reused'] and report['draft_preserved'] and report['invalid_draft_preserved'],
                'Reopening Animation recreated the editor or replaced its raw draft.')
        report['roundtrips'] += 1

        editor.layer_vars['font_size'].set(valid_font_size)
        pump(.08)
        require(editor._forms_valid, 'The unfinished font-size field did not recover after correction.')
        editor.toggle_play()
        pump(.08)
        require(editor._playing, 'Playback did not start for the navigation pause check.')
        editor.back_button.invoke()
        pump(.10)
        report['playback_paused_on_back'] = not editor._playing
        require(report['playback_paused_on_back'], 'Playback continued after leaving Animation.')
        require(app.active_page == 'patch', 'Back from playback did not restore the patch page.')

        hidden_renders = [0]
        original_render = editor._render_preview

        def observe_hidden_render():
            hidden_renders[0] += 1
            return original_render()

        editor._render_preview = observe_hidden_render
        pump(.18)
        editor._render_preview = original_render
        report['hidden_preview_renders'] = hidden_renders[0]
        require(hidden_renders[0] == 0, 'The hidden Animation page continued rendering preview frames.')
        report['screenshots']['patch'] = _capture_root(root, work / 'navigation-patch.png')
        reopened = app.open_animation()
        pump(.18)
        require(reopened is editor and not editor._playing,
                'Animation was recreated or resumed playback when reopened.')
        report['roundtrips'] += 1

        editor.back_button.invoke()
        pump(.08)
        require(app.active_page == 'patch', 'The third Back roundtrip did not reach patch.')
        require(app.open_animation() is editor, 'Repeated navigation replaced the editor instance.')
        pump(.18)
        report['roundtrips'] += 1
        require(editor.layer_vars['text'].get() == draft and not _toplevels(root),
                'Repeated navigation lost the draft or created an extra window.')
        # Present a useful settled frame for the evidence image; the playback
        # pause was already checked at its actual position before this scrub.
        editor.time_var.set(max(0., float(editor.project['intro']) - .2))
        editor._request_preview()
        pump(.08)
        report['screenshot_preview_seconds'] = float(editor.time_var.get())
        report['screenshots']['animation'] = _capture_root(root, work / 'navigation-animation.png')
        report['root_hwnd'] = report['screenshots']['animation']['hwnd']
        require(report['screenshots']['patch']['hwnd'] == report['root_hwnd'],
                'Navigation changed the native application window.')
        require(report['usb_open_attempts'] == 0 and app.thread is None,
                'Navigation started a device operation.')
        report['final_page'] = app.active_page
        report['toplevel_windows'] = _toplevels(root)
        report['status'] = 'PASS' if not report['errors'] else 'FAILED'
    except Exception:
        report['errors'].append(traceback.format_exc())
    finally:
        app_module.discover = original_discover
        Connection.open = original_open
        for provider, name, original in dialog_guards:
            setattr(provider, name, original)
        if app is not None:
            app.closing = True
            app.cancel.set()
        if editor is not None and not editor._destroyed:
            # The diagnostic owns this instance and never starts an export.
            # Avoid close()/autosave validation changing the draft under test.
            editor._destroy()
        if root is not None:
            try:
                for identifier in root.tk.splitlist(root.tk.call('after', 'info')):
                    root.after_cancel(identifier)
                root.destroy()
            except tk.TclError:
                pass
        report['duration_ms'] = round((time.perf_counter() - started) * 1000, 2)
        if report['errors']:
            report['status'] = 'FAILED'
        (work / 'navigation-ui-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report
