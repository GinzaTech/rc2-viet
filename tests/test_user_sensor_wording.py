from pathlib import Path
import xml.etree.ElementTree as ET
import pytest


@pytest.mark.parametrize('locale',['values','values-en','values-en-rUS','values-vi'])
def test_sensor_system_translation_is_consistent_in_each_rc_locale(locale):
    file=Path(__file__).resolve().parents[1]/'translation/review-round2/overlay/res'/locale/'strings.xml'
    strings={e.get('name'):e.text for e in ET.parse(file).getroot()}
    assert strings['fpv_basic_flight_topbar_panel_tof_obstacle_avoid_state']=='Hệ thống cảm biến'
    assert not any('Hệ thống nhạy cảm' in (text or '') for text in strings.values())
