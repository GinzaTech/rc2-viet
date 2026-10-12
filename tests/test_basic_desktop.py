"""Public Basic desktop boundaries and receipt guards, using fake transports only."""
from pathlib import Path
import json
import sys
import tkinter as tk
from tkinter import ttk
from unittest.mock import Mock, call

import pytest

import app as desktop
from rc2vi.controller import Worker
from rc2vi.core import Device
from rc2vi.hud_tools import HudCancelled
from tests.test_controller import FakeActivator, FakeConnection


def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


def menu_button(window):
    return next(widget for widget in widgets(window.rc_actions)
                if isinstance(widget, ttk.Button)
                and widget.cget('text') == 'Cài / cập nhật menu')


@pytest.fixture(autouse=True)
def no_device_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Basic desktop tests must not access devices or ADB')
    monkeypatch.setattr(desktop, 'discover', forbidden)
    monkeypatch.setattr('rc2vi.transport.Adb.command', forbidden)
    monkeypatch.setattr('rc2vi.transport.Connection.open', forbidden)


@pytest.fixture
def ui(tmp_path):
    root = tk.Tk()
    window = None
    try:
        window = desktop.App(root, tmp_path, tmp_path, start_worker=False)
        window.worker = Mock()
        window.phone_worker = Mock()
        yield window
    finally:
        if window:
            window.progress.stop()
        for timer in root.tk.splitlist(root.tk.call('after', 'info')):
            root.after_cancel(timer)
        root.destroy()
        if hasattr(root, '_material_images'):
            root._material_images.clear()


@pytest.fixture
def menu_worker(tmp_path):
    builder = Mock(spec=['build', 'build_variant', 'latest'])
    builder.build.return_value = {
        'status': 'hud_built', 'variant': 'basic',
        'apk': str(tmp_path / 'hud.apk'), 'receipt': str(tmp_path / 'new' / 'receipt.json'),
    }
    builder.build_variant.return_value = {
        **builder.build.return_value, 'variant': 'advanced',
    }
    builder.latest.side_effect = AssertionError('Never replace the current receipt with latest')
    installer = Mock(spec=['pull_source', 'prepare', 'approve', 'cancel_pending', 'cleanup_pending'])
    installer.pull_source.return_value = tmp_path / 'pulled official.apk'
    installer.prepare.return_value = {'status': 'hud_installed'}
    installer.approve.return_value = {'status': 'hud_installed'}
    events = []
    worker = Worker(tmp_path, FakeActivator(), lambda *event: events.append(event),
                    discover=lambda: [Device('RC', 'usb')], connection_factory=FakeConnection,
                    hud_builder=builder, hud_installer=installer)
    worker.selected = 'RC'
    worker.auto = False
    worker.step()
    events.clear()
    return worker, builder, installer, events


@pytest.mark.parametrize('geometry', ['960x740', '860x580'])
def test_public_ui_has_single_menu_action_without_variant_selector(ui, geometry):
    ui.root.geometry(geometry)
    ui.root.update()
    assert not hasattr(ui, 'hud_variant')
    assert [widget for widget in widgets(ui.root) if isinstance(widget, ttk.Combobox)] == [ui.selector]
    button = menu_button(ui)
    assert [widget for widget in widgets(button.master.master) if isinstance(widget, ttk.Button)] == [button]
    assert button.winfo_ismapped() and button.winfo_height() <= 36
    assert button.cget('style') == 'Primary.TButton'
    ui.tabs['phone'].invoke()
    ui.root.update()
    assert not button.winfo_ismapped()
    ui.tabs['rc'].invoke()
    ui.root.update()
    assert button.winfo_ismapped()


def test_menu_action_always_queues_basic_auto_source_request(ui, monkeypatch):
    choose = Mock(side_effect=AssertionError('One-click menu must not ask for an APK'))
    monkeypatch.setattr(ui, 'select_hud_source', choose)
    monkeypatch.setattr(desktop.filedialog, 'askopenfilename', choose)
    # A stale programmatic attribute must not influence the public action.
    ui.hud_variant = Mock()
    ui.hud_variant.get.return_value = 'Nâng cấp'
    menu_button(ui).invoke()
    ui.worker.request.assert_called_once_with('hud_patch_menu', None)
    ui.phone_worker.request.assert_not_called()
    choose.assert_not_called()


def test_gui_compatibility_text_does_not_claim_unrestricted_fly_versions(ui):
    labels = [str(widget.cget('text')) for widget in widgets(ui.rc_actions)
              if isinstance(widget, ttk.Label)]
    assert not any('Không khóa phiên bản DJI Fly' in label for label in labels)
    assert not any('Nâng cấp' in label or 'Advanced' in label for label in labels)


@pytest.mark.parametrize('approved', [False, True])
def test_basic_menu_keeps_signer_consent_on_rc_worker_after_platform_change(ui, monkeypatch, approved):
    confirm = Mock(return_value=approved)
    monkeypatch.setattr(desktop.messagebox, 'askokcancel', confirm)
    ui.patch_menu()
    confirm.assert_not_called()
    ui.set_mode('phone')
    plan = {'serial': 'RC', 'token': 'one-use', 'summary': 'Different signer'}
    ui.emit('hud_confirm', plan)
    ui.poll()
    confirm.assert_called_once_with(title='Xác nhận thay DJI Fly trên RC 2',
                                    message=plan['summary'], parent=ui.root,
                                    icon='warning', default='cancel')
    assert ui.worker.request.call_args_list == [
        call('hud_patch_menu', None),
        call('hud_approve' if approved else 'hud_cancel', {'token': 'one-use', 'serial': 'RC'}),
    ]
    ui.phone_worker.request.assert_not_called()


INVALID_REQUESTS = [
    {'variant': 'advanced'}, {'variant': 'Advanced'}, {'variant': 'unknown'}, {},
    {'variant': ''}, {'variant': None}, {'variant': True}, {'variant': []}, {'variant': {}},
    {'variant': 'basic', 'source': Path('official.apk')},
    {'variant': 'basic', 'receipt': 'latest.json'},
    'advanced', 'official.apk', [], 1, False,
]


@pytest.mark.parametrize('payload', INVALID_REQUESTS)
@pytest.mark.parametrize('boundary', ['queue', 'dispatch'])
def test_non_basic_or_malformed_menu_request_fails_before_pull_build_or_install(menu_worker, payload, boundary):
    worker, builder, installer, _ = menu_worker
    handler = worker.request if boundary == 'queue' else worker._command
    with pytest.raises(ValueError):
        handler('hud_patch_menu', payload)
    assert worker.commands.empty()
    installer.pull_source.assert_not_called()
    builder.build.assert_not_called()
    builder.build_variant.assert_not_called()
    builder.latest.assert_not_called()
    installer.prepare.assert_not_called()
    installer.approve.assert_not_called()


def test_advanced_request_is_rejected_even_before_connection_checks(menu_worker):
    worker, builder, installer, _ = menu_worker
    worker.connection = None
    worker.adb = None
    with pytest.raises(ValueError):
        worker._command('hud_patch_menu', {'variant': 'advanced'})
    installer.pull_source.assert_not_called()
    builder.build.assert_not_called()
    builder.build_variant.assert_not_called()


@pytest.mark.parametrize('payload', [None, Path('official.apk'), {'variant': 'basic'}])
@pytest.mark.parametrize('legacy_result', [False, True])
def test_basic_and_legacy_requests_queue_then_prepare_only_the_new_receipt(menu_worker, payload, legacy_result):
    worker, _, installer, _ = menu_worker
    builder = Mock(spec=['build', 'latest'])
    builder.build.return_value = {'status': 'hud_built', 'apk': 'hud.apk', 'receipt': 'new/receipt.json'}
    if not legacy_result:
        builder.build.return_value = {**builder.build.return_value, 'variant': 'basic'}
    worker.hud_builder = builder
    calls = Mock()
    calls.attach_mock(installer.pull_source, 'pull')
    calls.attach_mock(builder.build, 'build')
    calls.attach_mock(installer.prepare, 'prepare')
    worker.request('hud_patch_menu', payload)
    assert not calls.mock_calls
    worker.step()
    source = payload if isinstance(payload, Path) else installer.pull_source.return_value
    expected = [] if isinstance(payload, Path) else [call.pull(worker.adb, 'RC')]
    assert calls.mock_calls == expected + [
        call.build(source), call.prepare(worker.adb, 'RC', builder.build.return_value['receipt']),
    ]
    builder.latest.assert_not_called()
    installer.approve.assert_not_called()
    assert worker.handled and not worker.activator.calls


def test_queued_basic_request_is_not_changed_by_caller_mutation(menu_worker):
    worker, builder, installer, _ = menu_worker
    request = {'variant': 'basic'}
    worker.request('hud_patch_menu', request)
    request['variant'] = 'advanced'
    worker.step()
    builder.build.assert_called_once_with(installer.pull_source.return_value)
    builder.build_variant.assert_not_called()
    installer.prepare.assert_called_once_with(worker.adb, 'RC', builder.build.return_value['receipt'])
    assert request == {'variant': 'advanced'}


def test_rejected_advanced_request_cannot_be_mutated_into_a_queued_basic_build(menu_worker):
    worker, builder, installer, _ = menu_worker
    request = {'variant': 'advanced'}
    with pytest.raises(ValueError):
        worker.request('hud_patch_menu', request)
    request['variant'] = 'basic'
    worker.step()
    assert worker.commands.empty()
    installer.pull_source.assert_not_called()
    builder.build.assert_not_called()
    builder.build_variant.assert_not_called()
    installer.prepare.assert_not_called()


def test_basic_dispatch_captures_request_before_pull_callback_mutates_it(menu_worker):
    worker, builder, installer, _ = menu_worker
    request = {'variant': 'basic'}
    source = installer.pull_source.return_value
    def pull(*args):
        request['variant'] = 'advanced'
        return source
    installer.pull_source.side_effect = pull
    worker._command('hud_patch_menu', request)
    builder.build.assert_called_once_with(source)
    builder.build_variant.assert_not_called()
    installer.prepare.assert_called_once_with(worker.adb, 'RC', builder.build.return_value['receipt'])


@pytest.mark.parametrize('result', [
    None, {}, {'status': 'failed'}, {'status': 'hud_built'},
    {'status': 'hud_built', 'receipt': ''},
    {'status': 'hud_built', 'receipt': 'other/receipt.json', 'variant': 'advanced'},
    {'status': 'hud_built', 'receipt': 'other/receipt.json', 'variant': 'unknown'},
])
def test_invalid_or_non_basic_result_never_uses_other_or_latest_receipt(menu_worker, result):
    worker, builder, installer, _ = menu_worker
    builder.build.return_value = result
    with pytest.raises(ValueError):
        worker._command('hud_patch_menu', None)
    builder.build_variant.assert_not_called()
    builder.latest.assert_not_called()
    installer.prepare.assert_not_called()
    installer.approve.assert_not_called()


def test_basic_receipt_is_captured_before_progress_consumer_mutates_result(menu_worker):
    worker, builder, installer, events = menu_worker
    receipt = builder.build.return_value['receipt']
    def emit(kind, value):
        events.append((kind, value))
        if kind == 'hud_built':
            value['receipt'] = 'other/latest-receipt.json'
    worker.emit = emit
    worker._command('hud_patch_menu', None)
    installer.prepare.assert_called_once_with(worker.adb, 'RC', receipt)
    builder.latest.assert_not_called()


@pytest.mark.parametrize('phase', ['pull', 'build'])
@pytest.mark.parametrize('change', ['disconnect', 'connection', 'serial', 'selection', 'adb', 'cancel'])
def test_basic_preserves_connection_serial_and_cancel_guards(menu_worker, tmp_path, phase, change):
    worker, builder, installer, events = menu_worker
    method = installer.pull_source if phase == 'pull' else builder.build
    def changed(*args):
        if change == 'disconnect':
            worker.connection.close()
        elif change == 'connection':
            worker.connection = FakeConnection(Device('RC', 'usb'), tmp_path, worker.emit)
        elif change == 'serial':
            worker.connection.device = Device('OTHER', 'usb')
        elif change == 'selection':
            worker.selected = 'OTHER'
        elif change == 'adb':
            worker.adb = object()
        else:
            worker.stop_event.set()
        return method.return_value
    method.side_effect = changed
    if change == 'cancel':
        with pytest.raises(HudCancelled):
            worker._command('hud_patch_menu', None)
    else:
        worker._command('hud_patch_menu', None)
        assert events[-1][0] == 'error'
    if phase == 'pull':
        builder.build.assert_not_called()
    builder.build_variant.assert_not_called()
    installer.prepare.assert_not_called()
    installer.approve.assert_not_called()
    assert not worker.handled


@pytest.mark.parametrize('variant', ['advanced', 'Advanced', 'unknown', ''])
@pytest.mark.parametrize('arguments', [[], ['--hud-build', 'official.apk'], ['--gui-smoke']])
def test_cli_rejects_non_basic_before_paths_build_or_gui(monkeypatch, variant, arguments):
    paths = Mock(side_effect=AssertionError('CLI must reject before resolving paths'))
    root = Mock(side_effect=AssertionError('CLI must reject before creating a GUI'))
    monkeypatch.setattr(desktop, 'paths', paths)
    monkeypatch.setattr(desktop.tk, 'Tk', root)
    monkeypatch.setattr(sys, 'argv', ['app.py', *arguments, '--menu-variant', variant])
    with pytest.raises(SystemExit) as error:
        desktop.main()
    assert error.value.code == 2
    paths.assert_not_called()
    root.assert_not_called()


def test_cli_help_advertises_basic_only(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['app.py', '--help'])
    with pytest.raises(SystemExit) as error:
        desktop.main()
    assert error.value.code == 0
    output = capsys.readouterr().out
    assert '--menu-variant {basic}' in output
    assert 'advanced' not in output.lower()


@pytest.mark.parametrize('variant', [None, 'basic'])
def test_cli_basic_build_uses_legacy_builder_and_preserves_report(tmp_path, monkeypatch, variant):
    builder = Mock(spec=['build'])
    builder.build.return_value = {'status': 'hud_built', 'apk': 'hud.apk', 'receipt': 'new/receipt.json'}
    factory = Mock(return_value=builder)
    monkeypatch.setattr('rc2vi.hud_build.HudBuilder', factory)
    monkeypatch.setattr(desktop, 'paths', lambda: (tmp_path / 'assets', tmp_path / 'work'))
    source = tmp_path / 'official Fly.apk'
    report = tmp_path / 'build report.json'
    arguments = ['app.py', '--hud-build', str(source), '--report', str(report)]
    if variant:
        arguments += ['--menu-variant', variant]
    monkeypatch.setattr(sys, 'argv', arguments)
    assert desktop.main() == 0
    factory.assert_called_once()
    builder.build.assert_called_once_with(source)
    assert json.loads(report.read_text(encoding='utf-8')) == {**builder.build.return_value, 'events': []}


@pytest.mark.parametrize('variant', [None, 'basic'])
def test_gui_smoke_reports_basic_without_a_variant_selector_or_device_workers(tmp_path, monkeypatch, variant):
    worker = Mock(side_effect=AssertionError('GUI smoke must not start device workers'))
    monkeypatch.setattr(desktop, 'Worker', worker)
    monkeypatch.setattr(desktop, 'paths', lambda: (tmp_path / 'assets', tmp_path / 'work'))
    report = tmp_path / 'gui smoke.json'
    arguments = ['app.py', '--gui-smoke', '--report', str(report)]
    if variant:
        arguments += ['--menu-variant', variant]
    monkeypatch.setattr(sys, 'argv', arguments)
    assert desktop.main() == 0
    value = json.loads(report.read_text(encoding='utf-8'))
    assert value['status'] == 'PASS' and value['gui_smoke'] == 'PASS'
    assert value['menu_variant_default'] == value['menu_variant_selected'] == 'basic'
    assert value['menu_variant_choices'] == ['basic']
    assert value['menu_variant_labels'] == []
    assert value['menu_variant_state'] == 'absent'
    worker.assert_not_called()
