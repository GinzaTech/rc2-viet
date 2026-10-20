from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from rc2vi.usb_authorization import authorize_usb


READS = {
    'getprop ro.serialno': 'RC2-A',
    'getprop ro.product.model': 'DJI RC 2',
    'getprop ro.product.device': 'rc331',
    'id': 'uid=0(root) gid=0(root) groups=0(root)',
    'getprop ro.build.version.sdk': '30',
}


def fixture_factory(values=None, on_open=None, on_read=None, fail_open=None):
    sessions = []
    results = dict(READS)
    results.update(values or {})

    class FakeConnection:
        def __init__(self, device, assets, emit):
            self.device, self.assets, self.emit = device, assets, emit
            self.open_calls, self.close_calls = 0, 0
            self.commands = []
            sessions.append(self)

        def open(self):
            self.open_calls += 1
            if on_open:
                on_open(self)
            if fail_open:
                raise fail_open
            return self

        def shell(self, command, **kwargs):
            self.commands.append(command)
            assert command in READS, 'Authorization attempted a device write or unrelated read.'
            if on_read:
                on_read(command)
            return results[command]

        def close(self):
            self.close_calls += 1

    return FakeConnection, sessions


def test_authorization_reads_only_exact_identity_and_closes_without_grounded_flag(tmp_path):
    factory, sessions = fixture_factory()
    selected = SimpleNamespace(serial='RC2-A')
    events = []
    result = authorize_usb(tmp_path, 'RC2-A', connection_factory=factory,
        discover_fn=lambda: [SimpleNamespace(serial='OTHER'), selected],
        emit=lambda *event: events.append(event))
    assert result == {'status': 'authorized', 'authorized_verified': True,
                      'device_modified': False, 'serial': 'RC2-A'}
    assert len(sessions) == 1 and sessions[0].device is selected
    assert sessions[0].assets == Path(tmp_path)
    assert sessions[0].commands == list(READS)
    assert sessions[0].open_calls == sessions[0].close_calls == 1
    assert events[-1][0] == 'identity'


def test_manual_reconnect_is_passed_separately_and_does_not_cancel_authorization(tmp_path):
    cancel, reconnect = Event(), Event()
    reconnect.set()
    def opening(connection):
        assert connection._opening_cancel is cancel
        assert connection._opening_reconnect_event is reconnect
        assert not connection._opening_cancel.is_set()
    factory, sessions = fixture_factory(on_open=opening)
    assert authorize_usb(tmp_path, 'RC2-A', cancel=cancel, reconnect_event=reconnect,
        connection_factory=factory, discover_fn=lambda: [SimpleNamespace(serial='RC2-A')])['authorized_verified']
    assert not cancel.is_set() and sessions[0].close_calls == 1


@pytest.mark.parametrize('devices', [[], [SimpleNamespace(serial='OTHER')],
    [SimpleNamespace(serial='RC2-A'), SimpleNamespace(serial='RC2-A')]])
def test_missing_mismatched_or_ambiguous_selection_never_opens_usb(tmp_path, devices):
    factory, sessions = fixture_factory()
    with pytest.raises(ValueError, match='serial'):
        authorize_usb(tmp_path, 'RC2-A', connection_factory=factory, discover_fn=lambda: devices)
    assert sessions == []


@pytest.mark.parametrize('serial', ['', '../RC2', 'RC2;id', None, 'X' * 129])
def test_invalid_serial_is_rejected_before_discovery(tmp_path, serial):
    def no_discovery():
        raise AssertionError('Invalid serial must not enumerate USB.')
    with pytest.raises(ValueError, match='serial'):
        authorize_usb(tmp_path, serial, discover_fn=no_discovery)


def test_cancel_before_discovery_does_not_open_usb(tmp_path):
    cancel = Event(); cancel.set()
    def no_discovery():
        raise AssertionError('Cancelled operation must not enumerate USB.')
    with pytest.raises(InterruptedError):
        authorize_usb(tmp_path, 'RC2-A', cancel=cancel, discover_fn=no_discovery)


def test_cancel_during_discovery_does_not_construct_connection(tmp_path):
    cancel = Event()
    factory, sessions = fixture_factory()
    def discovery():
        cancel.set()
        return [SimpleNamespace(serial='RC2-A')]
    with pytest.raises(InterruptedError):
        authorize_usb(tmp_path, 'RC2-A', cancel=cancel,
                      connection_factory=factory, discover_fn=discovery)
    assert sessions == []


@pytest.mark.parametrize('at_open', [True, False])
def test_cancel_after_open_or_identity_read_closes_without_further_commands(tmp_path, at_open):
    cancel = Event()
    factory, sessions = fixture_factory(
        on_open=(lambda _: cancel.set()) if at_open else None,
        on_read=(lambda _: cancel.set()) if not at_open else None)
    with pytest.raises(InterruptedError):
        authorize_usb(tmp_path, 'RC2-A', cancel=cancel, connection_factory=factory,
                      discover_fn=lambda: [SimpleNamespace(serial='RC2-A')])
    assert sessions[0].close_calls == 1
    assert sessions[0].commands == ([] if at_open else ['getprop ro.serialno'])


@pytest.mark.parametrize('values', [
    {'getprop ro.serialno': 'RC2-B'},
    {'getprop ro.product.model': 'DJI RC'},
    {'getprop ro.product.device': 'other'},
    {'id': 'uid=2000(shell) gid=2000(shell)'},
    {'getprop ro.build.version.sdk': '31'},
])
def test_wrong_identity_closes_and_never_reports_authorized(tmp_path, values):
    factory, sessions = fixture_factory(values)
    events = []
    with pytest.raises(ValueError):
        authorize_usb(tmp_path, 'RC2-A', connection_factory=factory,
            discover_fn=lambda: [SimpleNamespace(serial='RC2-A')],
            emit=lambda *event: events.append(event))
    assert sessions[0].close_calls == 1
    assert not events


def test_connection_open_failure_is_not_retried_by_authorization_helper(tmp_path):
    factory, sessions = fixture_factory(fail_open=TimeoutError('Allow timed out'))
    with pytest.raises(TimeoutError, match='Allow timed out'):
        authorize_usb(tmp_path, 'RC2-A', connection_factory=factory,
                      discover_fn=lambda: [SimpleNamespace(serial='RC2-A')])
    assert len(sessions) == 1
    assert sessions[0].open_calls == sessions[0].close_calls == 1
    assert sessions[0].commands == []
