$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& .\.venv\Scripts\python.exe -m pytest tests -q --ignore=tests/test_hud_release_package.py --cov=rc2vi.core --cov=rc2vi.activation --cov=rc2vi.controller --cov=rc2vi.launcher --cov=rc2vi.developer --cov=rc2vi.lawnchair --cov=rc2vi.freefcc --cov=rc2vi.apk_install --cov=rc2vi.phone --cov=rc2vi.phone_overlay --cov=rc2vi.phone_resources --cov=rc2vi.hud_build --cov=rc2vi.hud_tools --cov=rc2vi.hud_keys --cov=rc2vi.hud_install --cov=rc2vi.hud_backup --cov-fail-under=80
if ($LASTEXITCODE -ne 0) { throw 'Kiểm thử chưa đạt' }
& .\.venv\Scripts\python.exe app.py --gui-smoke
if ($LASTEXITCODE -ne 0) { throw 'Kiểm tra GUI chưa đạt' }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name RC2-TiengViet --version-file packaging/windows-version.txt --add-data 'assets;assets' app.py
if ($LASTEXITCODE -ne 0) { throw 'Đóng gói chưa thành công' }
& .\.venv\Scripts\python.exe scripts/package_windows.py
if ($LASTEXITCODE -ne 0) { throw 'Tạo ZIP/checksum phát hành chưa thành công' }
& .\.venv\Scripts\python.exe -m pytest tests/test_hud_release_package.py -q
if ($LASTEXITCODE -ne 0) { throw 'Kiểm tra ZIP/checksum phát hành chưa đạt' }
