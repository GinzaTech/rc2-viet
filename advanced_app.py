"""Private Windows desktop for the 430-class Advanced 1.21.10 recipe only.

USB/build/install/translation run on one owned worker. Tk receives queue events;
consent tokens never enter the progress log or the offline JSON report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import struct
import sys
import threading
import tkinter as tk
from types import FunctionType
from typing import Callable

VERSION = '1.21.10'
VERSION_CODE = 3115981
STOCK_SHA256 = 'f6c11267d465c303e2aecb737fe4f6b41b54da083368cac497404f4c9a464f98'
from rc2vi.advanced_desktop import App, MAIN_BUTTON
HASH = re.compile(r'[0-9a-f]{64}')
SERIAL = re.compile(r'[A-Za-z0-9_.:-]{1,128}')


def check_space(work):
    """Preflight only; never delete existing files to make room."""
    work = Path(work).absolute()
    parent = work
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    free = shutil.disk_usage(parent).free
    if free < 3 * 1024 ** 3:
        raise ValueError(f'Ổ làm việc chỉ còn {free / 1024 ** 3:.2f} GiB trống. '
                         'Cần ít nhất khoảng 3 GiB cho APK nguồn, APK mới và phục hồi. '
                         'Giải phóng dung lượng hoặc dùng CLI --work trên ổ khác; công cụ không tự xóa tệp.')


def paths() -> tuple[Path, Path]:
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local')))
    work = local / 'RC2Advanced12110'
    work.mkdir(parents=True, exist_ok=True)
    return base / 'assets', work


def friendly_error(exc: Exception) -> str:
    if isinstance(exc, ImportError):
        return 'Thiếu thành phần Nâng cao 1.21.10 trong bản đóng gói.'
    text = str(exc)
    text = re.sub(r'(?i)((?:token|password|HUD_SIGN_PASS|private_key)\s*[=:]\s*)\S+',
                  r'\1[ẩn]', text)
    if 'cancel' in text.lower() or 'hủy' in text.lower():
        return 'Đã hủy thao tác; quy trình phục hồi đã nhận xác nhận vẫn tiếp tục nếu cần.'
    return 'Thao tác chưa hoàn tất: ' + (text[:1000] or type(exc).__name__)


def checksum_relay_class(base):
    """RC2 advertises modern ADB but still requires checksums on USB commands."""
    class UsbChecksumRelay(base):
        def _send_usb(self, wire):
            from rc2vi.core import pack
            if len(wire) < 24:
                raise ValueError('Gói USB không đầy đủ.')
            command, arg0, arg1, length, _, magic = struct.unpack('<6I', wire[:24])
            if length != len(wire) - 24 or magic != command ^ 0xffffffff:
                raise ValueError('Gói USB không đầy đủ hoặc sai header.')
            wire = pack(wire[:4].decode('ascii'), arg0, arg1, wire[24:])
            return super()._send_usb(wire)
    return UsbChecksumRelay


def first_key_adb_class(base, key_path=None):
    expected = Path(key_path) if key_path is not None else Path.home() / '.android/adbkey'

    class FirstKeyAdb(base):
        def command(self, *args, **kwargs):
            if 'keygen' in args:
                if (len(args) != 2 or args[0] != 'keygen'
                        or Path(args[1]).absolute() != expected.absolute()
                        or os.path.lexists(expected) or os.path.lexists(expected.with_suffix('.pub'))):
                    raise ValueError('Chỉ tạo khóa USB lần đầu ở .android/adbkey; không ghi đè khóa hiện có.')
            return super().command(*args, **kwargs)
    return FirstKeyAdb


def private_connection(device, assets, emit):
    from rc2vi.activation import verify_bundle
    from rc2vi import transport
    verify_bundle(assets)

    # Clone only the private invocation's globals. Public Connection and Relay
    # remain unchanged, including when another controller exists in this process.
    method = transport.Connection._open
    private_open = FunctionType(method.__code__, {
        **method.__globals__, 'Relay': checksum_relay_class(transport.Relay),
        'Adb': first_key_adb_class(transport.Adb),
    }, method.__name__, method.__defaults__, method.__closure__)

    class AdvancedConnection(transport.Connection):
        def bind_cancel(self,event):
            self._opening_cancel=event
        def bind_reconnect(self,event):
            self._opening_reconnect_event=event
        def _open(self):
            from rc2vi.hud_tools import check_cancel
            cancel=getattr(self,'_opening_cancel',None)
            check_cancel(cancel)
            base=private_open.__globals__['Relay']
            class OpeningRelay(base):
                def start(relay):
                    check_cancel(cancel)
                    return super().start()
            opening=FunctionType(private_open.__code__,{
                **private_open.__globals__,'Relay':OpeningRelay},private_open.__name__,
                private_open.__defaults__,private_open.__closure__)
            return opening(self)
    return AdvancedConnection(device, assets, emit)


def discover_rc2():
    from rc2vi.usb_windows import discover
    return discover()  # VID/PID/interface filtering is supplied by the RC2 USB enumerator.


def pin_adb(adb, serial):
    from rc2vi.hud_backup import PinnedAdb
    return PinnedAdb(adb, serial)


def builder_factory(assets, work, emit, cancel=None, profile=None):
    from rc2vi.advanced_patch import AdvancedBuilder
    from rc2vi.hud_keys import HudKeyStore
    builder = AdvancedBuilder(assets, work, emit, cancel=cancel, profile=profile)
    # Offline --work can reside on another drive; signing storage stays in the
    # dedicated per-user AppData directory, never beside source/bundled assets.
    local = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
    stable = HudKeyStore(builder.tools, local / 'RC2Studio/signing')
    existing=HudKeyStore(builder.tools)
    if os.path.lexists(stable.root / 'signer.json'):
        # An explicitly retained identity owns this location even when corrupt.
        # load/ensure must report that error rather than choose a different key.
        builder.keys = stable
    elif (existing.root/'signer.json').is_file():
        # Reuse the PC's previous menu signer to preserve same-signer updates.
        # A corrupt existing identity fails closed when the builder loads it.
        builder.keys=existing
    else:
        builder.keys = HudKeyStore(builder.tools, paths()[1] / 'advanced-signing')
    return builder


class TranslationTransport:
    """Keep HUD's physical/transport binding through the public translation API.

AdaptiveTranslation accepts an adb/root pair or a direct root ADB. PinnedAdb's
internal -t client has no serial; expose the physical serial on a direct adapter
while every actual dispatch still passes through PinnedAdb's immutable binding.
"""
    def __init__(self, pinned):
        self.pinned, self.serial = pinned, pinned.serial

    def bind(self, serial):
        if serial != self.serial or self.pinned.serial != self.serial:
            raise ValueError('Serial bản dịch đã thay đổi.')
        return TranslationTransport(self.pinned)

    def command(self, *args, **kwargs):
        if self.pinned.serial != self.serial:
            raise ValueError('Serial bản dịch đã thay đổi.')
        return self.pinned.command(*args, **kwargs)

    def shell(self, command, **kwargs):
        if self.pinned.serial != self.serial:
            raise ValueError('Serial bản dịch đã thay đổi.')
        return self.pinned.shell(command, **kwargs)


def verified_build(builder, result: dict, cancel=None) -> dict:
    """Bind this workflow to its own verified receipt, never an unrelated latest()."""
    from rc2vi.hud_tools import check_cancel, sha256_file
    check_cancel(cancel)
    if not isinstance(result, dict) or result.get('status') != 'hud_built' or not result.get('receipt'):
        raise ValueError('Không có biên nhận APK Nâng cao vừa tạo.')
    verified = builder.verify(result['receipt'])
    if not isinstance(verified, dict):
        raise ValueError('Biên nhận APK Nâng cao không hợp lệ.')
    for field in ('digest', 'source_digest', 'certificate_sha256'):
        if (not isinstance(verified.get(field), str) or not HASH.fullmatch(verified[field])
                or verified[field] != result.get(field)):
            raise ValueError('Hash/chữ ký của biên nhận khác APK vừa tạo; đã dừng.')
    identity = verified.get('source_identity', {})
    if (verified['source_digest'] != STOCK_SHA256 or not isinstance(identity, dict)
            or identity.get('version') != VERSION or identity.get('code') != VERSION_CODE
            or result.get('source_identity') != identity):
        raise ValueError('Chỉ hỗ trợ nguồn stock F6 / DJI Fly RC 1.21.10 (3115981).')
    for field in ('recipe_sha256', 'workflow_digest'):
        if field in result or field in verified:
            if result.get(field) != verified.get(field):
                raise ValueError('Recipe/quy trình tạo APK đã thay đổi.')
    if not verified.get('apk') or Path(verified['apk']).resolve() != Path(result.get('apk', '')).resolve():
        raise ValueError('Biên nhận trỏ đến APK khác quy trình vừa tạo.')
    if sha256_file(Path(verified['apk']), cancel) != verified['digest']:
        raise ValueError('APK vừa tạo đã thay đổi; không bắt đầu cài đặt.')
    check_cancel(cancel)
    return {**verified, 'status': 'hud_built', 'receipt': result['receipt']}


class Backend:
    def __init__(self, assets, work, emit, cancel):
        from rc2vi.advanced_patch import AdvancedInstaller
        self.assets, self.work, self.emit, self.cancel = assets, work, emit, cancel
        self.builder = builder_factory(assets, work / 'advanced', emit, cancel)
        class DesktopInstaller(AdvancedInstaller):
            def confirm(self, adb, serial, token):
                confirm = getattr(super(), 'confirm', None)
                if callable(confirm):
                    return confirm(adb, serial, token)
                return super().approve(adb, serial, token)
        self.installer = DesktopInstaller(assets, work / 'advanced', emit, self.builder, cancel=cancel)

    def translate(self, adb, before_deploy):
        from rc2vi.activation import Activator
        from rc2vi.translation_install import AdaptiveTranslation
        from rc2vi.translation_build import TranslationBuilder
        from rc2vi.translation_engine import LocalTranslationEngine
        from rc2vi.hud_keys import HudKeyStore

        class SettingsTranslation(AdaptiveTranslation):
            def _deploy(self, adb, root, before, safe, artifact, local):
                # Fly can reopen FPV during a long resource build. Reassert
                # Settings immediately before deployment; retain all base guards.
                before_deploy()
                safe()
                return super()._deploy(adb, root, before, safe, artifact, local)

        work = self.work / 'translation'
        engine = LocalTranslationEngine(self.assets, work / 'engine', self.emit, cancel=self.cancel,
                                        payload_roots=[self.assets / 'translation-engine',
                                                       self.assets.parent / 'translation-engine'])
        builder = TranslationBuilder(self.assets, work / 'build', self.emit,
                                     cancel=self.cancel, sdk=30, engine=engine)
        builder.keys = HudKeyStore(builder.tools, paths()[1] / 'translation-signing')
        adaptive = SettingsTranslation(self.assets, work, self.emit, cancel=self.cancel, builder=builder)
        activation = Activator(self.assets, work / 'activation', self.emit, adaptive=adaptive)
        activation.cancel = self.cancel
        activation.trusted_hud = self.installer.trusted_artifact
        return activation.apply(TranslationTransport(adb))


class AdvancedWorker:
    """One operation at a time, including pending consent and recovery/cleanup."""
    def __init__(self, assets, work, emit, *, backend_factory=Backend,
                 discover=discover_rc2, connection_factory=private_connection, pin_factory=pin_adb,
                 space_check=check_space):
        self.assets, self.work, self.emit = Path(assets), Path(work), emit
        self.backend_factory, self.discover = backend_factory, discover
        self.connection_factory, self.pin_factory = connection_factory, pin_factory
        self.space_check = space_check
        self.backend = self.connection = self.adb = self.thread = None
        self.selected = ''
        self.busy = self.closing = False
        self.stop_event = threading.Event()
        self._lock = threading.RLock()
        self._answers = queue.Queue()
        self._pending = None
        self._translation_active = False
        self._install_consent = False
        self._opening_connection=False

    def set_work(self, work):
        with self._lock:
            if self.busy or self.closing:
                return False
            self.work = Path(work).expanduser().absolute()
            self.backend = None
            return True

    def request(self, operation, serial='', *, grounded=False, translate=True) -> bool:
        if operation not in {'scan', 'connect', 'install', 'translate', 'release'}:
            raise ValueError('Thao tác không được hỗ trợ.')
        with self._lock:
            if self.busy or self.closing:
                return False
            if operation in {'install', 'translate'} and grounded is not True:
                self.emit('warning', 'Đánh dấu đã hạ cánh và động cơ dừng trước khi tiếp tục.')
                return False
            if operation not in {'scan', 'release'} and not SERIAL.fullmatch(serial):
                self.emit('warning', 'Chọn số sê-ri RC 2 cần kết nối.')
                return False
            self.busy = True
            self.stop_event.clear()
            while not self._answers.empty():
                self._answers.get_nowait()
            self.selected = serial or self.selected
            self.thread = threading.Thread(target=self._run,
                                           args=(operation, serial, grounded, translate),
                                           name='RC2Advanced12110-worker', daemon=False)
            self.thread.start()
            return True

    def _check(self):
        from rc2vi.hud_tools import check_cancel
        check_cancel(self.stop_event)

    def _backend(self):
        if self.backend is None:
            self.backend = self.backend_factory(self.assets, self.work, self.emit, self.stop_event)
        self._check()
        return self.backend

    def _guard(self, serial):
        self._check()
        if (self.selected != serial or self.connection is None or self.adb is None
                or self.connection.device.serial != serial or not self.connection.alive()):
            raise ValueError('Kết nối hoặc RC 2 đã chọn thay đổi; đã dừng.')
        root = self.pin_factory(self.adb, serial)
        if root.command('get-state', timeout=10).strip() != 'device':
            raise ValueError('RC 2 chưa cho phép USB debugging hoặc đã ngắt kết nối.')
        if (root.shell('getprop ro.serialno').strip() != serial
                or root.shell('getprop ro.product.model').replace('_', ' ').strip() != 'DJI RC 2'
                or root.shell('getprop ro.product.device').strip() != 'rc331'
                or root.shell('getprop ro.build.version.sdk').strip() != '30'
                or not root.shell('id').startswith('uid=0(')):
            raise ValueError('Cần đúng RC 2 / rc331 / SDK30 / shell root / serial đã chọn.')
        package = root.shell('dumpsys package dji.go.v5')
        version = re.search(r'\bversionName=([^\s]+)', package)
        code = re.search(r'\bversionCode=(\d+)\b', package)
        if not version or not code or version[1] != VERSION or int(code[1]) != VERSION_CODE:
            raise ValueError('Chỉ hỗ trợ DJI Fly RC 1.21.10 (3115981).')
        self._check()
        return root

    def _connect(self, serial):
        self._check()
        if self.connection and (self.connection.device.serial != serial or not self.connection.alive()):
            self._release()
        if self.connection is None:
            devices = self.discover()
            chosen = [d for d in devices if d.serial == serial]
            if len(chosen) != 1:
                raise ValueError('RC 2 đã chọn không còn trên USB. Bấm Quét và kiểm tra cáp.')
            self.emit('connecting', 'Đang kết nối RC 2 ' + serial + '…')
            self.connection = self.connection_factory(chosen[0], self.assets, self.emit)
            with self._lock:self._opening_connection=True
            try:
                binder=getattr(self.connection,'bind_cancel',None)
                if binder:binder(self.stop_event)
                self._check()
                self.adb = self.connection.open()
            except BaseException:
                self.connection.close()
                self.connection=None;self.adb=None
                raise
            finally:
                with self._lock:self._opening_connection=False
        self._guard(serial)

    def _settings(self, serial, grounded):
        if grounded is not True:
            raise ValueError('Chưa xác nhận đã hạ cánh và động cơ dừng.')
        root = self._guard(serial)
        response = root.shell('am start -W -n com.android.settings/.Settings', timeout=60)
        if not re.search(r'^Status: ok\s*$', response, re.M):
            raise ValueError('Không mở được Settings; chưa dừng hoặc thay đổi DJI Fly.')
        root = self._guard(serial)
        foreground = root.shell('dumpsys activity activities | grep mResumedActivity')
        if not re.search(r'\bcom\.android\.settings/(?:\.Settings|com\.android\.settings\.Settings)\b',
                         foreground):
            raise ValueError('RC 2 chưa ở Settings; không tiếp tục cài đặt.')
        root.shell('am force-stop dji.go.v5')
        self._check()
        return root

    def _consent(self, plan, artifact, serial):
        if (not isinstance(plan, dict) or plan.get('serial') != serial
                or plan.get('digest') != artifact['digest']
                or not isinstance(plan.get('token'), str) or not plan['token']
                or not plan.get('summary') or not (plan.get('backup_path') or plan.get('backup'))):
            raise ValueError('Xác nhận thay chữ ký không khớp APK/RC 2/bản sao lưu vừa kiểm chứng.')
        with self._lock:
            self._pending = dict(plan)
        self.emit('confirmation', dict(plan))
        while True:
            self._check()
            try:
                approved, token = self._answers.get(timeout=0.1)
                break
            except queue.Empty:
                continue
        if not approved:
            self.cancel()
            self._check()
        return token

    def answer_confirmation(self, plan, approved) -> bool:
        with self._lock:
            pending = self._pending
            if (self.closing or self.stop_event.is_set() or not pending or not isinstance(plan, dict)
                    or any(plan.get(k) != pending[k] for k in ('serial', 'digest', 'token'))):
                return False
            self._pending = None
            self._answers.put((approved is True, pending['token']))
            return True

    def _installed_result(self, result, artifact, serial):
        if (not isinstance(result, dict) or result.get('serial') != serial
                or result.get('digest') != artifact['digest']):
            raise ValueError('Kết quả cài không khớp hash APK/RC 2 của quy trình này.')
        state = result.get('status')
        if state == 'hud_already_installed':
            self.emit('ready', 'RC 2 đã có đúng APK menu Nâng cao 1.21.10 đã kiểm chứng.')
        elif state == 'hud_installed':
            message = 'Đã cài và kiểm chứng menu Nâng cao 1.21.10.'
            if result.get('data_retained') is True:
                message += ' Cùng chữ ký, giữ dữ liệu ứng dụng.'
            elif result.get('data_restored') is True:
                message += ' Đã khôi phục dữ liệu; cần kiểm tra đăng nhập/Keystore trên tay.'
            self.emit('ready', message)
        else:
            raise ValueError('Trạng thái cài đặt không hợp lệ.')

    def _install(self, serial, grounded, translate):
        self.space_check(self.work)
        backend = self._backend()
        self._settings(serial, grounded)
        self.emit('applying', 'Đang tự lấy APK DJI Fly từ RC 2…')
        source = backend.installer.pull_source(self.adb, serial)
        self._guard(serial)
        self.emit('applying', 'Đang tạo và ký menu Nâng cao 1.21.10 trên máy tính…')
        artifact = verified_build(backend.builder, backend.builder.build(Path(source)), self.stop_event)
        self._settings(serial, grounded)  # Reassert after long pull/build, before prepare.
        self.emit('applying', 'Đang chuẩn bị cài APK vừa kiểm chứng…')
        result = backend.installer.prepare(self.adb, serial, artifact['receipt'])
        if result.get('status') == 'hud_confirmation_required':
            self._install_consent = True
            token = self._consent(result, artifact, serial)
            self._settings(serial, grounded)
            self.emit('applying', 'Đang thay chữ ký theo xác nhận và giữ phương án phục hồi…')
            result = backend.installer.confirm(self.adb, serial, token)
            self._install_consent = False
        if result.get('status') in {'hud_rolled_back', 'hud_recovery_required'}:
            self.emit('error' if result['status'] == 'hud_recovery_required' else 'warning',
                      'Cần kiểm tra phục hồi DJI Fly: ' + str(result.get('recovery_report', '')))
            return
        self._installed_result(result, artifact, serial)
        if translate and not self.stop_event.is_set() and not self.closing:
            self._translate(serial, grounded, expected_digest=artifact['digest'])

    def _translate(self, serial, grounded, expected_digest=None):
        self.space_check(self.work)
        backend = self._backend()
        root = self._settings(serial, grounded)
        if expected_digest is None:
            # Source acquisition validates/replays the installed private recipe
            # and registers it with trusted_artifact; a latest local APK is not proof.
            backend.installer.pull_source(self.adb, serial)
            root = self._guard(serial)
            from rc2vi.core import validate_package_path
            lines = root.shell('pm path dji.go.v5').splitlines()
            if len(lines) != 1 or not lines[0].startswith('package:'):
                raise ValueError('Không đọc được APK menu đang cài.')
            path = validate_package_path(lines[0][8:])
            checksum = root.shell('sha256sum ' + path, timeout=90).split()
            digest = checksum[0] if checksum else ''
            if not HASH.fullmatch(digest) or digest == STOCK_SHA256:
                raise ValueError('Cần menu Nâng cao đã cài và kiểm chứng trước khi bật tiếng Việt riêng.')
            trusted = backend.installer.trusted_artifact(digest)
            if trusted.get('digest') != digest or trusted.get('source_digest') != STOCK_SHA256:
                raise ValueError('Menu đang cài không có biên nhận/phục hồi Nâng cao hợp lệ.')
            expected_digest = digest
        root = self._settings(serial, grounded)
        from rc2vi.core import validate_package_path
        lines = root.shell('pm path dji.go.v5').splitlines()
        if len(lines) != 1 or not lines[0].startswith('package:'):
            raise ValueError('Không đọc được APK trước khi dịch.')
        target = validate_package_path(lines[0][8:])
        checksum = root.shell('sha256sum ' + target, timeout=90).split()
        if not checksum or checksum[0] != expected_digest:
            raise ValueError('APK menu đã thay đổi trước khi dịch.')
        self.emit('applying', 'Đang bật tiếng Việt cho menu đã kiểm chứng…')
        with self._lock:
            self._check()
            self._translation_active = True
        try:
            result = backend.translate(root, lambda: self._settings(serial, grounded))
        finally:
            with self._lock:
                self._translation_active = False
        self.emit('ready', result.get('message', 'Đã bật và đọc lại bản dịch tiếng Việt.'))

    def _cleanup(self):
        if self.backend:
            self.backend.installer.cleanup_pending(self.adb,
                                                   self.connection.device.serial if self.connection else None)

    def _release(self):
        try:
            self._cleanup()
        finally:
            if self.connection:
                self.connection.close()
            self.connection = self.adb = None

    def _run(self, operation, serial, grounded, translate):
        failed = False
        try:
            if operation == 'scan':
                self.emit('checking', 'Đang quét cổng USB của RC 2…')
                devices = tuple(d.serial for d in self.discover())
                self._check()
                self.emit('devices', devices)
                self.emit('ready' if devices else 'waiting',
                          'Chọn RC 2 và bấm Connect.' if devices else 'Cắm RC 2 và bật nguồn để kết nối USB.')
            elif operation == 'release':
                self._release()
            else:
                self._connect(serial)
                if operation == 'install':
                    self._install(serial, grounded, translate)
                elif operation == 'translate':
                    self._translate(serial, grounded)
                else:
                    self.emit('ready', 'Đã kết nối đúng RC 2 / SDK30 / root / DJI Fly 1.21.10.')
        except Exception as exc:
            failed = True
            self.emit('warning' if self.stop_event.is_set() else 'error', friendly_error(exc))
        finally:
            with self._lock:
                self._pending = None
            try:
                if self._install_consent and self.backend:
                    self.backend.installer.cancel_pending()
                    self._install_consent = False
                self._cleanup()
            except Exception as exc:
                self.emit('warning', 'Giữ báo cáo phục hồi; chưa dọn xong: ' + friendly_error(exc))
            finally:
                with self._lock:
                    release = self.closing or (failed and operation == 'connect')
                    if not release:
                        # Atomic handoff: a later close sees idle and starts its
                        # own release worker; an earlier close is handled below.
                        self.busy = False
                    if failed or self.stop_event.is_set():
                        if not release:
                            self.backend = None  # Fresh cancellation/consent state on retry.
                if release:
                    try:
                        self._release()
                    except Exception as exc:
                        self.emit('warning', friendly_error(exc))
                    finally:
                        with self._lock:
                            self.busy = False
                self.emit('idle', '')

    def cancel(self):
        self.stop_event.set()
        with self._lock:
            self._pending = None
            backend = self.backend
            connection=self.connection
            relay=getattr(connection,'relay',None)
            opening=self._opening_connection
        if opening and relay:
            relay.stop_event.set()  # Signal only; the opening worker owns cleanup.
        if backend:
            backend.installer.cancel_pending()  # No I/O, atomic consent revocation.

    def close(self):
        with self._lock:
            if self.closing:
                return
            self.closing = True
            self.stop_event.set()
            backend = self.backend
            connection = self.connection
            relay = getattr(connection, 'relay', None)
            translating = self._translation_active
        safe = not backend or backend.installer.cancel_for_close()
        # Once consented removal begins, the installer retains USB until its
        # completion/recovery and worker-only cleanup have finished.
        if self.busy:
            if safe and not translating and relay:
                relay.stop_event.set()
        else:
            with self._lock:
                self.busy = True
                self.thread = threading.Thread(target=self._run, args=('release', '', False, False),
                                               name='RC2Advanced12110-close', daemon=False)
                self.thread.start()


def write_report(report, destination):
    output = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(output, encoding='utf-8')
    if sys.stdout:
        try:
            print(output)
        except UnicodeEncodeError:
            # Windows consoles may use cp1252. Keep the JSON report UTF-8 and
            # emit equivalent escaped JSON on such consoles instead of crashing.
            print(json.dumps(report, ensure_ascii=True, indent=2, default=str))


def main(argv=None, *, builder_factory=builder_factory, paths_factory=paths, space_check=check_space):
    parser = argparse.ArgumentParser(description='RC 2 — menu Nâng cao riêng tư, DJI Fly 1.21.10')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--advanced-build', type=Path, metavar='APK', help='Tạo/kiểm chứng APK offline')
    modes.add_argument('--verify-stock', type=Path, metavar='APK', help='Kiểm tra nguồn DJI V2 offline, không kết nối USB')
    modes.add_argument('--gui-smoke', action='store_true', help='Kiểm tra GUI, tuyệt đối không kết nối USB')
    parser.add_argument('--report', type=Path, metavar='JSON')
    parser.add_argument('--work', '--work-dir', type=Path, metavar='PATH',
                        help='Thư mục làm việc GUI/build offline (khóa ký vẫn ở AppData riêng)')
    args = parser.parse_args(argv)
    assets, work = paths_factory()
    if args.work:
        work = args.work.expanduser().absolute()
    if args.advanced_build or args.verify_stock:
        events = []
        try:
            space_check(work)
            work.mkdir(parents=True, exist_ok=True)
            builder = builder_factory(assets, work / 'advanced',
                                      lambda s, m: events.append({'state': s, 'message': m}))
            if args.verify_stock:
                report = {**builder.verify_device_apk(args.verify_stock,args.verify_stock),
                          'offline_stock_verification':True,'usb_connected':False}
            else:
                report = verified_build(builder, builder.build(args.advanced_build))
        except Exception as exc:
            report = {'status': 'error', 'message': friendly_error(exc)}
        write_report({**report, 'events': events}, args.report)
        return 1 if report['status'] == 'error' else 0
    root = tk.Tk()
    if args.gui_smoke:
        root.withdraw()
    view = App(root, assets, work, start_worker=not args.gui_smoke)
    if args.gui_smoke:
        try:
            view.emit('devices', ('SMOKE-RC2',))
            view.emit('ready', 'Kiểm tra giao diện offline.')
            view.poll()
            root.update_idletasks()
            assert view.worker is None and view.vietnamese.get() and not view.grounded.get()
            assert str(view.install_button['state']) == 'disabled'
            view.grounded.set(True)
            view.wipe_ack.set(True)
            view.refresh_controls()
            assert str(view.install_button['state']) == 'normal'
            view.install_button.invoke()  # No worker exists: this cannot open USB or a file picker.
            assert 'offline' in view.status.get()
            report = {'status': 'PASS', 'gui_smoke': 'PASS', 'usb_connected': False,
                      'main_button': view.install_button['text'], 'vietnamese_default': True,
                      'ground_ack_default': False, 'rc2_only': True, 'frozen': bool(getattr(sys, 'frozen', False)),
                      'assets': str(assets), 'work': str(work)}
            write_report(report, args.report)
        finally:
            root.destroy()
        return 0
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
