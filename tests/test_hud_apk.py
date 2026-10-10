import warnings
import zipfile

import pytest

from scripts.hud_apk import validate_apk_change, repack_apk


def package(path, overrides=None, added=None):
    contents = {
        'AndroidManifest.xml': b'manifest', 'resources.arsc': b'resources',
        'classes.dex': b'bootstrap', 'classes2.dex': b'dji-code',
        'lib/armeabi-v7a/libAppGuard.so': b'native',
        'META-INF/DJI.RSA': b'certificate', 'META-INF/DJI.SF': b'signature',
        'META-INF/MANIFEST.MF': b'jar-manifest',
    }
    contents.update(overrides or {})
    contents.update(added or {})
    with zipfile.ZipFile(path, 'w') as archive:
        for name, value in contents.items():
            archive.writestr(name, value)
    return path


def test_accepts_only_hook_and_helper_changes(tmp_path):
    stock = package(tmp_path / 'stock.apk')
    candidate = package(tmp_path / 'hud.apk', {'classes.dex': b'hook'}, {'classes23.dex': b'helper'})
    report = validate_apk_change(stock, candidate, b'hook', b'helper')
    assert report['changed'] == ['classes.dex']
    assert report['added'] == ['classes23.dex']


@pytest.mark.parametrize('entry', ['AndroidManifest.xml', 'resources.arsc', 'classes2.dex',
                                  'lib/armeabi-v7a/libAppGuard.so', 'META-INF/DJI.RSA'])
def test_rejects_unrelated_byte_changes(tmp_path, entry):
    stock = package(tmp_path / 'stock.apk')
    candidate = package(tmp_path / 'hud.apk', {entry: b'changed', 'classes.dex': b'hook'}, {'classes23.dex': b'helper'})
    with pytest.raises(ValueError, match='Unexpected'):
        validate_apk_change(stock, candidate, b'hook', b'helper')


def test_rejects_wrong_helper(tmp_path):
    stock = package(tmp_path / 'stock.apk')
    candidate = package(tmp_path / 'hud.apk', {'classes.dex': b'hook'}, {'classes23.dex': b'wrong'})
    with pytest.raises(ValueError, match='helper'):
        validate_apk_change(stock, candidate, b'hook', b'helper')


def test_rejects_duplicate_zip_names(tmp_path):
    stock = package(tmp_path / 'stock.apk')
    candidate = package(tmp_path / 'hud.apk', {'classes.dex': b'hook'}, {'classes23.dex': b'helper'})
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with zipfile.ZipFile(candidate, 'a') as archive:
            archive.writestr('classes23.dex', b'helper')
    with pytest.raises(ValueError, match='Duplicate'):
        validate_apk_change(stock, candidate, b'hook', b'helper')


def test_rejects_removed_stock_entry(tmp_path):
    stock = package(tmp_path / 'stock.apk')
    candidate = tmp_path / 'hud.apk'
    with zipfile.ZipFile(stock) as original, zipfile.ZipFile(candidate, 'w') as result:
        for name in original.namelist():
            if name == 'META-INF/DJI.SF':
                continue
            result.writestr(name, b'hook' if name == 'classes.dex' else original.read(name))
        result.writestr('classes23.dex', b'helper')
    with pytest.raises(ValueError, match='Removed'):
        validate_apk_change(stock, candidate, b'hook', b'helper')


def test_unchanged_control_preserves_every_zip_entry(tmp_path):
    stock = package(tmp_path / 'stock.apk')
    control = package(tmp_path / 'control.apk')
    assert validate_apk_change(stock, control)['changed'] == []


def test_manifest_provider_candidate_changes_no_dji_dex(tmp_path):
    stock = package(tmp_path / 'stock.apk')
    candidate = tmp_path / 'hud.apk'
    repack_apk(stock, candidate, b'provider-manifest', b'helper')
    report = validate_apk_change(stock, candidate, expected_helper=b'helper', expected_manifest=b'provider-manifest')
    assert report['changed'] == ['AndroidManifest.xml']
    assert report['added'] == ['classes23.dex']


def test_repack_never_overwrites_original(tmp_path):
    stock = package(tmp_path / 'stock.apk')
    with pytest.raises(ValueError, match='overwrite'):
        repack_apk(stock, stock, b'manifest', b'helper')


def test_raw_repacked_control_changes_no_entry_bytes(tmp_path):
    stock = package(tmp_path / 'stock.apk')
    control = tmp_path / 'control.apk'
    repack_apk(stock, control)
    assert validate_apk_change(stock, control) == {'changed': [], 'added': []}


def test_raw_repack_startup_hook_matches_exact_expected_dex(tmp_path):
    stock = package(tmp_path / 'stock.apk')
    output = tmp_path / 'hook.apk'
    repack_apk(stock, output, b'new-manifest', b'helper', b'new-bootstrap')
    result = validate_apk_change(stock, output, b'new-bootstrap', b'helper', b'new-manifest')
    assert result['changed'] == ['AndroidManifest.xml', 'classes.dex']


def test_rejects_recompression_of_unchanged_entries(tmp_path):
    stock = package(tmp_path / 'stock.apk')
    output = tmp_path / 'recompressed.apk'
    with zipfile.ZipFile(stock) as source, zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            target.writestr(name, source.read(name))
    with pytest.raises(ValueError, match='container'):
        validate_apk_change(stock, output)
