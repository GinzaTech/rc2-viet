import pytest

from rc2vi.activation import Activator
from rc2vi.core import SUPPORTED_APK


class Adb:
    def shell(self, command, **kwargs):
        return {
            'getprop ro.product.model': 'DJI RC 2', 'getprop ro.product.device': 'rc331',
            'getprop ro.build.version.sdk': '30', 'id': 'uid=0(root)',
            'dumpsys package dji.go.v5': 'versionName=1.21.8\nversionCode=3115809',
            'pm path dji.go.v5': 'package:/data/app/dji/base.apk',
            'sha256sum /data/app/dji/base.apk': 'a' * 64 + ' file',
        }[command]


def test_dynamic_hud_requires_independently_verified_stock_recipe(tmp_path):
    def trusted(digest):
        assert digest == 'a' * 64
        return {'digest': digest, 'source_digest': SUPPORTED_APK}
    activator = Activator(tmp_path, tmp_path, lambda *e: None, verify_assets=False, trusted_hud=trusted)
    assert activator.verify(Adb()) == '/data/app/dji/base.apk'


def test_dynamic_hud_does_not_accept_callback_digest_or_source_mismatch(tmp_path):
    for result in [{'digest': 'b' * 64, 'source_digest': SUPPORTED_APK},
                   {'digest': 'a' * 64, 'source_digest': 'b' * 64}]:
        activator = Activator(tmp_path, tmp_path, lambda *e: None, False, trusted_hud=lambda digest: result)
        with pytest.raises(ValueError):
            activator.verify(Adb())
