"""Host JVM regression for the observed 1.21.16 guest Home view tree."""
from pathlib import Path
import os
import shutil
import subprocess
from zipfile import ZipFile

from rc2vi.hud_tools import HudTools
from scripts.build_12116_menu_recipe import _dex_dump, normalize_smali_encoding
from scripts.hotfix_12116_home_anchor import ANCHOR, DUMP_TOOL, TYPE, patch_screen_roles

ROOT = Path(__file__).resolve().parents[1]


def test_guest_home_anchor_is_exact_and_flight_role_keeps_priority(tmp_path):
    runner = tmp_path / 'GuestHomeAnchorTest.java'
    runner.write_text('''package local.rc2.hud;
import java.util.HashSet;
public final class GuestHomeAnchorTest {
 public static void main(String[] args) {
  HashSet<String> ids=new HashSet<>();
  if(ScreenRoles.home(ids::contains))throw new AssertionError("Empty tree is Home");
  ids.add("connection_disconnect_button");
  if(ScreenRoles.home(ids::contains))throw new AssertionError("Generic connection label matched");
  ids.clear();ids.add("go_fly_connection_disconnect_button");
  if(!ScreenRoles.home(ids::contains))throw new AssertionError("Guest Home anchor missing");
  if(ScreenRoles.select("new.pkg.GuestActivity",ids::contains)!=1)throw new AssertionError("Renamed Home not detected");
  ids.add("view_surface");ids.add("top_bar_shell_layout");ids.add("osd_shell_layout");
  if(ScreenRoles.select("new.pkg.GuestActivity",ids::contains)!=2)throw new AssertionError("Flight priority changed");
  ids.clear();ids.add("main_page_ui_device_disconnect_state_button");
  if(!ScreenRoles.home(ids::contains))throw new AssertionError("Existing Home anchor lost");
  System.out.println("guest_home_anchor_passed");
 }
}''', encoding='utf-8')
    subprocess.run(['javac', '-d', str(tmp_path),
                    str(ROOT / 'android-hud/src/local/rc2/hud/ScreenRoles.java'), str(runner)],
                   check=True, capture_output=True, timeout=60)
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.GuestHomeAnchorTest'],
                            check=True, capture_output=True, text=True, timeout=60)
    assert 'guest_home_anchor_passed' in result.stdout


def test_published_bridge_changes_only_screen_roles_home_initializer(tmp_path):
    """Read actual shipped DEX; never load any Android class on the host JVM."""
    tools = HudTools(ROOT / 'assets', tmp_path / 'bundle')
    bundle = tools.prepare()
    classes = tmp_path / 'classes'
    classes.mkdir()
    source = tmp_path / 'Menu12116DexTool.java'
    source.write_text(DUMP_TOOL, encoding='utf-8')
    libcp = os.pathsep.join(str(bundle / 'lib' / name) for name in ('apktool.jar', 'apksigner.jar'))
    subprocess.run(['javac', '-encoding', 'UTF-8', '-cp', libcp, '-d', str(classes),
                    str(ROOT / 'android-hud/AdaptiveHudTool.java'), str(source)],
                   check=True, capture_output=True, timeout=60)
    cp = str(classes) + os.pathsep + libcp
    java_executable = shutil.which('java')
    assert java_executable
    dumped = []
    # The prior shared bridge had no resource/API rebindings on 1.21.16. Its
    # retained 1.21.10 recipe supplies an independently committed comparison.
    for version in ('12110', '12116'):
        with ZipFile(ROOT / ('assets/advanced' + version + '/recipe.zip')) as archive:
            data = archive.read('additions/classes23.dex')
        dex = tmp_path / ('classes23-' + version + '.dex')
        dex.write_bytes(data)
        dumped.append(_dex_dump(Path(java_executable), cp, dex, tmp_path / ('dump-' + version)))
    before, after = dumped
    assert set(before) == set(after) and len(after) == 253
    assert all(normalize_smali_encoding(before[typ]) == normalize_smali_encoding(after[typ])
               for typ in before if typ != TYPE)
    assert normalize_smali_encoding(patch_screen_roles(before[TYPE])) == normalize_smali_encoding(after[TYPE])
    assert after[TYPE].count('"' + ANCHOR + '"') == 1
    assert 'filled-new-array/range {v0 .. v5}, [Ljava/lang/String;' in after[TYPE]
