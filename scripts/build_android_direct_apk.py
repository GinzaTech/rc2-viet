"""Build the pinned DJI Fly Android 1.21.12 Vietnamese/menu APK.

This is an offline host build. It never connects to an Android device or RC2.
The exact official input, translation table and current menu payload are pinned.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rc2vi.hud_capsule import CAPSULE_ENTRY, PROFILE_ENTRY, build_capsule, recover_capsule
from rc2vi.hud_keys import HudKeyStore
from rc2vi.hud_plan import analyze
from rc2vi.hud_tools import HudTools, sha256_file
from rc2vi.resource_embed import Table, embed
from scripts.hud_apk import repack_apk, validate_apk_change
from scripts.hud_manifest import add_adaptive_provider, inspect_application
from scripts.hud_signing_block import V2, block_entries_path, preserve_v2_file
from scripts.update_embedded_translation import WORDING

SOURCE_SHA256 = '1da8d5b2ee5cdcb6002131b8f6535605e7445080d1ca6f8411067a0d1524ce0b'
TRANSLATION_SHA256 = '6f6029c5540613bb05a173e96eefbaf045132176c3640b2a428152194df664ee'
MERGED_RESOURCE_SHA256 = '82e001acbec7db71a585ae4fc7a83179e8809e44bfba1537bb69c4ecbf18ea6a'
HELPER_SHA256 = '97e215a608e6ae85b32527b29755e3fd4d6a251beda7351af0561a442bae326f'
IDENTITY = {
    'package': 'dji.go.v5',
    'application': 'com.AppGuard.AppGuard.RGTYT',
    'version': '1.21.12',
    'code': 3131451,
}
EXPECTED_TRANSLATION_REPORT = {
    'embedded_resources': 11068,
    'translated_configurations': 208248,
    'translated_string_values': 208969,
    'appended_pool_strings': 7769,
    'all_existing_locale_variants_translated': True,
}
REQUIRED_MENU_LABELS = [
    'Tiện ích nâng cao', 'Nâng cao', 'Hiệu chỉnh gimbal',
    'Đèn càng', 'EC / gốc', 'Ép xuất',
]
OUTPUT_NAME = 'DJI-Fly-Android-1.21.12-Vietnamese-Menu-r13.1.apk'


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def translation_asset() -> bytes:
    path = ROOT / 'assets/android12112/vietnamese.arsc'
    data = path.read_bytes()
    if len(data) != 2906536 or digest(data) != TRANSLATION_SHA256:
        raise ValueError('Android 1.21.12 Vietnamese resource asset differs from its review pin')
    observed = {}
    table = Table(data)
    for key, config, positions in table.entries():
        if key[0] == 'string' and key[1] in WORDING and not any(config[4:]):
            kind, index = table.values(positions)[None]
            if kind == 3:
                observed[key[1]] = table.pool.strings[index]
    if observed != WORDING:
        raise ValueError('Reviewed Gmail/initialization wording is missing from Android translation asset')
    return data


def menu_payload() -> bytes:
    recipes = [ROOT / 'assets/advanced1218/recipe.zip',
               ROOT / 'assets/advanced12110/recipe.zip']
    payloads = []
    for recipe in recipes:
        with ZipFile(recipe) as archive:
            payloads.append(archive.read('additions/classes23.dex'))
    if payloads[0] != payloads[1] or digest(payloads[0]) != HELPER_SHA256:
        raise ValueError('Current r13.1 menu payloads differ or fail their review pin')
    if b'B\x1ed ch\x1edng rung' in payloads[0]:
        raise ValueError('Obsolete menu wording remains in current payload')
    return payloads[0]


def verify_identity(apk: Path) -> dict:
    with ZipFile(apk) as archive:
        identity = inspect_application(archive.read('AndroidManifest.xml'))
    if identity != IDENTITY:
        raise ValueError('APK identity is not the pinned DJI Fly Android 1.21.12 build')
    return identity


def build(source: Path, output: Path, work: Path) -> dict:
    source, output, work = source.resolve(), output.resolve(), work.resolve()
    if source == output:
        raise ValueError('Output must not overwrite the official source APK')
    if output.exists():
        raise FileExistsError('Refusing to replace an existing exported APK: ' + str(output))
    if sha256_file(source) != SOURCE_SHA256:
        raise ValueError('Input is not the pinned official DJI Fly Android 1.21.12 APK')
    identity = verify_identity(source)
    work.mkdir(parents=True, exist_ok=True)
    tools = HudTools(ROOT / 'assets', work / 'tools')
    helper = menu_payload()
    translated = translation_asset()
    print('PASS input/hash/identity; analyzing AppGuard bootstrap and resource IDs...', flush=True)

    with tempfile.TemporaryDirectory(prefix='android12112-', dir=work) as folder:
        stage = Path(folder)
        plan_stage = stage / 'plan'
        plan_stage.mkdir()
        plan = analyze(source, tools, plan_stage)
        if plan['identity'] != IDENTITY:
            raise ValueError('Structural menu plan identity changed')
        with ZipFile(source) as archive:
            replacements = {
                'AndroidManifest.xml': add_adaptive_provider(archive.read('AndroidManifest.xml')),
            }
            if plan['bootstrap']['mode'] == 'context_swap':
                name = plan['bootstrap']['entry']
                original = archive.read(name)
                before, after = stage / 'bootstrap-in.dex', stage / 'bootstrap-out.dex'
                before.write_bytes(original)
                tools.patch_adaptive(before, after, stage / 'smali',
                                     plan['bootstrap']['descriptor'])
                patched = after.read_bytes()
                if not patched or patched == original:
                    raise ValueError('AppGuard bootstrap patch was not applied')
                replacements[name] = patched
            merged_resources, translation_report = embed(
                archive.read('resources.arsc'), translated)
        if translation_report != EXPECTED_TRANSLATION_REPORT:
            raise ValueError('Android 1.21.12 translation coverage changed: ' + repr(translation_report))
        if digest(merged_resources) != MERGED_RESOURCE_SHA256:
            raise ValueError('Merged Android resource table differs from reviewed output')
        replacements['resources.arsc'] = merged_resources

        capsule = stage / 'recovery.zip'
        build_capsule(source, capsule, set(replacements))
        profile = {
            **plan,
            'variant': 'advanced',
            'kind': 'android-direct-vi-menu-r13.1',
            'menu_payload_sha256': HELPER_SHA256,
            'translation_sha256': TRANSLATION_SHA256,
            'translation_revision': 'r13.1-resource-initialization-wording',
            'embedded_vietnamese': translation_report,
            'standalone_language': True,
            'phone_android_build': True,
            'runtime_verified': False,
        }
        additions = {
            plan['helper_entry']: helper,
            CAPSULE_ENTRY: capsule.read_bytes(),
            PROFILE_ENTRY: json_bytes(profile),
        }
        print('PASS plan/resources/capsule; repacking, aligning and signing...', flush=True)
        unsigned, aligned, signed, candidate = [stage / (name + '.apk') for name in (
            'unsigned', 'aligned', 'signed', 'candidate')]
        repack_apk(source, unsigned, replacements=replacements, additions=additions)
        tools.align(unsigned, aligned)
        key = HudKeyStore(tools).ensure()
        tools.sign(aligned, signed, key.keyfile, key.alias, key.password)
        if plan['retain_loader_v2']:
            preserve_v2_file(source, signed, candidate)
        else:
            shutil.copyfile(signed, candidate)

        print('PASS signed; validating ZIP changes, signer, loader and exact recovery...', flush=True)
        changes = validate_apk_change(
            source, candidate, replacements=replacements, additions=additions)
        certificate = tools.verify(candidate)
        if certificate != key.certificate_sha256:
            raise ValueError('Selected Android SDK30 signer differs from local signing identity')
        if plan['retain_loader_v2']:
            original_blocks = block_entries_path(source)
            patched_blocks = block_entries_path(candidate)
            if V2 not in original_blocks or patched_blocks.get(V2) != original_blocks[V2]:
                raise ValueError('Original AppGuard loader V2 block was not preserved')
        with ZipFile(candidate) as archive:
            if archive.testzip() is not None:
                raise ValueError('Final APK contains a corrupt ZIP member')
            if json.loads(archive.read(PROFILE_ENTRY)) != profile:
                raise ValueError('Embedded direct-Android profile differs')
            if archive.read(plan['helper_entry']) != helper:
                raise ValueError('Embedded menu payload differs')
            if digest(archive.read('resources.arsc')) != MERGED_RESOURCE_SHA256:
                raise ValueError('Embedded Vietnamese resource table differs')
            if inspect_application(archive.read('AndroidManifest.xml')) != IDENTITY:
                raise ValueError('Final APK identity changed')
        restored = stage / 'restored-official.apk'
        recover_capsule(candidate, capsule, restored, set(additions))
        if sha256_file(restored) != SOURCE_SHA256:
            raise ValueError('Recovery capsule did not reconstruct the exact official APK')

        candidate_digest = sha256_file(candidate)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + '.tmp')
        if temporary.exists():
            temporary.unlink()
        shutil.copy2(candidate, temporary)
        if sha256_file(temporary) != candidate_digest:
            temporary.unlink(missing_ok=True)
            raise ValueError('Exported APK copy differs from verified candidate')
        os.replace(temporary, output)

    result = {
        'schema': 1,
        'status': 'PASS_OFFLINE_ANDROID_INSTALL_NOT_RUNTIME_TESTED',
        'apk': str(output),
        'sha256': candidate_digest,
        'bytes': output.stat().st_size,
        'source_sha256': SOURCE_SHA256,
        'source_identity': identity,
        'certificate_sha256': certificate,
        'translation_sha256': TRANSLATION_SHA256,
        'merged_resource_sha256': MERGED_RESOURCE_SHA256,
        'menu_payload_sha256': HELPER_SHA256,
        'menu_labels': REQUIRED_MENU_LABELS,
        'changes': changes,
        'original_loader_v2_preserved': bool(plan['retain_loader_v2']),
        'exact_official_source_recovery': 'PASS',
        'zip_integrity': 'PASS',
        'apksigner_sdk30_selection': 'PASS',
        'android_install_tested': False,
        'phone_menu_runtime_tested': False,
        'rc2_hardware_actions_on_phone_tested': False,
        'embedded_vietnamese': translation_report,
        'profile': profile,
    }
    report_path = output.with_suffix('.verification.json')
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path,
                        default=Path.cwd() / OUTPUT_NAME)
    parser.add_argument('--work', type=Path,
                        default=Path(os.environ.get('LOCALAPPDATA', Path.home())) /
                        'RC2DevWork/android12112-direct')
    args = parser.parse_args()
    build(args.source, args.output, args.work)


if __name__ == '__main__':
    main()
