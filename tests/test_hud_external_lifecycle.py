"""Real output classes on deterministic JVM Android stubs; no device/HDMI proof.

Only this test's fixtures and production CleanPresentation, ExternalOutput, and
OutputGeometry are compiled. OutputProbe is an inert collaborator here: its
virtual-display renderer is deliberately outside this lifecycle suite's scope.
"""
from pathlib import Path
import gc
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "android-hud/test/output-lifecycle-fixture"


@pytest.fixture(scope="module")
def output_classes(tmp_path_factory):
    classes = tmp_path_factory.mktemp("output-lifecycle")
    sources = sorted(FIXTURE.rglob("*.java")) + [
        ROOT / "android-hud/src/local/rc2/hud" / f"{name}.java"
        for name in ("CleanPresentation", "ExternalOutput", "OutputGeometry")
    ]
    # Finalize earlier Tk image cycles on pytest's main thread, before Windows
    # subprocess pipe-reader threads can trigger cyclic garbage collection.
    gc.collect()
    result = subprocess.run(
        ["javac", "-source", "8", "-target", "8", "-encoding", "UTF-8",
         "-d", str(classes), *map(str, sources)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return classes


@pytest.mark.parametrize("scenario", [
    "late-transaction-failure", "dismiss-before-startup", "stale-status",
    "buffer-geometry", "source-resize-forwarded", "intentional-hud",
    "intentional-pause", "intentional-close", "metrics-external-first",
    "metrics-presentation-first", "unexpected-dismiss", "stale-dismiss",
    "inflight-dismiss", "inflight-resize", "fallback-resize", "surface-recreate",
    "late-preview-inflate", "late-preview-surface", "preview-replacement",
    "preview-removal", "same-preview-layout", "layout-listener-pause",
    "layout-listener-close", "layout-owner-replacement",
    "public-copy",
    "diagnostic-snapshot",
])
def test_external_output_lifecycle(output_classes, scenario):
    gc.collect()
    result = subprocess.run(
        ["java", "-cp", str(output_classes),
         "local.rc2.hud.OutputLifecycleTest", scenario],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"output_lifecycle_passed:{scenario}" in result.stdout


@pytest.mark.parametrize("name,scenario,expected_failure", [
    ("unguarded-resize", "late-transaction-failure", "injected later geometry failure"),
    ("late-startup-status", "dismiss-before-startup", "dismissed startup must remain silent"),
    ("unfenced-status", "stale-status", "old renderer must not overwrite HUD selection"),
    ("view-crop", "buffer-geometry", "mirror crop must use buffer frame"),
    ("mutable-diagnostic", "diagnostic-snapshot", "validity must use the same observed preview"),
])
def test_regressions_detect_removed_fixes(tmp_path, name, scenario, expected_failure):
    """Faulted temporary production copies prove behavior assertions catch each fix.

    These are executable negative controls, not source-text assertions. Runtime
    source files remain untouched; each variant must compile and then fail the
    scenario at the corresponding behavioral assertion or injected exception.
    """
    runtime = ROOT / "android-hud/src/local/rc2/hud"
    copies = []
    for class_name in ("CleanPresentation", "ExternalOutput", "OutputGeometry"):
        text = (runtime / f"{class_name}.java").read_text(encoding="utf-8")
        if class_name == "CleanPresentation":
            if name == "unguarded-resize":
                text = text.replace(
                    "catch(RuntimeException | LinkageError error) { startFallback(); }",
                    "catch(RuntimeException | LinkageError error) { throw error; }", 1,
                )
            elif name == "late-startup-status":
                text = text.replace(
                    "if(!alive)return;",
                    'if(!alive) { status.changed("obsolete startup");return; }', 1,
                )
            elif name == "view-crop":
                text = text.replace(
                    "new Rect(0,0,frame.width(),frame.height())",
                    "new Rect(0,0,source.getWidth(),source.getHeight())", 1,
                )
        elif class_name == "ExternalOutput" and name == "unfenced-status":
            text = text.replace(
                "if(!closed && version==generation && clean!=null)status(value);",
                "status(value);", 1,
            )
        elif class_name == "ExternalOutput" and name == "mutable-diagnostic":
            text = text.replace(
                "observed!=null && observed.getHolder().getSurface().isValid()",
                "preview!=null && preview.getHolder().getSurface().isValid()", 1,
            )
        copied = tmp_path / "runtime" / f"{class_name}.java"
        copied.parent.mkdir(parents=True, exist_ok=True)
        copied.write_text(text, encoding="utf-8")
        copies.append(copied)
    classes = tmp_path / "classes"
    gc.collect()
    result = subprocess.run(
        ["javac", "-source", "8", "-target", "8", "-encoding", "UTF-8",
         "-d", str(classes), *map(str, sorted(FIXTURE.rglob("*.java")) + copies)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    gc.collect()
    result = subprocess.run(
        ["java", "-cp", str(classes), "local.rc2.hud.OutputLifecycleTest", scenario],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode != 0, f"negative control {name} escaped its regression test"
    assert expected_failure in result.stdout + result.stderr
