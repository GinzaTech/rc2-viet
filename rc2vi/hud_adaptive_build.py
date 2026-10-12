"""Build and replay a structural menu recipe, bound to the exact input at runtime.

Legacy plans without a variant replay as Basic with their original serialized
profile bytes. Explicit invalid variants never receive that compatibility default.
"""
import hashlib
import json
import re
from pathlib import Path
import shutil
import tempfile
import uuid
from zipfile import ZipFile

from .hud_plan import analyze, REVISION
from .hud_capsule import build_capsule, CAPSULE_ENTRY, PROFILE_ENTRY
from .hud_tools import check_cancel, load_json, sha256_file
from .hud_variants import HudVariant, validate_variant
from scripts.hud_apk import repack_apk, validate_apk_change
from scripts.hud_manifest import add_adaptive_provider
from scripts.hud_signing_block import V2, block_entries_path, preserve_v2_file


def _hash(value): return hashlib.sha256(value).hexdigest()


def _json(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


class AdaptiveBuild:
    def __init__(self, owner):
        self.owner = owner
        self.tools, self.keys, self.work, self.cancel = owner.tools, owner.keys, owner.work, owner.cancel

    def _payload(self, variant: HudVariant, expected: str | None = None,
                 historical: bool = False) -> bytes:
        validate_variant(variant)
        payload = self.tools.payload()
        if expected is None or _hash(payload) == expected:
            return payload
        if not historical:
            raise ValueError('Menu variant helper is unknown or outdated; rebuild before install')
        payload = self.tools.historical_payload(expected)
        if _hash(payload) != expected:
            raise ValueError('Historical menu helper checksum differs')
        return payload

    def _recipe(self, source, stage, helper=None, *, variant=HudVariant.BASIC,
                include_variant: bool = True):
        variant = validate_variant(variant)
        plan = analyze(source, self.tools, stage, self.cancel)
        if include_variant:
            plan = {**plan, 'variant': variant.value}
        with ZipFile(source) as archive:
            replacements = {'AndroidManifest.xml': add_adaptive_provider(archive.read('AndroidManifest.xml'))}
            if plan['bootstrap']['mode'] == 'context_swap':
                name = plan['bootstrap']['entry']
                dex, patched = stage/'bootstrap-input.dex', stage/'bootstrap-output.dex'
                dex.write_bytes(archive.read(name))
                self.tools.patch_adaptive(dex, patched, stage/'smali', plan['bootstrap']['descriptor'])
                value = patched.read_bytes()
                if not value or value == archive.read(name): raise ValueError('Menu startup patch missing')
                replacements[name] = value
        capsule = stage/'recovery.zip'
        build_capsule(source, capsule, set(replacements), self.cancel)
        payload = self._payload(variant) if helper is None else helper
        additions = {plan['helper_entry']: payload, CAPSULE_ENTRY: capsule.read_bytes(), PROFILE_ENTRY: _json(plan)}
        return plan, replacements, additions

    def _validate(self, source, candidate, plan, replacements, additions, certificate):
        check_cancel(self.cancel)
        report = validate_apk_change(source, candidate, replacements=replacements, additions=additions)
        if plan['retain_loader_v2']:
            original = block_entries_path(source); patched = block_entries_path(candidate)
            if V2 not in original or patched.get(V2) != original[V2]:
                raise ValueError('Original loader v2 input was not preserved')
        if self.tools.verify(candidate) != certificate:
            raise ValueError('Menu APK selected SDK30 signer differs')
        check_cancel(self.cancel)
        return report

    def build(self, source, variant: str = HudVariant.BASIC):
        from .hud_build import _guard, _write_json, _RECOVERED_SOURCE
        variant = validate_variant(variant)
        source = Path(source); _guard(source)
        recovered = _RECOVERED_SOURCE.get()
        expected = (recovered[2] if recovered is not None and recovered[0] is self.owner
                    and recovered[1] == source.absolute() else None)
        self.owner._stage('Đang phân tích APK và tài nguyên menu của phiên bản hiện tại…')
        binding = self.owner._tool_binding()
        before = sha256_file(source, self.cancel)
        if expected is not None and before != expected:
            raise ValueError('Recovered menu source changed before the build copy')
        _guard(self.work); builds = self.work/'builds'; _guard(builds); builds.mkdir(parents=True, exist_ok=True)
        directory = builds/uuid.uuid4().hex; directory.mkdir()
        published = False
        pointer = self.work/('latest-'+uuid.uuid4().hex+'.json')
        try:
            stock = directory/'source.apk'
            with source.open('rb') as inp, stock.open('xb') as out:
                while chunk := inp.read(1024*1024):
                    check_cancel(self.cancel); out.write(chunk)
            if sha256_file(stock, self.cancel) != before: raise ValueError('Input changed while copying source')
            stage = directory/'recipe'; stage.mkdir()
            plan, replacements, additions = self._recipe(stock, stage, variant=variant)
            self.owner._stage('Đang patch menu, tạo dữ liệu phục hồi và ký APK…')
            unsigned, aligned, signed, candidate = [directory/(name+'.apk') for name in ('unsigned','aligned','signed','hud')]
            repack_apk(stock, unsigned, replacements=replacements, additions=additions)
            self.tools.align(unsigned, aligned)
            key = self.keys.ensure()
            self.tools.sign(aligned, signed, key.keyfile, key.alias, key.password)
            if plan['retain_loader_v2']:
                preserve_v2_file(stock, signed, candidate, self.cancel)
            else:
                shutil.copyfile(signed, candidate)
            self.owner._stage('Đang kiểm chứng chữ ký, dữ liệu nguyên gốc và bản patch menu…')
            changes = self._validate(stock, candidate, plan, replacements, additions, key.certificate_sha256)
            value = {'schema': 2, 'status': 'hud_built', 'apk': 'hud.apk', 'source': 'source.apk',
                     'digest': sha256_file(candidate, self.cancel), 'source_digest': before,
                     'certificate_sha256': key.certificate_sha256, **binding, 'plan': plan,
                     'payload_sha256': _hash(additions[plan['helper_entry']]),
                     'capsule_sha256': _hash(additions[CAPSULE_ENTRY]),
                     'replacement_sha256': {name:_hash(data) for name,data in replacements.items()},
                     'changes': changes}
            _write_json(directory/'receipt.json', value)
            result = self.verify(directory/'receipt.json')
            _write_json(pointer, {'schema': 1, 'receipt': str(Path('builds')/directory.name/'receipt.json').replace('\\','/')})
            check_cancel(self.cancel); pointer.replace(self.work/'latest.json'); published = True
            self.owner._stage('Đã tạo và kiểm chứng APK menu theo cấu trúc đầu vào.')
            return result
        finally:
            pointer.unlink(missing_ok=True)
            _guard(directory)
            if directory.resolve().parent != builds.resolve(): raise ValueError('Menu build cleanup escaped root')
            if not published:
                shutil.rmtree(directory)
            else:
                for name in ('unsigned.apk','aligned.apk','signed.apk'): (directory/name).unlink(missing_ok=True)
                shutil.rmtree(directory/'recipe')

    def verify(self, receipt, historical=False):
        from .hud_build import _guard
        receipt = self.owner._receipt(receipt); value = load_json(receipt)
        required = {'schema','status','apk','source','digest','source_digest','certificate_sha256',
                    'tool_archive_sha256','tool_manifest_sha256','plan','payload_sha256',
                    'capsule_sha256','replacement_sha256','changes'}
        if (set(value) != required or value['schema'] != 2 or value['status'] != 'hud_built'
                or value['apk'] != 'hud.apk' or value['source'] != 'source.apk'
                or not isinstance(value['plan'], dict) or value['plan'].get('revision') != REVISION):
            raise ValueError('Invalid structural menu receipt')
        variant = validate_variant(value['plan'].get('variant', HudVariant.BASIC))
        source, candidate = receipt.parent/'source.apk', receipt.parent/'hud.apk'
        _guard(source); _guard(candidate)
        if sha256_file(source,self.cancel)!=value['source_digest'] or sha256_file(candidate,self.cancel)!=value['digest']:
            raise ValueError('Menu source/output checksum differs')
        if any(value[k] != v for k,v in self.owner._tool_binding().items()):
            raise ValueError('Menu tool binding changed; rebuild from current source')
        key = self.keys.load()
        if key.certificate_sha256 != value['certificate_sha256']: raise ValueError('Menu signer changed')
        payload = self._payload(variant, value['payload_sha256'], historical)
        with tempfile.TemporaryDirectory(prefix='menu-replay-',dir=receipt.parent) as tmp:
            plan, replacements, additions = self._recipe(
                source, Path(tmp), payload, variant=variant,
                include_variant='variant' in value['plan'])
            if (plan != value['plan'] or _hash(additions[CAPSULE_ENTRY]) != value['capsule_sha256']
                    or {name:_hash(data) for name,data in replacements.items()} != value['replacement_sha256']):
                raise ValueError('Structural menu recipe changed')
            changes = self._validate(source,candidate,plan,replacements,additions,key.certificate_sha256)
            if changes != value['changes']: raise ValueError('Menu entry changes differ from recipe')
        if (any(value[k] != v for k,v in self.owner._tool_binding().items())
                or self._payload(variant, value['payload_sha256'], historical) != payload):
            raise ValueError('Menu tools or variant payload changed during verification')
        if sha256_file(source,self.cancel)!=value['source_digest'] or sha256_file(candidate,self.cancel)!=value['digest']:
            raise ValueError('Menu files changed during verification')
        return {'status':'hud_built','variant':variant.value,'apk':str(candidate),'digest':value['digest'],
                'source_digest':value['source_digest'],'certificate_sha256':key.certificate_sha256,
                'receipt':str(receipt), 'source_identity': dict(value['plan']['identity'])}

    def verify_device(self, candidate, source):
        from .hud_build import _guard
        _guard(candidate); _guard(source)
        before = sha256_file(candidate,self.cancel); source_hash = sha256_file(source,self.cancel)
        with ZipFile(candidate) as archive:
            if archive.getinfo(PROFILE_ENTRY).file_size > 128*1024: raise ValueError('Oversized menu profile')
            from .hud_tools import _json_object
            plan = _json_object(archive.read(PROFILE_ENTRY))
            variant = validate_variant(plan.get('variant', HudVariant.BASIC))
            name = plan.get('helper_entry')
            if not isinstance(name,str) or not re.fullmatch(r'classes(?:[2-9]|[1-9][0-9]+)\.dex',name):
                raise ValueError('Invalid embedded helper name')
            if archive.getinfo(name).file_size > 1024*1024: raise ValueError('Oversized menu helper')
            helper = archive.read(name)
        if helper != self._payload(variant, _hash(helper), historical=True):
            raise ValueError('Unknown embedded menu helper')
        certificate = self.owner.verify_apk(candidate)
        self.work.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='menu-device-replay-',dir=self.work) as tmp:
            expected, replacements, additions = self._recipe(
                source, Path(tmp), helper, variant=variant,
                include_variant='variant' in plan)
            if plan != expected: raise ValueError('Embedded menu plan differs from recovered source')
            self._validate(source,candidate,expected,replacements,additions,certificate)
        if self._payload(variant, _hash(helper), historical=True) != helper:
            raise ValueError('Embedded variant payload changed during verification')
        if (sha256_file(candidate,self.cancel)!=before or sha256_file(source,self.cancel)!=source_hash):
            raise ValueError('Device APK/source changed during verification')
        return {'status':'hud_device_verified','variant':variant.value,'apk':str(candidate),'digest':before,
                'source_digest':source_hash,'certificate_sha256':certificate,
                'source_identity':dict(plan['identity'])}
