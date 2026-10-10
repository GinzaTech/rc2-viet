# Build và kiểm tra từ mã nguồn

## Bổ sung 0.8.0: engine dịch đầy đủ

`build.ps1` gọi `scripts/stage_desktop_assets.py`: stage không chứa hai APK RRO cũ `vietnamese-resources.apk` và `phone-vietnamese-resources.apk`. Giao diện luôn dựng tài nguyên cho APK đích.

Worker dịch có môi trường build riêng; cài dependency theo `translation-engine/requirements.txt` cùng PyInstaller6.16.0 rồi build `translation-engine/worker.py` bằng `--onefile --console --collect-binaries ctranslate2 --collect-data ctranslate2 --exclude-module torch --exclude-module transformers --exclude-module tensorflow`. App chạy worker với `CREATE_NO_WINDOW`, giữ input/output ở thư mục riêng trên PC.

`scripts/bundle_translation_engine.py` nhận `--model`, `--tokenizers`, `--chinese-model`, `--chinese-tokenizers`, `--worker`, `--licenses`; nó tạo thư mục payload theo nội dung trong `artifacts/translation-engine` và `assets/translation/engine.json`. Cập nhật `ENGINE_MANIFEST_SHA256` có chủ đích. Payload có hai model int8 và tokenizer; không đưa weights gốc PyTorch, APK DJI Fly, dữ liệu cá nhân hoặc khóa ký vào đó. Manifest, từng kích thước và từng hash được kiểm tra trước chạy.

Bản portable tự kèm thư mục engine cạnh EXE; EXE đơn lẻ tải cùng payload từ đường GitHub đã pin khi cần. Không gửi chuỗi tài nguyên ra mạng. Source/bundle độc lập Java/Python/SDK của host khi chạy EXE.

Dùng `--translation-build <APK> --translation-sdk 30|35 --report <JSON>` để kiểm chứng cục bộ. Thêm `--translation-no-memory` để xác minh không cần bất kỳ memory/gói dịch đã chuẩn bị nào. Thành công này là kiểm chứng build, không thay thế thử nghiệm thiết bị; lượt0.8 không dùng thiết bị theo yêu cầu người dùng.


## EXE Windows

Yêu cầu Python 3.11 x64 trên Windows và JDK 17 (`javac`/`java` trong PATH) để chạy đầy đủ kiểm thử chính sách chuyển Home. Người chạy EXE không cần JDK. Từ thư mục repository:

Từ0.4.0, test Android HUD cần SDK platform30 và build-tools36.1.0 ở `%LOCALAPPDATA%\Android\Sdk` để compile source và so DEX nhúng. Đây là yêu cầu kiểm thử/build source; người chạy EXE vẫn dùng runtime đã nhúng.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade "pip>=26.2.1"
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\build.ps1
```

Dependencies pin: PyInstaller 6.16.0, pytest 9.1.1, pytest-cov 7.0.0, setuptools 84.0.0. Môi trường build dùng pip 26.2.1 sau bước cập nhật. Runtime app chỉ dùng thư viện chuẩn Python và tài nguyên đã nhúng. `build.ps1` chạy tests/coverage, GUI smoke rồi PyInstaller `--onefile --windowed --add-data 'assets;assets'`.

EXE dùng `sys._MEIPASS/assets` khi chạy frozen. ADB được gọi bằng đường dẫn tuyệt đối tới `assets/adb/adb.exe`, các DLL nằm cùng thư mục; không tìm adb từ PATH. Cấu hình/tiến trình phiên ở `%LOCALAPPDATA%\RC2Vietnamese`.

Từ0.7.0, `assets/translation/catalog.json` chứa từ điển nguồn/bản dịch có hash pin trong `translation_build.py`. Tạo lại bằng `translation_catalog.make_catalog(<nguồn đã decode>/res, translation/review-round2/overlay/res)` rồi cập nhật hash có chủ đích. Toolchain Java cần module `java.desktop` để Apktool đọc tài nguyên. Các công cụ AAPT2/framework được lấy từ JAR Apktool đã kiểm tra hash; không dùng SDK hệ thống khi chạy EXE.

Kiểm chứng bộ dựng dịch cục bộ, không kết nối thiết bị: `RC2-TiengViet.exe --translation-build <APK_DJI_FLY> --translation-sdk 30 --report <JSON>`. Dùng `--translation-sdk 35` cho profile điện thoại Android15. Đây là CLI phục vụ kiểm chứng; giao diện người dùng chỉ cần Bật / cập nhật tiếng Việt và app tự lấy APK. Gói thích ứng luôn chỉ chứa tài nguyên; thành công cục bộ không chứng minh overlay đã chạy trên thiết bị.

Build EXE dùng APK có sẵn, không cần Android SDK hoặc khóa ký; JDK chỉ phục vụ kiểm thử Java của cầu Home. Khi thay bất kỳ APK, phải kiểm tra provenance/chữ ký/hash, cập nhật pin có chủ đích trong core.py và manifest.json, chạy kiểm thử và xác minh lại trên tay. Không dùng thay pin như một cách bỏ lỗi tương thích.

Từ0.3.0, EXE còn nhúng `assets/hud/toolchain.zip` và manifest hash cùng DEX HUD/helper khôi phục. Dùng bộ đã đóng gói thì không cần SDK để build EXE. Muốn dựng lại công cụ HUD, dùng JDK17 và build-tools36.1.0, APKtool2.12.1:

```powershell
.\.venv\Scripts\python.exe scripts/bundle_hud_tools.py --java-home 'C:\Program Files\Microsoft\jdk-17.0.20.8-hotspot' --sdk-tools "$env:LOCALAPPDATA\Android\Sdk\build-tools\36.1.0" --apktool 'C:\tools\apktool_2.12.1.jar'
```

Script biên dịch `android-hud/HudTool.java`, dựng Java runtime tối thiểu qua jlink, giữ license và tạo manifest SHA256 từng tệp. DEX ở `android-hud/dex/classes.dex` phải được dựng từ source Android HUD bằng javac/D8 trước; `assets/hud/restore-owner` được biên dịch từ `android-hud/RestoreOwner.c` bằng NDK cho ARMv7/API30. Đây là các đầu vào build, không phải tệp tải tùy ý. Thay toolchain/payload làm receipt cũ không còn khớp; tạo lại APK/receipt bằng bản EXE mới.

Khi chỉ sửa handler Android, dùng script dưới để cập nhật DEX và payload hash mà giữ nguyên toolchain/khóa:

```powershell
.\.venv\Scripts\python.exe scripts/build_hud_payload.py --java-home 'C:\Program Files\Microsoft\jdk-17.0.20.8-hotspot' --sdk "$env:LOCALAPPDATA\Android\Sdk"
```

`tests/test_hud_android.py` chạy các bài kiểm tra JVM trong `android-hud/test/` và compile toàn bộ helper bằng Android11/D8 để bảo đảm DEX nhúng khớp source. Không có lệnh gửi tới tay/máy bay trong các tests; TCP thử nghiệm chỉ là server loopback trên PC.

Luồng HUD đọc APK người dùng, ký bằng khóa ngoài bundle theo tài khoản Windows, rồi kiểm tra chữ ký và recipe. Build EXE không nhúng APK Fly gốc, khóa riêng hoặc bản sao lưu. [Hướng dẫn HUD](HUD_APK.md) giải thích quy trình và profile được pin. `build.ps1` đóng gói Portable ZIP/report/checksum từ EXE vừa build và kiểm tra chúng khớp nhau; thao tác đó chỉ tạo tệp cục bộ.

## Kiểm thử riêng

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --cov=rc2vi.core --cov=rc2vi.activation --cov=rc2vi.controller --cov=rc2vi.launcher --cov=rc2vi.developer --cov=rc2vi.lawnchair --cov=rc2vi.freefcc --cov=rc2vi.apk_install --cov-fail-under=80
.\.venv\Scripts\python.exe -m unittest discover -s translation/review-round2 -p test_review.py
.\dist\RC2-TiengViet.exe --gui-smoke
```

Các bài tests trong tests/ dùng fake ADB hoặc nút Tk thật với câu trả lời dialog được intercept; không gửi lệnh tới RC 2. `--gui-smoke` không mở worker. Kiểm chứng phần cứng cần một bước riêng, không chạy `--verify-once` trong lúc bay hoặc chưa muốn cài/bật bản dịch.

Để thử pipeline thật, dùng `--hud-build <APK_gốc> --report <JSON>` theo [HUD_APK.md](HUD_APK.md). Exit0/receipt không chứng minh boot: phải cài đúng đầu ra, đọc hash/foreground và quan sát sau reboot riêng. Các lượt0.3/0.4 dùng fake ADB; lượt0.6 có RC và cập nhật cùng chữ ký giữ dữ liệu. Bằng chứng từng chức năng ở báo cáo cài/kiểm tra, không suy từ coverage host.

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
