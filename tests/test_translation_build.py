from pathlib import Path
import zipfile

import pytest

from rc2vi.translation_build import resource_snapshot


def source_apk(tmp_path, extras=()):
    source = tmp_path / 'source.apk'
    with zipfile.ZipFile(source, 'w') as z:
        z.writestr('AndroidManifest.xml', b'manifest')
        z.writestr('resources.arsc', b'resources')
        for name, content in extras:
            info = zipfile.ZipInfo(name)
            info.filename = name  # Preserve hostile separators instead of Windows normalization.
            z.writestr(info, content)
    return source


def test_snapshot_excludes_executable_and_private_app_assets(tmp_path):
    source = source_apk(tmp_path, [('classes.dex', b'dex'), ('lib/a.so', b'lib'),
                                   ('assets/account.json', b'private'), ('res/xml/page.xml', b'xml')])
    output = tmp_path / 'resources.apk'
    resource_snapshot(source, output)
    with zipfile.ZipFile(output) as z:
        assert set(z.namelist()) == {'AndroidManifest.xml', 'resources.arsc', 'res/xml/page.xml'}
    assert source.exists()


@pytest.mark.parametrize('name', ['res/../../outside', '/res/file', 'res/a\\b',
                                 'res/a:stream', 'res/CON', 'res/a/../b'])
def test_unsafe_apk_paths_rejected_before_decoder(tmp_path, name):
    source = source_apk(tmp_path, [(name, b'bad')])
    with pytest.raises(ValueError):
        resource_snapshot(source, tmp_path / 'resources.apk')


def test_duplicate_resource_entries_are_rejected(tmp_path):
    with pytest.warns(UserWarning):
        source = source_apk(tmp_path, [('resources.arsc', b'other')])
    with pytest.raises(ValueError):
        resource_snapshot(source, tmp_path / 'resources.apk')


def test_snapshot_never_overwrites_existing_file(tmp_path):
    source = source_apk(tmp_path)
    output = tmp_path / 'resources.apk'
    output.write_bytes(b'existing')
    with pytest.raises(FileExistsError):
        resource_snapshot(source, output)
    assert output.read_bytes() == b'existing'


def test_non_apk_and_missing_resource_table_are_rejected(tmp_path):
    source = tmp_path / 'source.apk'
    with zipfile.ZipFile(source, 'w') as z:
        z.writestr('AndroidManifest.xml', b'manifest')
    with pytest.raises(ValueError):
        resource_snapshot(source, tmp_path / 'resources.apk')
