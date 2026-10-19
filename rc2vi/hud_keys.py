"""Per-user HUD signer. Only explicitly selected keystores may be imported.

Private keys remain in password-encrypted keystores; passwords use Windows DPAPI
with current-user scope. No credential is bundled or exposed in object reprs.
"""
from contextlib import contextmanager
import ctypes
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import sys
import time
import uuid

from .hud_tools import HudTools, check_cancel, load_json, sha256_file
from .hud_backup import make_private


@dataclass(frozen=True)
class SigningKey:
    keyfile: Path
    alias: str
    password: str = field(repr=False)
    certificate_sha256: str


def _dpapi(value: bytes, decrypt: bool) -> bytes:
    if os.name != 'nt' or not isinstance(value, bytes) or not value:
        raise RuntimeError('Windows DPAPI is required for HUD signing credentials.')

    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_uint32), ('data', ctypes.c_void_p)]

    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                         ctypes.POINTER(Blob)]
    function.restype = ctypes.c_int
    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.c_void_p))
    output = Blob()
    try:
        # CRYPTPROTECT_UI_FORBIDDEN; deliberately omit LOCAL_MACHINE.
        if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
            raise RuntimeError('Windows DPAPI could not protect or unlock HUD credentials.')
        return ctypes.string_at(output.data, output.size)
    finally:
        if output.data:
            ctypes.memset(output.data, 0, output.size)
            kernel.LocalFree(output.data)
        ctypes.memset(buffer, 0, len(value))


def protect(value: bytes) -> bytes:
    """Encrypt bytes using this Windows user's DPAPI identity, without prompts."""
    return _dpapi(value, False)


def unprotect(value: bytes) -> bytes:
    """Decrypt current-user DPAPI bytes, failing closed for corrupt/foreign data."""
    return _dpapi(value, True)


def _validate_input(alias: str, password: str) -> None:
    if not isinstance(alias, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', alias):
        raise ValueError('Invalid HUD signing alias.')
    if not isinstance(password, str) or not password or any(c in password for c in '\0\r\n'):
        raise ValueError('Invalid HUD signing password.')


def _guard(path: Path) -> None:
    for item in (path, *path.parents):
        try:
            metadata = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, 'st_file_attributes', 0) & 0x400:
            raise ValueError('HUD signing paths must not contain links or reparse points.')


def _user_work() -> Path:
    root = os.environ.get('LOCALAPPDATA')
    if not root:
        raise RuntimeError('A per-user Windows LOCALAPPDATA directory is required.')
    return Path(root) / 'RC2Vietnamese'


class HudKeyStore:
    """Generate/reuse a local RSA2048/P12 signer; imports require explicit paths.

    ``ensure`` creates a signer only when no identity exists. ``load`` never
    creates one. ``import_existing`` atomically replaces the selected identity
    after checking its certificate; older key files are retained for recovery.
    """

    def __init__(self, tools: HudTools, root: Path | None = None):
        self.tools = tools
        self.root = Path(root) if root is not None else _user_work() / 'hud-signing'
        self.cancel = getattr(tools, 'cancel', None)

    def _file(self, name: str) -> Path:
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
            raise ValueError('Invalid HUD signing identity path.')
        path = self.root / name
        _guard(path)
        return path

    def _private_file(self, path: Path) -> None:
        _guard(path)
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError('HUD signing storage must contain only regular files with one link.')
        make_private(path)

    def _repair_files(self) -> None:
        # ACL metadata only: retained older keys also need the same protection.
        # The cross-process lock keeps this walk away from in-progress publishes.
        for path in self.root.iterdir():
            check_cancel(self.cancel)
            self._private_file(self._file(path.name))

    @contextmanager
    def _locked(self):
        _guard(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        # New files inherit only Owner/System while their explicit protected
        # DACL is applied, never the application's broader parent permissions.
        make_private(self.root, directory=True)
        # Lock one byte across threads/processes; never truncate an existing lock.
        import msvcrt
        lock_path = self._file('signer.lock')
        if lock_path.exists():
            self._private_file(lock_path)
        with lock_path.open('a+b', buffering=0) as lock:
            self._private_file(lock_path)
            while True:
                check_cancel(self.cancel)
                try:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.1)
            try:
                # Windows permits locking byte zero past EOF. Acquire it
                # before inspecting/initializing an empty file so competing
                # handles cannot flush bootstrap writes over a held lock.
                # Unbuffered I/O also leaves no writes pending at unlock/close.
                lock.seek(0, 2)
                if lock.tell() == 0:
                    lock.write(b'\0')
                    lock.flush()
                self._repair_files()
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

    def _load(self) -> SigningKey:
        metadata = self._file('signer.json')
        if not metadata.is_file():
            raise ValueError('No local HUD signing identity exists.')
        value = load_json(metadata)
        required = {'schema', 'keyfile', 'password_file', 'alias', 'key_sha256', 'certificate_sha256'}
        if set(value) != required or type(value['schema']) is not int or value['schema'] != 1:
            raise ValueError('Invalid HUD signing identity metadata.')
        keyfile = self._file(value['keyfile'])
        password_file = self._file(value['password_file'])
        if sha256_file(keyfile, self.cancel) != value['key_sha256']:
            raise ValueError('Local HUD signing key was changed.')
        try:
            password = unprotect(password_file.read_bytes()).decode('utf-8')
        except (UnicodeError, OSError, RuntimeError):
            raise RuntimeError('DPAPI could not unlock the local HUD signer.') from None
        _validate_input(value['alias'], password)
        certificate = self.tools.keycert(keyfile, value['alias'], password)
        if certificate != value['certificate_sha256'] or not re.fullmatch(r'[0-9a-f]{64}', certificate):
            raise ValueError('Local HUD signer certificate was changed.')
        if sha256_file(keyfile, self.cancel) != value['key_sha256']:
            raise ValueError('Local HUD signing key changed during certificate inspection.')
        return SigningKey(keyfile, value['alias'], password, certificate)

    def load(self) -> SigningKey:
        with self._locked():
            return self._load()

    def _publish(self, keyfile: Path, alias: str, password: str) -> SigningKey:
        self._private_file(keyfile)
        certificate = self.tools.keycert(keyfile, alias, password)
        if not re.fullmatch(r'[0-9a-f]{64}', certificate):
            raise ValueError('Invalid HUD signer certificate digest.')
        encrypted = protect(password.encode('utf-8'))
        password_file = self._file(keyfile.stem + '.dpapi')
        metadata = self._file('signer-' + uuid.uuid4().hex + '.json')
        try:
            with password_file.open('xb') as output:
                self._private_file(password_file)
                output.write(encrypted)
            value = {'schema': 1, 'keyfile': keyfile.name, 'password_file': password_file.name,
                     'alias': alias, 'key_sha256': sha256_file(keyfile, self.cancel),
                     'certificate_sha256': certificate}
            with metadata.open('x', encoding='utf-8') as output:
                self._private_file(metadata)
                json.dump(value, output, sort_keys=True)
            check_cancel(self.cancel)
            # Same-directory atomic rename retains this already protected DACL.
            metadata.replace(self._file('signer.json'))
        except BaseException:
            metadata.unlink(missing_ok=True)
            password_file.unlink(missing_ok=True)
            raise
        return SigningKey(keyfile, alias, password, certificate)

    def ensure(self) -> SigningKey:
        with self._locked():
            if self._file('signer.json').exists():
                return self._load()
            password = secrets.token_urlsafe(32)
            keyfile = self._file('hud-' + uuid.uuid4().hex + '.p12')
            try:
                self.tools.generate_key(keyfile, 'hud', password)
                return self._publish(keyfile, 'hud', password)
            except BaseException:
                keyfile.unlink(missing_ok=True)
                raise

    def import_existing(self, keyfile: Path, alias: str, password: str) -> SigningKey:
        _validate_input(alias, password)
        source = Path(keyfile)
        _guard(source)
        if not source.is_file():
            raise ValueError('The explicitly selected HUD key file is missing.')
        with self._locked():
            # Certificate inspection happens before changing the current identity.
            self.tools.keycert(source, alias, password)
            target = self._file('hud-' + uuid.uuid4().hex + '.keystore')
            try:
                before = sha256_file(source, self.cancel)
                with source.open('rb') as input_file, target.open('xb') as output_file:
                    self._private_file(target)
                    shutil.copyfileobj(input_file, output_file, 1024 * 1024)
                if sha256_file(target, self.cancel) != before:
                    raise ValueError('Selected HUD signing key changed while importing.')
                return self._publish(target, alias, password)
            except BaseException:
                target.unlink(missing_ok=True)
                raise


def _default_store() -> HudKeyStore:
    bundle = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    return HudKeyStore(HudTools(bundle / 'assets', _user_work()))


def import_existing(keyfile: Path, alias: str, password: str) -> SigningKey:
    """Migrate ONLY the user-selected signer; never search developer key folders."""
    return _default_store().import_existing(Path(keyfile), alias, password)
