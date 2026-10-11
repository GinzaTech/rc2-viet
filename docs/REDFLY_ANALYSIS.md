# Phân tích tĩnh RedFly RC 2 — 11/10/2026

Theo yêu cầu, truy cập [trang tải RedFly](https://redfly.app/#download), đọc trang/JS và dùng đúng luồng `/api/visit` → `/api/download` của trang để tải hai bản RC2. Tệp được kiểm tra bằng SHA-256 công bố trong JS; token phiên chỉ dùng trong bộ nhớ khi tải. Không chạy hoặc cài APK trên thiết bị.

## Tệp thực tế

| APK | Package | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| `RedFly-1.21.10-dev-56-build-136-RC2-red-v5-final.apk` | `dji.go.v5` | 481.976.101 | `3e7a657ae4193789b59fedc6fb0274642756b3735e6469b52c010ecce0e363fe` |
| `RedFly-1.21.10-dev-56-build-136-RC2-red-v6-final.apk` | `dji.go.v6` | 482.078.501 | `fca136cde0f1911d7b4cb0ef8f94f20982f99a78c7aa21dab1852d8996d57fe0` |

Manifest cả hai: versionName `1.21.10`, versionCode `3115981`. dev56/build136 nằm trong tên phát hành. V5 thay package DJI Fly; V6 dùng package riêng để cài song song. Mỗi APK có 14.690 entry và 32 root DEX. Native ABI là `armeabi-v7a`, phù hợp gói RC2/ARM32; không coi đây là bản phone ARM64.

V5 xác minh được chữ ký v2/v3, một signer RSA2048. Chứng thư có DN `CN=DJI Fly Mod v6, O=Mod, C=US`, SHA-256 `4e1971daed82fe2025dd7f3e3bd5a493c9d79c00c1fb70845d623ee63a17e781`. Tên chứng thư tự khai không xác nhận danh tính tác giả. Hai biến thể có cùng tập tên ZIP entry; 23 entry khác CRC/kích thước, bao gồm manifest, bảng tài nguyên, layout trang chủ, một số DEX và META-INF. Đây là so sánh V5/V6, không phải diff với Fly chính thức cùng phiên bản.

## Mã bổ sung quan sát được

Giải mã tài nguyên/manifest bằng APKtool2.12.1, đọc class definitions và disassemble chọn lọc bằng dexlib/baksmali. Không tải thư viện/native trong APK vào tiến trình PC. Các đường dưới đây là namespace/class trong APK; Smali và inventory giữ ở `phone-work/redfly/` ngoài Git.

| Nhóm | Bằng chứng từ APK | Kết luận tĩnh |
| --- | --- | --- |
| Menu và điều khiển nhanh | `homequick/Catalog`, `homequick/Dashboard`, `redfly/Extras`, `fpvextras/Settings` | Có bảng nội dung/menu mới, tùy chọn GPS tay/máy bay, ATTI, hạ cánh và hiển thị bổ sung. |
| GPS máy bay | `redfly/Gps.readAsync`, `readSyncFallback`, `scheduleRetry`; chuỗi key `FCGPSEnabled` | Có luồng đọc trạng thái SDK, callback, đọc dự phòng và retry. Không suy ra quyền điều khiển GPS trên mọi firmware từ tên key. |
| ATTI/VPS | `fpvextras/Settings.addQuick`, tùy chọn `qt_atti_sport`; `redfly/Vision.write`, `observe`, `render` | Có UI gán ATTI vào vị trí Sport và adapter đọc/ghi thiết lập vision. |
| Hạ cánh bằng tay | `landing/Sdk.read/write/listen`, key `LandingProtectionEnabled`, `landing/Landing`, `landing/Transport` | Có điều khiển bảo vệ hạ cánh và đường đọc lại trạng thái. |
| Ẩn HUD | `cleanview/CleanView.installDoubleTapEnter`, `hideChrome`, `hideToolbarExceptTopBar`; `cleanview/DoubleTapCatcher` | Có cử chỉ chạm hai lần và thay đổi visibility/immersive của UI trong tiến trình Fly. |
| Pin/nhiệt độ | `app/openfcc/battery/BatteryOverlay`, `BatteryReading`, `fpvextras/Settings.telemetryCard` | Có lớp hiển thị pin, pin từng cell/nhiệt độ và tùy chọn telemetry. |
| Video qua mạng | `lanstream/Lan`, `LanEnc`, `LanHttp`, `LanHotspot`, `LanTel`, `LanUI`; `viewerUrl`, `wifiQr`, `acceptLoop`, `/stream` | Có module mã hóa/phục vụ video, trang xem/telemetry và tạo hotspot/QR. Đây là đường mạng; không chứng minh USB-C có HDMI/DisplayPort. |
| Tắt nguồn máy bay | `redfly/Power.bind`, `ready`, `stopped`, `sendNative`, `sendRc2Bridge` | Có nút, kiểm tra kết nối/động cơ và hai adapter gửi yêu cầu tắt nguồn. Không phát lệnh khi phân tích. |
| Tự mở khi boot | `redfly/Startup.stopSystemLaunch`, `stopMainPage`, `openOtherHome`, `noteIntent` | Có điều khiển hành vi trang chủ/intent và tùy chọn khởi động. |
| Công cụ FlightRecord | `frtool/Decryptor.decryptOne/decryptAllAsync`, `frtool/ProtoJson`, `frtool/X.scan/startPoller` | Có mã xử lý log bay/JSON và quét thư mục theo tùy chọn. Không đọc hoặc tải log cá nhân của người dùng. |

Application trong manifest là `com.dji.component.application.DJIApplication`, tìm thấy ở `classes23.dex`, kế thừa `com.uav.component.application.UAVApplication`. Manifest không dùng wrapper `com.AppGuard.AppGuard.*`; không thấy tệp native mang tên AppGuard trong ZIP. Quan sát này cho thấy bootstrap của APK tải về khác APK RC1.21.8 có sẵn, nhưng không đủ để khẳng định mọi cơ chế bảo vệ đã bị loại bỏ.

## Công bố trên trang và giới hạn xác minh

Trang giới thiệu FCC/băng5.8GHz, LTE/HYBRID, tùy chọn RTH, bản đồ offline mở rộng, giới hạn độ cao và thay đổi hạn chế khi chưa đăng nhập. Những mục đó được ghi nhận là **công bố của dự án**; lượt phân tích chưa dựng đủ chuỗi UI → SDK → ACK → readback cho từng mục. Không xác nhận công suất FCC, điều khiển LED, ATTI, RTH hoặc giới hạn bay trên Air3S/RC2 từ việc tìm được class/chuỗi.

Không có APK Fly RC1.21.10 chính thức tương ứng trong thư mục hiện tại để diff cùng phiên bản. Vì vậy báo cáo không khẳng định liệt kê mọi byte đã sửa hoặc mọi tính năng của RedFly. Cần một bản gốc đúng version/code/ABI để xác định đầy đủ thay đổi so với stock.

## Liên hệ với RC2 Việt

RedFly v5 được dùng như một đầu vào bổ sung cho kiểm chứng cấu trúc trên PC: bộ dựng menu chọn provider bootstrap và DEX33, giữ nguyên các entry gốc, ký/replay và capsule phục hồi lại đúng SHA-256 nguồn. Đây là kiểm chứng archive/signature; chưa chạy bản ghép menu để đánh giá UI hoặc tính năng RedFly.

Code native/Smali của RedFly không được nhập vào source/payload phát hành của RC2 Việt. Dữ liệu bản dịch nhập ở lượt này đến từ thư mục `rc2-viet-codex-initial-release` do người dùng chỉ định; các tài nguyên chưa đủ contract bị loại khi nhập.
