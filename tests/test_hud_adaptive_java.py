"""Runnable JVM structural checks; no Android runtime or device connection."""
from pathlib import Path
import os
import subprocess
from rc2vi.hud_tools import HudTools

ROOT=Path(__file__).resolve().parents[1]


def test_renamed_bootstrap_register_count_tail_and_unrelated_class_preservation(tmp_path):
    tools=HudTools(ROOT/'assets',tmp_path/'tools')
    bundle=tools.prepare()
    cp=os.pathsep.join(str(bundle/'lib'/n) for n in ('apktool.jar','apksigner.jar'))
    classes=tmp_path/'classes';classes.mkdir()
    subprocess.run(['javac','-encoding','UTF-8','-cp',cp,'-d',str(classes),
                    str(ROOT/'android-hud/AdaptiveHudTool.java'),str(ROOT/'android-hud/test/AdaptiveHudToolTest.java')],
                   check=True,capture_output=True,timeout=60)
    work=tmp_path/'work';work.mkdir()
    result=subprocess.run(['java','-cp',str(classes)+os.pathsep+cp,'AdaptiveHudToolTest',str(work)],
                          check=True,capture_output=True,text=True,timeout=60)
    assert 'adaptive_bootstrap_preserved_classes_and_tail' in result.stdout


def test_view_roles_reject_preview_only_and_support_renamed_activity_without_class_hint(tmp_path):
    runner=tmp_path/'ScreenRolesTest.java'
    runner.write_text('''package local.rc2.hud;
import java.util.Arrays;
import java.util.HashSet;
public class ScreenRolesTest {
 public static void main(String[] args) {
  HashSet<String> ids=new HashSet<>(Arrays.asList("view_surface"));
  if(ScreenRoles.flight(ids::contains)||ScreenRoles.home(ids::contains))throw new AssertionError();
  ids.add("top_bar_shell_layout");ids.add("osd_shell_layout");
  if(!ScreenRoles.flight(ids::contains))throw new AssertionError();
  ids.add("direct_enter_fpv_view");if(!ScreenRoles.home(ids::contains))throw new AssertionError();
  if(ScreenRoles.select("new.pkg.FpvComponentActivity",ids::contains)!=2)throw new AssertionError("Camera misclassified as Home");
  if(ScreenRoles.select("new.pkg.RenamedActivity",ids::contains)!=2)throw new AssertionError("Specific preview role lost");
  ids.remove("top_bar_shell_layout");
  if(ScreenRoles.select("new.pkg.RenamedActivity",ids::contains)!=1)throw new AssertionError("Home role lost");
  System.out.println("view_roles_passed");
 }
}''','utf-8')
    subprocess.run(['javac','-d',str(tmp_path),str(ROOT/'android-hud/src/local/rc2/hud/ScreenRoles.java'),str(runner)],
                   check=True,capture_output=True)
    result=subprocess.run(['java','-cp',str(tmp_path),'local.rc2.hud.ScreenRolesTest'],check=True,capture_output=True,text=True)
    assert 'view_roles_passed' in result.stdout
