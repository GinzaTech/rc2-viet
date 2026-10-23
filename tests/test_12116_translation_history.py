"""Old recipe/table pairs upgrade without requiring the old signing key."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from rc2vi import auto_patch as api, auto_recipe_history as history, advanced_patch as menu
from rc2vi.fly_versions import FLY_1218, FLY_12116
from rc2vi.hud_capsule import PROFILE_ENTRY
from scripts import build_auto_patch_exe as frozen
from scripts.hud_apk import repack_apk
from scripts.hud_signing_block import preserve_v2_file
from tests.test_auto_patch_builder import versions, retire_current_recipe
from tests.test_resource_embed import table


ASSETS = Path(__file__).resolve().parents[1] / 'assets'
OLD_TRANSLATION = 'dcb39692e2a56d9e2c5670c04691ee1b561d1116128ab487a55828b9be75b150'
OLD_RECIPES = [
    'b8df8c71949f43ac5582f41144e0b46dcc73663a96a43bd59b26680117d350a1',
    'f2706464162872a67fb5f3a940b0ed112f6798bcff0f6e56f90bfb59a570df8c',
]
REVIEW_BASELINE_TRANSLATION = '60381bce71f307f92c847f2abb0025e66a6cab351ee510a92052077bc579c509'
REVIEW_BASELINE_RECIPE = 'f2706464162872a67fb5f3a940b0ed112f6798bcff0f6e56f90bfb59a570df8c'
REVIEW_BASELINE_SOURCE = '9bec52ed4c43aad6c615b0a7a0650f0d35e842c4bf8a5e59d5da005a50d56b6a'
REVIEW_BASELINE_PATH = 'translations/' + REVIEW_BASELINE_TRANSLATION + '.arsc'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def register_inventory(assets, profile, monkeypatch):
    root = assets / profile.recipe_directory
    manifest = json.loads((root / 'manifest.json').read_bytes())
    with ZipFile(root / 'recipe.zip') as archive:
        template = archive.read('additions/' + PROFILE_ENTRY).decode('utf-8')
    raw = json.dumps({'schema': 1, 'manifest': manifest, 'template_json': template}).encode('utf-8')
    directory = assets / 'auto-history'
    directory.mkdir(exist_ok=True)
    name = 'fixture-current-recipe.json'
    (directory / name).write_bytes(raw)
    monkeypatch.setitem(history.PREVIOUS_RECIPES, manifest['recipe_sha256'], (name, sha(raw)))
    return manifest['recipe_sha256']


def upgrade_inputs(versions, tmp_path, monkeypatch, change_recipe):
    assets, profiles, sources = versions
    old = api.AutoPatchBuilder(assets, tmp_path / 'old')
    result = old.build(sources[2])
    old_profile = profiles[2]
    translation = assets / old_profile.translation_directory / 'vietnamese.arsc'
    raw = translation.read_bytes()
    recipe = (retire_current_recipe(assets, old_profile, monkeypatch)[1]
              if change_recipe else register_inventory(assets, old_profile, monkeypatch))
    archived = assets / 'auto-history/translations/fixture.arsc'
    archived.parent.mkdir(exist_ok=True)
    archived.write_bytes(raw)
    monkeypatch.setitem(history.PREVIOUS_TRANSLATIONS, sha(raw), {
        'path': 'translations/fixture.arsc', 'source_sha256': old_profile.source_sha256,
        'recipes': frozenset({recipe}), 'embedded_resources': old_profile.translation_count})
    names = ['visible_' + str(n) for n in range(old_profile.translation_count - 1)] + ['visible_only_in_12116']
    translation.write_bytes(table('string', names, ['Bảng dịch mới đã sửa'],
        [(b'', [(n, 0) for n in range(len(names))])]))
    profiles[2] = replace(old_profile, translation_sha256=sha(translation.read_bytes()))
    monkeypatch.setattr(api, 'SUPPORTED', tuple(profiles))
    class NoKeys:
        def __init__(self, *args):
            self.load = Mock(side_effect=AssertionError('Recovery must not load any signing key'))
            self.ensure = Mock(side_effect=AssertionError('Recovery must not create any signing key'))
    monkeypatch.setattr(menu, 'HudKeyStore', NoKeys)
    return assets, profiles, sources, Path(result['apk']), archived


@pytest.mark.parametrize('recipe', OLD_RECIPES)
def test_published_historical_pairs_keep_exact_old_translation_and_recipe(recipe):
    manifest, _ = history.load_previous(ASSETS, recipe, FLY_12116)
    assert manifest['recipe_sha256'] == recipe
    raw, count = history.load_previous_translation(ASSETS, recipe, OLD_TRANSLATION, FLY_12116)
    assert sha(raw) == OLD_TRANSLATION
    assert count == 11994


def test_r1461_public_review_baseline_keeps_exact_archived_bytes_and_pair():
    binding = history.PREVIOUS_TRANSLATIONS[REVIEW_BASELINE_TRANSLATION]
    assert binding == {
        'path': REVIEW_BASELINE_PATH,
        'source_sha256': REVIEW_BASELINE_SOURCE,
        'recipes': frozenset({REVIEW_BASELINE_RECIPE}),
        'embedded_resources': 11994,
    }
    archived = (ASSETS / 'auto-history' / REVIEW_BASELINE_PATH).read_bytes()
    assert sha(archived) == REVIEW_BASELINE_TRANSLATION
    manifest, _ = history.load_previous(ASSETS, REVIEW_BASELINE_RECIPE, FLY_12116)
    assert manifest['source_sha256'] == REVIEW_BASELINE_SOURCE
    raw, count = history.load_previous_translation(
        ASSETS, REVIEW_BASELINE_RECIPE, REVIEW_BASELINE_TRANSLATION, FLY_12116)
    assert raw == archived
    assert count == 11994
    assert (REVIEW_BASELINE_PATH, REVIEW_BASELINE_TRANSLATION) in history.history_assets()


@pytest.mark.parametrize('recipe,translation,profile', [
    (OLD_RECIPES[0], REVIEW_BASELINE_TRANSLATION, FLY_12116),
    ('f' * 64, REVIEW_BASELINE_TRANSLATION, FLY_12116),
    (REVIEW_BASELINE_RECIPE, REVIEW_BASELINE_TRANSLATION, FLY_1218),
    (REVIEW_BASELINE_RECIPE, REVIEW_BASELINE_TRANSLATION,
     replace(FLY_12116, source_sha256='0' * 64)),
    (REVIEW_BASELINE_RECIPE, 'f' * 64, FLY_12116),
    (REVIEW_BASELINE_RECIPE, None, FLY_12116),
], ids=['unpublished-r146-pair', 'unknown-recipe', 'other-fly-source',
        'changed-source', 'unknown-table', 'invalid-table-digest'])
def test_r1461_public_review_baseline_rejects_unreviewed_pairs(recipe, translation, profile):
    with pytest.raises(ValueError, match='Historical'):
        history.load_previous_translation(ASSETS, recipe, translation, profile)


@pytest.mark.parametrize('change', ['append', 'same-length', 'empty', 'missing'])
def test_r1461_public_review_baseline_requires_exact_archive(tmp_path, change):
    archive = tmp_path / 'auto-history' / REVIEW_BASELINE_PATH
    archive.parent.mkdir(parents=True)
    original = (ASSETS / 'auto-history' / REVIEW_BASELINE_PATH).read_bytes()
    if change == 'append':
        archive.write_bytes(original + b' ')
    elif change == 'same-length':
        archive.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    elif change == 'empty':
        archive.write_bytes(b'')
    with pytest.raises(ValueError, match='Historical translation data has changed|Missing historical translation data'):
        history.load_previous_translation(
            tmp_path, REVIEW_BASELINE_RECIPE, REVIEW_BASELINE_TRANSLATION, FLY_12116)


@pytest.mark.parametrize('recipe,translation,profile', [
    ('f' * 64, OLD_TRANSLATION, FLY_12116),
    (OLD_RECIPES[0], 'f' * 64, FLY_12116),
    (OLD_RECIPES[0], OLD_TRANSLATION, FLY_1218),
    (OLD_RECIPES[0], None, FLY_12116),
])
def test_unreviewed_recipe_translation_or_source_pair_is_rejected(recipe, translation, profile):
    with pytest.raises(ValueError):
        history.load_previous_translation(ASSETS, recipe, translation, profile)


@pytest.mark.parametrize('change_recipe', [False, True], ids=['same-recipe-new-table', 'new-recipe-and-table'])
def test_old_translation_recovery_is_exact_and_does_not_open_any_signing_key(versions, tmp_path, monkeypatch, change_recipe):
    assets, profiles, sources, candidate, _ = upgrade_inputs(versions, tmp_path, monkeypatch, change_recipe)
    current = api.AutoPatchBuilder(assets, tmp_path / 'current')
    recovered = tmp_path / 'recovered.apk'
    current.recover(candidate, recovered)
    assert recovered.read_bytes() == sources[2].read_bytes()
    assert current.current_recovery is None
    current.menu.keys.load.assert_not_called()
    current.menu.keys.ensure.assert_not_called()
    current.tools.sign.assert_not_called()
    with pytest.raises(ValueError):
        current.verify(recovered, candidate)


def test_current_recipe_and_translation_remain_reusable_when_recipe_also_has_history(versions, tmp_path, monkeypatch):
    assets, profiles, sources = versions
    old = api.AutoPatchBuilder(assets, tmp_path / 'old')
    result = old.build(sources[2])
    register_inventory(assets, profiles[2], monkeypatch)
    current = api.AutoPatchBuilder(assets, tmp_path / 'current')
    current.recover(Path(result['apk']), tmp_path / 'recovered.apk')
    assert current.current_recovery['digest'] == result['digest']
    current.menu.keys.ensure.assert_not_called()
    current.tools.sign.assert_not_called()


def test_archived_translation_hash_is_checked_before_using_old_payloads(versions, tmp_path, monkeypatch):
    assets, profiles, sources, candidate, archived = upgrade_inputs(versions, tmp_path, monkeypatch, False)
    archived.write_bytes(archived.read_bytes() + b' ')
    with pytest.raises(ValueError, match='Historical translation data has changed'):
        api.AutoPatchBuilder(assets, tmp_path / 'current').recover(candidate, tmp_path / 'recovered.apk')


@pytest.mark.parametrize('entry', ['resources.arsc', PROFILE_ENTRY, 'classes23.dex'])
def test_old_recipe_table_metadata_cannot_hide_modified_payloads(versions, tmp_path, monkeypatch, entry):
    assets, profiles, sources, candidate, _ = upgrade_inputs(versions, tmp_path, monkeypatch, False)
    with ZipFile(candidate) as archive:
        raw = archive.read(entry)
    if entry == PROFILE_ENTRY:
        value = json.loads(raw)
        value['embedded_vietnamese']['embedded_resources'] += 1
        changed = json.dumps(value).encode('utf-8')
    else:
        changed = raw + b':changed'
    unsigned, signed, tampered = (tmp_path / (name + '.apk') for name in ('unsigned', 'signed', 'tampered'))
    repack_apk(candidate, unsigned, replacements={entry: changed}, additions={})
    tools = api.AutoPatchBuilder(assets, tmp_path / 'signer').tools
    tools.sign(unsigned, signed)
    preserve_v2_file(candidate, signed, tampered)
    current = api.AutoPatchBuilder(assets, tmp_path / 'current')
    with pytest.raises(ValueError):
        current.recover(tampered, tmp_path / 'recovered.apk')
    current.menu.keys.load.assert_not_called()
    current.menu.keys.ensure.assert_not_called()
    current.tools.sign.assert_not_called()


def test_frozen_history_staging_includes_only_pinned_inventories_and_archived_table(tmp_path):
    stage = tmp_path / 'stage'
    stage.mkdir()
    inventory = frozen.stage_history_assets(ASSETS, stage)
    expected = {'auto-history/' + name for name, digest in history.history_assets()}
    assert set(inventory) == expected
    assert {str(p.relative_to(stage)).replace('\\', '/') for p in stage.rglob('*') if p.is_file()} == expected
    for name, digest in history.history_assets():
        assert sha((stage / 'auto-history' / name).read_bytes()) == digest


def test_frozen_history_staging_rejects_changed_archived_table(tmp_path, monkeypatch):
    source, stage = tmp_path / 'assets', tmp_path / 'stage'
    stage.mkdir()
    directory = source / 'auto-history/translations'
    directory.mkdir(parents=True)
    (directory / 'changed.arsc').write_bytes(b'unreviewed')
    monkeypatch.setattr(history, 'history_assets', lambda: (('translations/changed.arsc', '0' * 64),))
    with pytest.raises(ValueError, match='checksum mismatch'):
        frozen.stage_history_assets(source, stage)
