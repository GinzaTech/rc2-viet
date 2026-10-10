from unittest.mock import Mock
import pytest

from rc2vi.activation import Activator
from rc2vi.core import SUPPORTED_APK, HUD_APK
from test_activation import FakeAdb


@pytest.mark.parametrize('digest', [SUPPORTED_APK, HUD_APK, 'a'*64])
def test_stock_and_hud_hashes_use_adaptive_without_receipt_lookup(tmp_path,digest):
    trusted=Mock(side_effect=AssertionError('Translation must not consult HUD recipes'))
    adaptive=Mock();adaptive.apply.return_value={'status':'enabled'}
    activator=Activator(tmp_path,tmp_path,Mock(),False,trusted_hud=trusted,adaptive=adaptive)
    adb=FakeAdb(hash_value=digest)
    assert activator.verify(adb)==adb.target
    assert activator.target_info=={'version':'1.21.8','code':3115809,'digest':digest}
    assert activator.apply(adb) is adaptive.apply.return_value
    adaptive.apply.assert_called_once()
    trusted.assert_not_called()
    assert not adb.mutations
