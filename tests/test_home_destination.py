from pathlib import Path
import subprocess


def test_new_rc_launcher_is_preferred_and_lawnchair_is_only_fallback(tmp_path):
    source=Path(__file__).parents[1]/'android-home'
    subprocess.run(['javac','-encoding','UTF-8','-d',str(tmp_path),
                    str(source/'src/local/rc2/home/LauncherDestination.java'),
                    str(source/'test/local/rc2/home/LauncherDestinationTest.java')],check=True,capture_output=True)
    subprocess.run(['java','-cp',str(tmp_path),'local.rc2.home.LauncherDestinationTest'],check=True,capture_output=True)
