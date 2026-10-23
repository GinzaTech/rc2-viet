"""Frozen builds must include and pin every selected version's own data."""
from dataclasses import replace
import hashlib
import json

import pytest

from rc2vi.fly_versions import FLY_1218, FLY_12110
from scripts import build_auto_patch_exe as build


@pytest.fixture
def version_assets(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    stage = tmp_path / 'stage'
    stage.mkdir()
    old_table, new_table = b'old reviewed resource fixture', b'new separately reviewed resource fixture'
    old_hash = hashlib.sha256(old_table).hexdigest()
    profiles = (FLY_1218, FLY_12110, replace(
        FLY_12110, version='1.21.16', code=3132286, recipe_directory='advanced12116',
        translation_directory='auto12116', translation_sha256=hashlib.sha256(new_table).hexdigest()))
    monkeypatch.setattr(build, 'SUPPORTED', profiles)
    monkeypatch.setattr(build, 'TRANSLATION_SHA256', old_hash)
    for profile in profiles:
        recipe = source / profile.recipe_directory
        recipe.mkdir(parents=True)
        (recipe / 'manifest.json').write_text(json.dumps({'version': profile.version}), 'utf-8')
        (recipe / 'recipe.zip').write_bytes(profile.version.encode('ascii'))
        (recipe / 'original-source.apk').write_bytes(b'must not bundle original APK')
        (recipe / 'private.p12').write_bytes(b'not a key, forbidden fixture file')
        translation = source / profile.translation_directory
        translation.mkdir(exist_ok=True)
        (translation / 'manifest.json').write_text(json.dumps({'version': profile.translation_directory}), 'utf-8')
        (translation / 'vietnamese.arsc').write_bytes(new_table if profile.version == '1.21.16' else old_table)
    return source, stage, profiles


def test_all_supported_recipes_and_separate_translation_are_bundled_without_apks_or_keys(version_assets):
    source, stage, profiles = version_assets
    inventory, translations = build.stage_version_assets(source, stage)
    for profile in profiles:
        for name in ('manifest.json', 'recipe.zip'):
            relative = profile.recipe_directory + '/' + name
            assert relative in inventory
            assert (stage / relative).read_bytes() == (source / relative).read_bytes()
        assert profile.translation_directory + '/vietnamese.arsc' in inventory
    assert set(translations) == {'auto12110', 'auto12116'}
    assert len(inventory) == len(set(inventory))
    assert not list(stage.rglob('*.apk'))
    assert not list(stage.rglob('*.p12'))
    assert (stage / 'auto12116/vietnamese.arsc').read_bytes() != (stage / 'auto12110/vietnamese.arsc').read_bytes()


def test_new_version_cannot_ship_an_unreviewed_translation_table(version_assets):
    source, stage, _ = version_assets
    (source / 'auto12116/vietnamese.arsc').write_bytes(b'changed table')
    with pytest.raises(ValueError, match='1.21.16'):
        build.stage_version_assets(source, stage)
