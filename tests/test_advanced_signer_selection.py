"""Stable desktop signer selection; temporary metadata only, no real keys/USB."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

import advanced_app as app
from rc2vi import advanced_patch, hud_keys


@pytest.fixture
def selection(monkeypatch, tmp_path):
    local = tmp_path / 'local-appdata'
    stable = local / 'RC2Studio/signing'
    legacy = local / 'RC2Vietnamese/hud-signing'
    fallback = tmp_path / 'existing-app-work/advanced-signing'
    monkeypatch.setenv('LOCALAPPDATA', str(local))
    monkeypatch.setattr(app, 'paths', lambda: (tmp_path / 'assets', fallback.parent))
    tools = SimpleNamespace(cancel=None)
    def no_key_operation(*args, **kwargs):
        pytest.fail('Signer selection must not generate or inspect key material')
    tools.generate_key = no_key_operation
    tools.keycert = no_key_operation
    seen = []
    class Builder:
        def __init__(self, assets, work, emit, *, cancel=None, profile=None):
            self.tools = tools
            seen.append((assets, work, emit, cancel, profile))
    monkeypatch.setattr(advanced_patch, 'AdvancedBuilder', Builder)
    def build():
        return app.builder_factory(tmp_path / 'assets', tmp_path / 'other-drive-work',
                                   lambda *event: None, profile='selected-version')
    return SimpleNamespace(stable=stable, legacy=legacy, fallback=fallback,
                           build=build, seen=seen)


def marker(root, value='{}'):
    root.mkdir(parents=True)
    path = root / 'signer.json'
    path.write_text(value, encoding='utf-8')
    return path


def test_retained_stable_identity_wins_over_existing_legacy_and_workdir(selection):
    stable = marker(selection.stable)
    legacy = marker(selection.legacy)
    selected = selection.build()
    assert isinstance(selected.keys, hud_keys.HudKeyStore)
    assert selected.keys.root == selection.stable
    assert selected.keys.root != selection.seen[0][1]
    assert selection.seen[0][-1] == 'selected-version'
    assert stable.read_text(encoding='utf-8') == legacy.read_text(encoding='utf-8') == '{}'
    assert not selection.fallback.exists()


def test_existing_legacy_identity_is_reused_when_stable_identity_absent(selection):
    legacy = marker(selection.legacy)
    selection.stable.mkdir(parents=True)  # Empty reserved store is not an identity.
    selected = selection.build()
    assert selected.keys.root == selection.legacy
    assert legacy.read_text(encoding='utf-8') == '{}'
    assert not (selection.stable / 'signer.json').exists()
    assert not selection.fallback.exists()


def test_no_identity_preserves_previous_advanced_fallback(selection):
    selected = selection.build()
    assert selected.keys.root == selection.fallback
    assert not selection.stable.exists()
    assert not selection.legacy.exists()
    assert not selection.fallback.exists()  # Selection does not initialize a signer.


@pytest.mark.parametrize('operation', ['load', 'ensure'])
def test_corrupt_stable_metadata_fails_without_fallback_or_new_identity(selection, monkeypatch, operation):
    stable = marker(selection.stable, '{malformed-json')
    legacy = marker(selection.legacy)
    # Exercise the real load/ensure and metadata validation; only OS locking/ACLs
    # are omitted because this fixture contains no key material or credentials.
    @contextmanager
    def no_lock(_store):
        yield
    monkeypatch.setattr(hud_keys.HudKeyStore, '_locked', no_lock)
    selected = selection.build()
    with pytest.raises(ValueError, match='JSON'):
        getattr(selected.keys, operation)()
    assert selected.keys.root == selection.stable
    assert stable.read_text(encoding='utf-8') == '{malformed-json'
    assert legacy.read_text(encoding='utf-8') == '{}'
    assert set(path.name for path in selection.stable.iterdir()) == {'signer.json'}
    assert not selection.fallback.exists()
