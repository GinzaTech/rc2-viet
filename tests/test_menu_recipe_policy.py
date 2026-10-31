"""Check the executable menu payload in every currently supported RC recipe."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
from zipfile import ZipFile

import pytest

from rc2vi.fly_versions import SUPPORTED


ROOT = Path(__file__).resolve().parents[1]


def _method_references(data):
    """Read DEX method IDs; absence also excludes direct host calls to a page."""
    assert data.startswith(b'dex\n')
    string_count, string_offset = struct.unpack_from('<II', data, 0x38)
    type_count, type_offset = struct.unpack_from('<II', data, 0x40)
    method_count, method_offset = struct.unpack_from('<II', data, 0x58)

    def string(index):
        assert index < string_count
        offset = struct.unpack_from('<I', data, string_offset + index * 4)[0]
        for _ in range(5):
            byte = data[offset]
            offset += 1
            if not byte & 0x80:
                break
        else:
            raise AssertionError('Malformed DEX string length')
        return data[offset:data.index(b'\0', offset)]

    types = [string(struct.unpack_from('<I', data, type_offset + i * 4)[0])
             for i in range(type_count)]
    for i in range(method_count):
        owner, _, name = struct.unpack_from('<HHI', data, method_offset + i * 8)
        yield types[owner], string(name)


@pytest.fixture(scope="module")
def payload_auditor(tmp_path_factory):
    work = tmp_path_factory.mktemp("menu-policy")
    manifest = json.loads((ROOT / 'assets/hud/toolchain.json').read_text('utf-8'))
    name = 'lib/apktool.jar'
    with ZipFile(ROOT / 'assets/hud/toolchain.zip') as archive:
        data = archive.read(name)
    assert hashlib.sha256(data).hexdigest() == manifest['files'][name]
    jar = work / 'apktool.jar'
    jar.write_bytes(data)
    result = subprocess.run(['javac', '-encoding', 'UTF-8', '-cp', str(jar), '-d', str(work),
                             str(ROOT / 'android-hud/AdaptiveHudTool.java'),
                             str(ROOT / 'android-hud/test/MenuPolicyPayloadAudit.java')],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return work, os.pathsep.join((str(work), str(jar)))


@pytest.mark.parametrize('profile', SUPPORTED, ids=lambda profile: profile.version)
def test_recipe_payload_cannot_bypass_two_page_menu(profile, payload_auditor):
    work, classpath = payload_auditor
    directory = ROOT / 'assets' / profile.recipe_directory
    metadata = json.loads((directory / 'manifest.json').read_text('utf-8'))
    recipe = directory / 'recipe.zip'
    assert hashlib.sha256(recipe.read_bytes()).hexdigest() == metadata['recipe_sha256']
    dex_files = []
    with ZipFile(recipe) as archive:
        for name in ('classes23.dex', 'classes24.dex'):
            entry = 'additions/' + name
            data = archive.read(entry)
            assert hashlib.sha256(data).hexdigest() == metadata['entries'][entry]['sha256']
            path = work / (profile.version + '-' + name)
            path.write_bytes(data)
            dex_files.append(str(path))
    result = subprocess.run(['java', '-cp', classpath, 'MenuPolicyPayloadAudit', *dex_files],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'two_page_recipe_payload_verified' in result.stdout


@pytest.mark.parametrize('profile', SUPPORTED, ids=lambda profile: profile.version)
def test_patched_host_dex_has_no_direct_hidden_page_reference(profile):
    directory = ROOT / 'assets' / profile.recipe_directory
    metadata = json.loads((directory / 'manifest.json').read_text('utf-8'))
    recipe = directory / 'recipe.zip'
    assert hashlib.sha256(recipe.read_bytes()).hexdigest() == metadata['recipe_sha256']
    hidden = {b'tabBasic', b'tabControl', b'tabSafety'}
    checked = 0
    with ZipFile(recipe) as archive:
        for name in archive.namelist():
            if not name.startswith('replacements/') or not name.endswith('.dex'):
                continue
            references = _method_references(archive.read(name))
            assert not [(owner, method) for owner, method in references
                        if owner == b'Lflysettings/S;' and method in hidden], name
            checked += 1
    assert checked > 0
