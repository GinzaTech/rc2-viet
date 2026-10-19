"""Hash-pinned local CPU translator. Only public engine files may be downloaded."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import urllib.request

from .hud_tools import (_check_ancestors, _physical_stat, _tool_environment,
                        check_cancel, load_json, run_process, sha256_file)

ENGINE_MANIFEST_SHA256 = '1fabdd4e2a97bc8dfe3cc73e4bfe4bf548951e84e1178bc2b11896c7aaae8de2'
REQUIRED = frozenset({'worker.exe', 'model/model.bin', 'model/config.json',
                      'model/shared_vocabulary.json', 'model/source.spm', 'model/target.spm',
                      'model-zh/model.bin', 'model-zh/config.json', 'model-zh/shared_vocabulary.json',
                      'model-zh/source.spm', 'model-zh/target.spm'})
OPTIONAL = frozenset({'LICENSE.model.txt', 'LICENSE.runtime.txt', 'provenance.json'})
BASE_URL = 'https://raw.githubusercontent.com/GinzaTech/rc2-viet/codex/initial-release/artifacts/translation-engine/'


class LocalTranslationEngine:
    def __init__(self, assets: Path, work: Path, emit=lambda *args: None, cancel=None,
                 payload_roots=None):
        self.assets, self.work = Path(assets).absolute(), Path(work).absolute()
        self.emit, self.cancel = emit, cancel
        self.payload_roots = list(payload_roots) if payload_roots is not None else [
            Path(sys.executable).parent / 'translation-engine',
            self.assets.parent / 'artifacts/translation-engine',
        ]

    def manifest(self):
        path = self.assets / 'translation/engine.json'
        if path.stat().st_size > 128 * 1024 or sha256_file(path, self.cancel) != ENGINE_MANIFEST_SHA256:
            raise ValueError('Thông tin bộ máy dịch không khớp bản EXE.')
        value = load_json(path)
        if (value.get('schema') != 1 or not re.fullmatch(r'[0-9a-f]{24}', value.get('engine_id', ''))
                or not isinstance(value.get('files'), dict)
                or not REQUIRED <= value['files'].keys() <= REQUIRED | OPTIONAL):
            raise ValueError('Danh sách tệp bộ máy dịch không hợp lệ.')
        total = 0
        for item in value['files'].values():
            if (not isinstance(item, dict) or type(item.get('bytes')) is not int
                    or not 0 < item['bytes'] <= 100 * 1024 * 1024
                    or not re.fullmatch(r'[0-9a-f]{64}', item.get('sha256', ''))):
                raise ValueError('Kích thước/hash bộ máy dịch không hợp lệ.')
            total += item['bytes']
        if total > 250 * 1024 * 1024:
            raise ValueError('Bộ máy dịch vượt giới hạn dung lượng.')
        return value

    def _verify(self, root, files):
        _check_ancestors(root)
        for name, item in files.items():
            path = root / name
            _check_ancestors(path.parent)
            _physical_stat(path)
            if (not path.is_file() or path.stat().st_size != item['bytes']
                    or sha256_file(path, self.cancel) != item['sha256']):
                raise ValueError('Tệp bộ máy dịch bị thay đổi: ' + name)

    def _copy(self, source, destination, item):
        _check_ancestors(source.parent)
        _physical_stat(source)
        if source.stat().st_size != item['bytes']:
            raise ValueError('Tệp bộ máy dịch cục bộ bị thiếu hoặc thay đổi.')
        with source.open('rb') as src, destination.open('xb') as dst:
            while chunk := src.read(1024 * 1024):
                check_cancel(self.cancel)
                dst.write(chunk)

    def _download(self, url, destination, item):
        request = urllib.request.Request(url, headers={'User-Agent': 'RC2-Viet-Local-Translator/1'})
        with urllib.request.urlopen(request, timeout=30) as response, destination.open('xb') as output:
            if response.geturl().split(':', 1)[0] != 'https':
                raise ValueError('Bộ máy dịch phải được tải qua HTTPS.')
            total = 0
            while chunk := response.read(1024 * 1024):
                check_cancel(self.cancel)
                total += len(chunk)
                if total > item['bytes']:
                    raise ValueError('Tệp tải về vượt kích thước đã công bố.')
                output.write(chunk)
            if total != item['bytes']:
                raise ValueError('Tải bộ máy dịch chưa hoàn tất.')

    def prepare(self) -> Path:
        check_cancel(self.cancel)
        manifest = self.manifest()
        parent = self.work / 'engines'
        _check_ancestors(parent)
        parent.mkdir(parents=True, exist_ok=True)
        root = parent / manifest['engine_id']
        if root.exists():
            self._verify(root, manifest['files'])
            return root
        source = next((Path(p) / manifest['engine_id'] for p in self.payload_roots
                       if (Path(p) / manifest['engine_id']).is_dir()), None)
        if source is not None:
            self._verify(source, manifest['files'])
            self.emit('applying', 'Đang chuẩn bị bộ máy dịch cục bộ…')
        else:
            self.emit('applying', 'Lần đầu: đang tải bộ máy dịch về PC. Văn bản DJI Fly không được gửi lên mạng.')
        with tempfile.TemporaryDirectory(prefix='engine-', dir=parent) as temporary:
            stage = Path(temporary) / manifest['engine_id']
            stage.mkdir()
            for name, item in manifest['files'].items():
                check_cancel(self.cancel)
                output = stage / name
                output.parent.mkdir(parents=True, exist_ok=True)
                if source is not None:
                    self._copy(source / name, output, item)
                else:
                    self._download(BASE_URL + manifest['engine_id'] + '/' + name, output, item)
            self._verify(stage, manifest['files'])
            check_cancel(self.cancel)
            try:
                stage.rename(root)
            except OSError:
                if not root.exists():
                    raise
                self._verify(root, manifest['files'])
        return root

    def translate(self, texts: list[str]) -> list[str]:
        if not isinstance(texts, list) or len(texts) > 100000 or any(
                not isinstance(s, str) or not s.strip() or len(s) > 16000 for s in texts):
            raise ValueError('Văn bản đầu vào bộ máy dịch không hợp lệ.')
        output, batch, size = [], [], 0
        for text in texts:
            item_bytes = len(json.dumps(text, ensure_ascii=False).encode('utf-8')) + 2
            if batch and (len(batch) >= 2048 or size + item_bytes > 8 * 1024 * 1024):
                output.extend(self._translate_chunk(batch))
                self.emit('applying', f'Đã dịch {len(output)}/{len(texts)} đoạn trên PC…')
                batch, size = [], 0
            batch.append(text)
            size += item_bytes
        if batch:
            output.extend(self._translate_chunk(batch))
        return output

    def _translate_chunk(self, texts: list[str]) -> list[str]:
        if not texts:
            return []
        root = self.prepare()
        self.emit('applying', f'Đang dịch bổ sung {len(texts)} đoạn bằng CPU trên PC…')
        _check_ancestors(self.work)
        with tempfile.TemporaryDirectory(prefix='request-', dir=self.work) as temporary:
            request, response = (Path(temporary) / name for name in ('request.json', 'response.json'))
            # Equivalent linguistic normalization avoids two observed OPUS tokenization
            # errors: "redone" -> "red 1", and 二维码 -> an invented digit 2.
            normalized = [re.sub(r'\bredone\b', 'done again', text, flags=re.I).replace('二维码', 'QR code')
                          for text in texts]
            request.write_text(json.dumps({'schema': 1, 'texts': normalized}, ensure_ascii=False), encoding='utf-8')
            if request.stat().st_size > 16 * 1024 * 1024:
                raise ValueError('Lô văn bản quá lớn; cần chia nhỏ trước khi dịch.')
            run_process([str(root / 'worker.exe'), '--model-dir', str(root / 'model'),
                         '--request', str(request), '--response', str(response)],
                        cancel=self.cancel, env=_tool_environment())
            if not response.is_file() or response.stat().st_size > 16 * 1024 * 1024:
                raise ValueError('Bộ máy dịch chưa trả về kết quả hợp lệ.')
            value = load_json(response)
            output = value.get('translations')
            if (value.get('schema') != 1 or not isinstance(output, list) or len(output) != len(texts)
                    or any(not isinstance(s, str) or not s.strip() or len(s) > 16000 for s in output)):
                raise ValueError('Bộ máy dịch trả về thiếu hoặc sai cấu trúc.')
            check_cancel(self.cancel)
            return output
