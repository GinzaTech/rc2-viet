"""External picture geometry/resource limits; not proof of physical HDMI connectivity."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_external_picture_letterbox_and_bounded_copy_size(tmp_path):
    files = [ROOT / 'android-hud/src/local/rc2/hud/OutputGeometry.java',
             ROOT / 'android-hud/test/local/rc2/hud/OutputGeometryTest.java']
    result = subprocess.run(['javac', '-encoding', 'UTF-8', '-d', str(tmp_path),
                             *map(str, files)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(['java', '-cp', str(tmp_path), 'local.rc2.hud.OutputGeometryTest'],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'output_geometry_passed' in result.stdout
