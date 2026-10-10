"""Executable DeviceMenu interactions on API-30-shaped JVM UI stubs.

Compile the current production menu, placement, gate and typed LED contracts.
Backend collaborators are inert recorders; this is not Android rendering/device
or hardware verification. No SDK, ADB, network, APK or product binary is used.
"""
from pathlib import Path
import gc
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "android-hud/test/menu-fixture"


@pytest.fixture(scope="module")
def menu_classes(tmp_path_factory):
    classes = tmp_path_factory.mktemp("device-menu")
    source = ROOT / "android-hud/src/local/rc2/hud"
    files = sorted(FIXTURE.rglob("*.java")) + [
        source / f"{name}.java"
        for name in ("DeviceMenu", "MenuPlacement", "GroundGate", "LedJob")
    ]
    gc.collect()
    result = subprocess.run(
        ["javac", "-source", "8", "-target", "8", "-encoding", "UTF-8",
         "-d", str(classes), *map(str, files)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return classes


@pytest.mark.parametrize("scenario", [
    "unknown", "independent-front", "independent-rear", "all-off", "all-on",
    "partial-rear-status", "partial-rear-tail", "front-repeat", "rear-repeat",
    "pending", "success-readback", "failure-readback", "inspect-failure",
    "ground-disconnected", "ground-motors", "ground-flying", "ground-stale",
    "ground-click-race", "rapid-click", "radio-busy", "radio-locked",
    "dismiss-read", "dismiss-write", "queued-dismiss", "reopen-stale-read",
    "dispose", "dispose-pending", "explicit-all-on", "explicit-all-off",
    "radio-confirmation", "radio-restore-confirmation", "narrow-interactive", "ui-close",
    "rejected-no-callback", "rejected-inline-failure", "completion-get-failure",
    "queued-write-dismiss", "read-failure-reopen",
    "late-reconciliation", "reconciliation-closed", "reconciliation-disposed",
    "reconciliation-reopen", "reconciliation-reopen-reading",
    "reconciliation-busy", "reconciliation-reading", "reconciliation-burst",
    "reconciliation-queued-dismiss", "reconciliation-queued-dispose",
    "reconciliation-read-failure",
])
def test_device_menu_interaction(menu_classes, scenario):
    gc.collect()
    result = subprocess.run(
        ["java", "-cp", str(menu_classes),
         "local.rc2.hud.DeviceMenuInteractionTest", scenario],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"device_menu_passed:{scenario}" in result.stdout
