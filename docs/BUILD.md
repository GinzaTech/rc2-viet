# Build và kiểm tra RC2 Việt public Basic 0.10.1

Source/EXE public dành cho Việt hóa và menu LED/HUD/xuất hình/radio. Giao diện có hai thao tác riêng cho menu và tiếng Việt; CLI/payload chỉ nhận `basic`. Bản thử Advanced ở sibling `rc2-viet-advanced-local` là cục bộ, **không được xuất bản**. Không lấy mã, payload, APK riêng, khóa runtime/ký hoặc dữ liệu thiết bị của bản riêng làm đầu vào public.

Mốc release là **0.10.1**, metadata `0.10.1-local`. Build cuối đã đạt 2.003 test nguồn, coverage Python 90,10% và 15 test đóng gói. EXE đã được thử với PATH chỉ có System32, không JAVA_HOME/CLASSPATH; menu và bản dịch trên APK gốc 1.21.8/1.21.10 đều dựng được.

## Đầu vào và ranh giới tương thích

- Menu phân tích cấu trúc APK đang dùng; receipt/capsule bind đúng hash nguồn, payload, toolchain, signer và thiết bị. Hash dùng để ràng buộc dữ liệu, không phải danh sách số phiên bản được phép.
- Cầu SDK Basic tìm identifier có nghĩa thay vì pin tên field. ABI, callback, kiểu/quyền GET/SET và guard telemetry/kết nối/mặt đất/động cơ dừng vẫn phải hợp lệ. Không nới guard để xử lý field rename.
- Việt hóa dựng RRO chỉ chứa tài nguyên từ APK đích, bộ nhớ dịch tương thích và bảng diễn đạt đã rà; không ghép RRO vào APK menu hoặc đưa code tiện ích tham chiếu vào bản dịch.
- Dữ liệu người dùng ở `C:\Users\kona\Desktop\rc2-viet-codex-initial-release` ghi nguồn 1.21.10/code 3115981/hash `f6c11267d465c303e2aecb737fe4f6b41b54da083368cac497404f4c9a464f98`. Thư mục có RRO, báo cáo SDK và template hash `c296e4f326c7a3c80e2bba5474d986a1d5287457eca8e5e021fefcd0aa8ff9e7`; không có APK Fly nguồn. Báo cáo này không tự xác nhận nguồn đã được lấy hoặc build lại bằng Basic 0.10.1.
- Đã lấy APK gốc **1.21.10 / code 3115981** qua USB sau khi người dùng cập nhật; 468.109.376 byte, SHA-256 `f6c11267d465c303e2aecb737fe4f6b41b54da083368cac497404f4c9a464f98`, khớp báo cáo trong thư mục người dùng cung cấp. Menu Basic và RRO được dựng từ nguồn thật này, không dùng RedFly để dịch, patch hoặc cài. Verifier legacy dùng đúng sourceDigest; fixture không thay bằng chứng APK thật.
- Thử cấu trúc RedFly 1.21.10 trong 0.9.0 chỉ là lịch sử/tham chiếu, được loại khỏi bằng chứng tương thích Fly chính thức. Xem [trạng thái và nguồn dữ liệu](adaptive-menu-verification.json).

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

Đóng gói EXE dùng asset/toolchain public đã chuẩn bị; không cần khóa ký Fly riêng để đóng gói. Chạy toàn bộ kiểm thử source cần JDK và Android SDK theo yêu cầu ở trên. Khi thay asset nhúng, phải kiểm tra provenance/chữ ký/hash và cập nhật manifest có chủ đích. APK Fly đích vẫn được phân tích riêng; không sửa pin hoặc guard để ép tương thích.

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

Luồng HUD đọc APK người dùng, ký bằng khóa ngoài bundle theo tài khoản Windows, rồi kiểm tra chữ ký và recipe. Build EXE không nhúng APK Fly gốc, khóa riêng hoặc bản sao lưu. [Hướng dẫn HUD](HUD_APK.md) giải thích quy trình theo cấu trúc APK và các guard nền tảng. `build.ps1` đóng gói Portable ZIP/report/checksum từ EXE vừa build và kiểm tra chúng khớp nhau; thao tác đó chỉ tạo tệp cục bộ.

## Kiểm thử riêng

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --ignore=tests/test_hud_release_package.py --cov=rc2vi --cov=app --cov-fail-under=80
.\.venv\Scripts\python.exe -m unittest discover -s translation/review-round2 -p test_review.py
.\dist\RC2-TiengViet.exe --gui-smoke
.\.venv\Scripts\python.exe -m pytest tests/test_hud_release_package.py -q
```

Kiểm tra đóng gói chạy sau khi đã có EXE/Portable/metadata/checksum cuối khớp nhau. Các số test/coverage 0.9.0 trong [snapshot lịch sử](adaptive-menu-verification.json) không phải kết quả 0.10.1.

Các bài tests trong tests/ dùng fake ADB hoặc nút Tk thật với câu trả lời dialog được intercept; không gửi lệnh tới RC 2. `--gui-smoke` không mở worker. Kiểm chứng phần cứng cần một bước riêng, không chạy `--verify-once` trong lúc bay hoặc chưa muốn cài/bật bản dịch.

Để thử pipeline trên PC, dùng `--hud-build <APK_nguồn> --menu-variant basic --report <JSON>` theo [HUD_APK.md](HUD_APK.md). Exit 0/receipt không chứng minh cài hoặc boot. Bằng chứng thiết bị cần đúng hash đầu ra, signer/UID/foreground và quan sát chức năng sau cài/reboot. Các lượt 0.3/0.4 dùng fake ADB; lượt 0.6 và bản thử riêng có bằng chứng khác, không xác nhận Basic 0.10.1 hiện tại. Chưa xác minh HDR/HDMI vật lý, công suất FCC hoặc duy trì radio từ coverage host.

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

Luồng `review.py` cũ yêu cầu XML nguồn ở `translation/fly-1.21.8-source/res` cùng dữ liệu/bảng review đã lưu; đó là cách rà lại bộ nhớ lịch sử, không phải điều kiện pin phiên bản của pipeline hiện hành. Luồng hiện hành luôn bắt đầu từ APK đích, giữ sửa **Chế độ C (Tốc độ chậm)** và bảng cách diễn đạt khi contract phù hợp, dịch phần thiếu bằng engine cục bộ. APK DJI Fly nguồn và khóa ký riêng không được phân phối trong repo; worker/model public dùng manifest/inventory riêng.

Lưu ý: không chạy review.py chỉ để xem thống kê, vì nó ghi lại XML/report. Summary đã lưu đủ cho việc đọc. Chạy các kiểm thử quy tắc là thao tác kiểm tra không ghi lên tay.

## Các tệp bàn giao

Source/EXE Basic là phạm vi phân phối GitHub theo yêu cầu người dùng. Build chỉ tạo tệp cục bộ, không push, tạo tag/Release hoặc xuất bản thư mục bản riêng. Gói cuối phải có EXE, Portable, metadata và checksum cùng nguồn; không gọi một artifact là 0.10.1 đã phát hành chỉ vì tài liệu đã đổi version. Kiểm tra hash ví dụ:

```powershell
Get-FileHash .\dist\RC2-TiengViet.exe -Algorithm SHA256
Get-FileHash .\assets\freefcc.apk -Algorithm SHA256
```

Đối chiếu với SHA256SUMS và assets/manifest.json. Build lại EXE có thể thay hash do metadata/build/runtime; kiểm chứng bản build và assets có cùng nguồn không đồng nghĩa yêu cầu hash EXE mọi lần build phải byte-identical.

Staging asset public phải dùng allowlist đã review và từ chối đầu vào ngoài danh mục; không copy toàn bộ cây asset hoặc dữ liệu của bản riêng theo mặc định. Sửa ràng buộc `sourceDigest` legacy và allowlist staging đang được xử lý ở source; cần kiểm thử lại các đường này trước đóng gói cuối.

Sau khi cập nhật source và các tài liệu public, dựng lại gói cuối để tránh Portable chứa hướng dẫn cũ. Kiểm chứng không ghi lại output bằng:

```powershell
.\.venv\Scripts\python.exe scripts/package_windows.py --verify
```

Verifier đối chiếu version `0.10.1-local`, danh mục Basic, hash EXE/engine/tài liệu, Portable và checksum. Chỉ đưa các mục public đã review vào Git; thư mục sibling riêng, khóa, cache, backup, APK Fly nguồn và log thiết bị phải ở ngoài phạm vi phân phối. Việc cập nhật tài liệu không stage các tệp đó.

[Dependency audit đã lưu](dependency-audit.json) là snapshot của dependency Python đã kiểm tra ở lượt trước; không phải audit 0.10.1 mới, firmware/APK hoặc chứng nhận an toàn bay. Báo cáo build/test/đóng gói cuối và bằng chứng APK nguồn thực phải được bổ sung riêng.

Android 11 trên RC 2 dùng `cmd overlay lookup PACKAGE PACKAGE:TYPE/NAME`, không có `--user`; Android 15 giữ `--user 0`. 0.10.1 sửa chọn cú pháp theo SDK để gói dịch đúng không bị rollback do lệnh đọc lại sai. Sau cài menu, giữ tay ở **Settings/RC Launcher** trong lúc Việt hóa; mở lại DJI Fly sau khi có kết quả thành công.
