"""Installer authorization/recovery tests with no Android or GUI interaction."""
import hashlib
import json
from pathlib import Path
import threading

import pytest


def test_backup_moves_fly_home_to_settings_before_quiescent_capture(context):
    installer,adb,_,_=context
    adb.foreground='mResumedActivity: dji.go.v5/com.dji.mainpageui.device.DJIDeviceActivity'
    previous=adb.shell
    def shell(command,**kwargs):
        if command=='am start -W -n com.android.settings/.Settings':
            adb.foreground='mResumedActivity: com.android.settings/.Settings'
            return 'Status: ok\nComplete'
        return previous(command,**kwargs)
    adb.shell=shell
    installer._leave_fly_for_backup(__import__('rc2vi.hud_backup',fromlist=['PinnedAdb']).PinnedAdb(adb,adb.serial))
    assert 'com.android.settings/.Settings' in adb.foreground

from rc2vi import hud_install as backend
from rc2vi.core import HUD_APK, SUPPORTED_APK
from test_hud_backup import BackupAdb, checksum, remote_cleanup_calls


class Builder:
    def __init__(self, path):
        self.path = path
        self.result = {'status': 'hud_built', 'apk': str(path),
                       'digest': hashlib.sha256(path.read_bytes()).hexdigest(),
                       'source_digest': SUPPORTED_APK, 'certificate_sha256': 'c' * 64,
                       'receipt': str(path.with_suffix('.json'))}
        self.fail = False
        self.verifications = []

    def latest(self):
        return dict(self.result)

    def verify(self, receipt):
        self.verifications.append(receipt)
        if self.fail or hashlib.sha256(self.path.read_bytes()).hexdigest() != self.result['digest']:
            raise ValueError('synthetic-invalid-receipt')
        return dict(self.result)


class InstallAdb(BackupAdb):
    def __init__(self, candidate):
        super().__init__()
        self.candidate = candidate
        self.installed = SUPPORTED_APK
        self.prior_digest = SUPPORTED_APK
        self.model, self.device, self.sdk = 'DJI RC 2', 'rc331', '30'
        self.identity = 'uid=0(root)'
        self.physical = self.serial
        self.version, self.code, self.uid = '1.21.8', 3115809, 10029
        self.foreground = 'mResumedActivity: ActivityRecord{123 u0 app.lawnchair/.LawnchairLauncher t1}'
        self.update_result = 'Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: signer mismatch]'
        self.new_result = 'Success'
        self.removed = False
        self.disconnect_after_remove = False
        self.bad_stage = False
        self.installs = 0

    def command(self, *args, **kwargs):
        if args == ('get-state',):
            self.calls.append(args)
            if self.disconnect:
                raise ConnectionError('synthetic-disconnection')
            return 'device'
        return super().command(*args, **kwargs)

    def shell(self, cmd, **kwargs):
        if self.disconnect:
            raise ConnectionError('synthetic-disconnection')
        self.calls.append(cmd)
        props = {'ro.product.model': self.model, 'ro.product.device': self.device,
                 'ro.build.version.sdk': self.sdk, 'ro.serialno': self.physical}
        if cmd.startswith('getprop '):
            return props.get(cmd[8:], '')
        if cmd == 'id':
            return self.identity
        if cmd == 'dumpsys package dji.go.v5':
            return f'userId={self.uid}\nversionName={self.version}\nversionCode={self.code}\nUser 0: stopped=true'
        if cmd.startswith('pm path dji.go.v5'):
            return '' if self.removed else 'package:/data/app/dji.go.v5/base.apk'
        if cmd.startswith('dumpsys activity'):
            return self.foreground
        if cmd.startswith('sha256sum /data/app/'):
            return checksum(cmd, self.installed)
        if cmd.startswith('sha256sum ') and self.bad_stage and 'rc2vi-hud-apk-' in cmd:
            return checksum(cmd, '0' * 64)
        if cmd.startswith('pm install -r '):
            self.installs += 1
            if self.update_result == 'Success':
                self.installed = self.candidate
            return self.update_result
        if cmd == 'pm uninstall --user 0 dji.go.v5':
            self.removed = True
            if self.disconnect_after_remove:
                self.disconnect = True
                raise ConnectionError('synthetic-disconnection')
            return 'Success'
        if cmd.startswith('pm install --user 0 '):
            self.installs += 1
            if 'prior.apk' in cmd:
                self.installed, self.removed = self.prior_digest, False
                return 'Success'
            if self.new_result == 'Success':
                self.installed, self.removed, self.uid = self.candidate, False, 10031
            return self.new_result
        if cmd == 'cmd overlay list --user 0':
            return '[x] local.dji.fly.vietnamese'
        if cmd.startswith('stat -c %u'):
            return super().shell(cmd, **kwargs) if (':' in cmd or '/data/local/tmp/rc2vi-hud-data-' in cmd) else str(self.uid)
        # Prior APK is synthetic; map the trusted remote digest to its test bytes.
        self.calls.pop()
        return super().shell(cmd, **kwargs)


@pytest.fixture
def context(tmp_path, monkeypatch):
    assets = tmp_path / 'assets' / 'hud'
    assets.mkdir(parents=True)
    helper = b'synthetic-arm32-helper'
    (assets / 'restore-owner').write_bytes(helper)
    (assets / 'classes23.dex').write_bytes(b'synthetic-hud-dex')
    (assets / 'payload.json').write_text(json.dumps({
        'schema': 1, 'sha256': hashlib.sha256(b'synthetic-hud-dex').hexdigest(),
        'restore_owner_sha256': hashlib.sha256(helper).hexdigest(),
    }))
    candidate = tmp_path / 'candidate.apk'
    candidate.write_bytes(b'new-hud-apk')
    builder = Builder(candidate)
    adb = InstallAdb(builder.result['digest'])
    events = []
    installer = backend.HudInstaller(assets.parent, tmp_path / 'work',
                                     lambda *event: events.append(event), builder)
    # Synthetic stock bytes still go through backup digest validation.
    monkeypatch.setattr(backend, 'SUPPORTED_APK', hashlib.sha256(b'prior-apk').hexdigest())
    builder.result['source_digest'] = backend.SUPPORTED_APK
    adb.installed = backend.SUPPORTED_APK
    adb.prior_digest = backend.SUPPORTED_APK
    return installer, adb, builder, events


def destructive(adb):
    return [cmd for cmd in adb.calls if isinstance(cmd, str) and
            ('uninstall' in cmd or 'pm clear' in cmd)]


def test_exact_hash_already_installed_is_read_only(context):
    installer, adb, builder, _ = context
    adb.installed = builder.result['digest']
    assert installer.prepare(adb, adb.serial)['status'] == 'hud_already_installed'
    assert adb.installs == 0 and not destructive(adb)
    assert builder.verifications


def test_same_signer_update_is_retained_and_hash_verified(context):
    installer, adb, _, _ = context
    adb.update_result = 'Success'
    assert installer.prepare(adb, adb.serial)['status'] == 'hud_installed'
    assert not destructive(adb)


def test_signature_mismatch_requires_fresh_recovery_and_one_shot_consent(context):
    installer, adb, _, events = context
    result = installer.prepare(adb, adb.serial)
    assert result['status'] == 'hud_confirmation_required'
    assert result['serial'] == adb.serial and result['token'] and result['summary']
    assert Path(result['backup']).is_file()
    assert not destructive(adb)
    assert not any(event[0] in {'hud_confirm', 'hud_confirmation_required'} for event in events)
    assert adb.serial in result['summary'] and 'Keystore' in result['summary']
    assert 'đăng nhập' in result['summary']
    approved = installer.approve(adb, adb.serial, result['token'])
    assert approved['status'] == 'hud_installed'
    assert destructive(adb) == ['pm uninstall --user 0 dji.go.v5']
    with pytest.raises(ValueError):
        installer.approve(adb, adb.serial, result['token'])


@pytest.mark.parametrize('attribute,value', [
    ('model', 'DJI RC'), ('device', 'other'), ('sdk', '31'),
    ('identity', 'uid=2000(shell)'), ('version', '1.21.9'), ('code', 3115810),
    ('installed', 'f' * 64), ('physical', 'OTHER'),
    ('foreground', 'mResumedActivity: dji.go.v5/.CameraActivity'),
    ('foreground', 'garbage'),
])
def test_prepare_rejects_unsafe_device_version_apk_or_foreground(context, attribute, value):
    installer, adb, _, _ = context
    setattr(adb, attribute, value)
    with pytest.raises(ValueError):
        installer.prepare(adb, adb.serial)
    assert not destructive(adb) and adb.installs == 0


@pytest.mark.parametrize('change', ['serial', 'installed', 'candidate', 'archive', 'foreground', 'uid', 'sdk'])
def test_approve_rechecks_bound_consent_and_never_uninstalls_after_state_change(context, change):
    installer, adb, builder, _ = context
    result = installer.prepare(adb, adb.serial)
    serial = adb.serial
    if change == 'serial':
        serial = 'OTHER'
    elif change == 'candidate':
        builder.path.write_bytes(b'tampered')
    elif change == 'archive':
        Path(result['backup']).write_bytes(b'tampered')
    elif change == 'foreground':
        adb.foreground = 'mResumedActivity: dji.go.v5/.CameraActivity'
    elif change == 'uid':
        adb.uid += 1
    else:
        setattr(adb, change, 'f' * 64 if change == 'installed' else '31')
    with pytest.raises(ValueError):
        installer.approve(adb, serial, result['token'])
    assert not destructive(adb)


def test_backup_failure_or_bad_staging_cannot_request_confirmation(context):
    installer, adb, _, events = context
    adb.pull_fail = True
    with pytest.raises((ValueError, RuntimeError, ConnectionError)):
        installer.prepare(adb, adb.serial)
    assert not destructive(adb)
    assert not any(event[0] == 'hud_confirm' for event in events)


def test_staging_mismatch_is_detected_before_pm_install(context):
    installer, adb, _, _ = context
    adb.bad_stage = True
    with pytest.raises(ValueError):
        installer.prepare(adb, adb.serial)
    assert adb.installs == 0
    assert any(isinstance(cmd, str) and cmd.startswith('rm -f /data/local/tmp/rc2vi-hud-apk-')
               for cmd in adb.calls)


def test_cancel_pending_revokes_consent(context):
    installer, adb, _, _ = context
    result = installer.prepare(adb, adb.serial)
    installer.cancel_pending()
    with pytest.raises(ValueError):
        installer.approve(adb, adb.serial, result['token'])
    assert not destructive(adb)


def test_cancel_before_prepare_never_touches_device(context):
    installer, adb, _, _ = context
    installer.cancel = threading.Event()
    installer.cancel.set()
    with pytest.raises(RuntimeError):
        installer.prepare(adb, adb.serial)
    assert not adb.calls


def test_failed_new_install_rolls_back_verified_previous_apk_and_data(context):
    installer, adb, _, _ = context
    result = installer.prepare(adb, adb.serial)
    adb.new_result = 'Failure [INSTALL_FAILED_INVALID_APK]'
    rolled = installer.approve(adb, adb.serial, result['token'])
    assert rolled['status'] == 'hud_rolled_back'
    assert adb.installed == backend.SUPPORTED_APK
    assert any(isinstance(cmd, str) and cmd.startswith('tar -x') for cmd in adb.calls)


def test_disconnect_after_removal_preserves_private_recovery_and_uncertain_report(context):
    installer, adb, _, events = context
    result = installer.prepare(adb, adb.serial)
    adb.disconnect_after_remove = True
    report = installer.approve(adb, adb.serial, result['token'])
    assert report['status'] == 'hud_recovery_required'
    assert Path(report['backup']).is_file() and Path(report['recovery_report']).is_file()
    assert report['restored'] is False
    assert 'restored' not in report['summary'].lower()
    assert not any(event[0].startswith('hud_') for event in events)
    assert adb.serial in report['summary'] and 'Keystore' in report['summary']


def test_substring_success_is_not_accepted(context):
    installer, adb, _, _ = context
    adb.update_result = 'Failure: Success was not returned'
    with pytest.raises(RuntimeError):
        installer.prepare(adb, adb.serial)
    assert not destructive(adb)


def test_explicit_receipt_does_not_depend_on_latest(context):
    installer, adb, builder, _ = context
    builder.latest = lambda: None
    adb.update_result = 'Success'
    assert installer.prepare(adb, adb.serial, builder.result['receipt'])['status'] == 'hud_installed'


def test_missing_verified_build_rejects_before_device_reads(context):
    installer, adb, builder, _ = context
    builder.latest = lambda: None
    with pytest.raises(ValueError):
        installer.prepare(adb, adb.serial)
    assert not adb.calls


def test_wrong_token_cannot_remove_app_or_consume_valid_consent(context):
    installer, adb, _, _ = context
    result = installer.prepare(adb, adb.serial)
    with pytest.raises(ValueError):
        installer.approve(adb, adb.serial, 'wrong')
    assert not destructive(adb)
    assert installer.approve(adb, adb.serial, result['token'])['status'] == 'hud_installed'


def test_changed_userdata_before_approve_requires_new_confirmation(context):
    from test_hud_backup import archive_bytes
    installer, adb, _, _ = context
    result = installer.prepare(adb, adb.serial)
    adb.raw = archive_bytes([
        ('data/user/0/dji.go.v5', 'dir', b''),
        ('data/user_de/0/dji.go.v5', 'dir', b''),
        ('data/media/0/Android/data/dji.go.v5', 'dir', b''),
        ('data/user/0/dji.go.v5/files/new', 'file', b'updated'),
    ])
    with pytest.raises(ValueError):
        installer.approve(adb, adb.serial, result['token'])
    assert not destructive(adb)


@pytest.mark.parametrize('asset', ['restore-owner', 'classes23.dex', 'payload.json'])
def test_tampered_helper_or_payload_cannot_authorize_removal(context, asset):
    installer, adb, _, _ = context
    (installer.assets / 'hud' / asset).write_bytes(b'tampered')
    with pytest.raises(ValueError):
        installer.prepare(adb, adb.serial)
    assert not destructive(adb)


def test_optional_helper_hash_is_required_only_for_replacement(context):
    installer, adb, _, _ = context
    path = installer.assets / 'hud' / 'payload.json'
    value = json.loads(path.read_text())
    value.pop('restore_owner_sha256')
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        installer.prepare(adb, adb.serial)
    assert not destructive(adb)
    adb.update_result = 'Success'
    assert installer.prepare(adb, adb.serial)['status'] == 'hud_installed'


def test_relay_target_must_resolve_to_selected_physical_serial(context):
    installer, adb, builder, _ = context
    physical = adb.serial
    adb.serial = '127.0.0.1:49152'
    adb.update_result = 'Success'
    # Backup-free route exercises exactly the existing USB relay transport shape.
    assert installer.prepare(adb, physical)['status'] == 'hud_installed'
    assert adb.serial == '127.0.0.1:49152'


def test_changed_transport_serial_is_rejected(context):
    installer, adb, _, _ = context
    result = installer.prepare(adb, adb.serial)
    original = adb.serial
    adb.serial = 'OTHER'
    with pytest.raises(ValueError):
        installer.approve(adb, original, result['token'])
    assert not destructive(adb)


def test_disconnect_after_new_install_never_claims_data_restored(context):
    installer, adb, _, _ = context
    result = installer.prepare(adb, adb.serial)
    shell = adb.shell
    def disconnect(cmd, **kwargs):
        output = shell(cmd, **kwargs)
        if cmd.startswith('pm install --user 0 '):
            adb.disconnect = True
        return output
    adb.shell = disconnect
    report = installer.approve(adb, adb.serial, result['token'])
    assert report['status'] == 'hud_recovery_required' and not report['restored']


def test_restore_failure_rolls_back_or_retains_recovery_without_false_success(context):
    installer, adb, _, _ = context
    result = installer.prepare(adb, adb.serial)
    installer.backup.restore = lambda *args: (_ for _ in ()).throw(RuntimeError('synthetic-restore-failure'))
    report = installer.approve(adb, adb.serial, result['token'])
    assert report['status'] == 'hud_recovery_required' and not report['restored']
    assert Path(report['backup']).is_file()


def test_cancel_requested_after_remove_still_attempts_recovery(context):
    installer, adb, _, _ = context
    event = threading.Event()
    installer.cancel = event
    result = installer.prepare(adb, adb.serial)
    shell = adb.shell
    def cancel_after_remove(cmd, **kwargs):
        output = shell(cmd, **kwargs)
        if cmd == 'pm uninstall --user 0 dji.go.v5':
            event.set()
        return output
    adb.shell = cancel_after_remove
    adb.new_result = 'Failure [INSTALL_FAILED_INVALID_APK]'
    report = installer.approve(adb, adb.serial, result['token'])
    assert report['status'] == 'hud_rolled_back'


def test_public_trust_check_validates_builder_receipts_and_rejects_hash_bypass(context):
    installer, _, builder, _ = context
    result = backend.verify_trusted_installed_apk(builder, builder.result['digest'])
    assert result['digest'] == builder.result['digest'] and builder.verifications
    assert installer.trusted_artifact(builder.result['digest'])['digest'] == builder.result['digest']
    with pytest.raises(ValueError):
        backend.verify_trusted_installed_apk(builder, 'f' * 64)
    builder.path.write_bytes(b'tampered')
    with pytest.raises(ValueError):
        backend.verify_trusted_installed_apk(builder, builder.result['digest'])


def test_public_trust_check_discovers_previously_verified_builder_artifacts(context, tmp_path):
    installer, adb, builder, _ = context
    root = tmp_path / 'builder-work' / 'builds' / ('a' * 32)
    root.mkdir(parents=True)
    receipt = root / 'receipt.json'
    previous = root / 'hud.apk'
    previous.write_bytes(b'previous-local-hud')
    previous_digest = hashlib.sha256(previous.read_bytes()).hexdigest()
    receipt.write_text(json.dumps({'digest': previous_digest}))
    builder.work = root.parent.parent
    verify = builder.verify
    def verified(reference):
        if Path(reference) == receipt:
            return {**builder.result, 'apk': str(previous), 'digest': previous_digest, 'receipt': str(receipt)}
        return verify(reference)
    builder.verify = verified
    assert backend.verify_trusted_installed_apk(builder, previous_digest)['digest'] == previous_digest
    adb.installed = previous_digest
    adb.update_result = 'Success'
    assert installer.prepare(adb, adb.serial)['status'] == 'hud_installed'


def test_tampered_optional_helper_blocks_even_same_signer_update(context):
    installer, adb, _, _ = context
    (installer.assets / 'hud' / 'restore-owner').write_bytes(b'tampered')
    adb.update_result = 'Success'
    with pytest.raises(ValueError):
        installer.prepare(adb, adb.serial)
    assert adb.installs == 0


def test_cancel_pending_during_approval_revokes_before_uninstall_without_waiting(context):
    installer, adb, _, _ = context
    result = installer.prepare(adb, adb.serial)
    fresh = installer.backup.check_fresh
    canceled = threading.Event()
    def cancel_after_fresh(*args):
        fresh(*args)
        def revoke():
            installer.cancel_pending()
            canceled.set()
        thread = threading.Thread(target=revoke, daemon=True)
        thread.start()
        assert canceled.wait(1), 'GUI release/cancel must not wait on the approval lock'
    installer.backup.check_fresh = cancel_after_fresh
    with pytest.raises(RuntimeError):
        installer.approve(adb, adb.serial, result['token'])
    assert not destructive(adb)


def test_wrong_installed_hash_after_success_never_claims_hud_installed(context):
    installer, adb, _, _ = context
    result = installer.prepare(adb, adb.serial)
    shell = adb.shell
    def wrong_bytes(cmd, **kwargs):
        output = shell(cmd, **kwargs)
        if cmd.startswith('pm install --user 0 '):
            adb.installed = 'e' * 64
        return output
    adb.shell = wrong_bytes
    report = installer.approve(adb, adb.serial, result['token'])
    assert report['status'] == 'hud_recovery_required' and report['restored'] is False
    assert len(destructive(adb)) == 1  # Never remove the unexpected package as rollback.


def test_wrong_device_is_rejected_before_confirmation_is_consumed_or_mutation(context):
    installer, adb, _, _ = context
    result = installer.prepare(adb, adb.serial)
    adb.physical = 'OTHER'
    with pytest.raises(ValueError):
        installer.approve(adb, adb.serial, result['token'])
    assert not destructive(adb)
    with pytest.raises(ValueError):
        installer.approve(adb, adb.serial, result['token'])


@pytest.mark.parametrize('token', [None, 123, '☠'])
def test_invalid_token_type_or_encoding_is_a_safe_rejection(context, token):
    installer, adb, _, _ = context
    result = installer.prepare(adb, adb.serial)
    with pytest.raises(ValueError):
        installer.approve(adb, adb.serial, token)
    assert not destructive(adb)
    installer.cancel_pending()
    assert Path(result['backup']).is_file() and Path(result['recovery_report']).is_file()


def test_public_trust_check_does_not_leak_builder_source_path(context):
    installer, _, builder, _ = context
    def failure(reference):
        raise ValueError('SENSITIVE_SOURCE_PATH/private-artifact.apk')
    builder.verify = failure
    with pytest.raises(ValueError) as error:
        installer.trusted_artifact(builder.result['digest'])
    assert 'SENSITIVE_SOURCE_PATH' not in str(error.value)


def test_cancel_at_atomic_removal_handoff_still_blocks_dispatch(context):
    installer, adb, _, _ = context
    result = installer.prepare(adb, adb.serial)
    report = installer.backup.report
    def revoke_at_handoff(recovery, status, phase):
        value = report(recovery, status, phase)
        if phase == 'removal_starting':
            installer.cancel_pending()
        return value
    installer.backup.report = revoke_at_handoff
    with pytest.raises(RuntimeError):
        installer.approve(adb, adb.serial, result['token'])
    assert not destructive(adb)


def test_prepare_user_error_is_vietnamese_and_hides_private_io_path(context):
    installer, adb, _, _ = context
    def failure(*args, **kwargs):
        raise PermissionError(13, 'denied', 'PRIVATE_ACCOUNT_PATH/recovery/data.tar')
    installer._helper = failure
    with pytest.raises(RuntimeError) as error:
        installer.prepare(adb, adb.serial)
    assert 'Không thể' in str(error.value) and 'HUD_IO' in str(error.value)
    assert 'PRIVATE_ACCOUNT_PATH' not in str(error.value)
    assert not destructive(adb)


def test_close_before_handoff_revokes_consent_and_allows_shutdown_after_cleanup(context):
    installer, adb, _, _ = context
    pending = installer.prepare(adb, adb.serial)
    assert installer.cancel_for_close() is False
    with pytest.raises((ValueError, RuntimeError)):
        installer.approve(adb, adb.serial, pending['token'])
    assert not destructive(adb)
    assert Path(pending['backup']).is_file()
    assert installer.cleanup_pending(adb)['status'] == 'hud_cleanup_complete'
    assert installer.cancel_for_close() is True


def test_close_is_terminal_and_prepare_cannot_rearm_consent(context):
    installer, adb, _, _ = context
    assert installer.cancel_for_close() is True
    with pytest.raises(RuntimeError):
        installer.prepare(adb, adb.serial)
    assert not adb.calls


@pytest.mark.parametrize('new_install_result,expected_status', [
    ('Success', 'hud_installed'),
    ('Failure [INSTALL_FAILED_INVALID_APK]', 'hud_rolled_back'),
])
def test_close_during_install_or_rollback_preserves_usb_until_recovery_completes(
        context, new_install_result, expected_status):
    installer, adb, _, _ = context
    stop = threading.Event()
    installer.cancel = stop
    pending = installer.prepare(adb, adb.serial)
    adb.new_result = new_install_result
    original = installer.backup.restore
    close_results = []
    def close_then_restore(*args):
        safe = installer.cancel_for_close()
        close_results.append(safe)
        # Model Worker.close: stop its job loop, but close USB only on True.
        stop.set()
        if safe:
            adb.disconnect = True
        return original(*args)
    installer.backup.restore = close_then_restore
    result = installer.approve(adb, adb.serial, pending['token'])
    assert close_results == [False]
    assert result['status'] == expected_status and not adb.disconnect
    assert installer.cancel_for_close() is True


def test_close_racing_before_atomic_handoff_prevents_uninstall_without_waiting(context):
    installer, adb, _, _ = context
    pending = installer.prepare(adb, adb.serial)
    report = installer.backup.report
    close_results = []
    def close_at_handoff(recovery, status, phase):
        value = report(recovery, status, phase)
        if phase == 'removal_starting':
            finished = threading.Event()
            def close_worker():
                close_results.append(installer.cancel_for_close())
                finished.set()
            thread = threading.Thread(target=close_worker, daemon=True)
            thread.start()
            assert finished.wait(2), 'Close must use the consent lock, not the long approval lock'
            thread.join(timeout=1)
        return value
    installer.backup.report = close_at_handoff
    with pytest.raises(RuntimeError):
        installer.approve(adb, adb.serial, pending['token'])
    assert close_results == [False] and not destructive(adb)
    assert remote_cleanup_calls(adb) and installer.cancel_for_close() is True


def test_close_after_handoff_before_uninstall_dispatch_keeps_transport_open(context):
    installer, adb, _, _ = context
    pending = installer.prepare(adb, adb.serial)
    original = installer._replace
    close_results = []
    def close_at_dispatch(*args):
        finished = threading.Event()
        def close_worker():
            safe = installer.cancel_for_close()
            close_results.append(safe)
            if safe:
                adb.disconnect = True
            finished.set()
        thread = threading.Thread(target=close_worker, daemon=True)
        thread.start()
        assert finished.wait(2)
        thread.join(timeout=1)
        return original(*args)
    installer._replace = close_at_dispatch
    result = installer.approve(adb, adb.serial, pending['token'])
    assert close_results == [False] and not adb.disconnect
    assert result['status'] == 'hud_installed'
    assert installer.cancel_for_close() is True


def test_close_safety_stays_false_through_final_transport_cleanup(context):
    installer, adb, _, _ = context
    pending = installer.prepare(adb, adb.serial)
    cleanup = installer._cleanup_stage
    close_results = []
    def close_at_cleanup(*args):
        close_results.append(installer.cancel_for_close())
        return cleanup(*args)
    installer._cleanup_stage = close_at_cleanup
    result = installer.approve(adb, adb.serial, pending['token'])
    assert result['status'] == 'hud_installed' and close_results == [False]
    assert installer.cancel_for_close() is True


def test_close_safety_releases_after_uncertain_recovery_report_is_preserved(context):
    installer, adb, _, _ = context
    pending = installer.prepare(adb, adb.serial)
    adb.disconnect_after_remove = True
    result = installer.approve(adb, adb.serial, pending['token'])
    assert result['status'] == 'hud_recovery_required' and not result['restored']
    assert Path(result['backup']).is_file() and Path(result['recovery_report']).is_file()
    assert installer.cancel_for_close() is True


def test_close_safety_releases_when_final_cleanup_raises_after_completed_recovery(context):
    installer, adb, _, _ = context
    pending = installer.prepare(adb, adb.serial)
    close_results = []
    def failed_cleanup(*args):
        close_results.append(installer.cancel_for_close())
        raise RuntimeError('synthetic-cleanup-failure')
    installer._cleanup_stage = failed_cleanup
    with pytest.raises(RuntimeError, match='synthetic-cleanup-failure'):
        installer.approve(adb, adb.serial, pending['token'])
    assert close_results == [False]
    assert Path(pending['backup']).is_file() and Path(pending['recovery_report']).is_file()
    assert installer.cancel_for_close() is True


def test_close_prevents_prepare_publishing_confirmation_after_backup(context):
    installer, adb, _, events = context
    report = installer.backup.report
    close_results = []
    def close_before_publication(recovery, status, phase):
        value = report(recovery, status, phase)
        if phase == 'verified_backup_and_candidate':
            close_results.append(installer.cancel_for_close())
        return value
    installer.backup.report = close_before_publication
    with pytest.raises(RuntimeError):
        installer.prepare(adb, adb.serial)
    assert close_results == [False] and not destructive(adb)
    assert remote_cleanup_calls(adb) and installer.cancel_for_close() is True
    assert not any(event[0].startswith('hud_') for event in events)


@pytest.mark.parametrize('outcome', ['success', 'rollback', 'uncertain'])
def test_private_remote_cleanup_follows_verified_terminal_state_only(context, outcome):
    installer, adb, _, _ = context
    pending = installer.prepare(adb, adb.serial)
    if outcome == 'rollback':
        adb.new_result = 'Failure [INSTALL_FAILED_INVALID_APK]'
    elif outcome == 'uncertain':
        installer.backup.restore = lambda *args: (_ for _ in ()).throw(RuntimeError('synthetic-restore-failure'))
    result = installer.approve(adb, adb.serial, pending['token'])
    assert bool(remote_cleanup_calls(adb)) is (outcome != 'uncertain')
    assert Path(pending['backup']).is_file() and Path(pending['recovery_apk']).is_file()
    if outcome == 'uncertain':
        assert result['status'] == 'hud_recovery_required'


def test_cancel_queues_cleanup_without_gui_usb_io_then_worker_drains(context):
    installer, adb, _, _ = context
    pending = installer.prepare(adb, adb.serial)
    count = len(adb.calls)
    installer.cancel_pending()
    assert len(adb.calls) == count
    result = installer.cleanup_pending(adb, adb.serial)
    assert result['status'] == 'hud_cleanup_complete' and result['cleaned'] == 1
    assert remote_cleanup_calls(adb) and Path(pending['backup']).is_file()


def test_close_holds_usb_for_queued_cleanup_and_releases_after_worker_attempt(context):
    installer, adb, _, _ = context
    pending = installer.prepare(adb, adb.serial)
    count = len(adb.calls)
    assert installer.cancel_for_close() is False and len(adb.calls) == count
    original = installer.backup.cleanup_remote
    during = []
    def clean_while_closing(*args):
        during.append(installer.cancel_for_close())
        return original(*args)
    installer.backup.cleanup_remote = clean_while_closing
    result = installer.cleanup_pending(adb, adb.serial)
    assert result['status'] == 'hud_cleanup_complete' and during == [False]
    assert installer.cancel_for_close() is True and Path(pending['backup']).is_file()


def test_offline_cancel_cleanup_reports_retained_then_allows_close(context):
    installer, adb, _, events = context
    pending = installer.prepare(adb, adb.serial)
    installer.cancel_pending()
    adb.disconnect = True
    result = installer.cleanup_pending(adb, adb.serial)
    assert result['status'] == 'hud_cleanup_retained' and result['retained'] == 1
    assert any(event[0] == 'warning' for event in events)
    assert Path(pending['recovery_report']).is_file() and installer.cancel_for_close() is True


def test_pre_removal_guard_failure_cleans_remote_without_uninstall(context):
    installer, adb, _, _ = context
    pending = installer.prepare(adb, adb.serial)
    adb.foreground = 'mResumedActivity: dji.go.v5/.CameraActivity'
    with pytest.raises(ValueError):
        installer.approve(adb, adb.serial, pending['token'])
    assert remote_cleanup_calls(adb) and not destructive(adb)


def test_cancel_cleanup_never_runs_while_recovery_is_active(context):
    installer, adb, _, _ = context
    pending = installer.prepare(adb, adb.serial)
    original = installer.backup.restore
    states = []
    def during_restore(*args):
        installer.cancel_pending()
        states.append(installer.cleanup_pending(adb, adb.serial)['status'])
        return original(*args)
    installer.backup.restore = during_restore
    assert installer.approve(adb, adb.serial, pending['token'])['status'] == 'hud_installed'
    assert states == ['hud_cleanup_deferred']


def test_worker_finally_can_record_cleanup_without_a_live_transport(context):
    installer, adb, _, events = context
    pending = installer.prepare(adb, adb.serial)
    installer.cancel_pending()
    result = installer.cleanup_pending(None)
    assert result['status'] == 'hud_cleanup_retained' and result['retained'] == 1
    value = json.loads(Path(pending['recovery_report']).read_text())
    assert value['remote_cleanup'] == 'retained'
    assert any(event[0] == 'warning' for event in events)
    assert installer.cancel_for_close() is True
