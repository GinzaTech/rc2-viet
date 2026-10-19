"""Offline menu + embedded Vietnamese builder; contains no device commands."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from zipfile import ZipFile

from .advanced_patch import SOURCE_SHA256
from .fly_versions import FLY_12110, SUPPORTED, for_source
from .hud_backup import guard_path
from .hud_capsule import CAPSULE_ENTRY, PROFILE_ENTRY, build_capsule, recover_capsule
from .hud_tools import sha256_file, check_cancel
from .resource_embed import embed
from scripts.hud_apk import repack_apk, validate_apk_change
from scripts.hud_signing_block import preserve_v2_file, block_entries_path, V2

KIND = 'rc2-advanced-12110-vietnamese-auto-v1'
TRANSLATION_SHA256 = 'a9d86b6a3a46457f3a5b95a0276b3583011405c58009e0682084e1a72aa4a1fb'
# These releases were built, signed and byte-checked in this workspace. A capsule
# on its own never authorizes importing an arbitrary modified application.
REVIEWED_EMBEDDED = {
    '1436b7bc9cd43befb7c3f282d9dd2a1398b3c83e856306dccd49a3e0047a3ab7':
        '744bcae7b02111e24a0bb9f880bd85cc8802d0100f213954f76838a4c5b565aa',
    '42f1ae6f7f7b1b08aed3c7e9fdaa6ef552b3a9f301b19df347658e1f6b629664':
        '744bcae7b02111e24a0bb9f880bd85cc8802d0100f213954f76838a4c5b565aa',
    'c2a51eb830a030682e90e56c776c20558cff437e627d4c6f29e405718c7560e9':
        '744bcae7b02111e24a0bb9f880bd85cc8802d0100f213954f76838a4c5b565aa',
    'd59e2d7894f3d3f4aefec4eb003de034b64e717b007cb106f2870347b59d3861':
        '744bcae7b02111e24a0bb9f880bd85cc8802d0100f213954f76838a4c5b565aa',
    '62ed6b3d37a8a172180faf663c1840426b052370fcefd640d10b81f1ba4c0825':
        '744bcae7b02111e24a0bb9f880bd85cc8802d0100f213954f76838a4c5b565aa',
    '4e0131575f7411caba3c2b28f3d345e4ecb24c393e2b78eaae04191163d4d987':
        '744bcae7b02111e24a0bb9f880bd85cc8802d0100f213954f76838a4c5b565aa',
    'c90a2e12582312deb6ee1e69506105f32e6866bdc8b6a946c9bca52455ef302c':
        '744bcae7b02111e24a0bb9f880bd85cc8802d0100f213954f76838a4c5b565aa',
    '0640a8d559c5b628f451f6c1c872d8ac574f6d883adfca2f82d20d3faf5d36ac':
        '744bcae7b02111e24a0bb9f880bd85cc8802d0100f213954f76838a4c5b565aa',
    '697017a25c07237a0a64cd54a75a6b3053723f11918c11fb7708f009c9949058':
        '744bcae7b02111e24a0bb9f880bd85cc8802d0100f213954f76838a4c5b565aa',
    '7a1f2a304b9a14f0996469c3d132b853aed47d93449cbacc9e2094f0fa0719c9':
        '744bcae7b02111e24a0bb9f880bd85cc8802d0100f213954f76838a4c5b565aa',
    '4f8c2b69492e12191e5c66e944cd90aa22122bae364c4995bbaad566dc7e1c24':
        '744bcae7b02111e24a0bb9f880bd85cc8802d0100f213954f76838a4c5b565aa',
    '520d3c66457ed354f06a72b71404a2f8a620138e25cd0bf4d9278b6bcf05a2bf':
        '744bcae7b02111e24a0bb9f880bd85cc8802d0100f213954f76838a4c5b565aa',
    'df0c6ee3f2a37e8d50f57b68e9cf9536e6497be97d3b12fcc3bfddd66dededd3':
        '744bcae7b02111e24a0bb9f880bd85cc8802d0100f213954f76838a4c5b565aa',
    '214f48a04a067485cb76456029b1c3ba0b38509d69b46266840086ccb84b1726':
        '744bcae7b02111e24a0bb9f880bd85cc8802d0100f213954f76838a4c5b565aa',
    'd2934e0f90b6167ac53ef7652f15314236c127df8b86423789a0c7b1b525cb65':
        '1e26661faf2c6a93d32c2d8f969377fa890e2aa8e28ae2e6f7aa8b9cb9c90e50',
    'a414fa250eecdc6d3b209f3c19c9664e8fcc0e19c692f87b81658af408c0d806':
        '1e26661faf2c6a93d32c2d8f969377fa890e2aa8e28ae2e6f7aa8b9cb9c90e50',
    '79161774ff7f404665ee1a5326b9616de23e244962206e00144f8ef58bc45f68':
        '1e26661faf2c6a93d32c2d8f969377fa890e2aa8e28ae2e6f7aa8b9cb9c90e50',
    'b8696b07bc4a14bb747ece0a0fe017b3588da3ea194ea7ca3904b0681c47660e':
        '1e26661faf2c6a93d32c2d8f969377fa890e2aa8e28ae2e6f7aa8b9cb9c90e50',
    'b4fde7365b6e509289f6b17d296a84aa42203fc3447799fa4511f1d0fe819141':
        '1e26661faf2c6a93d32c2d8f969377fa890e2aa8e28ae2e6f7aa8b9cb9c90e50',
}
ADDED = {'classes23.dex', 'classes24.dex', PROFILE_ENTRY, CAPSULE_ENTRY}


def atomic_json(path, value):
    path = guard_path(Path(path).absolute())
    temporary = guard_path(path.with_name(path.name + '.tmp'))
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


class AutoPatchBuilder:
    def __init__(self, assets, work, emit=lambda *args: None, cancel=None):
        from advanced_app import builder_factory
        self.assets, self.work = Path(assets), Path(work)
        self.emit, self.cancel = emit, cancel
        self.version_profile = FLY_12110
        self.menu = builder_factory(self.assets, self.work / 'tools', emit, cancel)
        self.tools = self.menu.tools

    def select_profile(self, profile):
        from advanced_app import builder_factory
        if profile not in SUPPORTED:
            raise ValueError('Unknown RC Fly menu profile')
        if profile != self.version_profile:
            self.menu = builder_factory(self.assets, self.work / 'tools', self.emit,
                                        self.cancel, profile=profile)
            self.tools = self.menu.tools
            self.version_profile = profile

    def _select_source(self, source):
        self.select_profile(for_source(sha256_file(source, self.cancel)))

    def _translation(self):
        path = guard_path(self.assets / 'auto12110/vietnamese.arsc')
        if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('Thiếu dữ liệu tiếng Việt đã kiểm chứng của bản tự động.')
        if sha256_file(path, self.cancel) != TRANSLATION_SHA256:
            raise ValueError('Dữ liệu tiếng Việt bị thay đổi; chưa dựng hoặc cài APK.')
        return path.read_bytes()

    def _payloads(self, source, stage):
        self._select_source(source)
        self.menu._stock(source)
        manifest, manifest_hash, replacements, additions, template = self.menu._bundle()
        with ZipFile(source) as archive:
            resources, report = embed(archive.read('resources.arsc'), self._translation())
        if report['embedded_resources'] != 11313:
            raise ValueError('Số tài nguyên tiếng Việt không khớp bản RC đã kiểm chứng.')
        replacements = {**replacements, 'resources.arsc': resources}
        capsule = build_capsule(source, stage / 'recovery.zip', set(replacements), self.cancel)
        profile = {**template, 'kind': self.version_profile.auto_kind, 'recipe_sha256': manifest['recipe_sha256'],
                   'translation_sha256': TRANSLATION_SHA256, 'embedded_vietnamese': report,
                   'standalone_language': True}
        additions = {**additions, CAPSULE_ENTRY: capsule.read_bytes(),
                     PROFILE_ENTRY: json.dumps(profile, ensure_ascii=False, sort_keys=True).encode('utf-8')}
        self.menu._unchanged_bundle(manifest, manifest_hash)
        return replacements, additions, profile

    def verify(self, source, candidate, expected_digest=None):
        source, candidate = guard_path(source), guard_path(candidate)
        before = sha256_file(candidate, self.cancel)
        if expected_digest is not None and before != expected_digest:
            raise ValueError('APK đầu ra đã thay đổi; không cài.')
        self.work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='verify-', dir=self.work) as folder:
            stage = Path(folder)
            replacements, additions, profile = self._payloads(source, stage)
            validate_apk_change(source, candidate, replacements=replacements, additions=additions)
            if block_entries_path(candidate).get(V2) != block_entries_path(source).get(V2):
                raise ValueError('Loader V2 không khớp APK gốc.')
            certificate = self.tools.verify(candidate)
            with ZipFile(candidate) as archive:
                if json.loads(archive.read(PROFILE_ENTRY)) != profile:
                    raise ValueError('Thông tin APK tự động không khớp recipe hiện tại.')
            restored = stage / 'stock.apk'
            recover_capsule(candidate, stage / 'recovery.zip', restored, ADDED, self.cancel)
            if sha256_file(restored, self.cancel) != self.version_profile.source_sha256:
                raise ValueError('Không phục hồi được đúng APK gốc.')
        if sha256_file(candidate, self.cancel) != before:
            raise ValueError('APK thay đổi trong lúc kiểm chứng.')
        return {'apk': str(candidate), 'digest': before, 'source_digest': self.version_profile.source_sha256,
                'certificate_sha256': certificate, 'profile': profile,
                'embedded_vietnamese': True, 'separate_overlay_required': False}

    def recover(self, pulled, output):
        pulled, output = guard_path(pulled), guard_path(output)
        digest = sha256_file(pulled, self.cancel)
        if digest in {p.source_sha256 for p in SUPPORTED}:
            self.select_profile(for_source(digest))
            self.menu._stock(pulled)
            self.menu.verify_apk(pulled)
            shutil.copyfile(pulled, output)
            return output
        with ZipFile(pulled) as archive:
            if PROFILE_ENTRY not in archive.namelist():
                raise ValueError('Menu local chỉ hỗ trợ nguồn RC 1.21.8 / 1.21.10 đã kiểm chứng; chưa thay Fly.')
            if archive.getinfo(PROFILE_ENTRY).file_size > 128 * 1024:
                raise ValueError('Thông tin APK vượt giới hạn.')
            profile = json.loads(archive.read(PROFILE_ENTRY))
            if not isinstance(profile, dict):
                raise ValueError('Thông tin APK không hợp lệ.')
            self.select_profile(for_source(profile.get('source_sha256', profile.get('source_digest'))))
            certificate = self.menu.verify_apk(pulled)
            own = profile.get('kind') == self.version_profile.auto_kind
            reviewed = REVIEWED_EMBEDDED.get(digest) == certificate
            if not own and not reviewed:
                self.menu.recover_profile(pulled, output)
                self.menu.verify_device_apk(pulled, output)
                return output
            if profile.get('source_sha256') != self.version_profile.source_sha256:
                raise ValueError('APK không thuộc nguồn RC đã kiểm chứng.')
            if archive.getinfo(CAPSULE_ENTRY).file_size > 96 * 1024 * 1024:
                raise ValueError('Dữ liệu phục hồi vượt giới hạn.')
            capsule_bytes = archive.read(CAPSULE_ENTRY)
        with tempfile.TemporaryDirectory(prefix='recover-', dir=output.parent) as folder:
            capsule = Path(folder) / 'recovery.zip'
            capsule.write_bytes(capsule_bytes)
            recover_capsule(pulled, capsule, output, ADDED, self.cancel)
        self.menu._stock(output)
        if block_entries_path(pulled).get(V2) != block_entries_path(output).get(V2):
            raise ValueError('Loader của APK đã thay đổi.')
        if own and not reviewed:
            self.verify(output, pulled, digest)
        else:
            # Both the complete file hash and selected certificate were pinned.
            if sha256_file(pulled, self.cancel) != digest:
                raise ValueError('APK đầu vào đã thay đổi.')
        return output

    def build(self, source):
        source = guard_path(source)
        self._select_source(source)
        self.menu._stock(source)
        self._translation()
        self.work.mkdir(parents=True, exist_ok=True)
        output = self.work / 'patched.apk'
        if output.is_file():
            self.emit('building', 'Đang kiểm chứng lại APK đã dựng để tiếp tục…')
            return self.verify(source, output)
        self.emit('building', 'Đang patch menu local và nhúng 11.313 tài nguyên tiếng Việt vào APK…')
        with tempfile.TemporaryDirectory(prefix='build-', dir=self.work) as folder:
            stage = Path(folder)
            replacements, additions, profile = self._payloads(source, stage)
            unsigned, aligned, signed = (stage / (name + '.apk') for name in ('unsigned', 'aligned', 'signed'))
            repack_apk(source, unsigned, replacements=replacements, additions=additions)
            check_cancel(self.cancel)
            self.tools.align(unsigned, aligned)
            key = self.menu.keys.ensure()
            self.tools.sign(aligned, signed, key.keyfile, key.alias, key.password)
            candidate = stage / 'candidate.apk'
            preserve_v2_file(source, signed, candidate, self.cancel)
            self.emit('building', 'Đang kiểm tra toàn bộ APK, chữ ký và phục hồi bản gốc…')
            value = self.verify(source, candidate)
            if value['certificate_sha256'] != key.certificate_sha256:
                raise ValueError('Chữ ký APK không khớp khóa cục bộ.')
            candidate.replace(output)
        value = {**value, 'apk': str(output)}
        atomic_json(self.work / 'build-result.json', value)
        self.emit('built', 'Đã dựng và kiểm chứng APK: menu local + tiếng Việt tích hợp.')
        return value
