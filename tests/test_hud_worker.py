from pathlib import Path
from types import SimpleNamespace
import threading
from unittest.mock import Mock

import pytest

from rc2vi.controller import Worker
from rc2vi.core import Device
from rc2vi.hud_tools import HudCancelled
from tests.test_controller import FakeActivator, FakeConnection


class Builder:
    def __init__(self): self.sources = []
    def build(self, source):
        self.sources.append(source)
        return {'status': 'hud_built', 'apk': str(source.parent / 'HUD.apk'), 'digest': 'a' * 64}


class Installer:
    def __init__(self): self.calls = []; self.canceled = False
    def prepare(self, adb, serial):
        self.calls.append(('prepare', serial))
        return {'status': 'hud_confirmation_required', 'serial': serial, 'token': 'one-use', 'summary': 'Confirm'}
    def approve(self, adb, serial, token):
        self.calls.append(('approve', serial, token))
        return {'status': 'hud_installed'}
    def cancel_pending(self): self.canceled = True


def test_build_can_run_without_rc_usb_connection(tmp_path):
    events = []; builder = Builder()
    worker = Worker(tmp_path, FakeActivator(), lambda *e: events.append(e),
                    discover=lambda: [], hud_builder=builder)
    source = tmp_path / 'original.apk'
    worker._command('hud_build', source)
    assert builder.sources == [source]
    assert events[-1][0] == 'hud_built'


def test_install_prepares_and_waits_for_confirmation(tmp_path):
    events = []; installer = Installer()
    worker = Worker(tmp_path, FakeActivator(), lambda *e: events.append(e),
                    discover=lambda: [Device('RC', 'path')], connection_factory=FakeConnection,
                    hud_installer=installer)
    worker.auto = False; worker.step()
    worker._command('hud_install', None)
    assert installer.calls == [('prepare', 'RC')]
    assert events[-1][0] == 'hud_confirm'
    worker._command('hud_approve', {'serial': 'OTHER', 'token': 'one-use'})
    assert installer.calls == [('prepare', 'RC')]
    worker._command('hud_approve', {'serial': 'RC', 'token': 'one-use'})
    assert installer.calls[-1] == ('approve', 'RC', 'one-use')


def test_disconnect_and_selection_release_invalidate_pending_confirmation(tmp_path):
    installer = Installer()
    worker = Worker(tmp_path, FakeActivator(), lambda *e: None,
                    discover=lambda: [Device('RC', 'path')], connection_factory=FakeConnection,
                    hud_installer=installer)
    worker.auto = False; worker.step(); worker._release()
    assert installer.canceled


def test_incomplete_or_rolled_back_install_never_reports_success(tmp_path):
    events = []
    worker = Worker(tmp_path, FakeActivator(), lambda *e: events.append(e), discover=lambda: [])
    worker._hud_result({'status': 'hud_recovery_required', 'recovery_report': '/private/recovery.json'})
    assert events[-1][0] == 'error'
    worker._hud_result({'status': 'hud_rolled_back', 'recovery_report': '/private/recovery.json'})
    assert events[-1][0] == 'warning'


def test_close_keeps_usb_during_committed_recovery_and_finally_cleans(tmp_path):
    class ProtectedInstaller(Installer):
        def cancel_for_close(self): return False
        def cleanup_pending(self, adb, serial=None): self.calls.append(('cleanup', serial))
    installer = ProtectedInstaller()
    worker = Worker(tmp_path, FakeActivator(), lambda *e: None, hud_installer=installer, discover=lambda: [])
    relay = SimpleNamespace(stop_event=threading.Event())
    connection = SimpleNamespace(relay=relay, device=Device('RC', 'path'), close=lambda: None)
    worker.connection = connection; worker.adb = connection
    worker.close()
    assert not relay.stop_event.is_set()
    worker.run()
    assert ('cleanup', 'RC') in installer.calls


@pytest.fixture
def menu_worker(tmp_path):
    events = []
    builder = Mock()
    builder.build.return_value = {
        'status': 'hud_built', 'apk': str(tmp_path / 'HUD.apk'),
        'digest': 'a' * 64, 'receipt': str(tmp_path / 'new-build' / 'receipt.json'),
    }
    installer = Mock()
    installer.prepare.return_value = {'status': 'hud_installed', 'data_retained': True}
    worker = Worker(tmp_path, FakeActivator(), lambda *e: events.append(e),
                    discover=lambda: [Device('RC', 'path')], connection_factory=FakeConnection,
                    hud_builder=builder, hud_installer=installer)
    worker.selected = 'RC'
    worker.auto = False
    worker.step()
    events.clear()
    return worker, builder, installer, events


def test_patch_menu_builds_then_prepares_exact_new_receipt_on_pinned_device(menu_worker, tmp_path):
    worker, builder, installer, events = menu_worker
    calls = Mock()
    calls.attach_mock(builder.build, 'build')
    calls.attach_mock(installer.prepare, 'prepare')
    adb = worker.adb
    source = tmp_path / 'stock.apk'
    worker.request('hud_patch_menu', source)
    builder.build.assert_not_called()
    worker.step()
    assert calls.mock_calls == [
        ('build', (source,), {}),
        ('prepare', (adb, 'RC', builder.build.return_value['receipt']), {}),
    ]
    assert [event[0] for event in events] == ['applying', 'hud_built', 'applying', 'ready']
    assert events[1][1] is builder.build.return_value
    installer.approve.assert_not_called()
    assert worker.handled and worker.auto is False and worker.activator.calls == []


def test_patch_menu_without_file_pulls_before_build_and_installs_exact_receipt(menu_worker,tmp_path):
    worker,builder,installer,events=menu_worker
    source=tmp_path/'pulled-stock.apk';installer.pull_source.return_value=source
    calls=Mock();calls.attach_mock(installer.pull_source,'pull')
    calls.attach_mock(builder.build,'build');calls.attach_mock(installer.prepare,'prepare')
    worker._command('hud_patch_menu',None)
    assert calls.mock_calls==[
        ('pull',(worker.adb,'RC'),{}),('build',(source,),{}),
        ('prepare',(worker.adb,'RC',builder.build.return_value['receipt']),{})]
    assert events[-1][0]=='ready';installer.approve.assert_not_called()


def test_auto_source_failure_never_builds_or_installs(menu_worker):
    worker,builder,installer,_=menu_worker
    installer.pull_source.side_effect=ValueError('Unsupported source')
    with pytest.raises(ValueError):worker._command('hud_patch_menu',None)
    builder.build.assert_not_called();installer.prepare.assert_not_called()


@pytest.mark.parametrize('change',['serial','selection','adb','connection','cancel'])
def test_auto_source_identity_change_or_cancel_blocks_build(menu_worker,tmp_path,change):
    worker,builder,installer,events=menu_worker
    def pull(*args):
        if change=='serial':worker.connection.device=Device('OTHER','path')
        elif change=='selection':worker.selected='OTHER'
        elif change=='adb':worker.adb=object()
        elif change=='connection':worker.connection=object()
        else:worker.stop_event.set()
        return tmp_path/'pulled.apk'
    installer.pull_source.side_effect=pull
    if change=='cancel':
        with pytest.raises(HudCancelled):worker._command('hud_patch_menu',None)
    else:
        worker._command('hud_patch_menu',None)
        assert events[-1][0]=='error'
    builder.build.assert_not_called();installer.prepare.assert_not_called()


@pytest.mark.parametrize('missing', ['hud_builder', 'hud_installer', 'adb', 'connection'])
def test_patch_menu_requires_all_components_before_build(menu_worker, tmp_path, missing):
    worker, builder, installer, events = menu_worker
    setattr(worker, missing, None)
    worker._command('hud_patch_menu', tmp_path / 'stock.apk')
    builder.build.assert_not_called()
    installer.prepare.assert_not_called()
    assert events[-1][0] == 'error'


def test_patch_menu_disconnected_before_build_never_builds(menu_worker, tmp_path):
    worker, builder, installer, events = menu_worker
    worker.connection.close()
    worker._command('hud_patch_menu', tmp_path / 'stock.apk')
    builder.build.assert_not_called()
    installer.prepare.assert_not_called()
    assert events[-1][0] == 'error'


@pytest.mark.parametrize('failure', [ValueError('Build failed'), HudCancelled('Canceled')])
def test_patch_menu_build_failure_or_cancellation_never_installs(menu_worker, tmp_path, failure):
    worker, builder, installer, events = menu_worker
    builder.build.side_effect = failure
    with pytest.raises(type(failure), match=str(failure)):
        worker._command('hud_patch_menu', tmp_path / 'stock.apk')
    installer.prepare.assert_not_called()
    installer.approve.assert_not_called()
    assert [event[0] for event in events] == ['applying']
    assert not worker.handled


@pytest.mark.parametrize('when', ['before_build', 'after_build'])
def test_patch_menu_stop_event_prevents_install(menu_worker, tmp_path, when):
    worker, builder, installer, events = menu_worker
    if when == 'before_build':
        worker.stop_event.set()
    else:
        def build(source):
            worker.stop_event.set()
            return builder.build.return_value
        builder.build.side_effect = build
    with pytest.raises(HudCancelled):
        worker._command('hud_patch_menu', tmp_path / 'stock.apk')
    assert builder.build.call_count == (when == 'after_build')
    installer.prepare.assert_not_called()
    installer.approve.assert_not_called()
    assert not any(event[0] == 'ready' for event in events)


@pytest.mark.parametrize('change', ['disconnect', 'connection', 'serial', 'selected', 'adb'])
def test_patch_menu_device_change_during_build_prevents_install(menu_worker, tmp_path, change):
    worker, builder, installer, events = menu_worker
    def build(source):
        if change == 'disconnect':
            worker.connection.close()
        elif change == 'connection':
            worker.connection = FakeConnection(Device('RC', 'path'), tmp_path, worker.emit)
        elif change == 'serial':
            worker.connection.device = Device('OTHER', 'path')
        elif change == 'selected':
            worker.selected = 'OTHER'
        else:
            worker.adb = object()
        return builder.build.return_value
    builder.build.side_effect = build
    worker._command('hud_patch_menu', tmp_path / 'stock.apk')
    builder.build.assert_called_once()
    installer.prepare.assert_not_called()
    installer.approve.assert_not_called()
    assert events[-1][0] == 'error'
    assert not worker.handled


def test_patch_menu_single_device_without_explicit_selection_is_pinned(menu_worker, tmp_path):
    worker, builder, installer, events = menu_worker
    worker.selected = ''
    worker._command('hud_patch_menu', tmp_path / 'stock.apk')
    installer.prepare.assert_called_once_with(worker.adb, 'RC', builder.build.return_value['receipt'])
    assert events[-1][0] == 'ready'


def test_patch_menu_mismatched_selection_rejected_before_build(menu_worker, tmp_path):
    worker, builder, installer, events = menu_worker
    worker.selected = 'OTHER'
    worker._command('hud_patch_menu', tmp_path / 'stock.apk')
    builder.build.assert_not_called()
    installer.prepare.assert_not_called()
    assert events[-1][0] == 'error'


@pytest.mark.parametrize('result', [{'status': 'failed'}, {'status': 'hud_built'},
                                  {'status': 'hud_built', 'receipt': ''}])
def test_patch_menu_incomplete_build_result_never_uses_latest(menu_worker, tmp_path, result):
    worker, builder, installer, events = menu_worker
    builder.build.return_value = result
    with pytest.raises(ValueError):
        worker._command('hud_patch_menu', tmp_path / 'stock.apk')
    installer.prepare.assert_not_called()
    installer.approve.assert_not_called()
    assert not worker.handled


def test_patch_menu_different_signer_requires_existing_confirmation(menu_worker, tmp_path):
    worker, builder, installer, events = menu_worker
    confirmation = {'status': 'hud_confirmation_required', 'serial': 'RC', 'token': 'one-use'}
    installer.prepare.return_value = confirmation
    worker._command('hud_patch_menu', tmp_path / 'stock.apk')
    assert events[-1] == ('hud_confirm', confirmation)
    installer.approve.assert_not_called()
    worker._command('hud_approve', {'serial': 'OTHER', 'token': 'one-use'})
    installer.approve.assert_not_called()
    installer.approve.return_value = {'status': 'hud_installed'}
    worker._command('hud_approve', {'serial': 'RC', 'token': 'one-use'})
    installer.approve.assert_called_once_with(worker.adb, 'RC', 'one-use')
    assert events[-1][0] == 'ready'


@pytest.mark.parametrize('trigger', ['hud_built', 'install_progress'])
def test_patch_menu_cancellation_from_progress_never_prepares(menu_worker, tmp_path, trigger):
    worker, builder, installer, events = menu_worker
    def emit(kind, value):
        events.append((kind, value))
        if kind == trigger or (trigger == 'install_progress' and kind == 'applying'
                               and builder.build.called):
            worker.stop_event.set()
    worker.emit = emit
    with pytest.raises(HudCancelled):
        worker._command('hud_patch_menu', tmp_path / 'stock.apk')
    installer.prepare.assert_not_called()
    installer.approve.assert_not_called()


@pytest.mark.parametrize('status,event', [('hud_already_installed', 'ready'),
                                        ('hud_rolled_back', 'warning'),
                                        ('hud_recovery_required', 'error')])
def test_patch_menu_routes_terminal_installer_result(menu_worker, tmp_path, status, event):
    worker, builder, installer, events = menu_worker
    installer.prepare.return_value = {'status': status}
    worker._command('hud_patch_menu', tmp_path / 'stock.apk')
    assert events[-1][0] == event
    installer.approve.assert_not_called()


def test_patch_menu_prepare_failure_never_reports_ready_or_approves(menu_worker, tmp_path):
    worker, builder, installer, events = menu_worker
    installer.prepare.side_effect = ValueError('Device guard failed')
    with pytest.raises(ValueError, match='Device guard failed'):
        worker._command('hud_patch_menu', tmp_path / 'stock.apk')
    installer.approve.assert_not_called()
    assert [event[0] for event in events] == ['applying', 'hud_built', 'applying']
    assert not worker.handled
