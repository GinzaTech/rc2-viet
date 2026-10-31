"""The desktop resumes matching recipes without reusing an earlier cached APK."""
import hashlib
from dataclasses import replace
from pathlib import Path
import queue
import threading
from types import SimpleNamespace

import pytest

import auto_patch_app as app


@pytest.fixture
def assets(tmp_path):
    root = tmp_path / 'assets'
    for profile in app.SUPPORTED:
        path = root / profile.recipe_directory / 'manifest.json'
        path.parent.mkdir(parents=True)
        path.write_text('{"recipe_sha256":"' + profile.version + '-old"}', encoding='utf-8')
    return root


def test_identical_release_and_serial_resume_across_locations(assets, tmp_path):
    base = tmp_path / 'work'
    first = app.patch_work_directory(base, assets, 'RC2-A')
    first.mkdir(parents=True)
    (first / 'pending-state.json').write_text('retain resume state', encoding='utf-8')
    assert app.patch_work_directory(base, assets, 'RC2-A') == first
    assert (first / 'pending-state.json').read_text('utf-8') == 'retain resume state'
    assert app.patch_work_directory(base, assets, 'RC2-B') != first
    assert app.patch_work_directory(tmp_path / 'other', assets, 'RC2-A').name == first.name


@pytest.mark.parametrize('index', [0, 1, 2])
def test_either_recipe_change_preserves_previous_cached_apk(assets, tmp_path, index):
    base = tmp_path / 'work'
    previous = app.patch_work_directory(base, assets, 'RC2-A')
    cached = previous / 'build/patched.apk'
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b'old verified APK')
    manifest = assets / app.SUPPORTED[index].recipe_directory / 'manifest.json'
    manifest.write_bytes(manifest.read_bytes() + b'\n')
    current = app.patch_work_directory(base, assets, 'RC2-A')
    assert current != previous and not current.exists()
    assert cached.read_bytes() == b'old verified APK'


def test_translation_upgrade_uses_separate_work_directory(assets, tmp_path, monkeypatch):
    previous = app.patch_work_directory(tmp_path, assets, 'RC2-A')
    monkeypatch.setattr(app, 'TRANSLATION_SHA256', '0' * 64)
    assert app.patch_work_directory(tmp_path, assets, 'RC2-A') != previous


def test_version_specific_translation_upgrade_cannot_resume_old_candidate(assets, tmp_path, monkeypatch):
    previous = app.patch_work_directory(tmp_path, assets, 'RC2-A')
    profiles = list(app.SUPPORTED)
    profiles[-1] = replace(profiles[-1], translation_sha256='9' * 64)
    monkeypatch.setattr(app, 'SUPPORTED', tuple(profiles))
    assert app.patch_work_directory(tmp_path, assets, 'RC2-A') != previous


def test_gui_start_avoids_serial_only_r144_cache(assets, tmp_path, monkeypatch):
    base = tmp_path / 'work'
    old = base / ('rc2-' + hashlib.sha256(b'RC2-A').hexdigest()[:16])
    cached = old / 'build/patched.apk'
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b'completed r14.4 build')
    calls = []
    class ImmediateThread:
        def __init__(self, *, target, **kwargs):
            self.target = target
        def start(self):
            self.target()
        def is_alive(self):
            return False
    class Runner:
        def __init__(self, selected_assets, work, serial, *args, **kwargs):
            calls.append((selected_assets, work, serial))
        def run(self, **kwargs):
            assert kwargs == {'grounded': True, 'allow_data_reset': False}
    monkeypatch.setattr(app.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(app, 'AutoPatchRun', Runner)
    monkeypatch.setattr('shutil.disk_usage', lambda path: SimpleNamespace(free=10 * 1024**3))
    desktop = app.App.__new__(app.App)
    desktop.thread = None
    desktop.serial = SimpleNamespace(get=lambda: 'RC2-A')
    desktop.grounded = SimpleNamespace(get=lambda: True)
    desktop.reset = SimpleNamespace(get=lambda: False)
    desktop.assets, desktop.base = assets, base
    desktop.reconnect_event = threading.Event()
    desktop.progress = SimpleNamespace(configure=lambda **kw: None, start=lambda delay: None)
    desktop.stage = SimpleNamespace(set=lambda value: None)
    desktop.events = queue.Queue()
    desktop.controls = lambda: None
    desktop.start()
    assert calls == [(assets, desktop.current_work, 'RC2-A')]
    assert desktop.current_work != old and desktop.current_work.parent == base
    assert cached.read_bytes() == b'completed r14.4 build'
    assert not (desktop.current_work / 'build/patched.apk').exists()


@pytest.mark.parametrize('bad', ['missing', 'oversized'])
def test_unusable_recipe_metadata_fails_before_starting_device_work(assets, tmp_path, bad):
    manifest = assets / app.SUPPORTED[0].recipe_directory / 'manifest.json'
    if bad == 'missing':
        manifest.unlink()
    else:
        manifest.write_bytes(b'x' * (256 * 1024 + 1))
    with pytest.raises(ValueError):
        app.patch_work_directory(tmp_path / 'work', assets, 'RC2-A')
    assert not (tmp_path / 'work').exists()
