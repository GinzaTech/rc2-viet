"""Fail-closed inputs and bytecode preservation for the RC 1.21.18 port."""
from pathlib import Path

import pytest
from scripts import build_12118_menu_recipe as port


def test_older_stock_cannot_be_relabelled_as_12118(tmp_path):
    source, reference = tmp_path / '1.21.16.apk', tmp_path / 'reference.apk'
    source.write_bytes(b'older DJI Fly stock')
    reference.write_bytes(b'reference')
    stage, output = tmp_path / 'work', tmp_path / 'recipe'
    with pytest.raises(ValueError, match='independently pinned'):
        port.build(source, reference, tmp_path / 'jdk', stage, output)
    assert not stage.exists()
    assert not output.exists()


def test_reference_stock_mismatch_is_refused_before_tools(tmp_path, monkeypatch):
    source, reference = tmp_path / '1.21.18.apk', tmp_path / 'reference.apk'
    source.touch()
    reference.touch()
    monkeypatch.setattr(port, 'sha256_file', lambda path: port.SOURCE_SHA256 if path == source else '0' * 64)
    stage, output = tmp_path / 'work', tmp_path / 'recipe'
    with pytest.raises(ValueError, match='independently pinned'):
        port.build(source, reference, tmp_path / 'jdk', stage, output)
    assert not stage.exists()
    assert not output.exists()


@pytest.mark.parametrize('existing', ['work', 'recipe'])
def test_existing_build_or_published_output_is_never_overwritten(tmp_path, monkeypatch, existing):
    source, reference = tmp_path / 'stock.apk', tmp_path / 'reference.apk'
    source.touch()
    reference.touch()
    monkeypatch.setattr(port, 'sha256_file', lambda path: port.SOURCE_SHA256 if path == source else port.REFERENCE_SHA256)
    stage, output = tmp_path / 'work', tmp_path / 'recipe'
    occupied = tmp_path / existing
    occupied.mkdir()
    marker = occupied / 'keep'
    marker.write_bytes(b'preserved')
    with pytest.raises(ValueError, match='must both be new'):
        port.build(source, reference, tmp_path / 'jdk', stage, output)
    assert marker.read_bytes() == b'preserved'


def test_resource_rebinding_requires_the_actual_named_target():
    with pytest.raises(ValueError, match='Unbound resource'):
        port.remap_resource_literals('    const v0, 0x7f010001\n', {})
    source = '    const v0, 0x7f010001\n    const-string v1, "0x7f010001" # 0x7f010001\n'
    changed, refs = port.remap_resource_literals(source, {0x7f010001: 0x7f020002})
    assert changed == source.replace('const v0, 0x7f010001', 'const v0, 0x7f020002')
    assert len(refs) == 1


@pytest.mark.parametrize('replacement', ['if-eqz v0, :cond_2', 'if-nez v0, :cond_1'])
def test_semantic_guard_catches_a_changed_branch(replacement):
    source = ('.method public a()V\n    .registers 1\n    if-eqz v0, :cond_1\n'
              '    :cond_1\n    const/4 v0, 0x0\n    :cond_2\n    return-void\n.end method\n')
    changed = source.replace('if-eqz v0, :cond_1', replacement)
    assert port.normalize_smali_encoding(source) != port.normalize_smali_encoding(changed)


def test_semantic_guard_preserves_literal_label_text():
    source = ('.method public a()V\n    .registers 1\n    const-string v0, ":cond_1"\n'
              '    goto :cond_1\n    :cond_1\n    return-void\n.end method\n')
    moved = source.replace('goto :cond_1', 'goto :cond_4').replace('    :cond_1\n', '    :cond_4\n')
    assert port.normalize_smali_encoding(source) == port.normalize_smali_encoding(moved)
    assert '":cond_1"' in port.normalize_smali_encoding(moved)


HOME_ROLE = ('.class final Llocal/rc2/hud/ScreenRoles;\n.super Ljava/lang/Object;\n'
             '.method static constructor <clinit>()V\n    .registers 16\n'
             '    const-string v5, "go_fly_connection_disconnect_button"\n\n'
             '    filled-new-array/range {v0 .. v5}, [Ljava/lang/String;\n'
             '    move-result-object v0\n    sput-object v0, Llocal/rc2/hud/ScreenRoles;->HOME:[Ljava/lang/String;\n'
             '    return-void\n.end method\n'
             '.method static sentinel()Z\n    .registers 1\n    const/4 v0, 0x0\n    return v0\n.end method\n')


def test_connected_home_edit_is_limited_to_initializer():
    changed = port.patch_connected_home(HOME_ROLE)
    assert changed.count('"go_fly_connection_startfly_button"') == 1
    assert changed.count('"go_fly_connection_disconnect_button"') == 1
    assert 'filled-new-array/range {v0 .. v6}, [Ljava/lang/String;' in changed
    assert port._method(changed, 'sentinel()Z') == port._method(HOME_ROLE, 'sentinel()Z')
    with pytest.raises(ValueError, match='already patched'):
        port.patch_connected_home(changed)


@pytest.mark.parametrize('old,new', [('.registers 16', '.registers 15'),
                                    ('go_fly_connection_disconnect_button', 'unknown_anchor'),
                                    ('{v0 .. v5}', '{v0 .. v4}')])
def test_connected_home_edit_refuses_an_unrecognized_initializer(old, new):
    with pytest.raises(ValueError, match='initializer differs'):
        port.patch_connected_home(HOME_ROLE.replace(old, new))


def test_current_home_detection_and_menu_power_layout_on_jvm(tmp_path):
    import subprocess
    root = Path(__file__).resolve().parents[1]
    runner = tmp_path / 'ConnectedHome12118Test.java'
    runner.write_text('''package local.rc2.hud;
public final class ConnectedHome12118Test {
 static void check(boolean value, String message) { if (!value) throw new AssertionError(message); }
 public static void main(String[] args) {
  check(ScreenRoles.HOME.length == 7, "Home anchor inventory");
  for (String anchor : new String[]{"go_fly_connection_startfly_button", "go_fly_connection_disconnect_button"}) {
   check(ScreenRoles.home(n -> n.equals(anchor)), "Home anchor missing");
   check(ScreenRoles.select("example.RenamedHome", n -> n.equals(anchor)) == 1, "Obfuscated Home missing");
  }
  check(ScreenRoles.select("example.Other", n -> false) == 0, "False Home match");
  check(ScreenRoles.select("example.FpvComponentActivity", n -> true) == 2, "FPV priority changed");
  int[] menu = MenuPlacement.place(1222,921,100,0,0,1920,1080,100,17,17);
  check(menu[0] + 100 < 1222, "Menu overlaps Start Fly");
  int[] power = HomeActionPlacement.place(menu[0],menu[1],100,100,0,0,1920,1080,100,100,17,17);
  check(power != null && power[0] + 100 < menu[0] && power[1] == menu[1], "Power overlaps menu");
  System.out.println("connected_home_12118_passed");
 }
}''', encoding='utf-8')
    subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(tmp_path), str(runner),
                    str(root / 'android-hud/src/local/rc2/hud/ScreenRoles.java'),
                    str(root / 'android-hud/src/local/rc2/hud/MenuPlacement.java'),
                    str(root / 'android-hud/feature-port/local/rc2/hud/HomeActionPlacement.java')],
                   capture_output=True, check=True, timeout=60)
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.ConnectedHome12118Test'],
                            capture_output=True, check=True, text=True, timeout=60)
    assert 'connected_home_12118_passed' in result.stdout
