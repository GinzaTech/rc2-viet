"""Offline JVM checks for feature extraction and guarded host injection."""
from pathlib import Path
import os
import subprocess

import pytest

from rc2vi.hud_tools import HudTools

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def feature_java(tmp_path_factory):
    stage = tmp_path_factory.mktemp("feature-java")
    bundle = HudTools(ROOT / "assets", stage / "tools").prepare()
    libraries = os.pathsep.join(str(bundle / "lib" / n) for n in ("apktool.jar", "apksigner.jar"))
    sources = ["AdaptiveHudTool", "FeatureAssemblyTool", "FeatureHookTool", "FeatureAuditTool"]
    subprocess.run(["javac", "-encoding", "UTF-8", "-cp", libraries, "-d", str(stage),
                    *(str(ROOT / "android-hud" / (n + ".java")) for n in sources),
                    str(ROOT / "android-hud/test/FeaturePortTest.java")],
                   check=True, capture_output=True, timeout=60)
    return stage, str(stage) + os.pathsep + libraries


def test_host_hook_preserves_fallback_and_rejects_ambiguous_method(feature_java, tmp_path):
    _, classpath = feature_java
    result = subprocess.run(["java", "-cp", classpath, "FeaturePortTest", str(tmp_path)],
                            check=True, capture_output=True, text=True, timeout=60)
    assert "feature_extraction_host_guards_and_dependency_inheritance_passed" in result.stdout
