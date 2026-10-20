"""RC2 native animation overrides, without changing protected partitions.

The reviewed DJI library reads the two custom path properties. Every device
operation uses a selected, serial-checked Connection; Connection owns its USB
lease. Local receipts retain the previous setting separately for each kind.
Nothing here reboots the controller or starts/stops Android services.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import sys
import time
import uuid
import zipfile

from PIL import Image

from .core import validate_rc_device
from .hud_backup import guard_path, make_private
from .transport import Connection, UsbLease
from .usb_windows import discover


REMOTE_DIRECTORY = '/data/local/ginzatech-bootanimation'
NATIVE_LIBRARY = '/system/lib64/libbootanimation.so'
PERSISTENT_PROPERTIES = '/data/property/persistent_properties'
# Independently disassembled RC2 library: local-artifacts/bootanimation-
# ginzatech-v1/install-20261020-170903/override-evidence.md.
REVIEWED_LIBRARY_SHA256 = '9442ab962705a12d0b442b48250954d71be9c800ad650fe962ede36040a0b3a6'
SCHEMA = 'rc2.animation.installation.v1'
MAX_PACKAGE_BYTES = 768 * 1024 * 1024
MAX_FRAMES = 2400
MAX_LOOP_TEXTURE_BYTES = 256 * 1024 * 1024
_HASH = re.compile(r'[0-9a-f]{64}')
_OWNED = re.compile(re.escape(REMOTE_DIRECTORY) + r'/(boot|shutdown)animation-[0-9a-f]{16}\.zip')
_ABSENT = 'RC2_ANIM_ABSENT'


class AnimationCancelled(InterruptedError):
    """Cancellation leaves the previous animation selected whenever possible."""


def _check(cancel):
    if cancel is not None and (cancel.is_set() if hasattr(cancel, 'is_set') else cancel()):
        raise AnimationCancelled('Đã hủy thao tác animation.')


def _sha(path, cancel=None):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while True:
            _check(cancel)
            chunk = stream.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def _kind(kind):
    if kind not in ('boot', 'shutdown'):
        raise ValueError('Chỉ hỗ trợ animation khởi động hoặc tắt máy.')
    return kind


def _serial(serial):
    if not isinstance(serial, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', serial):
        raise ValueError('Serial RC 2 không hợp lệ.')
    return serial


def _property(kind):
    return 'persist.sys.customanim.' + _kind(kind)


def _property_value(value):
    # Android 11 property values are at most 91 UTF-8 bytes. Previous settings
    # may belong to another tool, but are never interpolated as shell code.
    if (not isinstance(value, str) or len(value.encode('utf-8')) > 91
            or (value and (not re.fullmatch(r'/[A-Za-z0-9_./+-]+\.zip', value)
                           or '..' in value.split('/')))):
        raise ValueError('Đường dẫn animation hiện tại không hợp lệ; đã dừng để giữ nguyên cấu hình.')
    return value


def _atomic_json(path, value):
    path = guard_path(path)
    temporary = guard_path(path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp'))
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        make_private(temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_zip(path, cancel=None):
    """Decode every PNG and check the deliberately small Android ZIP dialect."""
    path = guard_path(path)
    if not path.is_file() or not 1 <= path.stat().st_size <= MAX_PACKAGE_BYTES:
        raise ValueError('Gói animation bị thiếu hoặc vượt giới hạn 768 MiB.')
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if (not entries or len(entries) > MAX_FRAMES + 65 or len(set(names)) != len(names)
                    or names.count('desc.txt') != 1
                    or any(entry.compress_type != zipfile.ZIP_STORED or entry.flag_bits & 1
                           or entry.file_size > 32 * 1024 * 1024
                           or '\\' in entry.filename or entry.filename.startswith('/')
                           or '..' in entry.filename.split('/')
                           or ((entry.external_attr >> 16) & 0o170000) == 0o120000
                           for entry in entries)):
                raise ValueError('ZIP animation phải lưu không nén, có desc.txt ở gốc và đường dẫn an toàn.')
            if sum(entry.file_size for entry in entries) > MAX_PACKAGE_BYTES:
                raise ValueError('Dữ liệu animation vượt giới hạn.')
            descriptor = archive.read('desc.txt')
            if len(descriptor) > 16 * 1024:
                raise ValueError('desc.txt animation quá lớn.')
            lines = [line.strip() for line in descriptor.decode('ascii').splitlines() if line.strip()]
            header = lines[0].split() if lines else []
            if len(header) != 3 or not all(re.fullmatch(r'[0-9]{1,4}', field) for field in header):
                raise ValueError('Thông số animation không hợp lệ.')
            width, height, fps = map(int, header)
            if (not 64 <= width <= 1920 or not 64 <= height <= 1080
                    or width * 9 != height * 16 or not 6 <= fps <= 30):
                raise ValueError('Animation RC 2 cần tỉ lệ 16:9, tối đa 1920 × 1080, từ 6 đến 30 fps.')
            parts = []
            repeats = {}
            for line in lines[1:]:
                fields = line.split()
                if (len(fields) not in (4, 5) or fields[0] not in ('p', 'c')
                        or not all(re.fullmatch(r'[0-9]{1,4}', field) for field in fields[1:3])
                        or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', fields[3])
                        or (len(fields) == 5 and not re.fullmatch(r'#[0-9A-Fa-f]{6}', fields[4]))):
                    raise ValueError('Phân đoạn desc.txt animation không hợp lệ.')
                parts.append(fields[3])
                repeats[fields[3]] = int(fields[1])
            if not 1 <= len(parts) <= 32 or len(parts) != len(set(parts)):
                raise ValueError('Animation cần từ 1 đến 32 phân đoạn khác nhau.')
            frames_by_part = {part: [] for part in parts}
            for entry in entries:
                _check(cancel)
                if entry.filename == 'desc.txt':
                    continue
                if entry.is_dir() and entry.filename[:-1] in frames_by_part and entry.file_size == 0:
                    continue
                if entry.filename in {part + '/trim.txt' for part in parts}:
                    continue
                match = re.fullmatch(r'([A-Za-z0-9_-]{1,32})/([0-9]{1,12})\.png', entry.filename)
                if not match or match[1] not in frames_by_part:
                    raise ValueError('ZIP animation chứa tệp không được hỗ trợ.')
                frames_by_part[match[1]].append(entry)
            frames = sum(len(items) for items in frames_by_part.values())
            if not all(frames_by_part.values()) or not 1 <= frames <= MAX_FRAMES:
                raise ValueError('Animation có phân đoạn trống hoặc quá nhiều khung hình.')
            loop_texture_bytes = padded_loop_texture_bytes = 0
            for part, images in frames_by_part.items():
                images.sort(key=lambda entry: entry.filename)
                trim_name = part + '/trim.txt'
                trims = None
                if trim_name in names:
                    trim_info = archive.getinfo(trim_name)
                    if trim_info.file_size > 256 * 1024:
                        raise ValueError('trim.txt animation quá lớn.')
                    trims = archive.read(trim_name).decode('ascii').splitlines()
                    if len(trims) != len(images):
                        raise ValueError('trim.txt phải có đúng một dòng cho mỗi khung hình PNG.')
                for index, entry in enumerate(images):
                    _check(cancel)
                    expected = (width, height)
                    if trims is not None:
                        geometry = re.fullmatch(r'([0-9]{1,4})x([0-9]{1,4})\+([0-9]{1,4})\+([0-9]{1,4})', trims[index])
                        if geometry is None:
                            raise ValueError('Tọa độ cắt trong trim.txt animation không hợp lệ.')
                        crop_width, crop_height, x, y = map(int, geometry.groups())
                        if (crop_width < 1 or crop_height < 1 or x + crop_width > width
                                or y + crop_height > height):
                            raise ValueError('Khung hình cắt nằm ngoài màn hình animation.')
                        expected = crop_width, crop_height
                    raw = archive.read(entry)
                    with Image.open(io.BytesIO(raw)) as frame:
                        if frame.format != 'PNG' or frame.size != expected:
                            raise ValueError('PNG animation không khớp kích thước canvas/trim.txt.')
                        frame.verify()
                    # verify() checks PNG structure; load() also catches damaged
                    # pixel streams. Nothing is extracted from the archive.
                    with Image.open(io.BytesIO(raw)) as frame:
                        frame.load()
                    if repeats[part] != 1:
                        loop_texture_bytes += expected[0] * expected[1] * 4
                        padded_loop_texture_bytes += ((1 << (expected[0] - 1).bit_length())
                                                      * (1 << (expected[1] - 1).bit_length()) * 4)
                        if loop_texture_bytes > MAX_LOOP_TEXTURE_BYTES:
                            raise ValueError('Đoạn lặp animation vượt 256 MiB bộ nhớ hình ảnh; giảm FPS/thời lượng/độ phân giải.')
            return {'width': width, 'height': height, 'fps': fps, 'frames': frames,
                    'parts': len(parts), 'size': path.stat().st_size, 'sha256': _sha(path, cancel),
                    'loop_texture_bytes': loop_texture_bytes,
                    'loop_texture_padded_estimate_bytes': padded_loop_texture_bytes}
    except (zipfile.BadZipFile, UnicodeError, IndexError, OSError, SyntaxError) as exc:
        raise ValueError('Không đọc được ZIP/PNG animation hợp lệ.') from exc


def _snapshot(package, directory, cancel):
    package = guard_path(package)
    if not package.is_file() or not 1 <= package.stat().st_size <= MAX_PACKAGE_BYTES:
        raise ValueError('Chọn gói bootanimation.zip hợp lệ, tối đa 768 MiB.')
    temporary = guard_path(directory / ('package-' + uuid.uuid4().hex + '.partial'))
    try:
        with package.open('rb') as source, temporary.open('xb') as target:
            copied = 0
            while True:
                _check(cancel)
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > MAX_PACKAGE_BYTES:
                    raise ValueError('Gói animation vượt giới hạn 768 MiB.')
                target.write(chunk)
        make_private(temporary)
        details = _validate_zip(temporary, cancel)
        destination = guard_path(directory / ('package-' + details['sha256'] + '.zip'))
        if destination.exists():
            if not destination.is_file() or _sha(destination, cancel) != details['sha256']:
                raise ValueError('Bản gói animation lưu trước đó bị thay đổi.')
        else:
            temporary.replace(destination)
        return destination, details
    finally:
        temporary.unlink(missing_ok=True)


def _shell(adb, command, timeout=30):
    # Adb.shell uses shell -x, so subprocess success does not prove remote
    # success. The marker must be the last complete line from an && chain.
    marker = 'RC2_ANIM_OK_' + uuid.uuid4().hex
    output = adb.shell('(' + command + ') && echo ' + marker, timeout=timeout)
    lines = output.splitlines()
    if not lines or lines[-1] != marker:
        raise RuntimeError('RC 2 không xác nhận hoàn tất lệnh animation; cấu hình chưa được xác minh.')
    return '\n'.join(lines[:-1]).strip()


def _file(adb, path, required=True):
    quoted = shlex.quote(path)
    command = (f'if [ ! -e {quoted} ] && [ ! -L {quoted} ]; then echo {_ABSENT}; '
               f'else [ -f {quoted} ] && [ ! -L {quoted} ] && sha256sum {quoted} '
               f"&& stat -c '%s %u %g %a' {quoted}; fi")
    output = _shell(adb, command, timeout=120)
    if output == _ABSENT:
        if required:
            raise ValueError('Thiếu tệp animation cần xác minh trên RC 2.')
        return None
    lines = output.splitlines()
    digest = re.fullmatch(r'([0-9a-f]{64})\s+\*?' + re.escape(path), lines[0]) if lines else None
    metadata = re.fullmatch(r'([0-9]{1,12}) ([0-9]{1,10}) ([0-9]{1,10}) ([0-7]{3,4})', lines[1]) if len(lines) == 2 else None
    if not digest or not metadata:
        raise ValueError('Hash hoặc thông tin tệp animation trên RC 2 không hợp lệ.')
    return {'path': path, 'sha256': digest[1], 'size': int(metadata[1]),
            'uid': int(metadata[2]), 'gid': int(metadata[3]), 'mode': metadata[4]}


def _verify_identity(adb, serial):
    if _shell(adb, 'getprop ro.serialno') != serial:
        raise ValueError('Serial ADB không khớp đúng tay RC 2 đã chọn.')
    validate_rc_device(_shell(adb, 'getprop ro.product.model'),
                       _shell(adb, 'getprop ro.product.device'), _shell(adb, 'id'))
    if _shell(adb, 'getprop ro.build.version.sdk') != '30':
        raise ValueError('Animation hiện chỉ hỗ trợ Android 11 trên DJI RC 2 đã kiểm chứng.')


def _verify_native(adb, directory, cancel):
    before = _file(adb, NATIVE_LIBRARY)
    if before['sha256'] != REVIEWED_LIBRARY_SHA256 or not 64 <= before['size'] <= 2 * 1024 * 1024:
        raise ValueError('Thư viện animation của firmware này chưa được kiểm chứng; chưa đổi cấu hình.')
    local = guard_path(directory / ('native-' + uuid.uuid4().hex + '.so'))
    try:
        adb.command('pull', '-Z', NATIVE_LIBRARY, str(local), timeout=90)
        _check(cancel)
        raw = local.read_bytes()
        if (len(raw) != before['size'] or hashlib.sha256(raw).hexdigest() != before['sha256']
                or raw[:5] != b'\x7fELF\x02'
                or any(key.encode('ascii') + b'\0' not in raw
                       for key in (_property('boot'), _property('shutdown')))
                or _file(adb, NATIVE_LIBRARY) != before):
            raise ValueError('Không xác minh được cơ chế custom animation gốc của DJI trên tay.')
        return before['sha256']
    finally:
        local.unlink(missing_ok=True)


def _read_property(adb, kind):
    return _property_value(_shell(adb, 'getprop ' + _property(kind)))


def _persisted_value(raw, key):
    # AOSP Android 11 init/persistent_properties.proto: repeated field 1
    # contains records whose string fields 1/2 are name/value. Bound every
    # length; never print or retain unrelated persistent property values.
    # https://github.com/aosp-mirror/platform_system_core/blob/android-11.0.0_r1/init/persistent_properties.proto
    def fields(data):
        offset = 0

        def number():
            nonlocal offset
            result = 0
            for shift in range(0, 35, 7):
                if offset >= len(data):
                    break
                byte = data[offset]
                offset += 1
                result |= (byte & 127) << shift
                if byte < 128:
                    return result
            raise ValueError('Dữ liệu property lưu bền không đúng định dạng Android 11.')

        while offset < len(data):
            tag, length = number(), number()
            if tag & 7 != 2 or tag >> 3 == 0 or length > len(data) - offset:
                raise ValueError('Dữ liệu property lưu bền không đúng định dạng Android 11.')
            yield tag >> 3, data[offset:offset + length]
            offset += length

    if not raw or len(raw) > 1024 * 1024:
        raise ValueError('Tệp property lưu bền vượt giới hạn hoặc bị trống.')
    matches = []
    for tag, record in fields(raw):
        if tag != 1:
            raise ValueError('Định dạng property lưu bền của firmware chưa được hỗ trợ.')
        values = {}
        for field, value in fields(record):
            if field not in (1, 2) or field in values or len(value) > 4096:
                raise ValueError('Bản ghi property lưu bền không hợp lệ.')
            values[field] = value.decode('utf-8')
        if values.get(1) == key:
            matches.append(values.get(2, ''))
    if len(matches) != 1:
        raise ValueError('Không thấy đúng một property animation lưu bền trên RC 2.')
    return matches[0]


def _persistent(adb, kind, value, cancel=None):
    command = 'grep -a -F -q -- ' + shlex.quote(_property(kind)) + ' ' + PERSISTENT_PROPERTIES
    if value:
        command += ' && grep -a -F -q -- ' + shlex.quote(value) + ' ' + PERSISTENT_PROPERTIES
    for attempt in range(4):
        _check(cancel)
        try:
            _shell(adb, command)
            encoded = _shell(adb, f'[ -f {PERSISTENT_PROPERTIES} ] && [ ! -L {PERSISTENT_PROPERTIES} ] '
                             f'&& [ "$(stat -c %s {PERSISTENT_PROPERTIES})" -le 1048576 ] '
                             f'&& base64 {PERSISTENT_PROPERTIES}')
            compact = ''.join(encoded.split())
            if len(compact) > 4 * ((1024 * 1024 + 2) // 3):
                raise ValueError('Tệp property lưu bền vượt giới hạn.')
            raw = base64.b64decode(compact, validate=True)
            if _persisted_value(raw, _property(kind)) != value:
                raise ValueError('Property animation chưa được lưu bền đúng giá trị đã chọn.')
            return
        except (RuntimeError, ValueError, UnicodeError):
            if attempt == 3:
                raise
            time.sleep(.1)


def _select(adb, kind, value, cancel=None):
    _shell(adb, 'setprop ' + _property(kind) + ' ' + shlex.quote(_property_value(value)))
    if _read_property(adb, kind) != value:
        raise ValueError('Giá trị animation đọc lại không khớp; chưa xác nhận cài thành công.')
    _persistent(adb, kind, value, cancel)


def _load_receipt(directory, serial, kind):
    path = guard_path(directory / 'installation.json')
    if not path.exists():
        return None
    try:
        if path.stat().st_size > 128 * 1024:
            raise ValueError('Biên bản animation quá lớn.')
        receipt = json.loads(path.read_text('utf-8'))
        digest = receipt.get('package_sha256')
        expected = REMOTE_DIRECTORY + '/' + kind + 'animation-' + str(digest)[:16] + '.zip'
        if (receipt.get('schema') != SCHEMA or receipt.get('serial') != serial
                or receipt.get('kind') != kind or receipt.get('property') != _property(kind)
                or not isinstance(digest, str) or not _HASH.fullmatch(digest)
                or receipt.get('property_value') != expected
                or receipt.get('installed_verified') is not True
                or receipt.get('persistent_property_file_verified') is not True
                or receipt.get('persistent_property_binding_verified') is not True
                or receipt.get('status') not in ('installed', 'restored')):
            raise ValueError('Biên bản animation không khớp tay và loại animation đã chọn.')
        _property_value(receipt.get('previous_property_value'))
        previous = receipt.get('previous_file')
        if receipt['previous_property_value']:
            if (not isinstance(previous, dict) or previous.get('path') != receipt['previous_property_value']
                    or not isinstance(previous.get('sha256'), str) or not _HASH.fullmatch(previous['sha256'])
                    or type(previous.get('size')) is not int or previous['size'] < 1):
                raise ValueError('Biên bản thiếu bản animation trước đó đã xác minh.')
        return receipt
    except (json.JSONDecodeError, UnicodeError, AttributeError, TypeError) as exc:
        raise ValueError('Biên bản animation không hợp lệ; giữ nguyên cấu hình RC 2.') from exc


class _CancelView:
    def __init__(self, cancel):
        self.cancel = cancel

    def is_set(self):
        return bool(self.cancel is not None and
                    (self.cancel.is_set() if hasattr(self.cancel, 'is_set') else self.cancel()))


@contextmanager
def _session(assets, work, serial, kind, emit, cancel, connection_factory, discover_fn,
             reconnect_event=None):
    _check(cancel)
    matches = [device for device in discover_fn() if device.serial == serial]
    if len(matches) != 1:
        raise ValueError('Cần đúng một thiết bị USB khớp serial RC 2 đã chọn.')
    directory = guard_path(Path(work).absolute() / 'animation' /
                           ('rc2-' + hashlib.sha256(serial.encode()).hexdigest()[:16]) / kind)
    directory.mkdir(parents=True, exist_ok=True)
    make_private(directory, directory=True)
    lease = UsbLease('animation-work-' + str(directory))
    connection = None
    try:
        _check(cancel)
        connection = connection_factory(matches[0], Path(assets), emit)
        connection._opening_cancel = _CancelView(cancel)
        connection._opening_reconnect_event = reconnect_event
        adb = connection.open()
        _check(cancel)
        _verify_identity(adb, serial)
        yield adb, directory
    finally:
        try:
            if connection is not None:
                connection.close()
        finally:
            lease.close()


def _stage(adb, local, package, kind, cancel):
    final = REMOTE_DIRECTORY + '/' + kind + 'animation-' + package['sha256'][:16] + '.zip'
    stage = REMOTE_DIRECTORY + '/.upload-' + package['sha256'] + '.zip'
    directory = shlex.quote(REMOTE_DIRECTORY)
    # Refuse links and preexisting non-root-owned directories. The private
    # namespace is never created under an app-writable parent directory.
    _shell(adb, f'[ -d /data/local ] && [ ! -L /data/local ] '
           f'&& [ "$(stat -c %u /data/local)" = 0 ] '
           f'&& if [ -e {directory} ] || [ -L {directory} ]; then '
           f'[ -d {directory} ] && [ ! -L {directory} ] '
           f'&& [ "$(stat -c %u:%g {directory})" = 0:0 ]; else mkdir {directory}; fi '
           f'&& chown 0:0 {directory} && chmod 0755 {directory} '
           f'&& [ "$(stat -c %u:%g:%a {directory})" = 0:0:755 ]')
    existing = _file(adb, final, required=False)
    if existing is not None:
        _verify_package(existing, package)
        return final
    created = False
    try:
        _check(cancel)
        # noclobber refuses any preexisting upload, including a symbolic link.
        _shell(adb, f'(set -C; : > {shlex.quote(stage)}) '
               f'&& chown 0:0 {shlex.quote(stage)} && chmod 0644 {shlex.quote(stage)}')
        created = True
        adb.command('push', '-Z', str(local), stage, timeout=300)
        _check(cancel)
        # ADB SEND applies the host file's mode, overriding the permission set
        # when this upload was reserved. The retained RC2 session records
        # 0:0:666 immediately after a Windows push. Harden only this operation's
        # reserved regular/root-owned upload, then verify the resulting bytes
        # and all metadata again. Existing final packages are never repaired.
        uploaded = _file(adb, stage)
        if uploaded['uid'] != 0 or uploaded['gid'] != 0:
            _verify_package(uploaded, package)
        quoted_stage = shlex.quote(stage)
        _shell(adb, f'[ -f {quoted_stage} ] && [ ! -L {quoted_stage} ] '
               f'&& [ "$(stat -c %u:%g {quoted_stage})" = 0:0 ] '
               f'&& chown 0:0 {quoted_stage} && chmod 0644 {quoted_stage}')
        _verify_package(_file(adb, stage), package)
        _shell(adb, 'mv -n -- ' + shlex.quote(stage) + ' ' + shlex.quote(final))
        _verify_package(_file(adb, final), package)
        return final
    finally:
        if created:
            # Only this operation's newly reserved upload is eligible. Final
            # packages (including a previous good package) are never removed.
            primary_error = sys.exc_info()[1]
            try:
                _shell(adb, f'if [ ! -e {shlex.quote(stage)} ] && [ ! -L {shlex.quote(stage)} ]; then :; '
                       f'else [ -f {shlex.quote(stage)} ] && [ ! -L {shlex.quote(stage)} ] '
                       f'&& [ "$(stat -c %u:%g {shlex.quote(stage)})" = 0:0 ] '
                       f'&& rm -f -- {shlex.quote(stage)}; fi')
            except Exception:
                # A disconnected or replaced upload must not hide the actual
                # checksum/ownership error, or be removed without its guards.
                if primary_error is None:
                    raise


def _verify_package(remote, package):
    differences = []
    if remote['sha256'] != package['sha256']:
        differences.append(f"SHA-256 trên tay {remote['sha256']}, cần {package['sha256']}")
    if remote['size'] != package['size']:
        differences.append(f"kích thước {remote['size']} byte, cần {package['size']} byte")
    if remote['uid'] != 0 or remote['gid'] != 0:
        differences.append(f"chủ sở hữu UID:GID {remote['uid']}:{remote['gid']}, cần 0:0")
    if int(remote['mode'], 8) != 0o644:
        differences.append(f"quyền {int(remote['mode'], 8):04o}, cần 0644")
    if differences:
        raise ValueError('Gói animation trên RC 2 không khớp: ' + '; '.join(differences) + '.')


def _rollback(adb, kind, current, previous, report, report_path):
    try:
        observed = _read_property(adb, kind)
        if observed == current:
            _select(adb, kind, previous)
        elif observed != previous:
            raise ValueError('Cấu hình animation đã được thay đổi bởi một phiên khác; không ghi đè.')
        report['rollback_verified'] = _read_property(adb, kind) == previous
        _persistent(adb, kind, previous)
    except Exception as exc:
        report['rollback_verified'] = False
        report['rollback_error'] = str(exc)
    _atomic_json(report_path, report)


def install_animation(assets, work, serial, package_path, kind='boot', *, grounded=False,
                      emit=None, cancel=None, reconnect_event=None,
                      connection_factory=Connection, discover_fn=discover):
    """Validate/export first, then select a hash-verified native custom ZIP.

    Requires the caller's explicit grounded checkbox. No reboot is performed;
    returned installed_verified covers transfer/property persistence, never
    physical boot/shutdown playback.
    """
    if grounded is not True:
        raise ValueError('Xác nhận đã hạ cánh và động cơ dừng trước khi cài animation.')
    serial, kind = _serial(serial), _kind(kind)
    emit = emit or (lambda *_: None)
    _check(cancel)
    # Snapshot and fully decode the package before enumerating/opening USB.
    offline = guard_path(Path(work).absolute() / 'animation' / 'validated-packages')
    offline.mkdir(parents=True, exist_ok=True)
    make_private(offline, directory=True)
    local, package = _snapshot(Path(package_path), offline, cancel)
    emit('animation_check', 'Đã kiểm tra ZIP/PNG; đang kiểm tra đúng tay RC 2 và cơ chế animation gốc…')
    with _session(assets, work, serial, kind, emit, cancel, connection_factory, discover_fn,
                  reconnect_event) as (adb, directory):
        library = _verify_native(adb, directory, cancel)
        current = _read_property(adb, kind)
        other_kind = 'shutdown' if kind == 'boot' else 'boot'
        other = _read_property(adb, other_kind)
        receipt = _load_receipt(directory, serial, kind)
        if receipt and receipt['status'] == 'installed' and current != receipt['property_value']:
            raise ValueError('Animation hiện tại khác biên bản lần trước; chưa ghi đè cấu hình đã thay đổi.')
        previous = receipt['previous_property_value'] if receipt and receipt['status'] == 'installed' else current
        previous_file = receipt.get('previous_file') if receipt and receipt['status'] == 'installed' else None
        if previous:
            observed = _file(adb, previous)
            if previous_file and (observed['sha256'], observed['size']) != (previous_file['sha256'], previous_file['size']):
                raise ValueError('Animation trước đó đã thay đổi; chưa cài gói mới.')
            previous_file = observed
            backup = guard_path(directory / ('previous-' + observed['sha256'] + '.zip'))
            if not backup.is_file() or _sha(backup, cancel) != observed['sha256']:
                adb.command('pull', '-Z', previous, str(backup), timeout=180)
                _check(cancel)
                if not backup.is_file() or _sha(backup, cancel) != observed['sha256'] or _file(adb, previous) != observed:
                    raise ValueError('Không sao lưu được animation đang dùng; chưa thay đổi cấu hình.')
                make_private(backup)
        stock_path = '/product/media/' + kind + 'animation.zip'
        stock = _file(adb, stock_path, required=False)
        _check(cancel)
        emit('animation_upload', 'Đang chuyển và xác minh gói animation; giữ nguyên các tệp hệ thống…')
        final = _stage(adb, local, package, kind, cancel)
        report = {'schema': SCHEMA, 'serial': serial, 'kind': kind, 'status': 'prepared',
                  'time_utc': datetime.now(timezone.utc).isoformat(), 'property': _property(kind),
                  'property_value': final, 'previous_property_value': previous, 'previous_file': previous_file,
                  'package_sha256': package['sha256'], 'package_size': package['size'], 'package': package,
                  'native_library_sha256': library, 'stock_file': stock, 'installed_verified': False,
                  'persistent_property_file_verified': False, 'persistent_property_binding_verified': False,
                  'reboot_performed': False,
                  'boot_visual_verified': False, 'shutdown_visual_verified': False, 'partitions_remounted': False}
        report_path = guard_path(directory / ('operation-' + uuid.uuid4().hex + '.json'))
        _atomic_json(report_path, report)
        changed = False
        try:
            _check(cancel)
            _verify_identity(adb, serial)
            if _read_property(adb, kind) != current or _read_property(adb, other_kind) != other:
                raise ValueError('Cấu hình animation đã đổi trong lúc chuẩn bị; chưa chọn gói mới.')
            changed = True  # A transport error after setprop may still mean it executed.
            _select(adb, kind, final, cancel)
            _check(cancel)
            _verify_package(_file(adb, final), package)
            if (_file(adb, stock_path, required=False) != stock
                    or _read_property(adb, other_kind) != other or _read_property(adb, kind) != final):
                raise ValueError('Cấu hình gốc/animation còn lại đã đổi trong lúc xác minh.')
            report.update(status='installed', installed_verified=True,
                          persistent_property_file_verified=True, persistent_property_binding_verified=True,
                          stock_unchanged=True,
                          other_animation_unchanged=True, receipt=str(directory / 'installation.json'),
                          operation_report=str(report_path))
            _atomic_json(report_path, report)
            # Keep the prior good receipt until all other verification/report
            # writes finish. Replacing the receipt is the transaction commit.
            _atomic_json(directory / 'installation.json', report)
        except BaseException as exc:
            report.update(status='failed', installed_verified=False, error=str(exc))
            if changed:
                # Restore the immediately preceding selection on failure; the
                # receipt's original previous value may be older than that.
                _rollback(adb, kind, final, current, report, report_path)
            else:
                _atomic_json(report_path, report)
            raise
        emit('animation_installed', 'Đã cài animation và đọc lại hash/cấu hình lưu bền. Khởi động/tắt máy thật để kiểm tra hiển thị.')
        return report


def restore_animation(assets, work, serial, kind='boot', *, grounded=False,
                      emit=None, cancel=None, reconnect_event=None,
                      connection_factory=Connection, discover_fn=discover):
    """Restore this tool's saved selection, or clear a legacy owned override.

    A configuration changed by another tool is left alone. Packages are kept
    for recovery; clearing the native override returns selection to stock.
    """
    if grounded is not True:
        raise ValueError('Xác nhận đã hạ cánh và động cơ dừng trước khi khôi phục animation.')
    serial, kind = _serial(serial), _kind(kind)
    emit = emit or (lambda *_: None)
    with _session(assets, work, serial, kind, emit, cancel, connection_factory, discover_fn,
                  reconnect_event) as (adb, directory):
        _verify_native(adb, directory, cancel)
        current = _read_property(adb, kind)
        other_kind = 'shutdown' if kind == 'boot' else 'boot'
        other = _read_property(adb, other_kind)
        receipt = _load_receipt(directory, serial, kind)
        if receipt:
            previous = receipt['previous_property_value']
            if current == previous:
                return {'status': 'restored', 'serial': serial, 'kind': kind, 'changed': False,
                        'property_value': previous, 'restored_verified': True, 'reboot_performed': False}
            if current != receipt['property_value']:
                raise ValueError('Cấu hình animation đã đổi ngoài công cụ; không ghi đè khi khôi phục.')
            if previous:
                observed = _file(adb, previous)
                old = receipt['previous_file']
                if (observed['sha256'], observed['size']) != (old['sha256'], old['size']):
                    raise ValueError('Animation trước đó không còn đúng bản sao lưu; chưa khôi phục.')
        else:
            previous = ''
            if current and not (_OWNED.fullmatch(current) and _OWNED.fullmatch(current)[1] == kind):
                raise ValueError('Animation hiện tại thuộc cấu hình khác; không xóa khi chưa có biên bản của công cụ.')
            if not current:
                return {'status': 'restored', 'serial': serial, 'kind': kind, 'changed': False,
                        'property_value': '', 'restored_verified': True, 'reboot_performed': False}
        report = {'schema': SCHEMA, 'serial': serial, 'kind': kind, 'status': 'restoring',
                  'property': _property(kind), 'property_value': previous, 'previous_property_value': current,
                  'changed': True, 'restored_verified': False, 'reboot_performed': False,
                  'partitions_remounted': False, 'boot_visual_verified': False, 'shutdown_visual_verified': False}
        report_path = guard_path(directory / ('restore-' + uuid.uuid4().hex + '.json'))
        _atomic_json(report_path, report)
        changed = False
        try:
            _check(cancel)
            _verify_identity(adb, serial)
            if _read_property(adb, kind) != current or _read_property(adb, other_kind) != other:
                raise ValueError('Cấu hình animation đã đổi trong lúc chuẩn bị khôi phục.')
            changed = True
            _select(adb, kind, previous, cancel)
            _check(cancel)
            if _read_property(adb, other_kind) != other:
                raise ValueError('Animation còn lại đã đổi trong lúc xác minh khôi phục.')
            report.update(status='restored', restored_verified=True, persistent_property_file_verified=True,
                          persistent_property_binding_verified=True, other_animation_unchanged=True,
                          operation_report=str(report_path))
            _atomic_json(report_path, report)
            if receipt:
                receipt.update(status='restored', restored_verified=True, restore_report=str(report_path))
                _atomic_json(directory / 'installation.json', receipt)
        except BaseException as exc:
            report.update(status='failed', restored_verified=False, error=str(exc))
            if changed:
                _rollback(adb, kind, previous, current, report, report_path)
            else:
                _atomic_json(report_path, report)
            raise
        emit('animation_restored', 'Đã khôi phục lựa chọn animation trước đó; các gói ZIP được giữ để phục hồi.')
        return report
