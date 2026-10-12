"""Publish boundary: experimental builds and reference mods stay outside this repo."""
from pathlib import Path
import json
import pytest

from rc2vi.hud_variants import validate_variant
from scripts import package_windows

ROOT=Path(__file__).resolve().parents[1]


def test_public_profile_rejects_nonbasic_values():
    for value in ('advanced','../advanced','redfly',None,{},True):
        with pytest.raises(ValueError):
            validate_variant(value)
    assert validate_variant('basic').value=='basic'


def test_public_assets_and_source_exclude_experimental_components():
    for relative in ('android-hud/advanced','android-hud/feature-port',
                     'assets/hud/advanced.dex','assets/hud/advanced-payload.json',
                     'scripts/build_feature_candidate.py','scripts/feature_host_patch.py'):
        assert not (ROOT/relative).exists(), relative
    content=(ROOT/'assets/hud/classes23.dex').read_bytes()
    for name in (b'AdvancedMenu',b'AdvancedSdk',b'AdvancedJob',b'PortIntegration',b'PortHooks'):
        assert name not in content


def test_public_release_has_only_basic_and_no_reference_mod():
    flags=package_windows.FLAGS
    assert flags['menu_variants']==['basic']
    assert flags['experimental_features_bundled'] is False
    assert flags['reference_mod_used'] is False
    assert not any('REDFLY' in path or 'DUAL_VARIANTS' in path for path in package_windows.DOCS.values())


def test_private_snapshot_is_outside_git_and_has_verified_artifacts():
    private=ROOT.parent/'rc2-viet-advanced-local'
    if not private.exists():
        pytest.skip('Local private snapshot is intentionally not distributed')
    assert not private.is_relative_to(ROOT)
    assert not (private/'.git').exists()
    value=json.loads((private/'LOCAL_ONLY.json').read_text('utf-8'))
    assert value['publish_allowed'] is False and value['local_only'] is True
    assert (private/'local-artifacts/DJI-Fly-RC2-Advanced.apk').is_file()


def test_staging_drops_unknown_and_experimental_assets(tmp_path):
    from scripts.stage_desktop_assets import stage_assets
    source=tmp_path/'source'
    (source/'hud/history').mkdir(parents=True)
    (source/'adb').mkdir()
    (source/'adb/adb.exe').write_bytes(b'public adb fixture')
    (source/'hud/advanced.dex').write_bytes(b'private AdvancedMenu')
    (source/'hud/history/unknown.dex').write_bytes(b'private AdvancedSdk')
    (source/'surprise.bin').write_bytes(b'private')
    target=tmp_path/'staged'
    stage_assets(source,target)
    assert [p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()]==['adb/adb.exe']


def test_staging_rejects_a_private_class_in_a_public_slot(tmp_path):
    from scripts.stage_desktop_assets import stage_assets
    source=tmp_path/'source'
    (source/'hud').mkdir(parents=True)
    (source/'hud/classes23.dex').write_bytes(b'dex private AdvancedMenu')
    with pytest.raises(ValueError,match='Private experiment'):
        stage_assets(source,tmp_path/'staged')
