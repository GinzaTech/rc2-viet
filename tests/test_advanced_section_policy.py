from pathlib import Path
import subprocess


def test_advanced_and_gimbal_pages_on_real_jvm(tmp_path):
    root = Path(__file__).resolve().parents[1]
    subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(tmp_path),
        str(root/'android-hud/feature-port/local/rc2/hud/AdvancedSectionPolicy.java'),
        str(root/'android-hud/test/AdvancedSectionPolicyTest.java')],
        check=True, capture_output=True, timeout=30)
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.AdvancedSectionPolicyTest'],
                            check=True, capture_output=True, text=True, timeout=30)
    assert 'advanced_and_gimbal_pages_are_allowed' in result.stdout


def test_original_menu_has_one_utilities_entry_with_two_working_child_pages(tmp_path):
    root = Path(__file__).resolve().parents[1]
    files = sorted((root/'android-hud/test/menu-fixture/android').rglob('*.java'))
    files += sorted((root/'android-hud/test/advanced-menu-fixture').rglob('*.java'))
    files += [root/'android-hud/feature-port/local/rc2/hud'/name
              for name in ('AdvancedSectionMenu.java','AdvancedSectionPolicy.java')]
    result = subprocess.run(['javac','-encoding','UTF-8','-d',str(tmp_path),*map(str,files)],
                            capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(['java','-cp',str(tmp_path),'local.rc2.hud.AdvancedSectionHierarchyTest'],
                            capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'original_menu_preserved_with_nested_two_item_utilities' in result.stdout
