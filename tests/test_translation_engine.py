import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from rc2vi import translation_engine as module


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    assets = tmp_path / 'assets'
    (assets / 'translation').mkdir(parents=True)
    source = tmp_path / 'source'
    engine_id = 'a' * 24
    files = {}
    for name in module.REQUIRED:
        p = source / engine_id / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(('synthetic-' + name).encode())
        files[name] = {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
    manifest = {'schema': 1, 'engine_id': engine_id, 'files': files}
    raw = json.dumps(manifest).encode()
    (assets / 'translation/engine.json').write_bytes(raw)
    monkeypatch.setattr(module, 'ENGINE_MANIFEST_SHA256', hashlib.sha256(raw).hexdigest())
    tool = module.LocalTranslationEngine(assets, tmp_path / 'work', Mock(), payload_roots=[source])
    return tool, source, manifest


def test_verified_local_payload_needs_no_network(fixture, monkeypatch):
    tool, _, manifest = fixture
    download = Mock(side_effect=AssertionError('No download expected'))
    monkeypatch.setattr(module.urllib.request, 'urlopen', download)
    root = tool.prepare()
    assert (root / 'worker.exe').read_bytes() == b'synthetic-worker.exe'
    assert root.name == manifest['engine_id']
    assert tool.prepare() == root
    download.assert_not_called()


def test_changed_cached_executable_cannot_run(fixture, monkeypatch):
    tool, _, _ = fixture
    root = tool.prepare()
    (root / 'worker.exe').write_bytes(b'tampered')
    runner = Mock()
    monkeypatch.setattr(module, 'run_process', runner)
    with pytest.raises(ValueError):
        tool.translate(['Test sentence.'])
    runner.assert_not_called()


def test_payload_paths_must_not_escape_cache(fixture, monkeypatch):
    tool, _, manifest = fixture
    manifest['files']['../outside.exe'] = {'bytes': 1, 'sha256': 'a' * 64}
    raw = json.dumps(manifest).encode()
    (tool.assets / 'translation/engine.json').write_bytes(raw)
    monkeypatch.setattr(module, 'ENGINE_MANIFEST_SHA256', hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError):
        tool.prepare()


def test_missing_or_bad_output_is_not_translation_success(fixture, monkeypatch):
    tool, _, _ = fixture
    def run(args, **kwargs):
        response = Path(args[args.index('--response') + 1])
        response.write_text(json.dumps({'schema': 1, 'translations': []}))
    monkeypatch.setattr(module, 'run_process', run)
    with pytest.raises(ValueError):
        tool.translate(['Connect to Aircraft'])


def test_translation_request_stays_in_local_files(fixture, monkeypatch):
    tool, _, _ = fixture
    def run(args, **kwargs):
        assert 'Hello aircraft' not in ' '.join(map(str, args))
        request = Path(args[args.index('--request') + 1])
        response = Path(args[args.index('--response') + 1])
        assert json.loads(request.read_text())['texts'] == ['Hello aircraft']
        response.write_text(json.dumps({'schema': 1, 'translations': ['Xin chào máy bay']}), encoding='utf-8')
    monkeypatch.setattr(module, 'run_process', run)
    assert tool.translate(['Hello aircraft']) == ['Xin chào máy bay']
    assert not list(tool.work.glob('request-*'))


def test_first_use_downloads_only_public_pinned_files(fixture, monkeypatch):
    import io
    tool, source, manifest = fixture
    tool.payload_roots = []
    urls = []
    class Response(io.BytesIO):
        def geturl(self):
            return module.BASE_URL + manifest['engine_id'] + '/worker.exe'
    def download(request, **kwargs):
        urls.append(request.full_url)
        prefix = module.BASE_URL + manifest['engine_id'] + '/'
        assert request.full_url.startswith(prefix)
        name = request.full_url.removeprefix(prefix)
        assert name in module.REQUIRED
        return Response((source / manifest['engine_id'] / name).read_bytes())
    monkeypatch.setattr(module.urllib.request, 'urlopen', download)
    root = tool.prepare()
    assert len(urls) == len(module.REQUIRED)
    assert (root / 'model/model.bin').exists()


@pytest.mark.parametrize('failure', ['truncated', 'oversized', 'bad_hash', 'http'])
def test_bad_download_is_never_published(fixture, monkeypatch, failure):
    import io
    tool, _, manifest = fixture
    tool.payload_roots = []
    class Response(io.BytesIO):
        def geturl(self):
            return ('http' if failure == 'http' else 'https') + '://example.test/file'
    def download(request, **kwargs):
        name = request.full_url.rsplit(manifest['engine_id'] + '/', 1)[1]
        size = manifest['files'][name]['bytes']
        return Response(b'x' * (size - 1 if failure == 'truncated' else size + 1 if failure == 'oversized' else size))
    monkeypatch.setattr(module.urllib.request, 'urlopen', download)
    with pytest.raises(ValueError):
        tool.prepare()
    assert not (tool.work / 'engines' / manifest['engine_id']).exists()
    assert not list((tool.work / 'engines').glob('engine-*'))


def test_empty_memory_sized_workload_is_batched_without_truncation(fixture, monkeypatch):
    tool, _, _ = fixture
    calls = []
    def chunk(texts):
        calls.append(list(texts))
        return ['vi:' + text for text in texts]
    monkeypatch.setattr(tool, '_translate_chunk', chunk)
    texts = ['New resource ' + str(i) for i in range(10001)]
    assert tool.translate(texts) == ['vi:' + text for text in texts]
    assert [s for batch in calls for s in batch] == texts
    assert max(map(len, calls)) <= 2048
