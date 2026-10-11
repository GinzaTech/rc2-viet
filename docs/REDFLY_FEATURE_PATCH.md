# APK thử nghiệm ghép tiện ích RedFly trên Fly gốc RC 2

Ngày 11/10/2026. Đã patch, dựng và ký trên PC theo yêu cầu «patch trước, sáng mai kiểm tra». **Chưa cài hoặc chạy APK này trên RC 2, chưa gửi lệnh cho Air 3S.** Không xác nhận tất cả chức năng đã hoạt động thực tế.

## Tệp bàn giao

Thư mục cục bộ: `C:/Users/kona/Downloads/RC2-FeaturePort-20261011/`.

| Tệp | Mục đích |
| --- | --- |
| `DJI-Fly-RC2-1.21.8-FeaturePort-Experimental.apk` | Fly gốc 1.21.8 được ghép menu/tiện ích và ký bằng khóa mod của PC này |
| `DJI-Fly-Vietnamese-RC2-1.21.8.apk` | RRO tiếng Việt tương ứng với bảng tài nguyên Fly 1.21.8 |
| `DJI-Fly-RC2-1.21.8-Original-Recovered.apk` | APK gốc được tái tạo byte-exact từ dữ liệu phục hồi của bản mod |
| `BAO-CAO.md` | Báo cáo này |
| `patch-report.json` | Thông tin đầu vào, chữ ký, DEX, các method đã ghép và giới hạn kiểm chứng |
| `SHA256SUMS.txt` | Hash các APK và báo cáo |

APK mod cuối: **500.462.624 byte**, SHA256 `5c08c4908d8a198b0b079cbbe0b715fca5fdc9cdd6a5b22ae881a00949729ab0`.

APK gốc giữ versionName `1.21.8`, versionCode `3115809`, package `dji.go.v5`; SHA256 `cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e`. Gói tham chiếu là RedFly RC1.21.10/dev56/build136 v5, SHA256 `3e7a657ae4193789b59fedc6fb0274642756b3735e6469b52c010ecce0e363fe`. Chứng thư SDK30 của bản mod có SHA256 `eedb66b037d3ef53edff1bcce9f1f81173a7b8192c97646ef12f8bbb113af6d2`.

## Cách ghép

Nền ứng dụng vẫn là APK Fly gốc của người dùng trên PC. Giữ nguyên bảng tài nguyên, thư viện native, asset và các entry không nằm trong inventory sửa. Giữ bootstrap AppGuard và các bước khởi tạo gốc; đăng ký helper sau khi Application đã đổi context.

430 class tiện ích được trích theo namespace được chọn. Helper RC2 Việt và cầu tích hợp dùng `classes23.dex`; tiện ích bổ sung dùng `classes24.dex`. Các hook sửa **44 method trong 31 class của 11 DEX gốc**, gồm các đường vùng radio, bản đồ, nút tùy chỉnh, LAN, log, startup, RTH và phạm vi độ cao trên giao diện. Class ngoài tập sửa được kiểm tra giữ nguyên nội dung disassembly khi reassemble.

Các tài nguyên được đọc trực tiếp từ cả hai APK bằng AAPT2 và ghép theo type/name. Năm ID được tham chiếu trực tiếp đều khớp với stock, nên số ID phải đổi là 0. `Integer.MAX_VALUE` được nhận diện riêng, không coi là resource.

Từ điển menu có 396 mục được rà, với 247 sửa diễn đạt. Chỉ thay literal tại nhánh dịch Nga/Anh đã nhận diện, giữ khóa cấu hình, tên file, protocol và mã kỹ thuật. Trong payload cuối có **239 vị trí literal UI được thay bằng tiếng Việt**. Bộ Việt hóa tài nguyên Fly gốc vẫn dùng RRO riêng; không chuyển thành sửa trực tiếp `resources.arsc`.

## Tính năng đã ghép và phần cần kiểm tra

«Đã ghép» trong bảng là có mã, dependency phù hợp và điểm gọi trong APK. Tất cả mục ở cột thiết bị còn **NOT VERIFIED**.

| Nhóm | Phần đã ghép trên PC | Kiểm tra thực tế còn thiếu |
| --- | --- | --- |
| Menu | Giữ menu RC2 Việt; thêm hai nút gọn «Tiện ích nâng cao» và «Truyền hình qua Wi-Fi» | Vị trí nút, mở/đóng dialog, chữ và thao tác trên màn RC 2 |
| GPS / ATTI / VPS | Cài đặt, công tắc nhanh và đường SDK; bỏ nhánh GPS gửi UDP thô lặp sau lệnh SDK | Trạng thái, ACK/readback, chế độ C/Sport và tác động trên Air 3S |
| LED | Giữ adapter RC2 Việt có đọc trạng thái, guard mặt đất và thay đổi từng nhóm; LED không có nút riêng trên HUD; hành động LED của nút tùy chỉnh dùng adapter này | Bật/tắt trước, sau, cả hai; readback và giữ kết nối |
| Hạ cánh bằng tay | Menu bảo vệ hạ cánh và adapter của tiện ích | Quyền đọc/ghi, trạng thái và hành vi thực tế; chưa thử hạ cánh bằng tay |
| HUD / pin | Giữ một bộ chạm hai lần; thêm pin từng cell/nhiệt độ; ẩn các view tiện ích cùng HUD và tháo view khi pause | Ẩn/hiện, cử chỉ không đụng điều khiển khác, số liệu và tài nguyên nền |
| Nút tùy chỉnh | Nhãn và xử lý `CUSTOM100`–`CUSTOM105` được nối vào router stock | Firmware có nhận/gán đúng các hành động hay không |
| Radio | Force FCC / vùng gốc của helper; ghép getter vùng vào hai luồng stock; đồng bộ lựa chọn vùng sau khi giao dịch helper báo thành công | Chế độ thực tế, băng tần, duy trì sau reboot và khôi phục; chưa đo công suất RF |
| LAN / hotspot | Menu, encoder, HTTP/viewer/telemetry và tile phát trực tiếp | Mở máy chủ, tạo hotspot, xem video bằng trình duyệt, dừng/giải phóng tài nguyên |
| LTE / HYBRID | Mô-đun và điểm khởi tạo; mặc định không bật nếu chưa chọn tùy chọn | Phần cứng/modem, SIM, mạng và firmware hỗ trợ |
| RTH | Menu, bộ theo dõi và hook manual/countdown/video; giữ code stock hạ cánh bắt buộc | Phản hồi SDK, các lý do RTH, guard pin tới hạn và timeout; chưa thử khi bay |
| Bản đồ | Provider/style, chọn nguồn trong map, Find My Drone, FlightRecord, offline/tile manager | Hiển thị, chuyển nguồn, tải/mở offline và dung lượng lưu trữ |
| Độ cao trên UI | Trả phạm vi `IntMinMax` mà SDK báo về thay cho chặn 120 m trong method UI đã đối chiếu | Phạm vi thực và quyền đặt; không xác nhận đã mở giới hạn firmware |
| Tắt nguồn máy bay | Bind nút power; thêm gate trạng thái mới nhất trước cả đường SDK và socket dự phòng | Vị trí nút và phản hồi máy bay; chưa gửi lệnh |
| Startup / ghi màn hình | Hook launch/main/new intent và công tắc trì hoãn ghi màn hình | Boot, mở từ launcher, nút Home và quay màn hình |
| Log / FlightRecord | Hook mã hóa log và công cụ xuất JSON; không tự giải mã lúc mở app khi tùy chọn còn tắt | Đọc file thật, JSON, tương thích định dạng; chưa đọc log cá nhân |
| Xuất hình có/không HUD | Giữ đường màn ngoài của helper hiện có | USB-C/HDMI trên màn LG/adapter chưa xác minh; LAN là đường riêng |

## Các phần chưa chuyển

**Bỏ hạn chế đăng nhập của RedFly chưa được chuyển.** Đường đã quan sát có ghi UID tổng hợp vào luồng activation. Bản này giữ logic tài khoản/activation stock. Không đưa hook `ridkill` hoặc thay đổi Remote ID/DroneID vào APK. Không thay toàn bộ native/SDK 1.21.8 bằng các binary từ 1.21.10.

Do đó đây là **bản thử nghiệm có các nhóm tiện ích đã ghép**, không phải bản sao có đầy đủ mọi sửa của RedFly. Bản mod tiếp tục dùng AppGuard gốc; khả năng khởi chạy và tính ổn định phải kiểm tra trên RC 2.

## Bằng chứng trên PC

- Dựng/assemble DEX thành công; đối chiếu tên class, prototype và kế thừa với 176.045 definitions của stock.
- Kiểm tra dependency của **650 class bổ sung** gồm 430 tiện ích và 220 helper/cầu tích hợp: **0 tham chiếu chưa giải quyết**; các method SDK gọi trực tiếp cũng được kiểm tra visibility. API framework kế thừa và `array.clone` được phân biệt với dependency trong APK.
- Zipalign và xác minh chứng thư SDK30 thành công. Khối v2 stock được giữ cho loader AppGuard; đây không phải tuyên bố chữ ký v2 cũ xác thực các byte đã thay đổi.
- Đối chiếu các entry không sửa, cả nội dung đã nén và metadata ZIP.
- Dùng capsule nằm trong APK để phục hồi nguồn, được đúng SHA256 stock nêu trên.
- Bộ kiểm thử nguồn đầy đủ ở snapshot thực hiện: **1.854 passed**. Các sửa cuối của scanner/bridge được kiểm tra mục tiêu và bằng dựng APK; chi tiết bổ sung ở `feature-port-verification.json`.
- Không chạy ADB, không cài APK, không thay firmware hoặc gửi lệnh thiết bị ở lượt này.

## Cách kiểm tra khi quay lại

1. Dùng APK trong thư mục bàn giao. Xác nhận bản Fly hiện cài trên tay, chữ ký và sao lưu dữ liệu trước khi thay ứng dụng. Gói này là RC2/ARM32/Android11 trên nền1.21.8; chưa phải gói cho mọi phiên bản/điện thoại.
2. Nếu tay đang dùng mod có cùng chứng thư, có thể cập nhật giữ dữ liệu. Nếu Android báo khác chữ ký, không tự gỡ app khi chưa sao lưu và xác nhận thao tác; gỡ có thể làm mất phiên đăng nhập/Keystore.
3. Kiểm tra mở Fly, menu, Home và chạm hai lần trước. Kiểm tra RRO tiếng Việt đã được cài và bật; nếu có sẵn RRO của nền1.21.8 thì bảng tài nguyên này được giữ nguyên.
4. Với Air 3S trên mặt đất và động cơ dừng, kiểm tra từng nhóm độc lập và quan sát phản hồi/readback. Không suy ra công suất FCC hoặc hiệu lực RTH từ việc nút đổi màu/lưu lựa chọn.
5. Kiểm tra phát video LAN và màn ngoài bằng đúng thiết bị/phần cứng đang có. USB-C trực tiếp cần đường xuất hình được phần cứng/driver hỗ trợ.
6. Nếu lỗi, giữ lại thông báo/log `RC2FeaturePort` và `RC2Hud` để đối chiếu. APK gốc phục hồi có trong cùng thư mục; cài lại stock có thể gặp khác signer so với mod và cần xử lý dữ liệu trước.

## Dựng lại từ source

Recipe thử nghiệm nằm ở `scripts/build_feature_candidate.py`, `scripts/feature_host_patch.py` và `android-hud/feature-port/`. Cần JDK17, Android SDK `android-30` và build-tools36.1.0. Mẫu lệnh PowerShell:

```powershell
.venv\Scripts\python.exe -X utf8 scripts\build_feature_candidate.py --source "C:\path\DJI_FLY.apk" --reference "C:\path\RedFly-1.21.10-dev-56-build-136-RC2-red-v5-final.apk" --java-home "C:\path\jdk-17" --sdk "C:\path\Android\Sdk"
```

Recipe này ràng buộc hai hash đầu vào đã đối chiếu để tránh ghép ABI/hook không xác định. Nó tự đọc tài nguyên hai APK và dựng helper; không phụ thuộc folder Smali/inventory của lần phân tích trước. Chỉ source cầu tích hợp, recipe, từ điển Việt đã rà và báo cáo được đưa vào Git. APK tham chiếu, Smali, khóa ký và kết quả build giữ trong thư mục riêng.

**EXE0.9.0 vẫn là bản đang phát hành**, với bộ menu/ngôn ngữ thích ứng nhiều phiên bản đã kiểm chứng trên PC. Bản feature-port này chưa được đưa vào EXE/payload dùng chung hoặc GitHub Release; cần kiểm tra thực tế trước khi hợp nhất.
