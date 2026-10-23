"""Private, version-bound Fly recipes. No device/aircraft commands during build.

The GUI owns ground confirmation before calling inherited install operations.
Device import never opens a signing key. A recovery capsule alone grants no trust.
"""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import stat
import tempfile
import uuid
from zipfile import ZipFile

from .hud_backup import PinnedAdb, guard_path, make_private, assert_stopped
from .hud_capsule import (CAPSULE_ENTRY, PROFILE_ENTRY, MAX_LITERAL, build_capsule,
                          recover_capsule, _recipe as capsule_recipe)
from .hud_install import HudInstaller
from .hud_keys import HudKeyStore
from .hud_stock import entries as apk_entries, safe_name
from .hud_tools import HudTools, check_cancel, load_json, sha256_file, _json_object
from scripts.hud_apk import repack_apk, validate_apk_change
from scripts.hud_manifest import inspect_application
from scripts.hud_signing_block import V2, block_entries_path, preserve_v2_file
from .advanced_stock_signature import verify_stock_apk

SOURCE_SHA256 = 'f6c11267d465c303e2aecb737fe4f6b41b54da083368cac497404f4c9a464f98'
SOURCE_CERTIFICATE_SHA256 = '01a42c94aa87020f41e8c252598df98b86a0acf6c05ff61c75f18fa29cad1dd4'
PROFILE_KIND = 'rc2-advanced-12110'
VERSION, VERSION_CODE = '1.21.10', 3115981
REPLACEMENT_ENTRIES = frozenset({
    'AndroidManifest.xml', 'classes.dex', 'classes10.dex', 'classes12.dex',
    'classes13.dex', 'classes14.dex', 'classes20.dex', 'classes21.dex',
    'classes4.dex', 'classes5.dex', 'classes7.dex', 'classes8.dex', 'classes9.dex',
})
ADDITION_ENTRIES = frozenset({'classes23.dex', 'classes24.dex', PROFILE_ENTRY})
_HEX = re.compile(r'[0-9a-f]{64}\Z')
_DEX = re.compile(r'classes(?:[2-9]|[1-9][0-9]+)\.dex\Z')
_MANIFEST_FIELDS = {'schema', 'version', 'code', 'source_sha256', 'recipe_sha256',
                    'entries', 'profile_kind', 'compatible_installed'}
_OPTIONAL_MANIFEST = {'feature_classes': 430, 'localized_ui_sites': 1150,
                      'translated_constants': 1126, 'local_only': True,
                      'publish_allowed': False, 'full_fly_apk_embedded': False,
                      'private_signing_key_embedded': False,
                      'recovery_capsule_created_from_user_source': True,
                      'visible_menu_sections': ['Nâng cao','Hiệu chỉnh gimbal'],
                      'menu_hierarchy': {'parent': 'Tiện ích nâng cao', 'children': ['Nâng cao','Hiệu chỉnh gimbal']}}
_RECEIPT_FIELDS = {'schema', 'status', 'apk', 'source', 'digest', 'source_digest',
                   'certificate_sha256', 'source_identity', 'recipe_sha256',
                   'manifest_sha256', 'tool_archive_sha256', 'tool_manifest_sha256',
                   'profile', 'capsule_sha256', 'changes'}


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def _hex(value):
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise ValueError('Expected a full lowercase SHA-256 digest')
    return value


def _file(path, limit=None):
    path = guard_path(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not info.st_size or (limit and info.st_size > limit):
        raise ValueError('Invalid file type or size: ' + path.name)
    return path


def _name(name):
    safe_name(name)
    if any(part in ('', '.') for part in name.split('/')):
        raise ValueError('Unsafe ZIP name')
    return name


def _write(path, value):
    path = guard_path(path)
    with path.open('xb') as stream:
        stream.write(_json(value))


def _identity(value, version=None, code=None):
    version = VERSION if version is None else version
    code = VERSION_CODE if code is None else code
    if (not isinstance(value, dict) or set(value) != {'package', 'application', 'version', 'code'}
            or value['package'] != 'dji.go.v5' or value['version'] != version
            or type(value['code']) is not int or value['code'] != code
            or not isinstance(value['application'], str)
            or not re.fullmatch(r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+', value['application'])):
        raise ValueError(f'Only stock DJI Fly {version} / {code} is supported')
    return dict(value)


class AdvancedBuilder:
    def __init__(self, assets, work, emit, cancel=None, profile=None):
        self.source_sha256 = SOURCE_SHA256 if profile is None else profile.source_sha256
        self.source_certificate = SOURCE_CERTIFICATE_SHA256 if profile is None else profile.certificate_sha256
        self.version = VERSION if profile is None else profile.version
        self.version_code = VERSION_CODE if profile is None else profile.code
        self.profile_kind = PROFILE_KIND if profile is None else profile.profile_kind
        self.recipe_directory = "advanced12110" if profile is None else profile.recipe_directory
        self.replacement_entries = (REPLACEMENT_ENTRIES if profile is None or profile.replacement_entries is None
                                    else frozenset(profile.replacement_entries))
        self.assets, self.work = guard_path(assets), guard_path(work)
        self.emit, self.cancel = emit, cancel
        self.tools = HudTools(self.assets, self.work, cancel)
        self.keys = HudKeyStore(self.tools)

    def _identity(self, value):
        return _identity(value, self.version, self.version_code)

    def _stage(self, message):
        check_cancel(self.cancel)
        self.emit('applying', message)

    def _stock(self, source):
        source = _file(source, 1536 * 1024 * 1024)
        if sha256_file(source, self.cancel) != self.source_sha256:
            raise ValueError(f'Cần đúng APK Fly gốc {self.version} / SHA-256 {self.source_sha256[:8]}; chưa ghi hoặc ký APK.')
        with ZipFile(source) as archive:
            apk_entries(archive)
            names = set(archive.namelist())
            if (not self.replacement_entries | {'resources.arsc'} <= names
                    or (ADDITION_ENTRIES | {CAPSULE_ENTRY}) & names):
                raise ValueError('Stock APK inventory differs')
            if archive.getinfo('AndroidManifest.xml').file_size > 4 * 1024 * 1024:
                raise ValueError('Oversized source manifest')
            identity = self._identity(inspect_application(archive.read('AndroidManifest.xml')))
        if V2 not in block_entries_path(source):
            raise ValueError('Stock loader V2 signature missing')
        if sha256_file(source, self.cancel) != self.source_sha256:
            raise ValueError('Source changed during inspection')
        return identity

    def _bundle(self):
        check_cancel(self.cancel)
        root = guard_path(self.assets / self.recipe_directory)
        metadata = _file(root / 'manifest.json', 256 * 1024)
        raw = metadata.read_bytes()
        manifest = _json_object(raw)
        if (not _MANIFEST_FIELDS <= manifest.keys()
                or not manifest.keys() <= _MANIFEST_FIELDS | _OPTIONAL_MANIFEST.keys()
                or type(manifest.get('schema')) is not int or manifest['schema'] != 1
                or manifest.get('version') != self.version or type(manifest.get('code')) is not int
                or manifest['code'] != self.version_code or manifest.get('source_sha256') != self.source_sha256
                or manifest.get('profile_kind') != self.profile_kind):
            raise ValueError('Invalid private version-specific recipe manifest')
        for key, expected in _OPTIONAL_MANIFEST.items():
            if key in manifest and (type(manifest[key]) is not type(expected) or manifest[key] != expected):
                raise ValueError('Invalid private recipe metadata: ' + key)
        _hex(manifest['recipe_sha256'])
        history = manifest['compatible_installed']
        if not isinstance(history, dict) or len(history) > 64:
            raise ValueError('Invalid compatible installed inventory')
        for digest, row in history.items():
            _hex(digest)
            if not isinstance(row, dict) or set(row) != {'certificate_sha256'}:
                raise ValueError('Invalid historical signer row')
            _hex(row['certificate_sha256'])
        expected = {'replacements/' + n for n in self.replacement_entries} | {
            'additions/' + n for n in ADDITION_ENTRIES}
        rows = manifest['entries']
        if not isinstance(rows, dict) or set(rows) != expected:
            raise ValueError('Recipe payload inventory differs from the selected RC version')
        for name, row in rows.items():
            _name(name)
            if (not isinstance(row, dict) or set(row) != {'sha256', 'bytes'}
                    or type(row['bytes']) is not int or not 0 < row['bytes'] <= 32 * 1024 * 1024):
                raise ValueError('Invalid recipe entry size/metadata')
            _hex(row['sha256'])
        recipe = _file(root / 'recipe.zip', 128 * 1024 * 1024)
        if sha256_file(recipe, self.cancel) != manifest['recipe_sha256']:
            raise ValueError('Recipe ZIP SHA-256 differs')
        payloads = {}
        with ZipFile(recipe) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != expected:
                raise ValueError('Recipe ZIP inventory differs or contains duplicate entries')
            for info in archive.infolist():
                check_cancel(self.cancel)
                _name(info.filename)
                row = rows[info.filename]
                if (info.is_dir() or info.flag_bits & 1 or info.compress_type not in (0, 8)
                        or stat.S_ISLNK(info.external_attr >> 16) or info.file_size != row['bytes']):
                    raise ValueError('Invalid recipe ZIP entry metadata')
                data = archive.read(info)
                if len(data) != row['bytes'] or _hash(data) != row['sha256']:
                    raise ValueError('Recipe payload SHA-256 differs')
                payloads[info.filename] = data
        profile = _json_object(payloads['additions/' + PROFILE_ENTRY])
        self._profile(profile, template=True)
        replacements = {name: payloads['replacements/' + name] for name in self.replacement_entries}
        if self._identity(inspect_application(replacements['AndroidManifest.xml'])) != profile['plan']['identity']:
            raise ValueError('Replacement manifest identity differs from profile')
        self._unchanged_bundle(manifest, _hash(raw))
        return manifest, _hash(raw), replacements, {
            name: payloads['additions/' + name] for name in ADDITION_ENTRIES}, profile

    def _unchanged_bundle(self, manifest, manifest_hash):
        root = guard_path(self.assets / self.recipe_directory)
        if (sha256_file(_file(root / 'manifest.json'), self.cancel) != manifest_hash
                or sha256_file(_file(root / 'recipe.zip'), self.cancel) != manifest['recipe_sha256']):
            raise ValueError('Recipe assets changed during operation')

    def _profile(self, profile, template=False):
        if (profile.get('kind') != self.profile_kind or type(profile.get('schema')) is not int
                or profile['schema'] != 1 or profile.get('source_sha256') != self.source_sha256
                or profile.get('helper_entry') != 'classes23.dex'
                or profile.get('feature_entry') != 'classes24.dex'
                or type(profile.get('feature_classes')) is not int or profile['feature_classes'] != 430
                or type(profile.get('localized_ui_sites')) is not int or profile['localized_ui_sites'] != 1150):
            raise ValueError('Invalid advanced profile kind or inventory')
        plan = profile.get('plan')
        if (not isinstance(plan, dict) or plan.get('source_digest') != self.source_sha256
                or plan.get('helper_entry') != profile['helper_entry'] or plan.get('retain_loader_v2') is not True
                or not isinstance(plan.get('bootstrap'), dict)
                or plan['bootstrap'].get('entry') != 'classes.dex'):
            raise ValueError('Invalid advanced source/bootstrap plan')
        self._identity(plan.get('identity'))
        if not template:
            _hex(profile.get('recipe_sha256'))
        return dict(plan['identity'])

    def _binding(self):
        self.tools.prepare()
        return {'tool_archive_sha256': _hex(self.tools.archive_sha256),
                'tool_manifest_sha256': _hex(self.tools.manifest_sha256)}

    def _space(self, source):
        ancestor = self.work
        while not ancestor.exists():
            ancestor = ancestor.parent
        needed = source.stat().st_size * 5 + 256 * 1024 * 1024
        if shutil.disk_usage(guard_path(ancestor)).free < needed:
            raise ValueError('Không đủ dung lượng dựng APK (cần khoảng %.2f GiB). Chọn --work trên ổ khác.'
                             % (needed / 1024 ** 3))

    def _copy(self, source, target):
        with _file(source).open('rb') as inp, guard_path(target).open('xb') as out:
            while chunk := inp.read(1024 * 1024):
                check_cancel(self.cancel)
                out.write(chunk)
        if sha256_file(_file(target), self.cancel) != self.source_sha256:
            raise ValueError('Source changed during immutable snapshot copy')

    def _replay(self, source, stage, manifest, replacements, additions, template):
        profile = {**template, 'kind': self.profile_kind, 'recipe_sha256': manifest['recipe_sha256']}
        capsule = stage / 'recovery.zip'
        build_capsule(source, capsule, set(replacements), self.cancel)
        return profile, {**additions, PROFILE_ENTRY: _json(profile), CAPSULE_ENTRY: capsule.read_bytes()}

    def _recover(self, candidate, source, stage, inventory, changed=None):
        with ZipFile(candidate) as archive:
            if archive.getinfo(CAPSULE_ENTRY).file_size > MAX_LITERAL:
                raise ValueError('Oversized embedded recovery capsule')
            raw = archive.read(CAPSULE_ENTRY)
        with ZipFile(io.BytesIO(raw)) as capsule:
            recipe = capsule_recipe(capsule)
            if recipe['stock_sha256'] != self.source_sha256 or (changed is not None and set(recipe['changed']) != changed):
                raise ValueError('Recovery capsule source or changed inventory differs')
        capsule_path = stage / 'capsule-check.zip'
        capsule_path.write_bytes(raw)
        recovered = stage / 'recovered.apk'
        recover_capsule(candidate, capsule_path, recovered, inventory, self.cancel)
        if sha256_file(recovered, self.cancel) != self.source_sha256 or sha256_file(source, self.cancel) != self.source_sha256:
            raise ValueError('Recovery must restore exact pinned stock')

    def _validate(self, source, candidate, replacements, additions, certificate, stage):
        check_cancel(self.cancel)
        changes = validate_apk_change(source, candidate, replacements=replacements, additions=additions)
        if block_entries_path(candidate).get(V2) != block_entries_path(source).get(V2):
            raise ValueError('Original loader V2 bytes were not preserved')
        if _hex(self.tools.verify(candidate)) != certificate:
            raise ValueError('SDK30 signer certificate differs')
        self._recover(candidate, source, stage, set(additions), set(replacements))
        check_cancel(self.cancel)
        return changes

    def build(self, source):
        source = guard_path(source)
        identity = self._stock(source)  # Before tool preparation, mkdir or signing identity.
        manifest, manifest_hash, replacements, additions, template = self._bundle()
        if identity != template['plan']['identity']:
            raise ValueError('Stock application differs from pinned recipe')
        self._space(source)
        binding = self._binding()
        builds = guard_path(self.work / 'builds')
        builds.mkdir(parents=True, exist_ok=True)
        directory = guard_path(builds / uuid.uuid4().hex)
        directory.mkdir()
        make_private(directory, directory=True)
        published = False
        pointer = guard_path(self.work / ('latest-' + uuid.uuid4().hex + '.json'))
        try:
            stock, candidate = directory / 'source.apk', directory / 'hud.apk'
            self._stage(f'Đang giữ bản nguồn Fly {self.version} và áp recipe Nâng cao…')
            self._copy(source, stock)
            with tempfile.TemporaryDirectory(prefix='advanced-build-', dir=directory) as tmp:
                stage = Path(tmp)
                profile, all_additions = self._replay(stock, stage, manifest, replacements, additions, template)
                unsigned, aligned, signed = [stage / (name + '.apk') for name in ('unsigned', 'aligned', 'signed')]
                repack_apk(stock, unsigned, replacements=replacements, additions=all_additions)
                check_cancel(self.cancel)
                self.tools.align(unsigned, aligned)
                self._unchanged_bundle(manifest, manifest_hash)
                self._stock(stock)
                check_cancel(self.cancel)
                key = self.keys.ensure()
                certificate = _hex(key.certificate_sha256)
                self._stage('Đang ký bằng khóa cục bộ và giữ loader V2 gốc…')
                self.tools.sign(aligned, signed, key.keyfile, key.alias, key.password)
                preserve_v2_file(stock, signed, candidate, self.cancel)
                # Free only invocation-owned intermediates before exact recovery verification.
                for item in (unsigned, aligned, signed):
                    guard_path(item).unlink()
                changes = self._validate(stock, candidate, replacements, all_additions, certificate, stage)
                self._unchanged_bundle(manifest, manifest_hash)
                value = {'schema': 1, 'status': 'hud_built', 'apk': 'hud.apk', 'source': 'source.apk',
                         'digest': sha256_file(candidate, self.cancel), 'source_digest': self.source_sha256,
                         'certificate_sha256': certificate, 'source_identity': identity,
                         'recipe_sha256': manifest['recipe_sha256'], 'manifest_sha256': manifest_hash,
                         **binding, 'profile': profile, 'capsule_sha256': _hash(all_additions[CAPSULE_ENTRY]),
                         'changes': changes}
                _write(directory / 'receipt.json', value)
            result = self.verify(directory / 'receipt.json')
            _write(pointer, {'schema': 1, 'receipt': 'builds/' + directory.name + '/receipt.json'})
            check_cancel(self.cancel)
            guard_path(self.work / 'latest.json')
            pointer.replace(self.work / 'latest.json')
            published = True
            self._stage('Đã kiểm chứng recipe, chữ ký và phục hồi nguyên vẹn nguồn gốc.')
            return result
        finally:
            guard_path(pointer).unlink(missing_ok=True)
            if not published:
                checked = guard_path(directory)
                if checked.parent != guard_path(builds) or not re.fullmatch(r'[0-9a-f]{32}', checked.name):
                    raise ValueError('Build cleanup escaped owned directory')
                shutil.rmtree(checked)

    def _receipt(self, reference):
        if isinstance(reference, dict):
            reference = reference.get('receipt')
        if not isinstance(reference, (str, Path)):
            raise ValueError('Receipt path required')
        path = guard_path(reference)
        if (path.name != 'receipt.json' or not re.fullmatch(r'[0-9a-f]{32}', path.parent.name)
                or path.parent.parent != guard_path(self.work / 'builds')):
            raise ValueError('Receipt escaped builder artifact directory')
        return _file(path, 512 * 1024)

    def verify(self, receipt):
        receipt = self._receipt(receipt)
        receipt_hash = sha256_file(receipt, self.cancel)
        value = load_json(receipt)
        if (set(value) != _RECEIPT_FIELDS or type(value.get('schema')) is not int or value['schema'] != 1
                or value['status'] != 'hud_built' or value['apk'] != 'hud.apk' or value['source'] != 'source.apk'):
            raise ValueError('Invalid private advanced receipt')
        for name in ('digest', 'source_digest', 'certificate_sha256', 'recipe_sha256',
                     'manifest_sha256', 'tool_archive_sha256', 'tool_manifest_sha256', 'capsule_sha256'):
            _hex(value[name])
        source, candidate = _file(receipt.parent / 'source.apk'), _file(receipt.parent / 'hud.apk')
        identity = self._stock(source)
        if identity != value['source_identity'] or value['source_digest'] != self.source_sha256:
            raise ValueError('Receipt source identity differs')
        before = sha256_file(candidate, self.cancel)
        if before != value['digest']:
            raise ValueError('Receipt APK checksum differs')
        manifest, manifest_hash, replacements, additions, template = self._bundle()
        if value['recipe_sha256'] != manifest['recipe_sha256'] or value['manifest_sha256'] != manifest_hash:
            raise ValueError('Receipt recipe binding differs')
        binding = self._binding()
        if any(value[k] != v for k, v in binding.items()):
            raise ValueError('Receipt tool binding differs')
        if self.keys.load().certificate_sha256 != value['certificate_sha256']:
            raise ValueError('Local signer identity changed')
        with tempfile.TemporaryDirectory(prefix='advanced-verify-', dir=receipt.parent) as tmp:
            stage = Path(tmp)
            profile, all_additions = self._replay(source, stage, manifest, replacements, additions, template)
            if profile != value['profile'] or _hash(all_additions[CAPSULE_ENTRY]) != value['capsule_sha256']:
                raise ValueError('Receipt profile or capsule differs')
            changes = self._validate(source, candidate, replacements, all_additions,
                                     value['certificate_sha256'], stage)
            if changes != value['changes']:
                raise ValueError('Receipt changed inventory differs')
        self._unchanged_bundle(manifest, manifest_hash)
        if (sha256_file(receipt, self.cancel) != receipt_hash or sha256_file(candidate, self.cancel) != before
                or sha256_file(source, self.cancel) != self.source_sha256 or self._binding() != binding):
            raise ValueError('Artifacts changed during verification')
        return {'status': 'hud_built', 'apk': str(candidate), 'digest': before,
                'source_digest': self.source_sha256, 'certificate_sha256': value['certificate_sha256'],
                'receipt': str(receipt), 'source_identity': identity}

    def verify_historical(self, receipt):
        # No arbitrary historical recipe fallback; receipts replay the shipped recipe.
        return self.verify(receipt)

    def latest(self):
        path = guard_path(self.work / 'latest.json')
        if not path.exists():
            return None
        value = load_json(_file(path, 4096))
        if (set(value) != {'schema', 'receipt'} or type(value['schema']) is not int or value['schema'] != 1
                or not isinstance(value['receipt'], str)
                or not re.fullmatch(r'builds/[0-9a-f]{32}/receipt\.json', value['receipt'])):
            raise ValueError('Invalid latest advanced receipt pointer')
        return self.verify(self.work / value['receipt'])

    def verify_apk(self, apk):
        apk = _file(apk)
        if sha256_file(apk, self.cancel) == self.source_sha256:
            self._stock(apk)
            return verify_stock_apk(self.tools, apk, source_digest=self.source_sha256,
                                    certificate_digest=self.source_certificate)
        return _hex(self.tools.verify(apk))

    def _device_profile(self, candidate, manifest, digest, certificate):
        with ZipFile(candidate) as archive:
            apk_entries(archive)
            if archive.getinfo(PROFILE_ENTRY).file_size > 128 * 1024:
                raise ValueError('Oversized embedded profile')
            profile = _json_object(archive.read(PROFILE_ENTRY))
        if profile.get('kind') == self.profile_kind:
            identity = self._profile(profile)
            if profile['recipe_sha256'] != manifest['recipe_sha256']:
                raise ValueError('Embedded recipe hash differs')
            return profile, identity, {'classes23.dex', 'classes24.dex', PROFILE_ENTRY, CAPSULE_ENTRY}, False
        row = manifest['compatible_installed'].get(digest)
        if row is None or certificate != row['certificate_sha256']:
            raise ValueError('Legacy installed APK hash and certificate are not explicitly pinned')
        if profile.get('kind') == 'redfly-feature-candidate':
            if (profile.get('source_sha256') != self.source_sha256 or profile.get('helper_entry') != 'classes23.dex'
                    or profile.get('feature_entry') != 'classes24.dex'
                    or not isinstance(profile.get('plan'), dict)
                    or profile['plan'].get('source_digest') != self.source_sha256
                    or profile['plan'].get('retain_loader_v2') is not True):
                raise ValueError('Invalid known private legacy profile')
            identity = self._identity(profile['plan'].get('identity'))
            inventory = {'classes23.dex', 'classes24.dex', PROFILE_ENTRY, CAPSULE_ENTRY}
        elif ('kind' not in profile and profile.get('revision') == 'structural-menu-v1'
              and profile.get('variant') == 'basic' and profile.get('source_digest') == self.source_sha256
              and profile.get('helper_entry') == 'classes23.dex' and 'feature_entry' not in profile
              and profile.get('retain_loader_v2') is True):
            identity = self._identity(profile.get('identity'))
            inventory = {'classes23.dex', PROFILE_ENTRY, CAPSULE_ENTRY}
        else:
            raise ValueError('Unknown legacy profile kind; capsule recovery is not approval')
        return profile, identity, inventory, True

    def recover_profile(self, pulled, target):
        """Recover only a recognized profile; caller must subsequently verify_device_apk."""
        pulled, target = _file(pulled), guard_path(target)
        manifest, manifest_hash, _, _, _ = self._bundle()
        digest, certificate = sha256_file(pulled, self.cancel), self.verify_apk(pulled)
        _, _, inventory, _ = self._device_profile(pulled, manifest, digest, certificate)
        with tempfile.TemporaryDirectory(prefix='advanced-recover-', dir=target.parent) as tmp:
            capsule = Path(tmp) / 'recovery.zip'
            with ZipFile(pulled) as archive:
                if archive.getinfo(CAPSULE_ENTRY).file_size > MAX_LITERAL:
                    raise ValueError('Oversized embedded capsule')
                capsule.write_bytes(archive.read(CAPSULE_ENTRY))
            with ZipFile(capsule) as archive:
                if capsule_recipe(archive)['stock_sha256'] != self.source_sha256:
                    raise ValueError('Capsule does not recover pinned stock')
            self._unchanged_bundle(manifest, manifest_hash)
            if sha256_file(pulled, self.cancel) != digest:
                raise ValueError('Pulled APK changed during recovery')
            recover_capsule(pulled, capsule, target, inventory, self.cancel)
        self._stock(target)
        if sha256_file(pulled, self.cancel) != digest:
            raise ValueError('Pulled APK changed during recovery')
        return target

    def verify_device_apk(self, pulled, stock):
        pulled, stock = _file(pulled), _file(stock)
        identity = self._stock(stock)
        manifest, manifest_hash, replacements, additions, template = self._bundle()
        before = sha256_file(pulled, self.cancel)
        certificate = self.verify_apk(pulled)
        if before != self.source_sha256:
            profile, embedded_identity, inventory, legacy = self._device_profile(pulled, manifest, before, certificate)
            if embedded_identity != identity:
                raise ValueError('Embedded identity differs from recovered stock')
            with tempfile.TemporaryDirectory(prefix='advanced-device-', dir=stock.parent) as tmp:
                stage = Path(tmp)
                if legacy:
                    self._recover(pulled, stock, stage, inventory)
                    if block_entries_path(pulled).get(V2) != block_entries_path(stock).get(V2):
                        raise ValueError('Legacy loader V2 differs')
                else:
                    expected, all_additions = self._replay(stock, stage, manifest, replacements, additions, template)
                    if profile != expected:
                        raise ValueError('Embedded advanced profile differs from recipe')
                    self._validate(stock, pulled, replacements, all_additions, certificate, stage)
        self._unchanged_bundle(manifest, manifest_hash)
        if sha256_file(pulled, self.cancel) != before or sha256_file(stock, self.cancel) != self.source_sha256:
            raise ValueError('Device APK/source changed during verification')
        return {'status': 'hud_device_verified', 'apk': str(pulled), 'digest': before,
                'source_digest': self.source_sha256, 'certificate_sha256': certificate,
                'source_identity': identity}


class AdvancedInstaller(HudInstaller):
    """Base consent/backup/install guards, private pinned acquisition and Settings stage.

    GUI must obtain ground confirmation and enter Settings before prepare/approve.
    The post-push Settings transition closes Fly's auto-FPV race; it is not ground proof.
    """
    def _installed(self, adb, required=True):
        value = super()._installed(adb, required)
        if value is not None and (value['version'] != VERSION or value['code'] != VERSION_CODE):
            raise ValueError('Chỉ hỗ trợ Fly 1.21.10 / 3115981 trên RC 2 đã chọn.')
        return value

    def pull_source(self, adb, serial):
        with self._lock:
            self._check_cancel()
            bound = PinnedAdb(adb, serial)
            self._device(bound)
            before = dict(self._installed(bound))
            root = guard_path(self.work / 'imports')
            root.mkdir(parents=True, exist_ok=True)
            directory = guard_path(root / uuid.uuid4().hex)
            directory.mkdir()
            make_private(directory, directory=True)
            registered = False
            try:
                result = self._pull_checked(bound, before, directory)
                registered = True
                return result
            finally:
                if not registered:
                    checked = guard_path(directory)
                    if checked.parent != root or not re.fullmatch(r'[0-9a-f]{32}', checked.name):
                        raise ValueError('Import cleanup escaped owned directory')
                    shutil.rmtree(checked)

    def _pull_checked(self, bound, before, directory):
        pulled = directory / 'installed.apk'
        self.emit('applying', 'Đang tự lấy APK Fly 1.21.10 từ RC 2 đã chọn…')
        bound.command('pull', before['apk_path'], str(pulled), timeout=300)
        self._check_cancel()
        make_private(_file(pulled))
        if sha256_file(pulled, self.cancel) != before['digest']:
            raise ValueError('Pulled APK checksum differs from selected device')
        self._device(bound)
        if dict(self._installed(bound)) != before:
            raise ValueError('Selected device/package changed while pulling')
        stock = pulled if before['digest'] == SOURCE_SHA256 else directory / 'source.apk'
        if stock != pulled:
            self.builder.recover_profile(pulled, stock)
            make_private(_file(stock))
        verified = self.builder.verify_device_apk(pulled, stock)
        self._check_cancel()
        self._device(bound)
        if (verified['digest'] != before['digest'] or dict(self._installed(bound)) != before
                or sha256_file(pulled, self.cancel) != before['digest']):
            raise ValueError('Device APK changed before source registration')
        _write(directory / 'snapshot.json', {'schema': 1, 'device': before, 'verified': verified,
                                            'pulled': 'installed.apk', 'stock': stock.name})
        self._device_sources[before['digest']] = (pulled, stock)
        return stock

    def _stage(self, adb, candidate, name='candidate.apk'):
        self._check_cancel()
        # Keep base pre-push checks. Reassert Settings only after successful APK push.
        target = super()._stage(adb, candidate, name)
        try:
            self._check_cancel()
            response = adb.shell('am start -W -n com.android.settings/.Settings', timeout=60)
            if not re.search(r'^Status: ok\s*$', response, re.M):
                raise ValueError('Chưa mở được Settings sau khi gửi APK.')
            current = adb.shell('dumpsys activity activities | grep mResumedActivity')
            if not re.search(r'\bcom\.android\.settings/(?:\.Settings|com\.android\.settings\.Settings)\b', current):
                raise ValueError('Tay chưa ở Settings sau khi gửi APK.')
            adb.shell('am force-stop dji.go.v5')
            assert_stopped(adb)
            self._device(adb)
            return target
        except BaseException:
            self._cleanup_stage(adb, target)
            raise
