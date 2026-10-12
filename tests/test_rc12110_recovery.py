"""Separate template pins, independent of APK version labels supplied by callers."""
import hashlib
from pathlib import Path
from unittest.mock import Mock
import pytest
from rc2vi import hud_stock, hud_device_source
from tests.test_hud_stock import package
from scripts.bundle_hud_stock import bundle_stock
from scripts.hud_apk import repack_apk
from tests.test_hud_build import project


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def test_recovery_uses_the_independent_12110_pin_and_exact_bytes(tmp_path,monkeypatch):
    stock=package(tmp_path/'current.apk',descriptors=True)
    template=tmp_path/'current-recovery.zip'
    target_hash=digest(stock)
    with monkeypatch.context() as context:
        context.setattr(hud_stock,'SUPPORTED_APK',target_hash)
        bundle_stock(stock,template)
    monkeypatch.setattr(hud_stock,'RC_12110_APK',target_hash)
    monkeypatch.setattr(hud_stock,'SOURCE_RECOVERY_12110_SHA256',digest(template))
    mod=tmp_path/'mod.apk'
    repack_apk(stock,mod,b'mod manifest',b'helper',b'mod bootstrap')
    result=hud_stock.recover_stock(mod,template,tmp_path/'restored.apk',expected_digest=target_hash)
    assert result.read_bytes()==stock.read_bytes()
    with pytest.raises(ValueError,match='template'):
        hud_stock.recover_stock(mod,template,tmp_path/'wrong.apk')


def test_provided_12110_template_identity_is_bound_to_its_known_source():
    root=Path(__file__).resolve().parents[1]
    path=root/'assets/hud/source-recovery-1.21.10.zip'
    assert digest(path)==hud_stock.SOURCE_RECOVERY_12110_SHA256
    from zipfile import ZipFile
    with ZipFile(path) as archive:
        value=hud_stock.recipe_value(archive,expected_digest=hud_stock.RC_12110_APK)
    assert value['stock_size']==468109376


def test_legacy_receipt_and_pulled_apk_replay_carry_the_12110_source_pin(project,monkeypatch):
    from rc2vi import hud_build
    builder,stock,_=project
    source_hash=digest(stock)
    monkeypatch.setattr(hud_build,'RC_12110_APK',source_hash)
    monkeypatch.setattr(hud_build,'SUPPORTED_APK','0'*64)
    # The legacy builder writes the actual source digest; only its supported set changes.
    result=builder.build(stock)
    assert result['source_digest']==source_hash
    checked=builder.verify_device_apk(result['apk'],stock)
    assert checked['source_digest']==source_hash
    assert builder.verify(result['receipt'])['source_digest']==source_hash
