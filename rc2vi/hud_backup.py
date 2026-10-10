"""Private, verified Fly recovery. Never extract archives on the host PC.

Only three physical app directories are in scope. Recovery excludes native lib
links, code_cache and fixed transient Crashlytics reports; hardware Keystore keys
are not backed up or promised.
"""
import ctypes
from functools import wraps
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import tarfile
import uuid

from .core import validate_package_path

PACKAGE = 'dji.go.v5'
PRIVATE_ROOTS = ('data/user/0/' + PACKAGE, 'data/user_de/0/' + PACKAGE)
DATA_ROOTS = PRIVATE_ROOTS + ('data/media/0/Android/data/' + PACKAGE,)
CHUNK_SIZE = 64 * 1024 * 1024
MARKER = 'RC2VI_HUD_OK'
HASH = re.compile(r'[0-9a-f]{64}')
REMOTE_FILES = ('data.tar', 'prior.apk', 'transfer.part', 'freshness.tar',
                'restore.tar', 'restore-owner', 'links')
CLEANABLE_STATES = frozenset({'hud_backup_incomplete', 'hud_confirmation_required',
                             'hud_canceled', 'hud_prepare_failed', 'hud_approval_failed',
                             'hud_installed', 'hud_rolled_back'})


class HudCancelled(RuntimeError):
    pass


class HudTransportError(RuntimeError):
    """Public error deliberately excludes ADB stderr and private file names."""


def user_errors(operation):
    """Keep public I/O failures localized without exposing private filenames."""
    @wraps(operation)
    def guarded(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except ConnectionError:
            raise ConnectionError('Kết nối RC 2 bị gián đoạn; kiểm tra USB và kết nối lại. [ADB_CONNECTION]') from None
        except json.JSONDecodeError:
            raise ValueError('Cấu trúc tệp cấu hình HUD không hợp lệ; kiểm tra lại bộ tài nguyên. [HUD_JSON]') from None
        except (OSError, UnicodeError):
            raise RuntimeError('Không thể đọc hoặc ghi tệp HUD. Kiểm tra dung lượng trống '
                               'và quyền truy cập rồi thử lại. [HUD_IO]') from None
    return guarded


def check_cancel(cancel):
    if cancel is not None and (cancel.is_set() if hasattr(cancel, 'is_set') else cancel()):
        raise HudCancelled('Đã hủy thao tác HUD trước khi thay thế ứng dụng.')


def guard_path(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        try:
            metadata = item.lstat()
        except FileNotFoundError:
            continue
        if getattr(metadata, 'st_file_attributes', 0) & 0x400 or stat.S_ISLNK(metadata.st_mode):
            raise ValueError('Đường dẫn khôi phục HUD không được chứa liên kết hoặc điểm chuyển hướng Windows.')
    return path


def make_private(path, directory=False):
    """Owner/System only on Windows; chmod alone does not secure Windows files."""
    path = guard_path(path)
    os.chmod(path, 0o700 if directory else 0o600)
    if os.name == 'nt':
        advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p),
                            ctypes.POINTER(ctypes.c_uint32)]
        convert.restype = ctypes.c_int
        set_security = advapi.SetFileSecurityW
        set_security.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p]
        set_security.restype = ctypes.c_int
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        descriptor = ctypes.c_void_p()
        inherit = 'OICI' if directory else ''
        sddl = f'D:P(A;{inherit};FA;;;SY)(A;{inherit};FA;;;OW)'
        if not convert(sddl, 1, ctypes.byref(descriptor), None):
            raise RuntimeError('Không thiết lập được quyền riêng tư cho bản sao lưu HUD.')
        try:
            if not set_security(str(path), 0x80000004, descriptor):
                raise RuntimeError('Không bảo vệ được quyền truy cập bản sao lưu HUD; thao tác đã dừng.')
        finally:
            kernel.LocalFree(descriptor)


def sha256_file(path, cancel=None):
    path = guard_path(path)
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while True:
            check_cancel(cancel)
            chunk = source.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def valid_uid(uid):
    if type(uid) is not int or not 10000 <= uid <= 19999:
        raise ValueError('Chỉ hỗ trợ UID ứng dụng Android của người dùng 0 trong khoảng 10000–19999.')
    return uid


def transport_id_from_devices(listing, target):
    rows = [parts for line in listing.splitlines()
            if (parts := line.split()) and parts[0] == target]
    if len(rows) != 1 or len(rows[0]) < 3 or rows[0][1] != 'device':
        raise ValueError('Không xác định được đúng một kết nối ADB đang sẵn sàng của RC 2.')
    ids = [part[13:] for part in rows[0][2:] if part.startswith('transport_id:')]
    if (len(ids) != 1 or not re.fullmatch(r'[1-9][0-9]{0,19}', ids[0])
            or int(ids[0]) > 18446744073709551615):
        raise ValueError('Mã kết nối ADB của RC 2 bị thiếu hoặc không hợp lệ.')
    return ids[0]


class PinnedAdb:
    """Use the transport's existing -s target; never change a shared Adb object.

The existing USB relay uses a loopback transport serial. Physical ro.serialno
is separately checked against the GUI's RC serial before any device mutation.
"""
    def __init__(self, adb, serial):
        if not isinstance(serial, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', serial):
            raise ValueError('Cần số serial hợp lệ của RC 2 đã chọn.')
        target = getattr(adb, 'serial', '')
        if target != serial and not re.fullmatch(r'127\.0\.0\.1:[0-9]{1,5}', target):
            raise ValueError('Kết nối ADB phải được khóa vào đúng RC 2 đã chọn.')
        self.source, self.serial, self.target = adb, serial, target
        bind = getattr(adb, 'bind', None)
        if callable(bind):
            # Injectable transports must supply an immutable binding, not a
            # proxy that reads the shared object's target during dispatch.
            self.adb = bind(target)
        elif hasattr(adb, 'binary') and hasattr(adb, 'port'):
            from .transport import Adb
            control = Adb(adb.binary, adb.port, target)
            try:
                listing = control.command('devices', '-l', timeout=10)
            except (OSError, RuntimeError):
                raise HudTransportError('Không khóa được kết nối ADB; kiểm tra USB và kết nối lại. [ADB_BIND]') from None
            transport_id = transport_id_from_devices(listing, target)
            class TransportAdb(Adb):
                def command(self, *args, **kwargs):
                    return super().command('-t', transport_id, *args, **kwargs)
            self.adb = TransportAdb(adb.binary, adb.port)
        else:
            raise ValueError('Kết nối ADB không hỗ trợ khóa thiết bị ổn định; thao tác đã dừng.')
        self.fixed_serial = getattr(self.adb, 'serial', None)

    def _bound(self):
        if self.source.serial != self.target or self.adb.serial != self.fixed_serial:
            raise ValueError('Thiết bị đích ADB đã thay đổi trong khi xử lý HUD; thao tác đã dừng.')

    def shell(self, command, **kwargs):
        self._bound()
        # Device identity and the command share one shell/transport session.
        # This closes endpoint reuse between a prior guard and pm uninstall.
        command = ('if [ "$(getprop ro.serialno)" != ' + shlex.quote(self.serial)
                   + " ]; then printf 'RC2VI_HUD_WRONG_DEVICE\\n'; exit 1; fi; " + command)
        try:
            output = self.adb.shell(command, **kwargs)
        except (OSError, RuntimeError):
            raise HudTransportError('Lệnh ADB thất bại; kiểm tra kết nối và trạng thái RC 2. [ADB_IO]') from None
        if 'RC2VI_HUD_WRONG_DEVICE' in output.splitlines():
            raise ValueError('RC 2 đang kết nối không còn khớp serial đã chọn; thao tác đã dừng.')
        return output

    def command(self, *args, **kwargs):
        self._bound()
        try:
            return self.adb.command(*args, **kwargs)
        except (OSError, RuntimeError):
            raise HudTransportError('Lệnh ADB thất bại; kiểm tra kết nối và trạng thái RC 2. [ADB_IO]') from None


def run(adb, command, timeout=90):
    output = adb.shell(command + " && printf '\\n" + MARKER + "\\n'", timeout=timeout)
    if not output or output.splitlines()[-1] != MARKER:
        raise RuntimeError('Một bước khôi phục HUD không hoàn tất; chưa xác nhận dữ liệu đã được khôi phục.')


def remote_digest(adb, path):
    output = adb.shell('sha256sum ' + shlex.quote(path)
                       + " && printf '\\n" + MARKER + "\\n'", timeout=120).splitlines()
    output = [line for line in output if line != '']
    if len(output) != 2 or output[1] != MARKER:
        raise ValueError('Không kiểm chứng được mã SHA-256 của tệp trên RC 2.')
    match = re.fullmatch(r'([0-9a-f]{64}) [ *]' + re.escape(path), output[0])
    if match is None:
        raise ValueError('Kết quả SHA-256 trên RC 2 không rõ ràng hoặc không thuộc tệp cần kiểm tra.')
    return match[1]


def safe_roots_command():
    # Validate every component, not merely the terminal directory.
    paths = set()
    for root in DATA_ROOTS:
        paths.update(str(p) for p in PurePosixPath('/' + root).parents if str(p) != '/')
        paths.add('/' + root)
    checks = []
    for path in sorted(paths):
        if path == '/data/user/0':
            # Android's fixed user-0 CE alias is the sole permitted ancestor
            # link. Arbitrary aliases and linked /data/data remain rejected.
            checks.append('([ ! -L /data/user/0 ] || ([ "$(readlink /data/user/0)" = /data/data ]'
                          ' && [ -d /data/data ] && [ ! -L /data/data ]))')
        else:
            checks.append('[ ! -L ' + shlex.quote(path) + ' ]')
    return ' && '.join(checks)


def assert_stopped(adb):
    run(adb, 'am force-stop --user 0 ' + PACKAGE)
    run(adb, 'if pidof ' + PACKAGE + ' >/dev/null 2>&1; then exit 1; fi')


def validate_archive(path):
    """Validate raw tar checksums, canonical paths, types, exclusions and EOF."""
    path = guard_path(path)
    size = path.stat().st_size
    if size < 1024 or size % 512:
        raise ValueError('Bản sao lưu DJI Fly bị thiếu hoặc cắt ngắn dữ liệu.')
    seen, roots, owners, end = set(), set(), {}, 0
    external_app_ids=set()
    try:
        with tarfile.open(path, mode='r:') as archive:
            for member in archive:
                name = member.name.rstrip('/') if member.isdir() else member.name
                parts = name.split('/')
                if (not name or name.startswith('/') or any(p in {'', '.', '..'} for p in parts)
                        or '\\' in name or '\x00' in name or ':' in name
                        or any(ord(c) < 32 for c in name) or name in seen):
                    raise ValueError('Bản sao lưu DJI Fly chứa đường dẫn không an toàn.')
                root = next((r for r in DATA_ROOTS if name == r or name.startswith(r + '/')), None)
                if root is None or not (member.isdir() or member.isreg()):
                    raise ValueError('Bản sao lưu DJI Fly chứa đường dẫn hoặc liên kết không được phép.')
                if root not in PRIVATE_ROOTS:
                    if 10000<=member.uid<=19999:external_app_ids.add(member.uid)
                    if 10000<=member.gid<=19999:external_app_ids.add(member.gid)
                    elif 20000<=member.gid<=29999:external_app_ids.add(member.gid-10000)
                relative = name[len(root):].lstrip('/').split('/')
                if root in PRIVATE_ROOTS and relative[0] in {'lib', 'code_cache'}:
                    raise ValueError('Không khôi phục liên kết thư viện native hoặc thư mục code_cache.')
                if name == root:
                    if not member.isdir():
                        raise ValueError('Mỗi thư mục gốc trong bản sao lưu DJI Fly phải là thư mục thực.')
                    roots.add(root)
                    owners[root] = [member.uid, member.gid]
                seen.add(name)
                if len(seen) > 250000:
                    raise ValueError('Bản sao lưu DJI Fly chứa quá nhiều mục; thao tác đã dừng.')
                end = member.offset_data + ((member.size + 511) // 512) * 512
        if not set(DATA_ROOTS).issubset(roots):
            raise ValueError('Bản sao lưu DJI Fly thiếu một trong ba thư mục dữ liệu ứng dụng.')
        private_ids={owners[root][0] for root in PRIVATE_ROOTS}
        if external_app_ids and (len(private_ids)!=1 or not external_app_ids<=private_ids):
            raise ValueError('Dữ liệu ngoài chứa UID/GID ứng dụng khác DJI Fly. [EXTERNAL_UID]')
        with path.open('rb') as source:
            source.seek(end)
            if size - end < 1024:
                raise ValueError('Bản sao lưu DJI Fly thiếu dấu kết thúc tar; dữ liệu chưa toàn vẹn.')
            while True:
                tail = source.read(1024 * 1024)
                if not tail:
                    break
                if any(tail):
                    raise ValueError('Bản sao lưu DJI Fly chứa dữ liệu lạ sau phần kết thúc tar.')
    except (tarfile.TarError, EOFError, OSError):
        raise ValueError('Bản sao lưu DJI Fly không hợp lệ hoặc không đọc được.') from None
    return {'size': size, 'members': len(seen), 'roots': sorted(roots), 'owners': owners}


def private_json(path, value):
    path = guard_path(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.part')
    try:
        with temporary.open('x', encoding='utf-8') as output:
            make_private(temporary)
            json.dump(value, output, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class HudBackup:
    def __init__(self, work, emit, cancel=None):
        self.work, self.emit, self.cancel = Path(work), emit, cancel

    def _archive_command(self, remote):
        excludes = ' '.join('--exclude=' + r + '/' + name for r in PRIVATE_ROOTS
                            for name in ('lib', 'code_cache','files/.com.google.firebase.crashlytics.files.v2:'+PACKAGE))
        return ('tar -cpf ' + shlex.quote(remote) + ' -C / ' + excludes + ' '
                + ' '.join(DATA_ROOTS) + ' && chmod 600 ' + shlex.quote(remote))

    def _remote_stage(self, adb, remote, create=False):
        if create:
            run(adb, f'if [ ! -e {remote} ] && [ ! -L {remote} ]; then umask 077; mkdir {remote}; fi')
        run(adb, f'[ -d {remote} ] && [ ! -L {remote} ]')
        if adb.shell('stat -c %u:%a ' + remote).strip() != '0:700':
            raise ValueError('Thư mục khôi phục trên RC 2 phải là thư mục thực do root sở hữu, với quyền 700.')

    def _cleanup_record(self, recovery):
        if not isinstance(recovery, dict) or not {'directory', 'remote', 'serial'}.issubset(recovery):
            raise ValueError('Thiếu thông tin xác định staging khôi phục.')
        directory = guard_path(recovery['directory'])
        if (directory.parent != guard_path(self.work / 'recovery')
                or not re.fullmatch(r'[0-9a-f]{32}', directory.name)
                or recovery['remote'] != '/data/local/tmp/rc2vi-hud-data-' + directory.name
                or not isinstance(recovery['serial'], str)
                or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', recovery['serial'])):
            raise ValueError('Phạm vi dọn staging khôi phục không hợp lệ; không xóa tệp.')
        report = guard_path(directory / 'recovery.json')
        value = json.loads(report.read_text(encoding='utf-8'))
        if (not isinstance(value, dict) or any(value.get(key) != recovery[key]
                                              for key in ('directory', 'remote', 'serial'))):
            raise ValueError('Staging không khớp báo cáo khôi phục riêng tư; không xóa tệp.')
        return report, value

    def cleanup_result(self, recovery, cleaned, reason):
        """Worker-only durable outcome; does not access USB or remove PC files."""
        report, value = self._cleanup_record(recovery)
        result = {'status': 'hud_remote_cleaned' if cleaned else 'hud_remote_retained',
                  'cleaned': cleaned, 'serial': recovery['serial'], 'recovery_report': str(report),
                  'summary': ('Đã dọn staging khôi phục trên RC 2; bản sao lưu trên PC được giữ lại.'
                              if cleaned else 'Chưa dọn staging riêng tư trên RC 2. Giữ báo cáo '
                              'khôi phục và kiểm tra lại khi kết nối đúng thiết bị. [REMOTE_RETAINED]')}
        try:
            private_json(report, {**value, 'remote_cleanup': 'cleaned' if cleaned else 'retained',
                                  'remote_cleanup_reason': reason})
        except (OSError, RuntimeError, ValueError):
            self.emit('warning', 'Chưa ghi được kết quả dọn staging vào báo cáo riêng tư. [HUD_IO]')
        if not cleaned:
            self.emit('warning', result['summary'])
        return result

    @user_errors
    def cleanup_remote(self, adb, recovery):
        """Delete only known files in this recorded UUID/serial stage, then rmdir.

        No recursive deletion, PC deletion, app-data access or cancellation check.
        Uncertain recovery is retained even when a caller passes a stale record.
        """
        _, value = self._cleanup_record(recovery)
        if value.get('status') not in CLEANABLE_STATES:
            return self.cleanup_result(recovery, False, 'recovery_not_terminal')
        bound = adb if isinstance(adb, PinnedAdb) else PinnedAdb(adb, recovery['serial'])
        if bound.serial != recovery['serial']:
            raise ValueError('Không dọn staging của RC 2 khác với thiết bị đã chọn.')
        remote = recovery['remote']
        try:
            if bound.shell('getprop ro.serialno').strip() != recovery['serial']:
                raise ValueError('Serial thiết bị không khớp staging khôi phục; không xóa tệp.')
            if not bound.shell('id').startswith('uid=0('):
                raise ValueError('Cần shell root sẵn có để dọn staging khôi phục riêng tư.')
            run(bound, '[ ! -L /data ] && [ ! -L /data/local ] && [ ! -L /data/local/tmp ]')
            absent = bound.shell(f'if [ ! -e {remote} ] && [ ! -L {remote} ]; '
                                 "then printf 'RC2VI_HUD_ABSENT\\n'; fi").strip()
            if absent == 'RC2VI_HUD_ABSENT':
                return self.cleanup_result(recovery, True, 'already_absent')
            self._remote_stage(bound, remote)
            identity = value.get('remote_identity')
            if not isinstance(identity, str) or not re.fullmatch(r'[0-9]+:[1-9][0-9]*', identity):
                return self.cleanup_result(recovery, False, 'stage_identity_unverified')
            files = ' '.join(shlex.quote(name) for name in REMOTE_FILES)
            # Anchor relative unlinking to the recorded directory inode. A
            # rename/link swap cannot redirect deletion into another stage.
            command = ('cd ' + shlex.quote(remote)
                       + ' && [ "$(pwd -P)" = ' + shlex.quote(remote) + ' ]'
                       + ' && [ "$(stat -c %u:%a .)" = 0:700 ]'
                       + ' && [ "$(stat -c %d:%i .)" = ' + shlex.quote(identity) + ' ]'
                       + ' && rm -f -- ' + files + ' && rmdir -- ' + shlex.quote(remote))
            run(bound, command)
        except (OSError, RuntimeError):
            return self.cleanup_result(recovery, False, 'device_or_cleanup_unavailable')
        return self.cleanup_result(recovery, True, 'verified_stage_removed')

    def _download(self, adb, remote, local, staging, cancel=None):
        output = adb.shell('stat -c %s ' + shlex.quote(remote)).strip()
        if not re.fullmatch(r'[1-9][0-9]*', output):
            raise ValueError('Không kiểm chứng được kích thước tệp sao lưu DJI Fly.')
        size, expected = int(output), remote_digest(adb, remote)
        with local.open('xb') as destination:
            make_private(local)
            if size <= CHUNK_SIZE:
                check_cancel(cancel)
                adb.command('pull', remote, str(local), timeout=300)
            else:
                for offset in range(0, size, CHUNK_SIZE):
                    check_cancel(cancel)
                    part, remote_part = local.with_suffix('.part'), staging + '/transfer.part'
                    run(adb, 'dd if=' + shlex.quote(remote) + ' of=' + shlex.quote(remote_part)
                        + f' bs={CHUNK_SIZE} skip={offset // CHUNK_SIZE} count=1'
                        + ' && chmod 600 ' + shlex.quote(remote_part), timeout=300)
                    try:
                        with part.open('xb'):
                            make_private(part)
                        adb.command('pull', remote_part, str(part), timeout=300)
                        if part.stat().st_size != min(CHUNK_SIZE, size - offset):
                            raise ValueError('Một phần dữ liệu sao lưu DJI Fly chưa được truyền đầy đủ.')
                        with part.open('rb') as source:
                            while value := source.read(1024 * 1024):
                                destination.write(value)
                    finally:
                        part.unlink(missing_ok=True)
                destination.flush()
                os.fsync(destination.fileno())
        if local.stat().st_size != size or sha256_file(local, cancel) != expected:
            raise ValueError('Kích thước hoặc SHA-256 bản sao lưu DJI Fly không khớp sau khi truyền.')
        return {'size': size, 'digest': expected}

    def _upload(self, adb, local, target, staging, digest):
        """Use bounded chunks for large private archives in both directions."""
        local = guard_path(local)
        if sha256_file(local) != digest:
            raise ValueError('Tệp khôi phục riêng tư đã thay đổi trước khi gửi sang RC 2.')
        run(adb, '[ ! -L ' + target + ' ]')
        if local.stat().st_size <= CHUNK_SIZE:
            adb.command('push', str(local), target, timeout=300)
            run(adb, 'chmod 600 ' + target)
        else:
            run(adb, f'umask 077 && : > {target} && chmod 600 {target}')
            part = local.parent / ('upload-' + uuid.uuid4().hex + '.part')
            remote_part = staging + '/transfer.part'
            with local.open('rb') as source:
                while value := source.read(CHUNK_SIZE):
                    try:
                        with part.open('xb') as output:
                            make_private(part)
                            output.write(value)
                        run(adb, '[ ! -L ' + remote_part + ' ]')
                        adb.command('push', str(part), remote_part, timeout=300)
                        run(adb, f'chmod 600 {remote_part} && cat {remote_part} >> {target}')
                    finally:
                        part.unlink(missing_ok=True)
        if remote_digest(adb, target) != digest:
            raise ValueError('SHA-256 của tệp khôi phục tạm trên RC 2 không khớp.')

    @user_errors
    def create(self, adb, snapshot):
        check_cancel(self.cancel)
        uid = valid_uid(snapshot['uid'])
        apk_path = validate_package_path(snapshot['apk_path'])
        if adb.shell('getprop ro.serialno').strip() != snapshot['serial']:
            raise ValueError('Serial RC 2 đã thay đổi trước khi tạo bản sao lưu.')
        if remote_digest(adb, apk_path) != snapshot['digest']:
            raise ValueError('APK đang cài đã thay đổi trước khi tạo bản sao lưu khôi phục.')
        root = guard_path(self.work / 'recovery')
        root.mkdir(parents=True, exist_ok=True)
        make_private(root, directory=True)
        ident = uuid.uuid4().hex
        directory, remote = root / ident, '/data/local/tmp/rc2vi-hud-data-' + ident
        directory.mkdir(mode=0o700)
        make_private(directory, directory=True)
        record = {'schema': 1, 'directory': str(directory), 'serial': snapshot['serial'],
                  'uid': uid, 'apk_path': apk_path, 'remote': remote,
                  'report': str(directory / 'recovery.json')}
        self.report(record, 'hud_backup_incomplete', 'backup_preparing')
        try:
            assert_stopped(adb)
            run(adb, safe_roots_command())
            run(adb, 'umask 077 && mkdir ' + remote + ' && chmod 700 ' + remote)
            self._remote_stage(adb, remote)
            identity = adb.shell('stat -c %d:%i ' + remote).strip()
            if not re.fullmatch(r'[0-9]+:[1-9][0-9]*', identity):
                raise ValueError('Chưa kiểm chứng được danh tính thư mục staging riêng tư.')
            record = {**record, 'remote_identity': identity}
            self.report(record, 'hud_backup_incomplete', 'backup_capturing')
            return self._capture(adb, snapshot, record)
        except Exception:
            try:
                self.cleanup_remote(adb, record)
            except (OSError, RuntimeError, ValueError):
                self.cleanup_result(record, False, 'backup_failure_cleanup_unavailable')
            raise

    def _capture(self, adb, snapshot, record):
        directory, remote = Path(record['directory']), record['remote']
        apk_path = record['apk_path']
        archive, prior = directory / 'data.tar', directory / 'prior.apk'
        # All three app roots must be present; missing roots fail closed.
        run(adb, self._archive_command(remote + '/data.tar'), timeout=600)
        self.emit('applying', 'Đang kiểm tra bản sao lưu riêng tư của DJI Fly và APK đang cài…')
        archive_info = self._download(adb, remote + '/data.tar', archive, remote, self.cancel)
        tar_info = validate_archive(archive)
        run(adb, f'cp {shlex.quote(apk_path)} {remote}/prior.apk && chmod 600 {remote}/prior.apk')
        prior_info = self._download(adb, remote + '/prior.apk', prior, remote, self.cancel)
        if prior_info['digest'] != snapshot['digest'] or remote_digest(adb, apk_path) != snapshot['digest']:
            raise ValueError('APK giữ lại để khôi phục không khớp APK đang cài trên RC 2.')
        run(adb, 'if pidof ' + PACKAGE + ' >/dev/null 2>&1; then exit 1; fi')
        result = {**record, 'apk': str(prior),
                  'apk_digest': prior_info['digest'], 'apk_size': prior_info['size'],
                  'archive': str(archive), 'archive_digest': archive_info['digest'],
                  'archive_size': archive_info['size'], 'roots': tar_info['roots'],
                  'owners': tar_info['owners'],
                  'remote': remote, 'report': str(directory / 'recovery.json')}
        self.verify(result)
        self.report(result, 'hud_confirmation_required', 'verified_backup')
        return result

    @user_errors
    def check_fresh(self, adb, recovery):
        """Reject stale consent if userdata changed while the dialog was open.

        Do not silently replace the token-bound archive with newer bytes. Force
        stopping is done by the caller first; the comparison catches changes
        even if the app was reopened and then stopped again between calls.
        """
        self.verify(recovery)
        self._remote_stage(adb, recovery['remote'])
        if adb.shell('getprop ro.serialno').strip() != recovery['serial']:
            raise ValueError('Bản sao lưu thuộc RC 2 khác; không kiểm tra hoặc khôi phục trên thiết bị này.')
        run(adb, safe_roots_command())
        run(adb, 'if pidof ' + PACKAGE + ' >/dev/null 2>&1; then exit 1; fi')
        target = recovery['remote'] + '/freshness.tar'
        run(adb, '[ ! -L ' + shlex.quote(target) + ' ]')
        run(adb, self._archive_command(target), timeout=600)
        size = adb.shell('stat -c %s ' + shlex.quote(target)).strip()
        if size != str(recovery['archive_size']) or remote_digest(adb, target) != recovery['archive_digest']:
            raise ValueError('Dữ liệu DJI Fly đã thay đổi; cần tạo bản sao lưu mới và xác nhận lại.')
        run(adb, 'if pidof ' + PACKAGE + ' >/dev/null 2>&1; then exit 1; fi')

    @user_errors
    def verify(self, recovery):
        directory = guard_path(recovery['directory'])
        root = guard_path(self.work / 'recovery')
        if directory.parent != root or not re.fullmatch(r'[0-9a-f]{32}', directory.name):
            raise ValueError('Bản sao lưu phải thuộc thư mục khôi phục riêng tư do công cụ quản lý.')
        valid_uid(recovery['uid'])
        validate_package_path(recovery['apk_path'])
        if recovery['remote'] != '/data/local/tmp/rc2vi-hud-data-' + directory.name:
            raise ValueError('Thư mục khôi phục tạm trên RC 2 không khớp bản sao lưu đã chọn.')
        for key, name in [('archive', 'data.tar'), ('apk', 'prior.apk')]:
            path = guard_path(recovery[key])
            if (path != directory / name or path.stat().st_size != recovery[key + '_size']
                    or sha256_file(path) != recovery[key + '_digest']):
                raise ValueError('Kích thước, SHA-256 hoặc vị trí bản sao lưu đã thay đổi.')
        info = validate_archive(recovery['archive'])
        if info['roots'] != recovery['roots'] or info['owners'] != recovery['owners']:
            raise ValueError('Thư mục dữ liệu hoặc chủ sở hữu trong bản sao lưu đã thay đổi.')
        if any(info['owners'][root][0] != recovery['uid'] for root in PRIVATE_ROOTS):
            raise ValueError('Chủ sở hữu thư mục dữ liệu riêng tư không khớp UID của DJI Fly đang cài.')

    @user_errors
    def report(self, recovery, status, phase):
        path = guard_path(recovery['directory']) / 'recovery.json'
        value = {**recovery, 'status': status, 'phase': phase,
                 'restored': status == 'hud_rolled_back', 'keystore_restored': False}
        if status == 'hud_recovery_required':
            value.update(remote_cleanup='retained', remote_cleanup_reason='recovery_required')
        private_json(path, value)
        return str(path)

    @user_errors
    def restore(self, adb, recovery, new_uid, helper, helper_digest):
        self.verify(recovery)
        valid_uid(new_uid)
        if adb.shell('getprop ro.serialno').strip() != recovery['serial']:
            raise ValueError('Bản sao lưu thuộc RC 2 khác; không khôi phục trên thiết bị này.')
        if not HASH.fullmatch(helper_digest) or sha256_file(helper) != helper_digest:
            raise ValueError('Công cụ đổi chủ sở hữu dữ liệu không vượt qua kiểm tra toàn vẹn.')
        assert_stopped(adb)
        run(adb, safe_roots_command())
        remote = recovery['remote']
        # Recreate a lost private stage after reconnection; never chmod a link.
        self._remote_stage(adb, remote, create=True)
        for path, target, digest in [(recovery['archive'], remote + '/restore.tar', recovery['archive_digest']),
                                     (helper, remote + '/restore-owner', helper_digest)]:
            self._upload(adb, path, target, remote, digest)
        run(adb, 'chmod 700 ' + remote + '/restore-owner')
        # Existing destination links could redirect even a link-free archive.
        roots = ' '.join('/' + r for r in DATA_ROOTS)
        run(adb, 'mkdir -p ' + roots)
        excludes = ' -o '.join('-path /' + r + '/lib' for r in PRIVATE_ROOTS)
        # A pipeline would hide find failures behind wc's zero count. Check the
        # traversal exit status before counting its private output file.
        links = remote + '/links'
        run(adb, f'find {roots} \\( {excludes} \\) -prune -o -type l -print > {links}')
        output = adb.shell('wc -l < ' + links).strip()
        if output != '0':
            raise ValueError('Thư mục đích khôi phục chứa liên kết không được phép; thao tác đã dừng.')
        run(adb, f'tar -xpf {remote}/restore.tar -C /', timeout=600)
        run(adb, f'{remote}/restore-owner {recovery["uid"]} {new_uid}', timeout=300)
        run(adb, 'restorecon -RF ' + ' '.join('/' + r for r in DATA_ROOTS), timeout=300)
        for root in PRIVATE_ROOTS:
            if adb.shell('stat -c %u /' + root).strip() != str(new_uid):
                raise ValueError('Chưa kiểm chứng được chủ sở hữu dữ liệu DJI Fly sau khi khôi phục.')
            context = adb.shell('ls -Zd /' + root)
            if not re.search(r'\bu:object_r:app_data_file:s0(?::c\d+(?:,c\d+)*)?\b', context):
                raise ValueError('Chưa kiểm chứng được nhãn SELinux của dữ liệu DJI Fly sau khi khôi phục.')
        external = DATA_ROOTS[2]
        old_owner,old_group=recovery['owners'][external]
        expected_owner=new_uid if old_owner==recovery['uid'] else old_owner
        expected_group=(new_uid if old_group==recovery['uid'] else
                        new_uid+10000 if old_group==recovery['uid']+10000 else old_group)
        expected = str(expected_owner)+':'+str(expected_group)
        if adb.shell('stat -c %u:%g /' + external).strip() != expected:
            raise ValueError('Chưa kiểm chứng được chủ sở hữu vùng dữ liệu ngoài của DJI Fly sau khi khôi phục.')
        if 'u:object_r:media_rw_data_file:s0' not in adb.shell('ls -Zd /' + external).split():
            raise ValueError('Chưa kiểm chứng được nhãn SELinux của vùng dữ liệu ngoài DJI Fly sau khi khôi phục.')
        run(adb, 'if pidof ' + PACKAGE + ' >/dev/null 2>&1; then exit 1; fi')
