"""Exact-byte recovery tests; no SDK, signing, installation or device access."""
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import threading
import warnings
import zipfile

import pytest

from scripts.hud_apk import repack_apk


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        while block := source.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


class NonSeekable(io.BytesIO):
    def seekable(self):
        return False

    def seek(self, *args):
        raise OSError('nonseekable fixture')


def package(path, descriptors=False, extra=None):
    stream = NonSeekable() if descriptors else io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in {
            'AndroidManifest.xml': b'stock manifest', 'classes.dex': b'stock dex',
            'resources.arsc': b'resource data' * 1000,
            'lib/armeabi-v7a/libAppGuard.so': b'native payload' * 1000,
            'META-INF/DJI.RSA': b'original signature', **(extra or {}),
        }.items():
            info = zipfile.ZipInfo(name, (2026, 10, 8, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.extra = b'\xfe\xca\x04\x00TEST'
            archive.writestr(info, data)
        archive.comment = b'original EOCD comment'
    raw = stream.getvalue()
    end = raw.rfind(b'PK\x05\x06')
    central = struct.unpack_from('<I', raw, end + 16)[0]
    gap = b'stock signing block and alignment bytes'
    raw = raw[:central] + gap + raw[central:]
    raw = bytearray(raw)
    struct.pack_into('<I', raw, end + len(gap) + 16, central + len(gap))
    path.write_bytes(raw)
    return path


@pytest.fixture
def setup(tmp_path, monkeypatch):
    from rc2vi import hud_stock as api
    from scripts.bundle_hud_stock import bundle_stock
    stock = package(tmp_path / 'stock.apk', descriptors=True)
    monkeypatch.setattr(api, 'SUPPORTED_APK', digest(stock))
    template = tmp_path / 'template.zip'
    bundle_stock(stock, template)
    monkeypatch.setattr(api, 'SOURCE_RECOVERY_SHA256', digest(template))
    mod = tmp_path / 'mod.apk'
    repack_apk(stock, mod, b'mod manifest', b'helper', b'mod bootstrap')
    return api, stock, template, mod, tmp_path / 'recovered.apk'


def test_exact_recovery_with_descriptors_headers_signing_and_comment(setup):
    api, stock, template, mod, output = setup
    assert api.recover_stock(mod, template, output) == output
    assert output.read_bytes() == stock.read_bytes()
    with zipfile.ZipFile(template) as capsule:
        assert capsule.namelist() == ['recipe.json', 'literals.bin']
        recipe = json.loads(capsule.read('recipe.json'))
        assert recipe['stock_sha256'] == digest(stock)
        assert recipe['literal_size'] < stock.stat().st_size


def test_stock_and_repacked_without_helper_are_supported(setup):
    api, stock, template, mod, output = setup
    api.recover_stock(stock, template, output)
    output.unlink()
    repack_apk(stock, mod, b'mod manifest', None, b'mod dex')
    api.recover_stock(mod, template, output)
    assert digest(output) == digest(stock)


@pytest.mark.parametrize('overrides', [
    {'resources.arsc': b'changed'}, {'unexpected': b'extra'},
    {'../escape': b'unsafe'}, {'C:/escape': b'unsafe'},
    {'a\\b': b'unsafe'}, {'/absolute': b'unsafe'},
])
def test_rejects_extra_unsafe_and_changed_payloads(setup, overrides):
    api, stock, template, mod, output = setup
    package(mod, extra=overrides)
    with pytest.raises(ValueError):
        api.recover_stock(mod, template, output)
    assert not output.exists()
    assert not list(output.parent.glob('.stock-recovery-*'))


def test_rejects_missing_and_duplicate_entries(setup):
    api, stock, template, mod, output = setup
    with zipfile.ZipFile(mod, 'w') as z:
        z.writestr('classes.dex', b'dex')
    with pytest.raises(ValueError):
        api.recover_stock(mod, template, output)
    repack_apk(stock, mod)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with zipfile.ZipFile(mod, 'a') as z:
            z.writestr('classes.dex', b'duplicate')
    with pytest.raises(ValueError):
        api.recover_stock(mod, template, output)


def mutate_central(path, name, offset, fmt, value):
    raw = bytearray(path.read_bytes())
    with zipfile.ZipFile(path) as z:
        pos = z.start_dir
    while raw[pos:pos + 4] == b'PK\x01\x02':
        nl, el, cl = struct.unpack_from('<HHH', raw, pos + 28)
        if raw[pos + 46:pos + 46 + nl].decode() == name:
            struct.pack_into(fmt, raw, pos + offset, value)
            path.write_bytes(raw)
            return
        pos += 46 + nl + el + cl
    raise AssertionError(name)


@pytest.mark.parametrize('offset,fmt,value', [
    (8, '<H', 1), (20, '<I', 0xffffffff), (24, '<I', 0xffffffff),
    (34, '<H', 1), (42, '<I', 0), (10, '<H', 99),
])
def test_rejects_encrypted_zip64_multidisk_overlap_and_method(setup, offset, fmt, value):
    api, stock, template, mod, output = setup
    mutate_central(mod, 'resources.arsc', offset, fmt, value)
    with pytest.raises(ValueError):
        api.recover_stock(mod, template, output)
    assert not output.exists()


@pytest.mark.parametrize('offset,fmt,value', [(24, '<I', 100_000_000), (16, '<I', 0)])
def test_unchanged_metadata_is_checked_without_decompression(setup, offset, fmt, value):
    api, stock, template, mod, output = setup
    mutate_central(mod, 'resources.arsc', offset, fmt, value)
    with pytest.raises(ValueError):
        api.recover_stock(mod, template, output)
    assert not output.exists()


def test_rejects_compressed_payload_corruption(setup):
    api, stock, template, mod, output = setup
    with zipfile.ZipFile(mod) as z:
        entry = z.getinfo('resources.arsc')
    raw = bytearray(mod.read_bytes())
    nl, el = struct.unpack_from('<HH', raw, entry.header_offset + 26)
    raw[entry.header_offset + 30 + nl + el] ^= 1
    mod.write_bytes(raw)
    with pytest.raises(ValueError, match='compressed'):
        api.recover_stock(mod, template, output)
    assert not output.exists()


def test_template_pin_and_final_full_hash_are_mandatory(setup, monkeypatch):
    api, stock, template, mod, output = setup
    monkeypatch.setattr(api, 'SOURCE_RECOVERY_SHA256', '0' * 64)
    with pytest.raises(ValueError, match='template'):
        api.recover_stock(mod, template, output)
    monkeypatch.setattr(api, 'SOURCE_RECOVERY_SHA256', digest(template))
    monkeypatch.setattr(api, 'SUPPORTED_APK', '0' * 64)
    with pytest.raises(ValueError):
        api.recover_stock(mod, template, output)
    assert not output.exists()


def rewrite_recipe(setup, monkeypatch, edit):
    api, stock, template, mod, output = setup
    with zipfile.ZipFile(template) as z:
        recipe, literals = json.loads(z.read('recipe.json')), z.read('literals.bin')
    edit(recipe)
    with zipfile.ZipFile(template, 'w') as z:
        z.writestr('recipe.json', json.dumps(recipe))
        z.writestr('literals.bin', literals)
    monkeypatch.setattr(api, 'SOURCE_RECOVERY_SHA256', digest(template))


@pytest.mark.parametrize('edit', [
    lambda r: r.update(schema=True), lambda r: r.update(extra=1),
    lambda r: r.update(literal_size=10**12),
    lambda r: r['entries'][0].update(header_offset=1),
    lambda r: r['entries'][0].update(compressed_size=-1),
    lambda r: r['entries'][0].update(name='../escape'),
    lambda r: r['entries'].append(r['entries'][0]),
    lambda r: r.update(stock_sha256='0' * 64),
])
def test_bounded_strict_recipe_validation(setup, monkeypatch, edit):
    rewrite_recipe(setup, monkeypatch, edit)
    api, stock, template, mod, output = setup
    with pytest.raises(ValueError):
        api.recover_stock(mod, template, output)
    assert not output.exists()


def test_final_hash_rejects_literal_tampering_even_with_test_pin(setup, monkeypatch):
    api, stock, template, mod, output = setup
    with zipfile.ZipFile(template) as z:
        recipe, literals = z.read('recipe.json'), bytearray(z.read('literals.bin'))
    literals[-1] ^= 1
    with zipfile.ZipFile(template, 'w') as z:
        z.writestr('recipe.json', recipe)
        z.writestr('literals.bin', literals)
    monkeypatch.setattr(api, 'SOURCE_RECOVERY_SHA256', digest(template))
    with pytest.raises(ValueError):
        api.recover_stock(mod, template, output)
    assert not output.exists()


@pytest.mark.parametrize('which', ['stock', 'template', 'existing', 'hardlink'])
def test_output_never_overwrites_any_existing_file(setup, which):
    api, stock, template, mod, output = setup
    if which == 'hardlink':
        os.link(mod, output)
    elif which == 'existing':
        output.write_bytes(b'keep me')
    else:
        output = stock if which == 'stock' else template
    before = output.read_bytes()
    with pytest.raises((ValueError, FileExistsError)):
        api.recover_stock(mod, template, output)
    assert output.read_bytes() == before


def test_cancel_before_and_during_streaming_cleans_partial(setup):
    api, stock, template, mod, output = setup
    event = threading.Event()
    event.set()
    with pytest.raises(api.HudCancelled):
        api.recover_stock(mod, template, output, event)
    def cancel_after_output_started():
        return bool(list(output.parent.glob('.stock-recovery-*')))
    with pytest.raises(api.HudCancelled):
        api.recover_stock(mod, template, output, cancel_after_output_started)
    assert not output.exists()
    assert not list(output.parent.glob('.stock-recovery-*'))


def test_actual_pinned_stock_and_raw_repack_roundtrip(tmp_path):
    from rc2vi import hud_stock as api
    from scripts.bundle_hud_stock import bundle_stock
    stock = Path(os.environ.get('RC2_STOCK_APK',
        r'C:\Users\kona\Downloads\DJI_RC2_VIETNAMESE_20261005\DJI_FLY.apk'))
    if not stock.is_file():
        pytest.skip('Set RC2_STOCK_APK for the optional real-stock integration fixture')
    template = Path(__file__).resolve().parents[1] / 'assets/hud/source-recovery.zip'
    generated = tmp_path / 'generated.zip'
    bundle_stock(stock, generated)
    assert digest(generated) == api.SOURCE_RECOVERY_SHA256 == digest(template)
    assert template.stat().st_size < stock.stat().st_size // 50
    mod, output = tmp_path / 'mod.apk', tmp_path / 'recovered.apk'
    repack_apk(stock, mod, b'replacement manifest', b'helper', b'replacement bootstrap')
    api.recover_stock(mod, template, output)
    assert output.stat().st_size == stock.stat().st_size
    assert digest(output) == api.SUPPORTED_APK
