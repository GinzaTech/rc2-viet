"""Verified HUD installation sidecar with explicit one-shot replacement consent.

GUI calls prepare(), shows its summary, and calls approve() only after an explicit
confirmation. No GUI imports, signing keys, network, camera controls or auto-clear.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import re
import secrets
import shlex
import threading
import uuid

from .core import HUD_APK, OVERLAY_PACKAGE, SUPPORTED_APK, validate_package_path
from .hud_backup import (HASH, PACKAGE, HudBackup, HudCancelled, PinnedAdb, assert_stopped,
                         check_cancel, guard_path, make_private, remote_digest,
                         run, sha256_file, user_errors, valid_uid)


def _verified_artifact(builder, reference, cancel=None, historical=False):
    check_cancel(cancel)
    try:
        verifier = getattr(builder, 'verify_historical', builder.verify) if historical else builder.verify
        value = verifier(reference)
        required = {'apk', 'digest', 'source_digest', 'certificate_sha256'}
        if (not isinstance(value, dict) or not required.issubset(value)
                or value['source_digest'] != SUPPORTED_APK
                or not isinstance(value['digest'], str) or not HASH.fullmatch(value['digest'])
                or not isinstance(value['certificate_sha256'], str)
                or not HASH.fullmatch(value['certificate_sha256'])):
            raise ValueError('Thông tin kiểm chứng APK HUD không hợp lệ.')
        path = guard_path(value['apk'])
        if sha256_file(path, cancel) != value['digest']:
            raise ValueError('SHA-256 của APK HUD cần cài không khớp.')
        return {**{key: value[key] for key in required}, 'apk': str(path), 'receipt': str(reference)}
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        check_cancel(cancel)
        raise ValueError('Không kiểm chứng được biên nhận hoặc tính toàn vẹn của APK HUD.') from None


@user_errors
def verify_trusted_installed_apk(builder, digest, receipt=None, cancel=None):
    """Return builder-revalidated metadata for a dynamic installed HUD hash.

    For Activator: keep model/root/SDK/version/path/foreground guards, then use
    this ONLY to recognize an APK not in the two fixed stock/legacy pins. Every
    match requires the full builder verifier, pinned stock source, public signer
    digest and an independent hash of retained bytes. Scanned receipt metadata
    only filters candidates; it never grants trust. Unknown hashes raise.
    No device access, arbitrary hash allowlist or package-guard bypass is provided.
    """
    from .hud_tools import load_json

    if not isinstance(digest, str) or not HASH.fullmatch(digest):
        raise ValueError('Cần mã SHA-256 đầy đủ của APK đang cài.')
    check_cancel(cancel)
    work = getattr(builder, 'work', None)
    references = []
    if receipt is not None:
        references.append(receipt.get('receipt') if isinstance(receipt, dict) else receipt)
    elif work is None:
        # Managed scans must not call latest(): it fully verifies an unrelated APK.
        try:
            latest = builder.latest()
            if isinstance(latest, dict) and latest.get('receipt'):
                references.append(latest['receipt'])
        except (OSError, ValueError, RuntimeError):
            check_cancel(cancel)
    direct_references = {str(ref) for ref in references if ref is not None}
    if work is not None:
        root = guard_path(Path(work) / 'builds')
        references.extend(str(path) for path in root.glob('*/receipt.json'))
    for reference in dict.fromkeys(str(ref) for ref in references if ref is not None):
        check_cancel(cancel)
        try:
            if reference not in direct_references:
                metadata = load_json(guard_path(reference))
                if metadata.get('digest') != digest:
                    continue
            value = _verified_artifact(builder, reference, cancel, historical=True)
            if value['digest'] == digest:
                return value
        except (OSError, ValueError):
            check_cancel(cancel)
            continue
    check_cancel(cancel)
    raise ValueError('APK DJI Fly đang cài không thuộc bản HUD được trình tạo APK kiểm chứng.')


@dataclass(frozen=True)
class PendingInstall:
    token: str
    serial: str
    snapshot: dict
    candidate: dict
    recovery: dict
    helper_digest: str
    overlay: bool


class HudInstaller:
    """Public contract: prepare(), approve(), cancel_pending(), cancel_for_close().

Device failures before removal raise sanitized errors. After removal begins, an
uncertain or incomplete recovery returns hud_recovery_required and a private report.
"""
    def __init__(self, assets, work, emit, builder, cancel=None):
        self.assets, self.work = Path(assets), Path(work)
        self.emit, self.builder, self.cancel = emit, builder, cancel
        self.backup = HudBackup(self.work, emit, cancel)
        self._pending = None
        self._trusted = {}
        self._device_sources = {}
        self._lock = threading.RLock()
        self._consent_lock = threading.RLock()
        self._revoked = threading.Event()
        self._removal_started = False
        self._close_requested = False
        self._active_recovery = None
        self._backup_work_active = False
        self._cleanup_active = False
        self._cleanup_queue = {}

    def _queue_pending(self):
        if self._pending is not None:
            recovery = self._pending.recovery
            self._cleanup_queue[recovery['remote']] = dict(recovery)
            self._pending = None

    def cancel_pending(self):
        # GUI release/cancel must revoke immediately even while approve holds
        # the operation lock. Once removal starts, restoration remains active.
        with self._consent_lock:
            self._revoked.set()
            self._queue_pending()

    def cancel_for_close(self) -> bool:
        """Atomically revoke consent and decide whether Worker may stop USB.

        False also means a private stage is queued for worker-only cleanup.
        Call cleanup_pending(adb, serial) before stopping the relay, then retry.
        A failed/offline attempt records retention and allows shutdown afterwards.
        Closing is terminal; this method performs no USB or filesystem I/O.
        """
        with self._consent_lock:
            self._close_requested = True
            self._revoked.set()
            self._queue_pending()
            return not (self._recovery_busy() or self._cleanup_queue)

    def _recovery_busy(self):
        return (self._removal_started or self._active_recovery is not None
                or self._backup_work_active or self._cleanup_active)

    def _cleanup_safe(self, adb, recovery, status=None):
        try:
            if status is not None:
                self.backup.report(recovery, status, 'before_removal_cleanup')
            return self.backup.cleanup_remote(adb, recovery)
        except (OSError, RuntimeError, ValueError):
            try:
                return self.backup.cleanup_result(recovery, False, 'cleanup_unavailable')
            except (OSError, RuntimeError, ValueError):
                self.emit('warning', 'Chưa dọn staging hoặc ghi được báo cáo riêng tư. [REMOTE_RETAINED]')
                return {'status': 'hud_remote_retained', 'cleaned': False, 'serial': recovery['serial']}

    @user_errors
    def cleanup_pending(self, adb, serial=None):
        """Worker-only cleanup dispatch, usable after cancel/terminal close.

        No archive is removed during active backup, approval or recovery. Failed
        attempts are recorded as retained, not retried against another device.
        """
        with self._consent_lock:
            if self._recovery_busy():
                return {'status': 'hud_cleanup_deferred', 'cleaned': 0, 'retained': 0}
        with self._lock:
            with self._consent_lock:
                tasks = tuple(self._cleanup_queue.values())
                self._cleanup_active = bool(tasks)
                self._cleanup_queue.clear()
            results = []
            try:
                for recovery in tasks:
                    if serial is not None and recovery['serial'] != serial:
                        results.append(self._cleanup_safe(None, recovery, 'hud_canceled'))
                    else:
                        results.append(self._cleanup_safe(adb, recovery, 'hud_canceled'))
            finally:
                with self._consent_lock:
                    self._cleanup_active = False
            cleaned = sum(item['cleaned'] for item in results)
            retained = len(results) - cleaned
            return {'status': 'hud_cleanup_retained' if retained else 'hud_cleanup_complete',
                    'serial': serial, 'cleaned': cleaned, 'retained': retained,
                    'results': results}

    def _begin_removal(self):
        # Atomic consent handoff is the point of no return. cancel_pending
        # cannot land between a final check and this state transition; after
        # dispatch is committed, completion/recovery must run even on cancel.
        with self._consent_lock:
            self._check_cancel()
            self._removal_started = True

    def _check_cancel(self):
        if self._close_requested:
            raise HudCancelled('Đang đóng công cụ HUD; không bắt đầu thao tác mới.')
        check_cancel(self.cancel)
        if self._revoked.is_set():
            raise HudCancelled('Đã hủy xác nhận HUD trước khi gỡ ứng dụng.')

    def trusted_artifact(self, digest):
        """Activator hook: revalidate a retained builder receipt, never trust a hash alone."""
        if digest in self._device_sources:
            installed,stock=self._device_sources[digest]
            value=self.builder.verify_device_apk(installed,stock)
            if value['digest']!=digest:raise ValueError('APK lấy từ tay đã thay đổi.')
            return value
        value = verify_trusted_installed_apk(self.builder, digest, self._trusted.get(digest), self.cancel)
        self._trusted[digest] = value['receipt']
        return value

    @user_errors
    def pull_source(self,adb,serial):
        """Read-only device acquisition; never installs, removes or loads signing keys."""
        from .hud_device_source import acquire_source
        with self._lock:return acquire_source(self,adb,serial)

    def _candidate(self, receipt=None):
        self._check_cancel()
        try:
            selected = self.builder.latest() if receipt is None else receipt
        except (ValueError, RuntimeError, OSError):
            check_cancel(self.cancel)
            raise ValueError('Không kiểm chứng lại được biên nhận APK HUD mới nhất.') from None
        if selected is None:
            raise ValueError('Hãy tạo và kiểm chứng APK HUD trước khi cài đặt.')
        reference = selected.get('receipt') if isinstance(selected, dict) else selected
        if reference is None:
            raise ValueError('Cần biên nhận APK HUD đã được trình tạo APK kiểm chứng.')
        candidate = _verified_artifact(self.builder, reference, self.cancel)
        self._trusted[candidate['digest']] = str(reference)
        return candidate

    def _known(self, digest, candidate):
        if digest in {SUPPORTED_APK, HUD_APK, candidate['digest']}:
            return
        self.trusted_artifact(digest)

    def _foreground(self, adb):
        output = adb.shell('dumpsys activity activities | grep mResumedActivity')
        components = re.findall(r'\b([A-Za-z][A-Za-z0-9_.]*)/([A-Za-z0-9_.$]+)', output)
        if len(components) != 1:
            raise ValueError('Không xác định được màn hình đang mở; hãy về trang chủ DJI Fly hoặc mở ứng dụng khác.')
        package, activity = components[0]
        if package == PACKAGE and activity not in {
            'com.dji.mainpageui.device.DJIDeviceActivity',
        }:
            raise ValueError('Hãy về trang chủ DJI Fly hoặc mở ứng dụng khác trước khi cài, khi không bay.')

    def _leave_fly_for_backup(self,adb):
        foreground=adb.shell('dumpsys activity activities | grep mResumedActivity')
        if re.search(r'\bdji\.go\.v5/com\.dji\.mainpageui\.device\.DJIDeviceActivity\b',foreground):
            response=adb.shell('am start -W -n com.android.settings/.Settings')
            if not re.search(r'^Status: ok\s*$',response,re.M):
                raise ValueError('Chưa mở được Settings để giữ DJI Fly dừng trong lúc sao lưu.')
            current=adb.shell('dumpsys activity activities | grep mResumedActivity')
            if not re.search(r'\bcom\.android\.settings/(?:\.Settings|com\.android\.settings\.Settings)\b',current):
                raise ValueError('Tay chưa ở Settings; chưa bắt đầu sao lưu hoặc gỡ ứng dụng.')

    def _device(self, adb):
        if adb.command('get-state', timeout=10).strip() != 'device':
            raise ValueError('RC 2 đã chọn chưa kết nối hoặc chưa cho phép USB debugging.')
        if adb.shell('getprop ro.serialno').strip() != adb.serial:
            raise ValueError('RC 2 đang kết nối không khớp serial đã chọn.')
        model = adb.shell('getprop ro.product.model').replace('_', ' ').strip()
        if (model != 'DJI RC 2' or adb.shell('getprop ro.product.device').strip() != 'rc331'
                or adb.shell('getprop ro.build.version.sdk').strip() != '30'):
            raise ValueError('Chỉ hỗ trợ cài HUD trên DJI RC 2 / rc331 / Android 11 (SDK30).')
        if not adb.shell('id').startswith('uid=0('):
            raise ValueError('Cần quyền shell root sẵn có trên RC 2; công cụ không tự root thiết bị.')
        self._foreground(adb)

    def _installed(self, adb, required=True):
        output = adb.shell('pm path ' + PACKAGE).strip()
        if not output and not required:
            return None
        lines = output.splitlines()
        if len(lines) != 1 or not lines[0].startswith('package:'):
            raise ValueError('Cần xác định đúng một APK DJI Fly đang cài trên RC 2.')
        path = validate_package_path(lines[0][8:])
        info = adb.shell('dumpsys package ' + PACKAGE)
        version = re.findall(r'\bversionName=([^\s]+)', info)
        code = re.findall(r'\bversionCode=(\d+)', info)
        uid = re.findall(r'\buserId=(\d+)', info)
        if version != ['1.21.8'] or code != ['3115809'] or len(uid) != 1:
            raise ValueError('Chỉ hỗ trợ DJI Fly 1.21.8, mã phiên bản 3115809.')
        return {'serial': adb.serial, 'apk_path': path, 'digest': remote_digest(adb, path),
                'uid': valid_uid(int(uid[0]))}

    def _helper(self, required=True):
        root = guard_path(self.assets / 'hud')
        manifest = guard_path(root / 'payload.json')
        value = json.loads(manifest.read_text(encoding='utf-8'))
        if (not isinstance(value, dict) or type(value.get('schema')) is not int
                or value['schema'] != 1 or not isinstance(value.get('sha256'), str)
                or not HASH.fullmatch(value['sha256'])
                or sha256_file(root / 'classes23.dex', self.cancel) != value['sha256']):
            raise ValueError('Thông tin kiểm tra toàn vẹn của tài nguyên HUD không hợp lệ.')
        expected = value.get('restore_owner_sha256')
        if expected is None:
            # Optional for offline building, required before data replacement.
            if required:
                raise ValueError('Để thay thế ứng dụng và khôi phục dữ liệu, cần công cụ đổi chủ sở hữu ARM32 đã kiểm chứng.')
            return None, None
        helper = root / 'restore-owner'
        if not isinstance(expected, str) or not HASH.fullmatch(expected) or sha256_file(helper) != expected:
            raise ValueError('Công cụ đổi chủ sở hữu dữ liệu không vượt qua kiểm tra toàn vẹn.')
        return helper, expected

    def _stage(self, adb, candidate, name='candidate.apk'):
        self._check_cancel()
        if sha256_file(candidate['apk'], self.cancel) != candidate['digest']:
            raise ValueError('APK đã thay đổi trước khi gửi sang RC 2.')
        remote = '/data/local/tmp/rc2vi-hud-apk-' + uuid.uuid4().hex
        # PackageInstaller can read APKs in this public stage. Userdata is never
        # placed here; it stays in a distinct root-only 700 recovery directory.
        run(adb, 'mkdir ' + remote + ' && chmod 755 ' + remote)
        target = remote + '/' + name
        try:
            adb.command('push', candidate['apk'], target, timeout=300)
            run(adb, 'chmod 644 ' + target)
            if remote_digest(adb, target) != candidate['digest']:
                raise ValueError('SHA-256 của APK gửi sang RC 2 không khớp; chưa bắt đầu cài đặt.')
            return target
        except Exception:
            self._cleanup_stage(adb, target)
            raise

    def _cleanup_stage(self, adb, target):
        # Only the fresh APK directory created here is removed; never userdata.
        root = str(Path(target).parent).replace('\\', '/')
        if not re.fullmatch(r'/data/local/tmp/rc2vi-hud-apk-[0-9a-f]{32}', root):
            raise ValueError('Vị trí APK HUD tạm không khớp thư mục do công cụ tạo.')
        try:
            run(adb, 'rm -f ' + shlex.quote(target) + ' && rmdir ' + shlex.quote(root))
        except (RuntimeError, OSError, ValueError):
            self.emit('warning', 'Chưa xóa được APK tạm; kết nối lại đúng RC 2 để kiểm tra và dọn tệp.')

    def _overlay_enabled(self, adb):
        output = adb.shell('cmd overlay list --user 0')
        return bool(re.search(r'^\[x\]\s+' + re.escape(OVERLAY_PACKAGE) + r'\s*$', output, re.M))

    def _restore_overlay(self, adb, enabled):
        if enabled:
            output = adb.shell('cmd overlay list --user 0')
            if re.search(r'^\[[ x]\]\s+' + re.escape(OVERLAY_PACKAGE) + r'\s*$', output, re.M):
                run(adb, 'cmd overlay enable --user 0 ' + OVERLAY_PACKAGE)
                if not self._overlay_enabled(adb):
                    raise RuntimeError('Chưa xác nhận được gói giao diện tiếng Việt đã bật lại.')

    def _verify_installed(self, adb, digest):
        current = self._installed(adb)
        if current['digest'] != digest:
            raise ValueError('APK DJI Fly đang cài không khớp APK đã kiểm chứng.')
        return current

    @user_errors
    def prepare(self, adb, serial, receipt=None):
        with self._lock:
            with self._consent_lock:
                if self._close_requested:
                    raise HudCancelled('Đang đóng công cụ HUD; không bắt đầu thao tác mới.')
                self._queue_pending()
                self._revoked.clear()
            self.cleanup_pending(adb, serial)
            candidate = self._candidate(receipt)
            self._helper(required=False)
            bound = PinnedAdb(adb, serial)
            self._device(bound)
            snapshot = self._installed(bound)
            self._known(snapshot['digest'], candidate)
            if snapshot['digest'] == candidate['digest']:
                return {'status': 'hud_already_installed', 'serial': serial, 'digest': candidate['digest']}
            enabled = self._overlay_enabled(bound)
            staged = self._stage(bound, candidate)
            recovery, published = None, False
            try:
                self._check_cancel()
                self._device(bound)
                if self._installed(bound) != snapshot:
                    raise ValueError('DJI Fly đang cài đã thay đổi trước khi cập nhật giữ dữ liệu.')
                response = bound.shell('pm install -r --user 0 ' + shlex.quote(staged), timeout=180).strip()
                if response == 'Success':
                    self._verify_installed(bound, candidate['digest'])
                    self._restore_overlay(bound, enabled)
                    return {'status': 'hud_installed', 'serial': serial, 'digest': candidate['digest'],
                            'data_retained': True}
                if not re.fullmatch(r'Failure \[INSTALL_FAILED_UPDATE_INCOMPATIBLE(?::[^\r\n]*)?\]', response):
                    raise RuntimeError('Cập nhật HUD giữ dữ liệu thất bại; chưa thực hiện gỡ ứng dụng.')
                helper, helper_digest = self._helper()
                self._check_cancel()
                self._device(bound)
                if self._installed(bound) != snapshot:
                    raise ValueError('DJI Fly đang cài đã thay đổi trước khi tạo bản sao lưu.')
                with self._consent_lock:
                    self._check_cancel()
                    self._backup_work_active = True
                self._leave_fly_for_backup(bound)
                recovery = self.backup.create(bound, snapshot)
                with self._consent_lock:
                    self._active_recovery = recovery
                    self._backup_work_active = False
                # Retain a private candidate copy to bind consent to immutable
                # bytes while still revalidating the original builder receipt.
                copy = guard_path(recovery['directory']) / 'candidate.apk'
                with Path(candidate['apk']).open('rb') as source, copy.open('xb') as output:
                    make_private(copy)
                    while value := source.read(1024 * 1024):
                        check_cancel(self.cancel)
                        output.write(value)
                if sha256_file(copy, self.cancel) != candidate['digest']:
                    raise ValueError('APK HUD đã thay đổi trong khi chuẩn bị phương án khôi phục.')
                recovery = {**recovery, 'candidate_apk': str(copy),
                            'candidate_digest': candidate['digest'],
                            'candidate_certificate_sha256': candidate['certificate_sha256'],
                            'restore_owner_sha256': helper_digest}
                self.backup.report(recovery, 'hud_confirmation_required', 'verified_backup_and_candidate')
                with self._consent_lock:
                    self._check_cancel()
                    token = secrets.token_urlsafe(32)
                    self._pending = PendingInstall(token, serial, dict(snapshot),
                                                   {**candidate, 'retained': str(copy)}, dict(recovery),
                                                   helper_digest, enabled)
                    self._active_recovery = None
                    published = True
                    result = self._confirmation(self._pending)
                return result
            finally:
                try:
                    if recovery is not None and not published:
                        self._cleanup_safe(bound, recovery, 'hud_prepare_failed')
                    self._cleanup_stage(bound, staged)
                finally:
                    with self._consent_lock:
                        self._active_recovery = None
                        self._backup_work_active = False

    def _confirmation(self, pending):
        return {'status': 'hud_confirmation_required', 'token': pending.token,
                'serial': pending.serial, 'digest': pending.candidate['digest'],
                'installed_digest': pending.snapshot['digest'],
                'backup': pending.recovery['archive'], 'backup_path': pending.recovery['archive'],
                'recovery_apk': pending.recovery['apk'], 'recovery_report': pending.recovery['report'],
                'summary': f'RC 2 — serial {pending.serial}: APK HUD dùng chữ ký khác. '
                           'Xác nhận này cho phép gỡ DJI Fly, cài APK HUD đã kiểm chứng rồi '
                           'khôi phục dữ liệu từ bản sao lưu riêng tư. Có thể phải đăng nhập lại; '
                           'khóa phần cứng Keystore không nằm trong bản sao lưu và không được '
                           'bảo đảm khôi phục. Chỉ xác nhận khi không bay và đã rời màn hình camera.'}

    @user_errors
    def approve(self, adb, serial, token):
        with self._lock:
            with self._consent_lock:
                pending = self._pending
                if (pending is None or not isinstance(token, str)
                        or not token.isascii()
                        or not secrets.compare_digest(pending.token, token)):
                    raise ValueError('Mã xác nhận HUD bị thiếu, không hợp lệ hoặc đã được sử dụng.')
                self._pending = None
                self._active_recovery = pending.recovery
            try:
                return self._approve_checked(adb, serial, pending)
            finally:
                try:
                    if not self._removal_started:
                        self._cleanup_safe(adb, pending.recovery, 'hud_approval_failed')
                finally:
                    with self._consent_lock:
                        self._active_recovery = None
                        self._removal_started = False

    def _approve_checked(self, adb, serial, pending):
        if serial != pending.serial:
            raise ValueError('Xác nhận HUD thuộc RC 2 khác; thao tác đã dừng.')
        self._check_cancel()
        candidate = self._candidate(pending.candidate['receipt'])
        if any(candidate[key] != pending.candidate[key] for key in candidate):
            raise ValueError('APK HUD hoặc biên nhận đã thay đổi sau khi xác nhận; cần chuẩn bị lại.')
        helper, helper_digest = self._helper()
        if (helper_digest != pending.helper_digest
                or sha256_file(pending.candidate['retained']) != candidate['digest']):
            raise ValueError('APK HUD giữ lại hoặc công cụ khôi phục đã thay đổi; thao tác đã dừng.')
        self.backup.verify(pending.recovery)
        bound = PinnedAdb(adb, serial)
        self._device(bound)
        current = self._installed(bound)
        self._known(current['digest'], candidate)
        if current != pending.snapshot:
            raise ValueError('APK DJI Fly đang cài, UID hoặc vị trí cài đã thay đổi sau khi xác nhận.')
        staged = self._stage(bound, {**candidate, 'apk': pending.candidate['retained']})
        try:
            self._check_cancel()
            self._device(bound)
            if self._installed(bound) != current:
                raise ValueError('DJI Fly đã thay đổi ngay trước bước thay thế được xác nhận.')
            assert_stopped(bound)
            self.backup.check_fresh(bound, pending.recovery)
            self._device(bound)
            if (self._installed(bound) != current
                    or remote_digest(bound, staged) != candidate['digest']):
                raise ValueError('APK đang cài hoặc APK tạm đã thay đổi trước bước gỡ được xác nhận.')
            self.backup.report(pending.recovery, 'hud_recovery_required', 'removal_starting')
            self._begin_removal()
            return self._replace(bound, pending, staged, helper, helper_digest)
        finally:
            self._cleanup_stage(bound, staged)

    def _replace(self, adb, pending, staged, helper, helper_digest):
        try:
            if adb.shell('pm uninstall --user 0 ' + PACKAGE, timeout=180).strip() != 'Success':
                raise RuntimeError('Bước gỡ DJI Fly chưa trả về đúng kết quả thành công. [PM_SUCCESS]')
            self.backup.report(pending.recovery, 'hud_recovery_required', 'prior_apk_removed')
            if self._installed(adb, required=False) is not None:
                raise RuntimeError('APK DJI Fly cũ vẫn còn sau bước gỡ; chưa tiếp tục cài HUD.')
            if remote_digest(adb, staged) != pending.candidate['digest']:
                raise ValueError('APK HUD tạm đã thay đổi sau khi xác nhận.')
            if adb.shell('pm install --user 0 ' + shlex.quote(staged), timeout=180).strip() != 'Success':
                raise RuntimeError('Bước cài HUD chưa trả về đúng kết quả thành công. [PM_SUCCESS]')
            installed = self._verify_installed(adb, pending.candidate['digest'])
            self.backup.restore(adb, pending.recovery, installed['uid'], helper, helper_digest)
            self._verify_installed(adb, pending.candidate['digest'])
            self._restore_overlay(adb, pending.overlay)
            self.backup.report(pending.recovery, 'hud_installed', 'verified_install_and_data_restore')
            self._cleanup_safe(adb, pending.recovery)
            return {'status': 'hud_installed', 'serial': pending.serial,
                    'digest': pending.candidate['digest'], 'data_restored': True,
                    'keystore_restored': False, 'backup': pending.recovery['archive'],
                    'recovery_report': pending.recovery['report']}
        except Exception:
            return self._rollback(adb, pending, helper, helper_digest)

    def _rollback(self, adb, pending, helper, helper_digest):
        prior_stage = None
        try:
            # Foreground/model/root/device guards still apply to automatic
            # recovery; unknown APKs are never removed as a rollback shortcut.
            self._device(adb)
            self.backup.verify(pending.recovery)
            installed = self._installed(adb, required=False)
            if installed and installed['digest'] not in {
                pending.snapshot['digest'], pending.candidate['digest'],
            }:
                raise ValueError('APK đang cài không thuộc phương án đã xác nhận; không tự động gỡ để khôi phục.')
            if installed and installed['digest'] == pending.candidate['digest']:
                assert_stopped(adb)
                if adb.shell('pm uninstall --user 0 ' + PACKAGE, timeout=180).strip() != 'Success':
                    raise RuntimeError('Chưa gỡ được APK HUD đã xác nhận để khôi phục bản trước.')
                installed = None
            if installed is None:
                # Recovery must run even if cancellation was requested after
                # removal. _stage normally observes cancellation, so stage prior
                # bytes with a separate non-cancelable recovery installer.
                recovery_installer = HudInstaller(self.assets, self.work, self.emit, self.builder)
                prior_stage = recovery_installer._stage(adb, {'apk': pending.recovery['apk'],
                                                            'digest': pending.snapshot['digest']}, 'prior.apk')
                if adb.shell('pm install --user 0 ' + shlex.quote(prior_stage), timeout=180).strip() != 'Success':
                    raise RuntimeError('Bước cài APK khôi phục chưa trả về đúng kết quả thành công. [PM_SUCCESS]')
            prior = self._verify_installed(adb, pending.snapshot['digest'])
            self.backup.restore(adb, pending.recovery, prior['uid'], helper, helper_digest)
            self._verify_installed(adb, pending.snapshot['digest'])
            self._restore_overlay(adb, pending.overlay)
            self.backup.report(pending.recovery, 'hud_rolled_back', 'verified_prior_apk_and_data')
            self._cleanup_safe(adb, pending.recovery)
            return {'status': 'hud_rolled_back', 'serial': pending.serial, 'restored': True,
                    'keystore_restored': False, 'backup': pending.recovery['archive'],
                    'recovery_report': pending.recovery['report'],
                    'summary': f'RC 2 — serial {pending.serial}: Cài HUD thất bại. '
                               'APK trước đó và dữ liệu ứng dụng đã được khôi phục và kiểm chứng. '
                               'Có thể phải đăng nhập lại; không bảo đảm khôi phục khóa Keystore.'}
        except Exception:
            report = self.backup.report(pending.recovery, 'hud_recovery_required', 'recovery_incomplete')
            result = {'status': 'hud_recovery_required', 'serial': pending.serial, 'restored': False,
                      'keystore_restored': False, 'backup': pending.recovery['archive'],
                      'recovery_apk': pending.recovery['apk'], 'recovery_report': report,
                      'summary': f'RC 2 — serial {pending.serial}: Khôi phục DJI Fly chưa hoàn tất '
                                 'hoặc chưa xác định được trạng thái. Giữ thư mục sao lưu riêng tư, '
                                 'kết nối lại đúng RC 2 này và kiểm tra phương án khôi phục trước khi '
                                 'tiếp tục. Chưa bảo đảm ứng dụng hay dữ liệu dùng được; có thể cần '
                                 'đăng nhập lại và khóa Keystore không được bảo đảm khôi phục.'}
            self.emit('warning', result['summary'])
            return result
        finally:
            if prior_stage:
                self._cleanup_stage(adb, prior_stage)
