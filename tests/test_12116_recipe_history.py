"""The first 1.21.16 auto recipe can upgrade without trusting its capsule alone."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from rc2vi import auto_recipe_history as history
from rc2vi.auto_patch import AutoPatchBuilder
from rc2vi.fly_versions import FLY_1218, FLY_12110, FLY_12116
from rc2vi.hud_capsule import PROFILE_ENTRY
from scripts.hud_apk import repack_apk
from scripts.hud_signing_block import preserve_v2_file
from tests.test_auto_patch_builder import versions, retire_current_recipe


OLD_RECIPE = 'b8df8c71949f43ac5582f41144e0b46dcc73663a96a43bd59b26680117d350a1'
ASSETS = Path(__file__).resolve().parents[1] / 'assets'


def test_published_12116_history_uses_exact_original_template_bytes():
    manifest, template = history.load_previous(ASSETS, OLD_RECIPE, FLY_12116)
    assert manifest['recipe_sha256'] == OLD_RECIPE
    assert manifest['source_sha256'] == FLY_12116.source_sha256
    assert template['kind'] == FLY_12116.profile_kind
    assert template['source_sha256'] == FLY_12116.source_sha256
    expected = {'replacements/' + name for name in FLY_12116.replacement_entries}
    expected.update('additions/' + name for name in history.ADDITION_ENTRIES)
    assert set(manifest['entries']) == expected
    name, digest = history.PREVIOUS_RECIPES[OLD_RECIPE]
    raw = (ASSETS / 'auto-history' / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest
    stored = json.loads(raw)['template_json'].encode('utf-8')
    row = manifest['entries']['additions/' + PROFILE_ENTRY]
    assert len(stored) == row['bytes']
    assert hashlib.sha256(stored).hexdigest() == row['sha256']


@pytest.mark.parametrize('profile', [FLY_1218, FLY_12110])
def test_12116_history_cannot_authorize_another_version(profile):
    with pytest.raises(ValueError, match='selected RC version'):
        history.load_previous(ASSETS, OLD_RECIPE, profile)


def test_unknown_recipe_remains_rejected():
    with pytest.raises(ValueError, match='chưa được kiểm chứng'):
        history.load_previous(ASSETS, 'f' * 64, FLY_12116)


def test_previous_12116_recovers_exact_source_and_builds_current_recipe(versions, tmp_path, monkeypatch):
    assets, profiles, sources = versions
    source, profile = sources[2], profiles[2]
    old = AutoPatchBuilder(assets, tmp_path / 'old')
    candidate = Path(old.build(source)['apk'])
    _, old_digest = retire_current_recipe(assets, profile, monkeypatch)
    current = AutoPatchBuilder(assets, tmp_path / 'current')
    recovered = tmp_path / 'recovered.apk'
    current.recover(candidate, recovered)
    assert recovered.read_bytes() == source.read_bytes()
    assert current.current_recovery is None
    current.menu.keys.ensure.assert_not_called()
    current.tools.sign.assert_not_called()
    with pytest.raises(ValueError):
        current.verify(recovered, candidate)
    result = current.build(recovered)
    assert result['profile']['recipe_sha256'] != old_digest
    assert current.verify(recovered, Path(result['apk']))['digest'] == result['digest']


@pytest.mark.parametrize('entry', ['classes11.dex', 'classes15.dex', 'classes22.dex',
                                  'classes6.dex', 'classes23.dex', 'resources.arsc', PROFILE_ENTRY])
def test_previous_12116_recovery_rejects_changed_payloads(versions, tmp_path, monkeypatch, entry):
    assets, profiles, sources = versions
    old = AutoPatchBuilder(assets, tmp_path / 'old')
    candidate = Path(old.build(sources[2])['apk'])
    retire_current_recipe(assets, profiles[2], monkeypatch)
    with ZipFile(candidate) as archive:
        data = archive.read(entry)
    changed = bytes([data[0] ^ 1]) + data[1:]
    unsigned, signed, tampered = (tmp_path / (name + '.apk') for name in ('unsigned', 'signed', 'tampered'))
    repack_apk(candidate, unsigned, replacements={entry: changed}, additions={})
    old.tools.sign(unsigned, signed)
    preserve_v2_file(candidate, signed, tampered)
    current = AutoPatchBuilder(assets, tmp_path / 'current')
    with pytest.raises((ValueError, json.JSONDecodeError)):
        current.recover(tampered, tmp_path / 'must-not-be-trusted.apk')
    current.menu.keys.ensure.assert_not_called()
    current.tools.sign.assert_not_called()


@pytest.mark.parametrize('change', ['missing', 'unexpected'])
def test_12116_history_requires_exact_version_inventory(tmp_path, monkeypatch, change):
    name, _ = history.PREVIOUS_RECIPES[OLD_RECIPE]
    value = json.loads((ASSETS / 'auto-history' / name).read_bytes())
    entries = value['manifest']['entries']
    if change == 'missing':
        del entries['replacements/classes11.dex']
    else:
        entries['replacements/classes12.dex'] = entries['replacements/classes11.dex']
    raw = json.dumps(value).encode('utf-8')
    directory = tmp_path / 'auto-history'
    directory.mkdir()
    (directory / name).write_bytes(raw)
    monkeypatch.setitem(history.PREVIOUS_RECIPES, OLD_RECIPE,
                        (name, hashlib.sha256(raw).hexdigest()))
    with pytest.raises(ValueError, match='payload inventory differs'):
        history.load_previous(tmp_path, OLD_RECIPE, FLY_12116)


def test_12116_history_is_hash_pinned_before_parsing(tmp_path):
    name, _ = history.PREVIOUS_RECIPES[OLD_RECIPE]
    directory = tmp_path / 'auto-history'
    directory.mkdir()
    (directory / name).write_bytes((ASSETS / 'auto-history' / name).read_bytes() + b' ')
    with pytest.raises(ValueError, match='recipe cũ bị thay đổi'):
        history.load_previous(tmp_path, OLD_RECIPE, FLY_12116)
