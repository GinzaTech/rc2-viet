import json
from pathlib import Path

from rc2vi.fly_versions import SUPPORTED


ROOT = Path(__file__).resolve().parents[1]


def test_r13_menu_exposes_requested_controls_and_truthful_ec_restore():
    menu = (ROOT / 'android-hud/src/local/rc2/hud/DeviceMenu.java').read_text('utf-8')
    for label in ('Đèn càng', 'Chạm 2 lần để ẩn / hiện', 'Xuất hình',
                  'Profile sóng', 'FCC', 'EC / gốc'):
        assert label in menu
    assert 'Khôi phục EC hoặc cấu hình radio ban đầu' in menu


def test_r13_utilities_have_exactly_advanced_and_gimbal_calibration():
    policy = (ROOT / 'android-hud/feature-port/local/rc2/hud/AdvancedSectionPolicy.java').read_text('utf-8')
    assert 'TITLES={"Nâng cao","Hiệu chỉnh gimbal"}' in policy
    assert 'FACTORIES={"tabAdvanced","gimbalPage"}' in policy
    assert all(hidden not in policy for hidden in ('"Chung"', '"Điều khiển"', '"An toàn"', '"Bộ chống rung"'))


def test_r13_supports_both_exact_fly_versions_with_matching_recipe_metadata():
    assert [(p.version, p.code) for p in SUPPORTED] == [('1.21.8', 3115809), ('1.21.10', 3115981)]
    expected = ['Nâng cao', 'Hiệu chỉnh gimbal']
    for profile in SUPPORTED:
        manifest = json.loads((ROOT / 'assets' / profile.recipe_directory / 'manifest.json').read_text('utf-8'))
        assert (manifest['version'], manifest['code']) == (profile.version, profile.code)
        assert manifest['source_sha256'] == profile.source_sha256
        assert manifest['visible_menu_sections'] == expected
        assert manifest['menu_hierarchy'] == {'parent': 'Tiện ích nâng cao', 'children': expected}
