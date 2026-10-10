"""Offline, pinned HUD toolchain and owned cancellable process execution.

HudTool's ``verify APK`` mode must select the SDK30 signer and print only its
certificate SHA256. ``keycert KEY ALIAS`` has the same stdout contract. Signing
and certificate inspection read HUD_SIGN_PASS from their process environment.
"""

from collections.abc import Callable, Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import threading
from typing import BinaryIO
import zipfile


Cancel = threading.Event | Callable[[], bool] | None
_CHUNK_SIZE = 1024 * 1024
_POLL_SECONDS = 0.1
_HEX64 = re.compile(r'[0-9a-fA-F]{64}', re.ASCII)
_REPARSE_POINT = 0x400
_UNSAFE_ENVIRONMENT = frozenset({
    'HUD_SIGN_PASS', 'JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS', 'CLASSPATH',
})
_REQUIRED_FILES = frozenset({
    'java/bin/java.exe', 'java/bin/keytool.exe', 'lib/apktool.jar',
    'lib/apksigner.jar', 'lib/hud-tool.jar', 'bin/zipalign.exe',
})
_RESERVED_NAMES = frozenset({
    'CON', 'PRN', 'AUX', 'NUL', 'CLOCK$', 'CONIN$', 'CONOUT$',
    *(f'{prefix}{number}' for prefix in ('COM', 'LPT')
      for number in '123456789\u00b9\u00b2\u00b3'),
})


LEGACY_HUD_PAYLOADS = frozenset({
    'a18ca3ba902e4856fd63c3dcb0bc5a64cd760bc369d65316896a61a2ddd56312',
    '0f410e39523cddee1c418855c635fae4f9d703cc6b8b4039a393dc899e148887',
    '962195af620c27f9d9739e962d440d60d436ca0ea1d2a608060319090b25f16d',
    '2afba062800f8820205b140c4aff4ca8079716e148f2d67d2eee2557796fccf3',
    '411bf90846b16f2385d1753f8da5a62fc6521983af69b39fe46a40404ffd0348',
    'da67b4887462f68ff932d7c9fb6b2175d91f441235d18d2617d0c9896ed3e60e',
    '78c0a4b7d932257793ab35487268b2fed204a19fec8addc3a701d357447480ef',
    '26a190cec7fe27351260c3e6b06f616f1f75c7413295071305d17222b50fd717',
    'ba7090e066f37d34555f80bdcbb8c8791e277fdae57c447b87d1ec80b95eae4e',
    '1cc26ac38e58ac18c8b0489012c762c3c120b8184e392b35ac777d464851c134',
    'c76678fd0337960775dc29315d68ea0c3b69581b093ab8d07139d9197c46e6c6',
    'e725691fe93614549267e4d00622931d5a88bb4ca0afb50760735f96b38f6c7d',
    '1fd0986b7490bb0aec92082835f783b85f7d2ec39c502ada94fad96f003962ec',
    'd2143abf12b9efd498e5edef248bc7e3355ce816e3de3af45408c2bf0d1afb90',
    '9d1d70dedc9ae0ae34117722f5ffbdcf2798d3b519f57331c911be268db778b1',
    '7a3542689cada6d8a903109bdaa85b87b411096dc3b2d4991c01033009edc4c6',
})


class HudCancelled(RuntimeError):
    """The caller canceled local HUD work."""


def check_cancel(cancel: Cancel) -> None:
    if cancel is None:
        return
    if isinstance(cancel, threading.Event):
        canceled = cancel.is_set()
    elif callable(cancel):
        canceled = cancel()
    else:
        raise TypeError('Cancellation must be an Event or callable.')
    if canceled:
        raise HudCancelled('HUD operation canceled.')


def _stream_digest(stream: BinaryIO, cancel: Cancel) -> str:
    result = hashlib.sha256()
    while True:
        check_cancel(cancel)
        chunk = stream.read(_CHUNK_SIZE)
        if not chunk:
            break
        result.update(chunk)
    check_cancel(cancel)
    return result.hexdigest()


def sha256_file(path: Path, cancel: Cancel = None) -> str:
    """Hash incrementally, including cancellation checks between reads."""
    check_cancel(cancel)
    with Path(path).open('rb') as stream:
        return _stream_digest(stream, cancel)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key.')
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError('Invalid JSON constant.')


def _json_object(data: bytes) -> dict:
    try:
        result = json.loads(data, object_pairs_hook=_unique_object,
                            parse_constant=_invalid_constant)
    except (ValueError, UnicodeError):
        raise ValueError('Invalid JSON manifest.') from None
    if not isinstance(result, dict):
        raise ValueError('JSON manifest must be an object.')
    return result


def load_json(path: Path) -> dict:
    """Read an object, rejecting duplicate keys at every nesting level."""
    return _json_object(Path(path).read_bytes())


def _hex_digest(value: object) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise ValueError('Expected a SHA256 digest containing only 64 hex digits.')
    return value.lower()


def _certificate_digest(output: str) -> str:
    # Java println may add one platform line terminator. Preserve all other
    # whitespace so diagnostics, multiple lines and padded digests fail closed.
    if output.endswith('\r\n'):
        output = output[:-2]
    elif output.endswith('\n'):
        output = output[:-1]
    return _hex_digest(output)


def _close_pipes(process: subprocess.Popen) -> None:
    for pipe in (process.stdout, process.stderr):
        if pipe is not None:
            try:
                pipe.close()
            except OSError:
                pass


def _tool_environment(password: str | None = None) -> dict[str, str]:
    environment = {name: value for name, value in os.environ.items()
                   if name.upper() not in _UNSAFE_ENVIRONMENT}
    if password is not None:
        environment['HUD_SIGN_PASS'] = password
    return environment


def _stop_process(process: subprocess.Popen) -> None:
    """Kill only our child, drain its pipes, and reap even after an I/O error."""
    try:
        if process.poll() is None:
            process.kill()
    except OSError:
        pass
    try:
        process.communicate()
    except Exception:
        try:
            process.wait()
        except OSError:
            pass


def run_process(args: Sequence[str | os.PathLike], *, cancel: Cancel = None,
                env: Mapping[str, str] | None = None, sensitive: bool = False) -> str:
    """Run an owned child with drained pipes and no shell or inherited stdin.

    All errors are redacted, including ordinary calls; sensitive calls receive
    the same guarantee. Successful stdout is returned as untrimmed UTF-8 text.
    """
    process = None
    try:
        check_cancel(cancel)
        if isinstance(args, (str, bytes, os.PathLike)):
            raise TypeError('Process arguments must be a sequence.')
        argv = [os.fspath(value) for value in args]
        process = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=False,
            env=None if env is None else dict(env),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        while True:
            check_cancel(cancel)
            try:
                stdout, _ = process.communicate(timeout=_POLL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                continue
        check_cancel(cancel)
        if process.returncode != 0:
            raise RuntimeError('HUD tool execution failed.')
        return stdout.decode('utf-8', errors='replace')
    except BaseException as error:
        if process is not None:
            _stop_process(process)
        if isinstance(error, (HudCancelled, KeyboardInterrupt, SystemExit)):
            raise
        # Suppress subprocess exceptions, which can contain passwords, command
        # arguments, paths, environment data or captured stdout/stderr.
        raise RuntimeError('HUD tool execution failed.') from None
    finally:
        if process is not None:
            _close_pipes(process)


def _safe_relative(name: str) -> str:
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('Unsafe toolchain path.')
    for part in name.split('/'):
        if (not part or part in ('.', '..') or part.endswith(('.', ' '))
                or any(ord(char) < 32 or char in '<>:"|?*' for char in part)
                or part.split('.')[0].rstrip(' ').upper() in _RESERVED_NAMES):
            raise ValueError('Unsafe toolchain path.')
    return name


def _inventory(raw: object) -> tuple[dict[str, str], set[str]]:
    if not isinstance(raw, dict) or not raw:
        raise ValueError('Invalid toolchain file inventory.')
    files = {_safe_relative(name): _hex_digest(value) for name, value in raw.items()}
    directories = {parent.as_posix() for name in files for parent in
                   Path(name).parents if parent != Path('.')}
    if files.keys() & directories:
        raise ValueError('Toolchain file is also a directory.')
    aliases = {}
    for name in (*files, *directories):
        folded = name.casefold()
        if folded in aliases and aliases[folded] != name:
            raise ValueError('Casefold collision in toolchain paths.')
        aliases[folded] = name
    if not _REQUIRED_FILES <= files.keys():
        raise ValueError('Required bundled toolchain files are missing.')
    return files, directories


def _archive_members(archive: zipfile.ZipFile, files: dict[str, str],
                     directories: set[str], cancel: Cancel) -> list[zipfile.ZipInfo]:
    seen = set()
    found = set()
    members = []
    for info in archive.infolist():
        check_cancel(cancel)
        if info.orig_filename != info.filename:
            raise ValueError('Truncated toolchain ZIP path.')
        name = _safe_relative(info.filename[:-1] if info.is_dir() else info.filename)
        folded = name.casefold()
        if folded in seen:
            raise ValueError('Duplicate or casefold toolchain ZIP entry.')
        seen.add(folded)
        mode = stat.S_IFMT(info.external_attr >> 16)
        expected_mode = stat.S_IFDIR if info.is_dir() else stat.S_IFREG
        if (mode not in (0, expected_mode) or info.flag_bits & 1
                or info.external_attr & _REPARSE_POINT):
            raise ValueError('Unsafe or encrypted toolchain ZIP entry.')
        if info.is_dir():
            if name not in directories:
                raise ValueError('Unlisted toolchain ZIP directory.')
        else:
            if name not in files:
                raise ValueError('Unlisted toolchain ZIP file.')
            found.add(name)
            members.append(info)
    if found != files.keys():
        raise ValueError('Toolchain ZIP inventory does not match manifest.')
    return members


def _physical_stat(path: Path):
    value = path.lstat()
    if stat.S_ISLNK(value.st_mode) or getattr(value, 'st_file_attributes', 0) & _REPARSE_POINT:
        raise ValueError('Toolchain cache contains a link or reparse point.')
    return value


def _check_ancestors(path: Path) -> None:
    for ancestor in reversed((path, *path.parents)):
        try:
            value = _physical_stat(ancestor)
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(value.st_mode):
            raise ValueError('Toolchain cache parent is not a directory.')


def _exists(path: Path) -> bool:
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def _verify_cache(root: Path, files: dict[str, str], directories: set[str],
                  cancel: Cancel) -> None:
    if not stat.S_ISDIR(_physical_stat(root).st_mode):
        raise ValueError('Toolchain cache is not a directory.')
    found_files, found_dirs = set(), set()
    pending = [root]
    while pending:
        check_cancel(cancel)
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                check_cancel(cancel)
                path = Path(entry.path)
                name = path.relative_to(root).as_posix()
                value = _physical_stat(path)
                if stat.S_ISDIR(value.st_mode):
                    if name not in directories:
                        raise ValueError('Unlisted toolchain cache directory.')
                    found_dirs.add(name)
                    pending.append(path)
                elif stat.S_ISREG(value.st_mode):
                    if name not in files or sha256_file(path, cancel) != files[name]:
                        raise ValueError('Toolchain cache file failed integrity verification.')
                    found_files.add(name)
                else:
                    raise ValueError('Non-regular file in toolchain cache.')
    if found_files != files.keys() or found_dirs != directories:
        raise ValueError('Toolchain cache inventory does not match manifest.')
    check_cancel(cancel)


def _extract(archive: zipfile.ZipFile, members: list[zipfile.ZipInfo], stage: Path,
             files: dict[str, str], cancel: Cancel) -> None:
    for info in members:
        check_cancel(cancel)
        output = stage.joinpath(*info.filename.split('/'))
        output.parent.mkdir(parents=True, exist_ok=True)
        result = hashlib.sha256()
        with archive.open(info) as source, output.open('xb') as destination:
            while True:
                check_cancel(cancel)
                chunk = source.read(_CHUNK_SIZE)
                if not chunk:
                    break
                destination.write(chunk)
                result.update(chunk)
        if result.hexdigest() != files[info.filename]:
            raise ValueError('Bundled toolchain file failed integrity verification.')


def _publish_cache(archive: zipfile.ZipFile, members: list[zipfile.ZipInfo],
                   root: Path, files: dict[str, str], directories: set[str],
                   cancel: Cancel) -> None:
    # Only this invocation's uniquely named staging directory is removed.
    stage = Path(tempfile.mkdtemp(prefix=f'.{root.name}-', dir=root.parent))
    try:
        _extract(archive, members, stage, files, cancel)
        _verify_cache(stage, files, directories, cancel)
        check_cancel(cancel)
        try:
            stage.rename(root)
        except OSError:
            if not _exists(root):
                raise
            # Another builder may have won publication. Never trust its bytes.
            _verify_cache(root, files, directories, cancel)
        _verify_cache(root, files, directories, cancel)
    finally:
        if _exists(stage):
            value = stage.lstat()
            if stat.S_ISLNK(value.st_mode):
                stage.unlink()
            elif getattr(value, 'st_file_attributes', 0) & _REPARSE_POINT:
                stage.rmdir()
            else:
                shutil.rmtree(stage)


class HudTools:
    def __init__(self, assets: Path, work: Path, cancel: Cancel = None):
        self.assets = Path(assets)
        self.work = Path(work)
        self.cancel = cancel
        self.archive_sha256 = ''
        self.manifest_sha256 = ''

    def prepare(self) -> Path:
        """Verify bundle and all cached bytes each time, or publish a new cache."""
        self.archive_sha256 = ''
        self.manifest_sha256 = ''
        check_cancel(self.cancel)
        hud = self.assets / 'hud'
        manifest_bytes = (hud / 'toolchain.json').read_bytes()
        manifest = _json_object(manifest_bytes)
        if (set(manifest) != {'schema', 'archive_sha256', 'files'}
                or type(manifest['schema']) is not int or manifest['schema'] != 1):
            raise ValueError('Unsupported toolchain manifest.')
        archive_hash = _hex_digest(manifest['archive_sha256'])
        files, directories = _inventory(manifest['files'])
        cache_parent = self.work.absolute() / 'toolchain'
        _check_ancestors(cache_parent)
        cache_parent.mkdir(parents=True, exist_ok=True)
        _check_ancestors(cache_parent)
        root = cache_parent / archive_hash
        try:
            # Hash and extract the same open archive, rather than reopen by path.
            with (hud / 'toolchain.zip').open('rb') as stream:
                if _stream_digest(stream, self.cancel) != archive_hash:
                    raise ValueError('Toolchain archive failed integrity verification.')
                stream.seek(0)
                with zipfile.ZipFile(stream) as archive:
                    members = _archive_members(archive, files, directories, self.cancel)
                    if _exists(root):
                        _verify_cache(root, files, directories, self.cancel)
                    else:
                        _publish_cache(archive, members, root, files, directories, self.cancel)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as error:
            if isinstance(error, HudCancelled):
                raise
            raise ValueError('Invalid bundled toolchain archive.') from None
        check_cancel(self.cancel)
        self.archive_sha256 = archive_hash
        self.manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        return root

    def payload(self) -> bytes:
        check_cancel(self.cancel)
        hud = self.assets / 'hud'
        manifest = load_json(hud / 'payload.json')
        required = {'schema', 'sha256'}
        allowed = required | {'restore_owner_sha256'}
        if (not required <= manifest.keys() or not manifest.keys() <= allowed
                or type(manifest['schema']) is not int or manifest['schema'] != 1):
            raise ValueError('Unsupported HUD payload manifest.')
        expected = _hex_digest(manifest['sha256'])
        if 'restore_owner_sha256' in manifest:
            _hex_digest(manifest['restore_owner_sha256'])
        chunks = []
        with (hud / 'classes23.dex').open('rb') as stream:
            while True:
                check_cancel(self.cancel)
                chunk = stream.read(_CHUNK_SIZE)
                if not chunk:
                    break
                chunks.append(chunk)
        result = b''.join(chunks)
        if hashlib.sha256(result).hexdigest() != expected:
            raise ValueError('HUD payload failed integrity verification.')
        check_cancel(self.cancel)
        return result

    def historical_payload(self, expected: str) -> bytes:
        """Recognize a pinned past helper for update verification only; never select it for a new build."""
        check_cancel(self.cancel)
        expected = _hex_digest(expected)
        if expected not in LEGACY_HUD_PAYLOADS:
            raise ValueError('Historical HUD payload is not explicitly supported.')
        path = self.assets / 'hud/history' / (expected + '.dex')
        for part in (path, *path.parents):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & _REPARSE_POINT:
                raise ValueError('Historical HUD payload path contains a link.')
        if not path.is_file() or path.stat().st_size > 1048576:
            raise ValueError('Historical HUD payload size or type is invalid.')
        value = path.read_bytes()
        if hashlib.sha256(value).hexdigest() != expected:
            raise ValueError('Historical HUD payload failed integrity verification.')
        check_cancel(self.cancel)
        return value

    def _java(self, mode: str, *args: str | os.PathLike,
              password: str | None = None) -> str:
        root = self.prepare()
        classpath = ';'.join(str(root / name) for name in (
            'lib/hud-tool.jar', 'lib/apktool.jar', 'lib/apksigner.jar'))
        environment = _tool_environment(password)
        return run_process(
            [str(root / 'java/bin/java.exe'), '-cp', classpath, 'HudTool', mode,
             *(os.fspath(arg) for arg in args)],
            cancel=self.cancel, env=environment, sensitive=password is not None,
        )

    def patch(self, inputDEX: Path, outputDEX: Path, workdir: Path) -> None:
        self._java('patch', inputDEX, outputDEX, workdir)

    def _zipalign(self, *args: str | os.PathLike) -> None:
        root = self.prepare()
        run_process([str(root / 'bin/zipalign.exe'), *(os.fspath(arg) for arg in args)],
                    cancel=self.cancel, env=_tool_environment())

    def align(self, input: Path, out: Path) -> None:
        self._zipalign('-f', '-p', '4', input, out)
        self._zipalign('-c', '-p', '4', out)

    def sign(self, input: Path, out: Path, keyfile: Path, alias: str, password: str) -> None:
        self._java('sign', input, out, keyfile, alias, password=password)

    def verify(self, input: Path) -> str:
        """Return only the SHA256 of HudTool's selected SDK30 certificate."""
        return _certificate_digest(self._java('verify', input))

    def keycert(self, keyfile: Path, alias: str, password: str) -> str:
        return _certificate_digest(self._java('keycert', keyfile, alias, password=password))

    def generate_key(self, keyfile: Path, alias: str, password: str) -> None:
        root = self.prepare()
        environment = _tool_environment(password)
        run_process([
            str(root / 'java/bin/keytool.exe'), '-genkeypair', '-keystore', str(keyfile),
            '-alias', alias, '-keyalg', 'RSA', '-keysize', '2048', '-validity', '36500',
            '-storetype', 'PKCS12', '-storepass:env', 'HUD_SIGN_PASS',
            '-keypass:env', 'HUD_SIGN_PASS', '-dname', 'CN=RC2 Vietnamese HUD', '-noprompt',
        ], cancel=self.cancel, env=environment, sensitive=True)
