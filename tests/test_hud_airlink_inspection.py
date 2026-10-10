"""Host-only pinned SDK contract and lifecycle checks, not aircraft proof."""
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "android-hud/test/airlink-fixture"


@pytest.fixture(scope="module")
def airlink_classes(tmp_path_factory):
    classes = tmp_path_factory.mktemp("airlink-inspection")
    sources = sorted(FIXTURE.rglob("*.java")) + [
        ROOT / "android-hud/src/local/rc2/hud/AirlinkInspection.java",
        ROOT / "android-hud/test/local/rc2/hud/AirlinkInspectionTest.java",
    ]
    result = subprocess.run(
        ["javac", "-source", "8", "-target", "8", "-encoding", "UTF-8",
         "-d", str(classes), *map(str, sources)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return classes


@pytest.mark.parametrize("scenario", [
    "success", "partial", "failures", "values", "wrong-key", "duplicate",
    "timeout", "close", "inactive", "busy", "binding", "scheduler",
    "immediate", "objects", "races", "boundaries", "stalled",
])
def test_airlink_read_only_contract(airlink_classes, scenario):
    result = subprocess.run(
        ["java", "-cp", str(airlink_classes),
         "local.rc2.hud.AirlinkInspectionTest", scenario],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"airlink_inspection_passed:{scenario}" in result.stdout


def test_airlink_signature_evidence_has_no_mode_mapping():
    pin = json.loads((FIXTURE / "stock-signatures.json").read_text(encoding="utf-8"))
    assert pin["stock_version"] == "1.21.8"
    assert pin["stock_sha256"] == "cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e"
    assert pin["area_value_class"] == "uav.sdk.keyvalue.value.common.AreaCodeInfo"
    assert pin["keys"] == {"w": "AreaCodeFromSky", "x": "AreaCodeFromGround"}
    assert pin["effective_mode_mapping_verified"] is False
    assert pin["candidates"]["N"]["getters"] == [
        "getTxPowerOffset", "getDistOffset", "getPathLossOffset", "getRcLinkOffset",
    ]
    assert pin["candidates"]["U"]["value_type"] == "java.lang.Integer"


@pytest.mark.parametrize("relative,old,new", [
    ("key/UAVKeyInfoBase.java", "public String e()", "public Object e()"),
    ("key/UAVKey.java", "public static UAVKey i(", "public static Object i("),
    ("key/UAVKey.java", "public static UAVKey i(", "public UAVKey i("),
    ("UAVKeyManager.java", "public static void t(", "public void t("),
    ("value/common/AreaCodeInfo.java", "public Integer getAcValue()", "public Number getAcValue()"),
    ("value/common/AreaCodeInfo.java", "public String getAreaCode()", "public Object getAreaCode()"),
])
def test_airlink_rejects_signature_drift_before_any_get(tmp_path, relative, old, new):
    sources = []
    for source in FIXTURE.rglob("*.java"):
        target = tmp_path / "fixtures" / source.relative_to(FIXTURE)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = source.read_text(encoding="utf-8")
        if source.relative_to(FIXTURE).as_posix() == "uav/sdk/keyvalue/" + relative:
            assert old in content
            content = content.replace(old, new)
        target.write_text(content, encoding="utf-8")
        sources.append(target)
    classes = tmp_path / "classes"
    result = subprocess.run(
        ["javac", "-source", "8", "-target", "8", "-encoding", "UTF-8", "-d", str(classes),
         *map(str, sources), str(ROOT / "android-hud/src/local/rc2/hud/AirlinkInspection.java"),
         str(ROOT / "android-hud/test/local/rc2/hud/AirlinkSignatureMismatchTest.java")],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    result = subprocess.run(
        ["java", "-cp", str(classes), "local.rc2.hud.AirlinkSignatureMismatchTest"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "airlink_signature_mismatch_passed" in result.stdout
