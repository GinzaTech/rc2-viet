# Báo cáo public Basic 0.10.1 và bằng chứng lịch sử 0.9.0

Cập nhật tài liệu: **12/10/2026**. Dự án: [RC2 Việt](https://github.com/GinzaTech/rc2-viet). Tên file `BAO_CAO_0.9.0.md` được giữ để các liên kết/đóng gói hiện có tiếp tục hoạt động; nội dung hiện tại mô tả phạm vi public Basic và phân loại lại snapshot cũ.

**Trạng thái xác minh — 13/10/2026:** EXE public 0.10.1 đã build và thử dựng/ký menu, Việt hóa từ APK gốc RC **1.21.8 và 1.21.10**. Basic 1.21.10 đã cài cùng chữ ký/giữ dữ liệu trên RC 2; menu không có Tiện ích SDK. Gói Việt hóa do chính EXE dựng đã được bật và đọc lại đúng tài nguyên trên tay. Công suất RF, xuất hình vật lý, thử bay và độ ổn định dài hạn chưa được xác minh.

## 1. Phạm vi public và bản riêng

Bản public chỉ phân phối luồng Việt hóa và menu **LED / HUD / xuất hình / radio**. Tab RC có hai thao tác riêng: **Cài / cập nhật menu** và **Bật / cập nhật tiếng Việt**. CLI/payload public chỉ nhận Basic; không có bộ chọn bản nâng cấp.

Bản thử Advanced được giữ ở sibling cục bộ `rc2-viet-advanced-local` và **không được xuất bản**. Mã, payload, APK riêng và khóa runtime/ký của bản đó không thuộc source/EXE public. Việc cập nhật tài liệu không chép, stage hoặc phát hành dữ liệu của bản riêng.

Đã lấy APK gốc **1.21.10 / code 3115981** qua USB sau khi người dùng cập nhật; 468.109.376 byte, SHA-256 `f6c11267d465c303e2aecb737fe4f6b41b54da083368cac497404f4c9a464f98`, khớp báo cáo trong thư mục người dùng cung cấp. Menu Basic và RRO được dựng từ nguồn thật này, không dùng RedFly để dịch, patch hoặc cài. Sau yêu cầu mới, tay được chuyển sang Basic; bản riêng vẫn nằm ngoài GitHub.

## 2. Dữ liệu 1.21.10 do người dùng cung cấp

Nguồn: `C:\Users\kona\Desktop\rc2-viet-codex-initial-release`.

| Mục | Thông tin và phạm vi bằng chứng |
| --- | --- |
| Nguồn Fly được các báo cáo nhận diện | RC 1.21.10 / code 3115981 |
| SHA-256 APK nguồn đã ghi nhận | `f6c11267d465c303e2aecb737fe4f6b41b54da083368cac497404f4c9a464f98` |
| APK Fly nguồn trong thư mục dữ liệu | Thư mục cung cấp không có APK đầy đủ; đã lấy đúng APK gốc từ RC 2 và tính lại hash ở lượt này |
| RRO | Có APK chỉ chứa tài nguyên dịch; không thay thế APK Fly nguồn |
| Binding SDK | Có `artifacts/device-update-2026-10-10/menu-sdk-1.21.10.json`, ghi method/key và hash source; phần cứng chưa được kiểm tra trong báo cáo này |
| Template phục hồi | Có `assets/hud/source-recovery-1.21.10.zip`, hash `c296e4f326c7a3c80e2bba5474d986a1d5287457eca8e5e021fefcd0aa8ff9e7`; hash template đã đối chiếu trên PC |
| Phục hồi từ menu Basic mới | Capsule của nguồn 1.21.10 đã phục hồi đúng byte/hash APK gốc F6; template legacy được giữ riêng cho nhận diện lịch sử |

Các file này dùng để đối chiếu nguồn và bổ sung bộ nhớ dịch. Chúng không xác nhận APK Fly 1.21.10 chính thức đã được lấy và chạy qua pipeline Basic 0.10.1 hiện hành. Không dùng tên file, version/code hoặc báo cáo cũ để thay kiểm tra APK nguồn thực.

## 3. Menu Basic và USB

Bộ dựng menu đọc manifest, Application/chuỗi kế thừa, bootstrap, DEX chưa dùng và view Home/preview/HUD. Capsule của từng APK cho phép phục hồi đúng bytes nguồn; sau phục hồi vẫn phải khớp SHA-256 và replay recipe/helper/chữ ký. Cấu trúc hoặc contract mơ hồ phải dừng trước cài.

Cầu SDK Basic tìm `Connection`, `IsFlying`, `AreMotorsOn`, `LEDsSettings` theo identifier có nghĩa, hỗ trợ tên field thay đổi. Kiểu/quyền GET/SET, chữ ký method/callback, dữ liệu telemetry còn mới, kết nối, mặt đất và động cơ dừng vẫn được kiểm tra. Các fixture field rename là kiểm thử contract trên PC, không phải bằng chứng ABI hoặc runtime của APK RC 1.21.10 thực.

Discovery hỗ trợ DJI cũ **VID 2CA3 / PID 1021** và Android chỉ ADB **VID 18D1 / PID 4EE7**, được nhận diện sau cập nhật trong bối cảnh người dùng cung cấp. VID/PID chỉ xác định transport. Trước khi áp dụng vẫn yêu cầu model DJI RC 2, device rc331, Android 11/API 30, shell root, đúng serial, foreground và APK.

Menu LED ghi một lần/đọc lại và giữ bit ngoài nhóm đã chọn. Radio dùng baseline của đúng máy bay trong phiên; không đoán CE, không tự ghi khi boot/reconnect, chưa có keepalive. Cùng signer có thể giữ dữ liệu; khác signer vẫn cần sao lưu và xác nhận gỡ/cài, không bảo đảm khôi phục Keystore/đăng nhập.

## 4. Việt hóa

Pipeline hiện hành bắt đầu từ **APK đích**, so khớp bộ nhớ dịch hợp lệ, dịch phần thiếu cục bộ rồi kiểm tra placeholder/markup/array/plural trước khi dựng RRO riêng. Bộ nhớ của thư mục người dùng là nguồn tùy chọn, không phải gói pin phiên bản hoặc mã tiện ích. Common locale và bản sửa cách diễn đạt được giữ trong luồng tài nguyên; không ghép mã menu vào RRO.

Nhãn **Chế độ C (Tốc độ chậm)** được ưu tiên theo bảng sửa diễn đạt; D-Cinelike vẫn là tên hồ sơ màu. Giữ bản dịch đã rà khi nguồn/contract khớp. Mục cần dịch bỏ dở hoặc contract sai phải chặn cài. Đủ tài nguyên không chứng minh 100% UI hay ngữ nghĩa toàn bộ câu dịch máy; HTML/server, ảnh và literal ngoài tài nguyên có giới hạn riêng.

Số liệu nhập bộ nhớ ở snapshot 0.9.0: 7 cặp mới hợp lệ, 10.736 cặp hiện có được giữ, 350 cặp lệch contract bị loại và 830 mục thiếu cấu trúc/nguồn bị bỏ qua. [Provenance bộ nhớ](../assets/translation/memory/rc12110-supplement.provenance.json) xác định nguồn người dùng; đây không phải dữ liệu dịch lấy từ RedFly.

## 5. Phân loại lại bằng chứng 0.9.0

Snapshot ngày 11/10/2026 ghi 1.822 test source đạt, coverage Python 88,27%, 60 kiểm tra Android/payload sau review và kết quả EXE/engine. Những số này chỉ thuộc **0.9.0**, không phải báo cáo kiểm thử hoặc đóng gói 0.10.1 mới.

| Đầu vào của lần thử cũ | Phạm vi |
| --- | --- |
| Fly RC 1.21.8 / code 3115809 / DEX23 | Kiểm tra cấu trúc, ký/replay/khôi phục trên PC của payload 0.9.0; không xác nhận runtime Basic 0.10.1 |
| Fly phone 1.21.12 / code 3131451 / DEX2 | Kiểm tra cấu trúc trên PC; tab điện thoại hiện không có installer menu |
| **RedFly v5 1.21.10 / code 3115981 / DEX33** | **APK mod tham chiếu lịch sử**, không phải Fly chính thức; loại khỏi bằng chứng tương thích RC 1.21.10 và không dùng làm nguồn dịch hiện tại |

SHA nguồn RedFly của lần thử cũ là `3e7a657ae4193789b59fedc6fb0274642756b3735e6469b52c010ecce0e363fe`, khác nguồn được báo cáo `f6c…4f98`. Không đổi tên hoặc gộp hai nguồn này. Chi tiết hash/recipe/test cũ giữ dưới mục lịch sử trong [adaptive-menu-verification.json](adaptive-menu-verification.json); không đưa feature-port hoặc phân tích tiện ích vào hướng dẫn Basic.

## 6. Bằng chứng còn cần bổ sung

| Tiêu chí | Trạng thái |
| --- | --- |
| APK Fly RC 1.21.10 nguồn thực | Đã lấy qua USB, version/code/size/hash khớp dữ liệu người dùng |
| Build/ký/replay/capsule mới | EXE dựng thành công cả stock 1.21.8 và 1.21.10; capsule trả lại đúng nguồn |
| Xác minh phục hồi legacy và staging | 9 test ràng buộc nguồn/public đạt; staging allowlist và frozen archive không có payload riêng |
| EXE/Portable/checksum/metadata 0.10.1 | Build nguồn 2.003 test/90,10% coverage; 15 test gói đạt; SHA tại dist/SHA256SUMS.txt |
| Cài/hash/UID/foreground Basic 1.21.10 | Cài cập nhật giữ dữ liệu, UID 10023; đã mở menu Basic và đọc lại RRO trên RC 2. Reboot/soak riêng còn giới hạn |
| LED vật lý với payload hiện hành | Đã thử trước/sau riêng, bật/tắt cả hai trên Basic 1.21.10; người dùng xác nhận đổi đúng và giữ kết nối |
| Xuất hình USB-C/HDMI và HDR vật lý | **Chưa xác minh**; probe/driver/lưu lựa chọn không chứng minh hình sạch |
| FCC công suất/hiệu lực, duy trì radio, khôi phục baseline | **Chưa xác minh đầy đủ**; ACK/readback/UI cũ không thay đo/quan sát mới |
| Thử bay, soak dài, firmware khác và ngữ nghĩa toàn bộ bản dịch | **Chưa xác minh** |

Source/EXE Basic là phạm vi GitHub người dùng đã yêu cầu. Bản riêng không được stage/push. Báo cáo hiện hành có bằng chứng APK thật và ADB; snapshot 0.9.0 bên dưới không được dùng thay thế các kết quả này.

[README](../README.md) · [Hướng dẫn](USAGE.md) · [Menu/HUD](HUD_APK.md) · [Build](BUILD.md) · [Việt hóa](VIETNAMESE.md).
