"""Stage desktop public assets without retired, version-specific translation APKs."""
from pathlib import Path
import shutil
import stat
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RETIRED = {'vietnamese-resources.apk', 'phone-vietnamese-resources.apk'}


def main():
    base = (ROOT / 'build').resolve()
    base.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='desktop-assets-', dir=base)).resolve()
    if not stage.is_relative_to(base):
        raise ValueError('Asset staging path escaped the build directory.')
    source = ROOT / 'assets'
    for path in source.rglob('*'):
        if path.lstat().st_file_attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
            raise ValueError('Public asset source contains a reparse point.')
    shutil.copytree(source, stage / 'assets', ignore=lambda directory, names: RETIRED if Path(directory) == source else set())
    print(stage / 'assets')


if __name__ == '__main__':
    main()
