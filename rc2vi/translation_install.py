"""Transactional resource-only deployment; callers supply an already selected transport.

``known_overlays(root)`` lists recognized legacy/adaptive packages and enabled flags.
``disable`` switches off all recognized legacy/adaptive overlays, without a Fly lock.
Rollback ignores cancellation/source updates, but never crosses a device identity.
``safe()`` must check foreground safety only, independently of cancellation.
"""
from collections.abc import Callable
import copy
import hashlib
from pathlib import Path
import re
import shlex
import stat
import tempfile
import uuid

from .core import approve_idmap, validate_package_path
from .phone_resources import approve_phone_idmap


ADAPTIVE = re.compile(r'local\.dji\.fly\.vi\.auto\.r[0-9a-f]{16}c[0-9a-f]{8}s[0-9a-f]{8}')
LEGACY = frozenset({'local.dji.fly.vietnamese', 'local.dji.fly.phone.vietnamese'})
HEX = re.compile(r'[0-9a-f]{64}')
MAX_APK = 1536 * 1024 * 1024
TARGET = 'dji.go.v5'


class _PinnedRoot:
    """Freeze native ADB dispatch; fake transports may implement bind(serial)."""
    def __init__(self, root, identity):
        adb = getattr(root, 'adb', root)
        self.selection, self.physical = adb, identity[1]
        bind = getattr(adb, 'bind', None)
        self.adb = (bind(identity[0]) if callable(bind) else copy.copy(adb)
                    if hasattr(adb, 'binary') and hasattr(adb, 'port') else adb)
        if root is adb:
            self.root = self.adb
        else:
            from .phone_overlay import RootShell
            self.root = RootShell(self.adb)

    def shell(self, command, **kwargs):
        return self.root.shell('test "$(getprop ro.serialno)" = ' + shlex.quote(self.physical)
                               + ' && ' + command, **kwargs)


def _run(root, command, timeout=90):
    lines = root.shell(command + ' && echo TRANSLATION_OK', timeout=timeout).splitlines()
    if not lines or lines[-1] != 'TRANSLATION_OK':
        raise RuntimeError('Lệnh tài nguyên chưa hoàn thành: ' + command.split()[0])
    return '\n'.join(lines[:-1])


def _path(root, package, required=True):
    output = _run(root, '(pm path ' + package + ' || true)')
    if not output and not required:
        return None
    if len(output.splitlines()) != 1 or not output.startswith('package:'):
        raise ValueError('Cần một APK nguyên khối: ' + package)
    path = validate_package_path(output[8:])
    if len(path) > 240 or '//' in path or '.' in path.split('/'):
        raise ValueError('Đường dẫn APK không hợp lệ.')
    return path


def _hash(root, path):
    parts = _run(root, 'sha256sum ' + shlex.quote(path)).split()
    if len(parts) != 2 or not HEX.fullmatch(parts[0]) or parts[1] != path:
        raise ValueError('SHA-256 từ thiết bị không hợp lệ.')
    return parts[0]


def _identity(root, recovery=False):
    adb = getattr(root, 'adb', root)
    selection = adb if recovery else getattr(root, 'selection', adb)
    selected = getattr(selection, 'serial', None)
    physical = _run(root, 'getprop ro.serialno')
    sdk = _run(root, 'getprop ro.build.version.sdk')
    if (not isinstance(selected, str) or not selected or len(selected) > 256
            or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', physical)
            or physical.lower() in {'unknown', 'null', 'none'} or not re.fullmatch(r'\d{1,3}', sdk)
            or selected != getattr(selection, 'serial', None)):
        raise ValueError('Không xác định được serial/SDK thiết bị đã chọn.')
    return selected, physical, int(sdk)


def _snapshot(root):
    identity = _identity(root)
    path = _path(root, TARGET)
    info = _run(root, 'dumpsys package ' + TARGET)
    versions = re.findall(r'\bversionName=([^\s]+)', info)
    codes = re.findall(r'\bversionCode=(\d+)(?=\s|$)', info)
    size = _run(root, 'stat -c %s ' + shlex.quote(path))
    if (len(versions) != 1 or len(codes) != 1 or not size.isdecimal() or len(size) > 12
            or not 0 < int(size) <= MAX_APK):
        raise ValueError('Phiên bản/kích thước APK DJI Fly không hợp lệ.')
    version, code = versions.pop(), codes.pop()
    if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+()-]{0,127}', version)
            or len(code) > 10 or not 0 < int(code) <= 2147483647):
        raise ValueError('Phiên bản DJI Fly không hợp lệ.')
    result = dict(identity=identity, path=path, version=version, version_code=int(code),
                  digest=_hash(root, path), size=int(size))
    if _identity(root) != identity:
        raise ValueError('Thiết bị đã thay đổi trong lúc đọc APK.')
    return result


def known_overlays(root) -> dict[str, bool]:
    """Recognize only exact package names in the target-specific user-0 listing."""
    output = _run(root, 'cmd overlay list --user 0 ' + TARGET)
    if len(output) > 200000:
        raise ValueError('Danh sách overlay vượt giới hạn.')
    result = {}
    for line in output.splitlines():
        if not line.strip() or line.strip() == TARGET:
            continue
        match = re.fullmatch(r'(\[x\]|\[ \]|---) (\S+)', line.strip())
        if not match:
            raise ValueError('Không đọc được trạng thái overlay.')
        package = match[2]
        if package in LEGACY or ADAPTIVE.fullmatch(package):
            if package in result:
                raise ValueError('Overlay trùng trong danh sách.')
            result[package] = match[1] == '[x]'
    return result


def _local(path):
    if not isinstance(path, Path) or not path.is_absolute() or '..' in path.parts:
        raise ValueError('Đường dẫn APK cục bộ không hợp lệ.')
    for part in (path, *path.parents):
        try:
            metadata = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Không chấp nhận liên kết/điểm chuyển hướng cục bộ.')
    return path


class AdaptiveTranslation:
    def __init__(self, assets: Path, work: Path, emit, cancel=None, builder=None):
        self.assets, self.work = Path(assets), Path(work).absolute()
        self.emit, self.cancel, self.builder = emit, cancel, builder

    def _cancel(self):
        if self.cancel is not None and (self.cancel.is_set() if hasattr(self.cancel, 'is_set') else self.cancel()):
            raise RuntimeError('Đã hủy thao tác bản dịch.')

    def _digest(self, path, maximum=MAX_APK):
        path = _local(path)
        if not path.is_file() or not 0 < path.stat().st_size <= maximum:
            raise ValueError('Kích thước/tệp cục bộ không hợp lệ.')
        value = hashlib.sha256()
        with path.open('rb') as stream:
            while True:
                self._cancel()
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    return value.hexdigest()
                value.update(chunk)

    def _artifact(self, value, before):
        if not isinstance(value, dict):
            raise ValueError('Builder không trả về artifact hợp lệ.')
        sdk = before['identity'][2]
        target_name = 'DJIFlyLocalTranslation' if sdk == 30 else 'DJIFlyPhoneTranslation'
        if (('profile_sdk' in value and (type(value['profile_sdk']) is not int or value['profile_sdk'] != sdk))
                or ('target_name' in value and value['target_name'] != target_name)):
            raise ValueError('Profile SDK/targetName của artifact không khớp thiết bị.')
        for field, pattern in (('package', ADAPTIVE), ('digest', HEX), ('source_digest', HEX)):
            if not isinstance(value.get(field), str) or not pattern.fullmatch(value[field]):
                raise ValueError('Artifact không hợp lệ: ' + field)
        apk = value.get('apk')
        if (not isinstance(apk, Path) or apk.suffix != '.apk' or not apk.is_relative_to(self.work)
                or value['source_digest'] != before['digest'] or value.get('version') != before['version']
                or not value['package'].startswith('local.dji.fly.vi.auto.r' + before['digest'][:16])
                or type(value.get('version_code')) is not int or value['version_code'] != before['version_code']):
            raise ValueError('Artifact không thuộc APK nguồn/thư mục build.')
        report, samples = value.get('report'), value.get('samples')
        if (not isinstance(report, dict) or any(type(report.get(k)) is not int or not 0 <= report[k] <= 1000000
                for k in ('matched', 'skipped', 'total')) or report['matched'] <= 0
                or report['matched'] + report['skipped'] != report['total']):
            raise ValueError('Thống kê bản dịch không hợp lệ.')
        if any(k in report for k in ('target_total', 'target_untranslated')) and (
                any(type(report.get(k)) is not int or not 0 <= report[k] <= 1000000
                    for k in ('target_total', 'target_untranslated'))
                or report['target_total'] != report['matched'] + report['target_untranslated']):
            raise ValueError('Thống kê tài nguyên nguồn không hợp lệ.')
        if not isinstance(samples, list) or not 0 < len(samples) <= min(64, report['matched']):
            raise ValueError('Cần mẫu chuỗi để đọc lại bản dịch.')
        for sample in samples:
            if (not isinstance(sample, dict) or not isinstance(sample.get('name'), str)
                    or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', sample['name'])
                    or not isinstance(sample.get('value'), str) or not 0 < len(sample['value']) <= 4096
                    or any(ord(c) < 32 or c in '\x7f\u2028\u2029' for c in sample['value'])):
                raise ValueError('Mẫu đọc lại không phải chuỗi đơn hợp lệ.')
        if len({s['name'] for s in samples}) != len(samples) or self._digest(apk) != value['digest']:
            raise ValueError('Hash APK/mẫu đọc lại không hợp lệ.')
        return {**value, 'report': dict(report), 'samples': [dict(s) for s in samples]}

    def _guard(self, root, before, safe=None):
        self._cancel()
        if safe is not None:
            safe()
        if _snapshot(root) != before:
            raise ValueError('Thiết bị hoặc APK DJI Fly đã thay đổi; đã dừng.')
        self._cancel()

    def _readback(self, root, before, artifact):
        self._guard(root, before)
        if not known_overlays(root).get(artifact['package']):
            raise RuntimeError('Chưa bật được overlay bản dịch.')
        for sample in artifact['samples']:
            self._guard(root, before)
            text = _run(root, 'cmd overlay lookup --user 0 ' + TARGET + ' ' + TARGET + ':string/' + sample['name'])
            if text != sample['value']:
                raise RuntimeError('Đọc lại bản dịch không khớp: ' + sample['name'])
        self._guard(root, before)

    def _recover(self, root, identity, commands, safe=None):
        # Never consult cancellation or the changing Fly source during compensation.
        errors = []
        for command in commands:
            try:
                if safe is not None:
                    safe()
                if _identity(root, recovery=True) != identity:
                    raise ValueError('Thiết bị/serial đã thay đổi; không ghi phục hồi.')
                _run(root, command)
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise RuntimeError('Phục hồi chưa hoàn tất: ' + '; '.join(errors))

    def _remove_new(self, root, before, artifact, overlay, safe):
        """Remove only this attempt's initially absent RRO; never honor cancellation here."""
        safe()
        if _identity(root, recovery=True) != before['identity']:
            raise ValueError('Thiết bị/serial đã thay đổi; không gỡ gói mới.')
        current = _path(root, artifact['package'], required=False)
        if current is None:
            return
        if (current == before['path'] or (overlay is not None and current != overlay)
                or _hash(root, current) != artifact['digest']):
            raise ValueError('Đường dẫn/hash gói mới đã thay đổi; từ chối gỡ.')
        safe()
        if (_identity(root, recovery=True) != before['identity']
                or _path(root, artifact['package']) != current or _hash(root, current) != artifact['digest']):
            raise ValueError('Gói hoặc thiết bị đã thay đổi trước khi gỡ.')
        if _run(root, 'pm uninstall --user 0 ' + artifact['package']).splitlines()[-1:] != ['Success']:
            raise RuntimeError('Không gỡ được gói mới của phiên này.')
        if _path(root, artifact['package'], required=False) is not None:
            raise RuntimeError('Gói mới vẫn còn sau khi gỡ.')

    def apply(self, adb, root, sdk: int, safe: Callable[[], None]) -> dict:
        self._cancel()
        if type(sdk) is not int or sdk not in (30, 35) or getattr(root, 'adb', root) is not adb:
            raise ValueError('SDK/transport không được hỗ trợ.')
        before = _snapshot(root)
        if before['identity'][2] != sdk:
            raise ValueError('SDK thiết bị khác SDK đã chọn.')
        root = _PinnedRoot(root, before['identity'])
        adb = root.adb
        _local(self.work)
        self.work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='translation-' + uuid.uuid4().hex + '-', dir=self.work) as folder:
            local = Path(folder)
            source = local / 'source.apk'
            self._guard(root, before)
            adb.command('pull', before['path'], str(source), timeout=300)
            self._guard(root, before)
            if self._digest(source) != before['digest'] or source.stat().st_size != before['size']:
                raise ValueError('APK kéo về không khớp nguồn thiết bị.')
            if self.builder is None:
                from .translation_build import TranslationBuilder
                self.builder = TranslationBuilder(self.assets, self.work, self.emit, cancel=self.cancel, sdk=sdk)
            artifact = self._artifact(self.builder.build(source), before)
            self._guard(root, before)
            report = artifact['report']
            total, untranslated = report.get('target_total'), report.get('target_untranslated')
            counts = (f"{report['matched']}/{total} tài nguyên DJI Fly đã dịch; {untranslated} giữ nguyên."
                      if total is not None else f"{report['matched']}/{report['total']} khớp từ điển; {report['skipped']} bỏ qua.")
            self.emit('applying', 'Bản dịch: ' + counts)
            if (untranslated if total is not None else report['skipped']):
                self.emit('warning', 'Bản dịch một phần; câu không khớp giữ nguyên ngôn ngữ gốc.')
            result = self._deploy(adb, root, before, safe, artifact, local)
            return dict(result, message=result['message'] + ' ' + counts)

    def _deploy(self, adb, root, before, safe, artifact, local):
        package = artifact['package']
        overlay = _path(root, package, required=False)
        if overlay and _hash(root, overlay) != artifact['digest']:
            raise ValueError('Gói cùng tên có hash khác; không thay thế gói ngoài công cụ.')
        prior = known_overlays(root)
        if prior.get(package) and not any(v for p, v in prior.items() if p != package):
            self._readback(root, before, artifact)
            return {**artifact, 'status': 'already_enabled', 'message': 'Bản dịch đã bật và đọc lại thành công.'}
        remote = '/data/local/tmp/translation-' + uuid.uuid4().hex
        cache, original, changed, owned, retained = None, False, False, False, False
        owned_installed = False
        backup_hash = None

        def write(command, transactional=False, installing=False):
            nonlocal changed, owned_installed
            self._guard(root, before, safe)
            changed = changed or transactional
            owned_installed = owned_installed or installing  # Journal before uncertain dispatch.
            return _run(root, command)

        try:
            write('mkdir -m 755 ' + remote)
            owned = True
            write('chown shell:shell ' + remote + ' && restorecon ' + remote)
            if not overlay:
                self._guard(root, before, safe)
                if self._digest(artifact['apk']) != artifact['digest']:
                    raise ValueError('Artifact đã thay đổi trước khi push.')
                adb.command('push', str(artifact['apk']), remote + '/pack.apk', timeout=120)
                if _hash(root, remote + '/pack.apk') != artifact['digest']:
                    raise ValueError('Hash gói đã push không khớp.')
                if _path(root, package, required=False):
                    raise ValueError('Gói overlay đã xuất hiện trong lúc cài; đã dừng.')
                if write('pm install --user 0 ' + remote + '/pack.apk', installing=True).splitlines()[-1:] != ['Success']:
                    raise RuntimeError('Cài gói tài nguyên thất bại.')
                overlay = _path(root, package)
            if _hash(root, overlay) != artifact['digest']:
                raise ValueError('Hash gói dịch đã cài không khớp.')
            cache = '/data/resource-cache/' + overlay.lstrip('/').replace('/', '@') + '@idmap'
            write('idmap2 create --target-apk-path ' + before['path'] + ' --overlay-apk-path ' + overlay
                  + ' --idmap-path ' + remote + '/raw.idmap --policy public --ignore-overlayable')
            write('chmod 644 ' + remote + '/raw.idmap')
            self._guard(root, before)
            adb.command('pull', remote + '/raw.idmap', str(local / 'raw.idmap'), timeout=60)
            self._digest(local / 'raw.idmap', maximum=64 * 1024 * 1024)
            approve = approve_idmap if before['identity'][2] == 30 else approve_phone_idmap
            (local / 'approved.idmap').write_bytes(approve((local / 'raw.idmap').read_bytes(), before['path'], overlay))
            self._guard(root, before, safe)
            adb.command('push', str(local / 'approved.idmap'), remote + '/approved.idmap', timeout=60)
            if _hash(root, remote + '/approved.idmap') != self._digest(local / 'approved.idmap'):
                raise ValueError('Hash idmap đã push không khớp.')
            original = _run(root, 'if [ -f ' + cache + ' ]; then echo yes; fi') == 'yes'
            if original:
                backup_hash = _hash(root, cache)
                write('cp ' + cache + ' ' + remote + '/previous.idmap')
                if _hash(root, remote + '/previous.idmap') != backup_hash or _hash(root, cache) != backup_hash:
                    raise ValueError('Bản sao cache không khớp; chưa thay đổi overlay.')
            self._guard(root, before, safe)
            if known_overlays(root) != {**prior, package: prior.get(package, False)}:
                raise ValueError('Trạng thái overlay đã thay đổi trong lúc dựng cache.')
            for previous, enabled in prior.items():
                if enabled and previous != package:
                    write('cmd overlay disable --user 0 ' + previous, transactional=True)
            write('cp ' + remote + '/approved.idmap ' + cache + ' && chown root:system ' + cache
                  + ' && chmod 644 ' + cache + ' && restorecon ' + cache, transactional=True)
            write('cmd overlay enable --user 0 ' + package, transactional=True)
            self._readback(root, before, artifact)
            if known_overlays(root) != {**dict.fromkeys(prior, False), package: True}:
                raise RuntimeError('Trạng thái overlay sau bật không khớp.')
            self._guard(root, before)
            return {**artifact, 'status': 'enabled', 'message': 'Đã bật bản dịch thích ứng và kiểm tra tài nguyên.'}
        except Exception as failure:
            recovery_errors = []
            if changed:
                commands = ['cmd overlay disable --user 0 ' + package]
                commands += (['cp ' + remote + '/previous.idmap ' + cache + ' && chown root:system ' + cache
                              + ' && chmod 644 ' + cache + ' && restorecon ' + cache]
                             if original else ['rm -f ' + cache])
                commands += ['cmd overlay enable --user 0 ' + p for p, enabled in prior.items() if enabled]
                try:
                    self._recover(root, before['identity'], commands, safe)
                    if original and _hash(root, cache) != backup_hash:
                        raise RuntimeError('Hash cache phục hồi không khớp.')
                    if not original and _run(root, 'if [ -f ' + cache + ' ]; then echo yes; fi'):
                        raise RuntimeError('Chưa xóa được cache mới khi phục hồi.')
                    if known_overlays(root) != {**prior, package: prior.get(package, False)}:
                        raise RuntimeError('Không khôi phục được trạng thái overlay ban đầu.')
                except Exception as exc:
                    recovery_errors.append(str(exc))
            if owned_installed:
                try:
                    self._remove_new(root, before, artifact, overlay, safe)
                except Exception as exc:
                    recovery_errors.append(str(exc))
            if recovery_errors:
                retained = True
                self.emit('warning', 'Giữ gói/tệp phục hồi tại ' + remote)
                raise RuntimeError('Phục hồi chưa hoàn tất; giữ tài nguyên tại ' + remote
                                   + ' [TRANSLATION_RETAINED]: ' + '; '.join(recovery_errors)) from failure
            raise
        finally:
            if owned and not retained:
                try:
                    self._recover(root, before['identity'], ['rm -f ' + ' '.join(remote + '/' + name for name in
                                  ('pack.apk', 'raw.idmap', 'approved.idmap', 'previous.idmap')) + ' && rmdir ' + remote])
                except Exception:
                    self.emit('warning', 'Không dọn được thư mục tạm thuộc phiên này: ' + remote)

    def disable(self, root, safe: Callable[[], None]) -> dict:
        self._cancel()
        identity = _identity(root)
        root = _PinnedRoot(root, identity)
        prior = known_overlays(root)
        attempted = []
        try:
            for package, enabled in prior.items():
                if not enabled:
                    continue
                self._cancel()
                safe()
                if _identity(root) != identity:
                    raise ValueError('Thiết bị/serial đã thay đổi trước khi tắt bản dịch.')
                self._cancel()
                attempted.append(package)
                _run(root, 'cmd overlay disable --user 0 ' + package)
            self._cancel()
            if _identity(root) != identity or any(known_overlays(root).values()):
                raise RuntimeError('Chưa xác nhận được tất cả bản dịch đã tắt.')
        except Exception:
            self._recover(root, identity, ['cmd overlay enable --user 0 ' + p for p in attempted], safe)
            if _identity(root, recovery=True) != identity or known_overlays(root) != prior:
                raise RuntimeError('Phục hồi trạng thái bản dịch sau khi tắt chưa hoàn tất.')
            raise
        return {'status': 'disabled' if prior else 'absent', 'message': 'Đã tắt tất cả các bản dịch đã nhận diện.',
                'count': sum(prior.values())}
