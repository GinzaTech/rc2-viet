"""Offline pinned-stock EXE HUD pipeline and independently revalidated receipts."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import tempfile
import uuid
from zipfile import ZipFile

from .core import SUPPORTED_APK
from .hud_keys import HudKeyStore
from .hud_tools import HudTools, check_cancel, load_json, sha256_file
from scripts.hud_apk import repack_apk, validate_apk_change
from scripts.hud_manifest import add_hud_provider
from scripts.hud_signing_block import V2, block_entries, replace_v2_block


def _guard(path: Path) -> None:
    for item in (path, *path.parents):
        try:
            metadata = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, 'st_file_attributes', 0) & 0x400:
            raise ValueError('HUD build paths must not contain links or reparse points.')


def _write_json(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8') as output:
        json.dump(value, output, sort_keys=True)


class HudBuilder:
    """Build exact stock only. Successful results contain paths, public hashes only.

    ``verify(receipt)`` reproduces the bootstrap patch from the retained pinned
    source using the currently verified tools. It validates compressed unchanged
    entries, manifest/payload, retained v2 bytes and selected SDK30 v3 signer.
    ``latest()`` revalidates the last successful build; only absence returns None.
    """

    def __init__(self, assets: Path, work: Path, emit, cancel=None):
        self.assets = Path(assets)
        self.work = Path(work)
        self.emit = emit
        self.cancel = cancel
        self.tools = HudTools(self.assets, self.work, cancel)
        self.keys = HudKeyStore(self.tools)

    def _stage(self, message: str) -> None:
        check_cancel(self.cancel)
        self.emit('applying', message)

    def _stock(self, source: Path) -> tuple[bytes, bytes]:
        _guard(source)
        if sha256_file(source, self.cancel) != SUPPORTED_APK:
            raise ValueError('HUD source must be the exact pinned stock Fly APK.')
        with ZipFile(source) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError('Duplicate stock APK ZIP entry.')
            required = {'AndroidManifest.xml', 'classes.dex', 'META-INF/DJI.RSA',
                        'META-INF/DJI.SF', 'META-INF/MANIFEST.MF'}
            if not required.issubset(names) or 'classes23.dex' in names:
                raise ValueError('Unexpected stock APK entry set.')
            if any(entry.flag_bits & 1 for entry in archive.infolist()):
                raise ValueError('Encrypted stock APK ZIP entry.')
            return archive.read('AndroidManifest.xml'), archive.read('classes.dex')

    def _recipe(self, source: Path, directory: Path, helper=None) -> tuple[bytes, bytes, bytes]:
        manifest, bootstrap = self._stock(source)
        input_dex = directory / 'input.dex'
        patched_dex = directory / 'patched.dex'
        input_dex.write_bytes(bootstrap)
        self.tools.patch(input_dex, patched_dex, directory / 'smali')
        check_cancel(self.cancel)
        patched = patched_dex.read_bytes()
        if not patched or patched == bootstrap:
            raise ValueError('HUD bootstrap startup patch is missing.')
        return add_hud_provider(manifest), patched, self.tools.payload() if helper is None else helper

    def _tool_binding(self) -> dict:
        self.tools.prepare()
        return {'tool_archive_sha256': self.tools.archive_sha256,
                'tool_manifest_sha256': self.tools.manifest_sha256}

    def _copy_stock(self, source: Path, target: Path) -> None:
        _guard(source)
        digest = hashlib.sha256()
        with source.open('rb') as original, target.open('xb') as output:
            while True:
                check_cancel(self.cancel)
                value = original.read(1024 * 1024)
                if not value:
                    break
                output.write(value)
                digest.update(value)
        if digest.hexdigest() != SUPPORTED_APK:
            raise ValueError('HUD source changed or is not the pinned stock APK.')

    def build(self, source: Path) -> dict:
        self._stage('Đang kiểm tra APK Fly gốc…')
        source = Path(source)
        self._stock(source)
        self._stage('Đang kiểm tra bộ công cụ HUD ngoại tuyến…')
        binding = self._tool_binding()
        _guard(self.work)
        builds = self.work / 'builds'
        _guard(builds)
        builds.mkdir(parents=True, exist_ok=True)
        directory = builds / uuid.uuid4().hex
        directory.mkdir()
        published = False
        pointer = self.work / ('latest-' + uuid.uuid4().hex + '.json')
        try:
            stock = directory / 'source.apk'
            self._copy_stock(source, stock)
            self._stage('Đang thêm HUD vào khởi động và manifest…')
            manifest, bootstrap, helper = self._recipe(stock, directory)
            unsigned, aligned = directory / 'unsigned.apk', directory / 'aligned.apk'
            signed, candidate = directory / 'signed.apk', directory / 'hud.apk'
            repack_apk(stock, unsigned, manifest, helper, bootstrap)
            self._stage('Đang căn chỉnh APK HUD…')
            self.tools.align(unsigned, aligned)
            self._stage('Đang mở khóa chữ ký HUD của người dùng…')
            key = self.keys.ensure()
            self.tools.sign(aligned, signed, key.keyfile, key.alias, key.password)
            self._stage('Đang giữ đầu vào AppGuard và kiểm tra chữ ký Android 11…')
            original_bytes = stock.read_bytes()
            candidate.write_bytes(replace_v2_block(original_bytes, signed.read_bytes()))
            del original_bytes
            report = self._validate_candidate(stock, candidate, manifest, bootstrap, helper,
                                              key.certificate_sha256)
            value = {'schema': 1, 'status': 'hud_built', 'apk': 'hud.apk', 'source': 'source.apk',
                     'digest': sha256_file(candidate, self.cancel), 'source_digest': SUPPORTED_APK,
                     'certificate_sha256': key.certificate_sha256, **binding,
                     'payload_sha256': hashlib.sha256(helper).hexdigest(),
                     'bootstrap_sha256': hashlib.sha256(bootstrap).hexdigest(),
                     'manifest_sha256': hashlib.sha256(manifest).hexdigest(), 'changes': report}
            receipt = directory / 'receipt.json'
            _write_json(receipt, value)
            # Detect tool/payload/source races and validate the persisted receipt.
            result = self.verify(receipt)
            _write_json(pointer, {'schema': 1, 'receipt': receipt.relative_to(self.work).as_posix()})
            check_cancel(self.cancel)
            _guard(self.work / 'latest.json')
            pointer.replace(self.work / 'latest.json')
            published = True
            return result
        finally:
            pointer.unlink(missing_ok=True)
            if not published:
                # The only deleted path is this build's freshly created UUID directory.
                _guard(directory)
                if directory.resolve().parent != builds.resolve():
                    raise ValueError('HUD temporary build path escaped the managed work directory.')
                shutil.rmtree(directory)
            else:
                for name in ('input.dex', 'patched.dex', 'unsigned.apk', 'aligned.apk', 'signed.apk'):
                    (directory / name).unlink(missing_ok=True)
                smali = directory / 'smali'
                if smali.exists():
                    _guard(smali)
                    shutil.rmtree(smali)

    def _validate_candidate(self, stock: Path, candidate: Path, manifest: bytes,
                            bootstrap: bytes, helper: bytes, certificate: str) -> dict:
        check_cancel(self.cancel)
        report = validate_apk_change(stock, candidate, bootstrap, helper, manifest)
        original_blocks = block_entries(stock.read_bytes())
        candidate_blocks = block_entries(candidate.read_bytes())
        if V2 not in original_blocks or candidate_blocks.get(V2) != original_blocks[V2]:
            raise ValueError('HUD candidate did not retain the stock v2 loader input.')
        if self.tools.verify(candidate) != certificate:
            raise ValueError('HUD selected SDK30 signer certificate does not match the local signer.')
        check_cancel(self.cancel)
        return report

    def _receipt(self, path: Path) -> Path:
        path = Path(path).absolute()
        _guard(path)
        root = (self.work / 'builds').absolute()
        if (path.name != 'receipt.json' or path.parent.parent != root
                or not re.fullmatch(r'[0-9a-f]{32}', path.parent.name)):
            raise ValueError('HUD receipt must belong to a managed build directory.')
        return path

    def verify_apk(self, path: Path) -> str:
        """Inspect ONLY the SDK30 v3 signer of a local APK, without loading keys.

        This public-certificate inspection is for installer signer comparison.
        It does not approve an APK as HUD output; use ``verify(receipt)`` for that.
        """
        check_cancel(self.cancel)
        path = Path(path)
        _guard(path)
        certificate = self.tools.verify(path)
        check_cancel(self.cancel)
        return certificate

    def verify_historical(self, receipt: Path) -> dict:
        """Recognize an installed prior release for upgrade, never choose it as an install candidate."""
        return self.verify(receipt, allow_historical=True)

    def verify_device_apk(self, path: Path, stock: Path) -> dict:
        """Recognize a pulled HUD recipe/signature without trusting a foreign PC receipt/key."""
        path,stock=Path(path),Path(stock)
        _guard(path);_guard(stock);check_cancel(self.cancel)
        self._stock(stock);self._tool_binding()
        before=sha256_file(path,self.cancel)
        with ZipFile(stock) as original,ZipFile(path) as archive:
            names=archive.namelist()
            if len(names)!=len(set(names)) or set(names)!=set(original.namelist())|{'classes23.dex'}:
                raise ValueError('Unrecognized device HUD APK entry set.')
            for entry in archive.infolist():
                if entry.flag_bits&1:raise ValueError('Encrypted device APK entry.')
                if entry.filename=='classes23.dex':
                    if not 0<entry.file_size<=1024*1024 or entry.compress_size>1024*1024:
                        raise ValueError('Oversized device HUD payload.')
                elif entry.filename in {'AndroidManifest.xml','classes.dex'}:
                    if entry.file_size>original.getinfo(entry.filename).file_size+1024*1024:
                        raise ValueError('Oversized modified device APK entry.')
                else:
                    previous=original.getinfo(entry.filename)
                    if (entry.file_size,entry.compress_size,entry.compress_type,entry.CRC)!=(
                            previous.file_size,previous.compress_size,previous.compress_type,previous.CRC):
                        raise ValueError('Device APK changes an unmodified entry.')
            helper=archive.read('classes23.dex')
        current=self.tools.payload();helper_hash=hashlib.sha256(helper).hexdigest()
        expected=current if helper==current else self.tools.historical_payload(helper_hash)
        if helper!=expected:raise ValueError('Unknown device HUD payload.')
        certificate=self.verify_apk(path)
        _guard(self.work);self.work.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='device-recipe-',dir=self.work) as temporary:
            manifest,bootstrap,verified_helper=self._recipe(stock,Path(temporary),helper)
            self._validate_candidate(stock,path,manifest,bootstrap,verified_helper,certificate)
        if sha256_file(path,self.cancel)!=before or sha256_file(stock,self.cancel)!=SUPPORTED_APK:
            raise ValueError('Device APK source changed during verification.')
        return {'status':'hud_device_verified','apk':str(path),'digest':before,
                'source_digest':SUPPORTED_APK,'certificate_sha256':certificate}

    def verify(self, receipt: Path, allow_historical=False) -> dict:
        check_cancel(self.cancel)
        receipt = self._receipt(Path(receipt))
        value = load_json(receipt)
        required = {'schema', 'status', 'apk', 'source', 'digest', 'source_digest',
                    'certificate_sha256', 'tool_archive_sha256', 'tool_manifest_sha256',
                    'payload_sha256', 'bootstrap_sha256', 'manifest_sha256', 'changes'}
        if (set(value) != required or type(value['schema']) is not int or value['schema'] != 1
                or value['status'] != 'hud_built' or value['apk'] != 'hud.apk'
                or value['source'] != 'source.apk' or value['source_digest'] != SUPPORTED_APK):
            raise ValueError('Invalid or unpinned HUD receipt.')
        candidate, stock = receipt.parent / 'hud.apk', receipt.parent / 'source.apk'
        _guard(candidate)
        for field, expected in self._tool_binding().items():
            if value[field] != expected:
                raise ValueError('HUD tool binding changed since this receipt was created.')
        if sha256_file(candidate, self.cancel) != value['digest']:
            raise ValueError('HUD output digest does not match its receipt.')
        key = self.keys.load()
        if value['certificate_sha256'] != key.certificate_sha256:
            raise ValueError('HUD receipt signer certificate does not match the current local signer.')
        current_helper = self.tools.payload()
        historical = value['payload_sha256'] != hashlib.sha256(current_helper).hexdigest()
        if historical and not allow_historical:
            raise ValueError('HUD payload is outdated; create the current APK before installing.')
        helper_override = self.tools.historical_payload(value['payload_sha256']) if historical else None
        with tempfile.TemporaryDirectory(prefix='verify-', dir=receipt.parent) as temporary:
            if helper_override is None:
                manifest, bootstrap, helper = self._recipe(stock, Path(temporary))
            else:
                manifest, bootstrap, helper = self._recipe(stock, Path(temporary), helper_override)
            for field, data in [('manifest_sha256', manifest), ('bootstrap_sha256', bootstrap),
                                ('payload_sha256', helper)]:
                if value[field] != hashlib.sha256(data).hexdigest():
                    raise ValueError('HUD receipt ' + field + ' no longer matches the verified recipe.')
            report = self._validate_candidate(stock, candidate, manifest, bootstrap, helper,
                                              key.certificate_sha256)
        if (report != value['changes'] or sha256_file(candidate, self.cancel) != value['digest']
                or sha256_file(stock, self.cancel) != SUPPORTED_APK):
            raise ValueError('HUD candidate changed during receipt verification.')
        if (any(value[field] != expected for field, expected in self._tool_binding().items())
                or value['payload_sha256'] != hashlib.sha256(
                    self.tools.historical_payload(value['payload_sha256']) if historical else self.tools.payload()).hexdigest()):
            raise ValueError('HUD tools or payload changed during receipt verification.')
        return {'status': 'hud_built', 'apk': str(candidate), 'digest': value['digest'],
                'source_digest': SUPPORTED_APK, 'certificate_sha256': key.certificate_sha256,
                'receipt': str(receipt)}

    def latest(self) -> dict | None:
        pointer = self.work / 'latest.json'
        _guard(pointer)
        if not pointer.exists():
            return None
        value = load_json(pointer)
        if (set(value) != {'schema', 'receipt'} or type(value['schema']) is not int
                or value['schema'] != 1 or not isinstance(value['receipt'], str)
                or not re.fullmatch(r'builds/[0-9a-f]{32}/receipt\.json', value['receipt'])):
            raise ValueError('Invalid HUD latest receipt pointer.')
        return self.verify(self.work / value['receipt'])
