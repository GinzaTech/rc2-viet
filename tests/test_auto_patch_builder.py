"""Small signed-layout fixtures exercise recipe selection and exact recovery.

Real Android signatures/dependencies are checked separately with both stock APKs.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
import advanced_app
from rc2vi import auto_patch as api, advanced_patch as menu
from rc2vi.fly_versions import FLY_1218, FLY_12110
from rc2vi.hud_capsule import CAPSULE_ENTRY, PROFILE_ENTRY
from scripts.hud_apk import repack_apk
from scripts.hud_signing_block import V2, preserve_v2_file
from tests.test_advanced_patch import Tools, Keys, sign_block
from tests.test_resource_embed import table


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def versions(tmp_path, monkeypatch):
    assets = tmp_path / 'assets'
    translation = assets / 'auto12110/vietnamese.arsc'
    translation.parent.mkdir(parents=True)
    names = ['visible_' + str(n) for n in range(11313)]
    entries = [(n, 0) for n in range(len(names))]
    translation.write_bytes(table('string', names, ['Cho phép liên kết'], [(b'', entries)]))
    monkeypatch.setattr(api, 'TRANSLATION_SHA256', sha(translation.read_bytes()))
    monkeypatch.setattr(menu, 'HudTools', Tools)
    monkeypatch.setattr(menu, 'HudKeyStore', Keys)
    monkeypatch.setattr(menu, 'inspect_application', lambda raw: json.loads(raw))
    monkeypatch.setattr(menu, 'verify_stock_apk', lambda *a, **kw: 'c' * 64)
    profiles = []
    sources = []
    new_names = names + ['visible_only_in_12116']
    new_translation = assets / 'auto12116/vietnamese.arsc'
    new_translation.parent.mkdir()
    new_translation.write_bytes(table('string', new_names, ['Bản dịch riêng 1.21.16'],
                                     [(b'', [(n, 0) for n in range(len(new_names))])]))
    new_profile = replace(FLY_12110, version='1.21.16', code=3132286,
        recipe_directory='advanced12116', profile_kind='rc2-advanced-12116',
        auto_kind='rc2-advanced-12116-vietnamese-auto-v1',
        translation_directory='auto12116', translation_sha256=sha(new_translation.read_bytes()),
        translation_count=len(new_names), replacement_entries=tuple(sorted(
            (menu.REPLACEMENT_ENTRIES - {'classes12.dex', 'classes8.dex'}) |
            {'classes11.dex', 'classes15.dex', 'classes22.dex', 'classes6.dex'})))
    for original in (FLY_1218, FLY_12110, new_profile):
        identity = {'package': 'dji.go.v5', 'application': 'com.fixture.Application',
                    'version': original.version, 'code': original.code}
        source = tmp_path / (original.version + '.apk')
        replacement_entries = frozenset(original.replacement_entries or menu.REPLACEMENT_ENTRIES)
        stock = {name: (original.version + ':' + name).encode() for name in replacement_entries}
        stock['AndroidManifest.xml'] = json.dumps(identity).encode()
        selected_names = new_names if original == new_profile else names
        stock['resources.arsc'] = table('string', selected_names, ['Original'],
            [(b'', [(n, 0) for n in range(len(selected_names))])])
        stock['lib/armeabi-v7a/unchanged.so'] = b'original protocol bytes'
        with ZipFile(source, 'w', ZIP_DEFLATED) as archive:
            for name, data in stock.items():
                archive.writestr(name, data)
        sign_block(source, [(V2, b'original loader ' + original.version.encode())])
        profile = replace(original, source_sha256=sha(source.read_bytes()))
        profiles.append(profile)
        sources.append(source)
        template = {'schema': 1, 'kind': profile.profile_kind, 'source_sha256': profile.source_sha256,
                    'helper_entry': 'classes23.dex', 'feature_entry': 'classes24.dex',
                    'feature_classes': 430, 'localized_ui_sites': 1150,
                    'plan': {'identity': identity, 'source_digest': profile.source_sha256,
                             'helper_entry': 'classes23.dex', 'retain_loader_v2': True,
                             'bootstrap': {'entry': 'classes.dex'}}}
        payloads = {'replacements/' + name: (data + b'\n' if name == 'AndroidManifest.xml' else data + b':patched')
                    for name, data in stock.items() if name in replacement_entries}
        payloads.update({'additions/classes23.dex': b'bridge', 'additions/classes24.dex': b'features',
                         'additions/' + PROFILE_ENTRY: json.dumps(template).encode()})
        root = assets / profile.recipe_directory
        root.mkdir()
        with ZipFile(root / 'recipe.zip', 'w', ZIP_DEFLATED) as archive:
            for name, data in payloads.items():
                archive.writestr(name, data)
        metadata = {'schema': 1, 'version': profile.version, 'code': profile.code,
                    'source_sha256': profile.source_sha256, 'profile_kind': profile.profile_kind,
                    'recipe_sha256': sha((root / 'recipe.zip').read_bytes()), 'compatible_installed': {},
                    'entries': {name: {'sha256': sha(data), 'bytes': len(data)} for name, data in payloads.items()}}
        (root / 'manifest.json').write_text(json.dumps(metadata), 'utf-8')
    monkeypatch.setattr(api, 'SUPPORTED', tuple(profiles))
    monkeypatch.setattr(api, 'FLY_12110', profiles[1])
    def lookup(digest):
        for profile in profiles:
            if digest == profile.source_sha256:
                return profile
        raise ValueError('Unrecognized stock hash')
    monkeypatch.setattr(api, 'for_source', lookup)
    monkeypatch.setattr(advanced_app, 'builder_factory', lambda assets, work, emit, cancel=None, profile=None:
                        menu.AdvancedBuilder(assets, work, emit, cancel, profile=profile or profiles[1]))
    return assets, profiles, sources


@pytest.mark.parametrize('index', [0, 1, 2], ids=['rc1218', 'rc12110', 'rc12116'])
def test_build_selects_own_recipe_and_recovery_is_exact(versions, tmp_path, index):
    assets, profiles, sources = versions
    builder = api.AutoPatchBuilder(assets, tmp_path / 'build')
    result = builder.build(sources[index])
    assert result['source_digest'] == profiles[index].source_sha256
    assert result['profile']['kind'] == profiles[index].auto_kind
    assert result['profile']['plan']['identity']['version'] == profiles[index].version
    recovered = tmp_path / 'recovered.apk'
    builder.recover(Path(result['apk']), recovered)
    assert builder.current_recovery['digest'] == result['digest']
    assert recovered.read_bytes() == sources[index].read_bytes()
    assert builder.verify(recovered, Path(result['apk']))['digest'] == result['digest']


@pytest.mark.parametrize('index', [0, 1, 2])
def test_mixed_version_recipe_fails_before_signing(versions, tmp_path, index):
    assets, profiles, sources = versions
    correct, wrong = (assets / profiles[i].recipe_directory for i in (index, (index + 1) % len(profiles)))
    for name in ('recipe.zip', 'manifest.json'):
        (correct / name).write_bytes((wrong / name).read_bytes())
    builder = api.AutoPatchBuilder(assets, tmp_path / 'build')
    with pytest.raises(ValueError, match='recipe manifest'):
        builder.build(sources[index])
    builder.tools.sign.assert_not_called()
    builder.menu.keys.ensure.assert_not_called()


def test_one_builder_switches_versions_without_using_previous_recipe(versions, tmp_path):
    assets, profiles, sources = versions
    builder = api.AutoPatchBuilder(assets, tmp_path / 'recover')
    for i in (0, 1, 0):
        output = tmp_path / ('copy-' + str(i) + '.apk')
        builder.recover(sources[i], output)
        assert builder.version_profile == profiles[i]
        assert output.read_bytes() == sources[i].read_bytes()


def test_existing_candidate_from_other_version_cannot_be_reused(versions, tmp_path):
    assets, profiles, sources = versions
    builder = api.AutoPatchBuilder(assets, tmp_path / 'build')
    builder.build(sources[0])
    with pytest.raises(ValueError):
        builder.build(sources[1])


def test_own_profile_does_not_authorize_a_modified_apk(versions, tmp_path):
    assets, profiles, sources = versions
    builder = api.AutoPatchBuilder(assets, tmp_path / 'build')
    result = builder.build(sources[0])
    original = Path(result['apk'])
    unsigned, signed, tampered = (tmp_path / (name + '.apk') for name in ('unsigned', 'signed', 'tampered'))
    repack_apk(original, unsigned, replacements={'classes4.dex': b'unreviewed replacement'}, additions={})
    builder.tools.sign(unsigned, signed)
    preserve_v2_file(original, signed, tampered)
    with pytest.raises(ValueError):
        builder.recover(tampered, tmp_path / 'must-not-be-trusted.apk')


def retire_current_recipe(assets, profile, monkeypatch):
    """Keep a pinned inventory, then change the currently shipped menu recipe."""
    from rc2vi import auto_recipe_history as history
    root = assets / profile.recipe_directory
    manifest = json.loads((root / 'manifest.json').read_bytes())
    old_digest = manifest['recipe_sha256']
    with ZipFile(root / 'recipe.zip') as archive:
        payloads = {name: archive.read(name) for name in archive.namelist()}
    record = {'schema': 1, 'manifest': manifest,
              'template_json': payloads['additions/' + PROFILE_ENTRY].decode('utf-8')}
    directory = assets / 'auto-history'
    directory.mkdir(exist_ok=True)
    inventory = directory / (profile.recipe_directory + '.json')
    inventory.write_text(json.dumps(record), encoding='utf-8')
    monkeypatch.setitem(history.PREVIOUS_RECIPES, old_digest, (inventory.name, sha(inventory.read_bytes())))
    payloads['additions/classes23.dex'] += b':refreshed-flight-bridge'
    with ZipFile(root / 'recipe.zip', 'w', ZIP_DEFLATED) as archive:
        for name, data in payloads.items():
            archive.writestr(name, data)
    updated = {**manifest, 'recipe_sha256': sha((root / 'recipe.zip').read_bytes()),
               'entries': {name: {'sha256': sha(data), 'bytes': len(data)}
                           for name, data in payloads.items()}}
    (root / 'manifest.json').write_text(json.dumps(updated), encoding='utf-8')
    return inventory, old_digest


@pytest.mark.parametrize('index', [0, 1], ids=['rc1218', 'rc12110'])
def test_previous_auto_recipe_recovers_exact_stock_and_upgrades_without_old_zip(versions, tmp_path, monkeypatch, index):
    assets, profiles, sources = versions
    old = api.AutoPatchBuilder(assets, tmp_path / 'old')
    candidate = Path(old.build(sources[index])['apk'])
    retire_current_recipe(assets, profiles[index], monkeypatch)
    current = api.AutoPatchBuilder(assets, tmp_path / 'current')
    recovered = tmp_path / 'recovered-old.apk'
    current.recover(candidate, recovered)
    assert current.current_recovery is None
    assert recovered.read_bytes() == sources[index].read_bytes()
    current.menu.keys.ensure.assert_not_called()
    current.tools.sign.assert_not_called()
    with pytest.raises(ValueError):
        current.verify(recovered, candidate)  # Old content cannot pass current recipe verification.
    result = current.build(recovered)
    with ZipFile(candidate) as archive:
        assert result['profile']['recipe_sha256'] != json.loads(archive.read(PROFILE_ENTRY))['recipe_sha256']
    assert current.verify(recovered, Path(result['apk']))['digest'] == result['digest']


@pytest.mark.parametrize('entry', ['classes23.dex', 'classes4.dex', 'resources.arsc',
                                  PROFILE_ENTRY, CAPSULE_ENTRY, 'lib/armeabi-v7a/unchanged.so'])
def test_previous_recipe_recovery_rejects_tampering_in_every_payload_category(versions, tmp_path, monkeypatch, entry):
    assets, profiles, sources = versions
    old = api.AutoPatchBuilder(assets, tmp_path / 'old')
    candidate = Path(old.build(sources[0])['apk'])
    retire_current_recipe(assets, profiles[0], monkeypatch)
    with ZipFile(candidate) as archive:
        changed = archive.read(entry)
    if entry == PROFILE_ENTRY:
        value = json.loads(changed)
        value['standalone_language'] = False
        changed = json.dumps(value).encode()
    elif entry == 'classes23.dex':
        changed = b'X' + changed[1:]  # Same length: the historical payload hash must reject it.
    else:
        changed += b':unreviewed'
    unsigned, signed, tampered = (tmp_path / (name + '.apk') for name in ('unsigned-old', 'signed-old', 'tampered-old'))
    repack_apk(candidate, unsigned, replacements={entry: changed}, additions={})
    old.tools.sign(unsigned, signed)
    preserve_v2_file(candidate, signed, tampered)
    current = api.AutoPatchBuilder(assets, tmp_path / 'current')
    with pytest.raises(ValueError, match='SHA-256 payload recipe' if entry == 'classes23.dex' else None):
        current.recover(tampered, tmp_path / 'recovered-tampered.apk')
    current.menu.keys.ensure.assert_not_called()
    current.tools.sign.assert_not_called()


def test_previous_recipe_inventory_is_hash_pinned_before_payload_trust(versions, tmp_path, monkeypatch):
    assets, profiles, sources = versions
    old = api.AutoPatchBuilder(assets, tmp_path / 'old')
    candidate = Path(old.build(sources[1])['apk'])
    inventory, _ = retire_current_recipe(assets, profiles[1], monkeypatch)
    inventory.write_bytes(inventory.read_bytes() + b' ')
    with pytest.raises(ValueError, match='recipe cũ bị thay đổi'):
        api.AutoPatchBuilder(assets, tmp_path / 'current').recover(candidate, tmp_path / 'recovered.apk')


def test_published_history_files_match_hardcoded_hashes_and_selected_version():
    from rc2vi.auto_recipe_history import load_previous
    for digest, profile in [
        ('be517b4e3de6ac99bcc6dee29bbc53616c54879520414370f3b0a1041d0f886d', FLY_1218),
        ('e8342bd9e479318bfff88fa19fcc8afedda3481e718526c9d8cce4ab7a9d6acb', FLY_12110),
    ]:
        manifest, template = load_previous(Path(__file__).resolve().parents[1] / 'assets', digest, profile)
        assert manifest['recipe_sha256'] == digest
        assert template['source_sha256'] == profile.source_sha256
        with pytest.raises(ValueError, match='selected RC version'):
            load_previous(Path(__file__).resolve().parents[1] / 'assets', digest,
                          FLY_12110 if profile == FLY_1218 else FLY_1218)


@pytest.mark.parametrize('binding', ['exact', 'wrong-digest', 'wrong-certificate'])
def test_reviewed_older_translation_upgrade_requires_exact_apk_and_signer(versions, tmp_path, monkeypatch, binding):
    assets, profiles, sources = versions
    previous = api.AutoPatchBuilder(assets, tmp_path / 'previous')
    result = previous.build(sources[0])
    candidate = Path(result['apk'])
    retire_current_recipe(assets, profiles[0], monkeypatch)
    # A newer reviewed translation is shipped after this prior APK was built.
    translation = assets / 'auto12110/vietnamese.arsc'
    names = ['visible_' + str(n) for n in range(11313)]
    translation.write_bytes(table('string', names, ['Bản dịch mới'],
                                  [(b'', [(n, 0) for n in range(len(names))])]))
    monkeypatch.setattr(api, 'TRANSLATION_SHA256', sha(translation.read_bytes()))
    digest = result['digest'] if binding != 'wrong-digest' else '0' * 64
    certificate = 'c' * 64 if binding != 'wrong-certificate' else 'd' * 64
    monkeypatch.setitem(api.REVIEWED_EMBEDDED, digest, certificate)
    current = api.AutoPatchBuilder(assets, tmp_path / 'current')
    recovered = tmp_path / 'recovered-reviewed.apk'
    if binding == 'exact':
        current.recover(candidate, recovered)
        assert recovered.read_bytes() == sources[0].read_bytes()
    else:
        with pytest.raises(ValueError):
            current.recover(candidate, recovered)
    current.menu.keys.ensure.assert_not_called()
    current.tools.sign.assert_not_called()


def test_audited_prior_device_build_has_only_exact_digest_signer_binding():
    assert api.REVIEWED_EMBEDDED['2874a7e8327951c0a6d2117049ab0a4012f578c03d964b5fb756a31ec911c23c'] == (
        'c581d1c3ff00db3b4d3d7cf5f6c384bb7719763c0986a3ee6b629aa001956915')
