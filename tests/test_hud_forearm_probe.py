"""PC-only contract/lifecycle tests for the in-process named forearm GET."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_forearm_param_probe_contract_and_lifecycle(tmp_path):
    fixtures = sorted((ROOT / "android-hud/test/forearm-fixture").rglob("*.java"))
    sources = [
        ROOT / "android-hud/src/local/rc2/hud/ForearmParamProbe.java",
        ROOT / "android-hud/test/local/rc2/hud/ForearmParamProbeTest.java",
    ]
    compile_result = subprocess.run(
        ["javac", "-source", "8", "-target", "8", "-encoding", "UTF-8",
         "-d", str(tmp_path), *map(str, fixtures + sources)],
        capture_output=True, text=True, timeout=30,
    )
    assert compile_result.returncode == 0, compile_result.stderr
    result = subprocess.run(
        ["java", "-cp", str(tmp_path), "local.rc2.hud.ForearmParamProbeTest"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "forearm_param_probe_passed" in result.stdout
