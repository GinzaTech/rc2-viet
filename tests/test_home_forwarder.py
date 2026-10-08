from pathlib import Path
import subprocess


def test_home_forwarding_lifecycle(tmp_path):
    source=Path(__file__).parents[1]/'android-home'
    subprocess.run(['javac','-encoding','UTF-8','-d',str(tmp_path),
                    str(source/'src/local/rc2/home/HomeForwarder.java'),
                    str(source/'test/local/rc2/home/HomeForwarderTest.java')],check=True,
                   capture_output=True,text=True)
    result=subprocess.run(['java','-cp',str(tmp_path),'local.rc2.home.HomeForwarderTest'],
                          check=True,capture_output=True,text=True)
    assert '6 home-forwarding scenarios passed' in result.stdout
