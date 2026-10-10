"""Publish a model/runtime payload inventory; no text, accounts or signing keys."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--tokenizers', type=Path, required=True)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--chinese-model', type=Path, required=True)
    parser.add_argument('--chinese-tokenizers', type=Path, required=True)
    parser.add_argument('--licenses', type=Path, required=True)
    args = parser.parse_args()
    inputs = {'worker.exe': args.worker,
              **{'model/' + name: args.model / name for name in ('model.bin', 'config.json', 'shared_vocabulary.json')},
              **{'model/' + name: args.tokenizers / name for name in ('source.spm', 'target.spm')},
              **{'model-zh/' + name: args.chinese_model / name for name in ('model.bin', 'config.json', 'shared_vocabulary.json')},
              **{'model-zh/' + name: args.chinese_tokenizers / name for name in ('source.spm', 'target.spm')},
              **{name: args.licenses / name for name in ('LICENSE.model.txt', 'LICENSE.runtime.txt', 'provenance.json')}}
    files = {name: {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
             for name, path in inputs.items()}
    if any(not 0 < item['bytes'] < 100 * 1024 * 1024 for item in files.values()):
        raise ValueError('Every payload file must be below the GitHub file-size limit.')
    engine_id = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:24]
    destination = ROOT / 'artifacts/translation-engine' / engine_id
    destination.mkdir(parents=True, exist_ok=True)
    for name, source in inputs.items():
        output = destination / name
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists() and hashlib.sha256(output.read_bytes()).hexdigest() != files[name]['sha256']:
            raise ValueError('Existing immutable engine payload has changed.')
        if not output.exists():
            shutil.copyfile(source, output)
    manifest = ROOT / 'assets/translation/engine.json'
    manifest.write_text(json.dumps({'schema': 1, 'engine_id': engine_id, 'files': files}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'engine_id': engine_id, 'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
                      'payload_bytes': sum(item['bytes'] for item in files.values())}))


if __name__ == '__main__':
    main()
