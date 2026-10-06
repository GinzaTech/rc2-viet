# Build và kiểm tra từ mã nguồn

## EXE Windows

Yêu cầu Python 3.11 x64 trên Windows. Từ thư mục repository:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade "pip>=26.2.1"
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\build.ps1
```

Dependencies pin: PyInstaller 6.16.0, pytest 9.1.1, pytest-cov 7.0.0, setuptools 84.0.0. Môi trường build dùng pip 26.2.1 sau bước cập nhật. Runtime app chỉ dùng thư viện chuẩn Python và tài nguyên đã nhúng. `build.ps1` chạy tests/coverage, GUI smoke rồi PyInstaller `--onefile --windowed --add-data 'assets;assets'`.

EXE dùng `sys._MEIPASS/assets` khi chạy frozen. ADB được gọi bằng đường dẫn tuyệt đối tới `assets/adb/adb.exe`, các DLL nằm cùng thư mục; không tìm adb từ PATH. Cấu hình/tiến trình phiên ở `%LOCALAPPDATA%\RC2Vietnamese`.

Build EXE dùng APK có sẵn, không cần Android SDK hoặc khóa ký. Khi thay bất kỳ APK, phải kiểm tra provenance/chữ ký/hash, cập nhật pin có chủ đích trong core.py và manifest.json, chạy kiểm thử và xác minh lại trên tay. Không dùng thay pin như một cách bỏ lỗi tương thích.

## Kiểm thử riêng

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --cov=rc2vi.core --cov=rc2vi.activation --cov=rc2vi.controller --cov=rc2vi.launcher --cov=rc2vi.developer --cov=rc2vi.lawnchair --cov=rc2vi.freefcc --cov=rc2vi.apk_install --cov-fail-under=80
.\.venv\Scripts\python.exe -m unittest discover -s translation/review-round2 -p test_review.py
.\dist\RC2-TiengViet.exe --gui-smoke
```

Các bài tests trong tests/ dùng fake ADB hoặc nút Tk thật với câu trả lời dialog được intercept; không gửi lệnh tới RC 2. `--gui-smoke` không mở worker. Kiểm chứng phần cứng cần một bước riêng, không chạy `--verify-once` trong lúc bay hoặc chưa muốn cài/bật bản dịch.

pytest.ini chọn `--capture=sys`: trong môi trường Windows đã thử, capture native file descriptor mặc định của pytest gây lỗi khởi tạo lại Tcl/Tk, còn capture Python-level chạy đủ các kiểm thử nút/dialog. Không bỏ qua test Tk hoặc thay bằng assert mô phỏng để che lỗi.

## Build lại RRO và cầu Home — tùy chọn

Yêu cầu JDK có javac, Android SDK platform android-30 và build-tools 36.1.0. Hai builder dùng SDK Windows ở `%LOCALAPPDATA%\Android\Sdk`, nên cài cấu trúc đó hoặc chủ động sửa đường dẫn builder cho môi trường của mình.

Khóa ký không có trong repository. Tạo thư mục riêng ngoài Git, chứa `local-vietnamese-draft.jks` và `local-signing.json`. JSON chứa alias/password của khóa riêng do người build quản lý; không dùng lại một mật khẩu mẫu và không commit file này. `.gitignore` đã chặn hai loại tệp.

Đặt biến chỉ đường dẫn, không phải mật khẩu:

```powershell
$env:RC2VI_SIGNING_DIR = 'C:\RC2-signing-private'
.\.venv\Scripts\python.exe translation/review-round2/build.py
.\.venv\Scripts\python.exe android-home/build.py
```

Builder đọc mật khẩu trong cấu hình riêng và đưa sang apksigner bằng biến môi trường, không dùng mật khẩu literal trên command line. RRO builder compile XML, link, zipalign, sign, verify và kiểm tra không có DEX/.so. Home builder compile Java 8-compatible với android.jar, chuyển D8, link manifest, thêm DEX, zipalign, sign và verify.

APK signed mới thường có hash khác, và không thể cập nhật một package ký bằng khóa khác theo cách cài -r thông thường. EXE kiểm tra pin chính xác và sẽ từ chối khi pin không phù hợp. Các APK unsigned/aligned đã lưu là dấu vết build, không phải tệp để cài.

## Chỉnh và rà bản dịch

Để sửa một câu cho phiên bản hiện tại, xem XML cuối trong translation/review-round2/overlay và các bảng review/user_wording. Không đổi tên tài nguyên, placeholder, cấu trúc arrays/plurals hoặc dữ liệu kỹ thuật tùy tiện.

Chạy lại toàn bộ `review.py` yêu cầu XML gốc đúng DJI Fly ở `translation/fly-1.21.8-source/res`, cùng dữ liệu nền và bảng review đã lưu. Không có APK DJI Fly gốc hoặc trọng số mô hình dịch trong repo. Đợt tạo bản nháp cũ dùng mô hình cục bộ; bản reviewed5 đã có XML cuối nên không cần mô hình để build lại tài nguyên.

Lưu ý: không chạy review.py chỉ để xem thống kê, vì nó ghi lại XML/report. Summary đã lưu đủ cho việc đọc. Chạy các kiểm thử quy tắc là thao tác kiểm tra không ghi lên tay.

## Các tệp bàn giao

EXE/APK được giữ trực tiếp trong Git. ZIP portable/source ở GitHub Releases, không nhân đôi các ZIP lớn vào Git. `dist/SHA256SUMS.txt` liệt kê hash của APK, EXE và các ZIP release. Kiểm tra ví dụ:

```powershell
Get-FileHash .\dist\RC2-TiengViet.exe -Algorithm SHA256
Get-FileHash .\assets\freefcc.apk -Algorithm SHA256
```

Đối chiếu với SHA256SUMS và assets/manifest.json. Build lại EXE có thể thay hash do metadata/build/runtime; kiểm chứng bản build và assets có cùng nguồn không đồng nghĩa yêu cầu hash EXE mọi lần build phải byte-identical.

Trước bàn giao đã chạy pip-audit trên môi trường build riêng, nâng pip/pytest/setuptools khỏi các bản bị báo lỗ hổng, rồi audit lại không còn lỗ hổng đã biết trong các package được audit. Báo cáo docs/dependency-audit.json chỉ là kiểm tra dependency Python, không phải audit firmware/APK hay chứng nhận an toàn bay.
