"""Optional reviewed text memories; the target APK and engine remain authoritative."""
import hashlib
import json
from pathlib import Path
import re

from .hud_tools import _safe_relative, load_json, sha256_file

MEMORY_MANIFEST_SHA256 = '71a9aea7de7a0192dbe98789cc8076a7b24f47b8a52a43fec7a1de65b4428c8f'


def load_memories(assets: Path, cancel=None, enabled=True):
    catalogs, overrides, inventory = [], {}, {}
    root = Path(assets) / 'translation'
    manifest_path = root / 'memories.json'
    if not enabled or not manifest_path.exists():
        return catalogs, overrides, hashlib.sha256(b'no-reviewed-memory').hexdigest()
    if manifest_path.stat().st_size > 128 * 1024 or sha256_file(manifest_path, cancel) != MEMORY_MANIFEST_SHA256:
        raise ValueError('Danh mục bộ nhớ bản dịch bị thay đổi.')
    manifest = load_json(manifest_path)
    files = manifest.get('files')
    if manifest.get('schema') != 1 or not isinstance(files, dict) or len(files) > 64:
        raise ValueError('Danh mục bộ nhớ bản dịch không hợp lệ.')
    for name, item in files.items():
        _safe_relative(name)
        if (not name.endswith('.json') or not isinstance(item, dict)
                or item.get('kind') not in {'catalog', 'text'}
                or not re.fullmatch(r'[0-9a-f]{64}', item.get('sha256', ''))):
            raise ValueError('Nguồn bộ nhớ bản dịch không hợp lệ.')
        path = root / name
        if not path.exists():
            continue  # A missing optional memory is handled by machine translation.
        if path.stat().st_size > 32 * 1024 * 1024 or sha256_file(path, cancel) != item['sha256']:
            raise ValueError('Bộ nhớ bản dịch bị thay đổi: ' + name)
        value = load_json(path)
        if item['kind'] == 'catalog':
            catalogs.append(value)
        else:
            if len(value) > 100000 or any(not isinstance(k, str) or not isinstance(v, str)
                                         or not k.strip() or not v.strip() for k, v in value.items()):
                raise ValueError('Bảng thuật ngữ/bản dịch không hợp lệ.')
            overrides.update(value)
        inventory[name] = item['sha256']
    fingerprint = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
    return catalogs, overrides, fingerprint


def with_reviewed_fragments(translate, overrides):
    """Use exact reviewed terminology inside fallback fragments, never fuzzy matches."""
    edges = " \t\r\n.,;:!?…，。；：！？、()[]{}\"'“”‘’–—-"
    def run(texts):
        output, pending, positions = [None] * len(texts), [], []
        for index, text in enumerate(texts):
            core = text.strip(edges)
            if core in overrides and '__RC2VI_' not in text:
                output[index] = text[:len(text)-len(text.lstrip(edges))] + overrides[core] + text[len(text.rstrip(edges)):]
            else:
                positions.append(index)
                pending.append(text)
        if pending:
            translated = translate(pending)
            if not isinstance(translated, list) or len(translated) != len(pending):
                raise ValueError('Bộ máy dịch trả về thiếu đoạn văn bản.')
            for index, value in zip(positions, translated):
                output[index] = value
        return output
    return run
