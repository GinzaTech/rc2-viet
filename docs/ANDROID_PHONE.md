# DJI Fly tiếng Việt trên điện thoại Android

Bản local ngày 08/10/2026, chưa cập nhật release GitHub v0.1.0.

## Các bản đã kiểm chứng

| Mục | Điện thoại | Tay RC 2 |
| --- | --- | --- |
| Thiết bị | Redmi K60, mondrian / 23013PC75G | DJI RC 2, rc331 |
| Android | Android 15 / SDK 35 | Android 11 / SDK 30 |
| DJI Fly | 1.21.12, code 3131451 | 1.21.8, code 3115809 |
| Kết nối | ADB chuẩn, root qua su | Cầu WinUSB/ADB riêng, shell root sẵn có |
| Gói dịch | local.dji.fly.phone.vietnamese | local.dji.fly.vietnamese |
| Idmap | v9, uint32 flag, chuỗi có độ dài | v4, uint8 flag, đường dẫn 256 byte |

Điện thoại ban đầu chưa cài Fly ở user 0/999. Theo lựa chọn người dùng, đã tải bản Android chính thức từ [DJI Download Center](https://www.dji.com/downloads/djiapp/dji-fly) và cài vào user 0. APK DJI giữ nguyên chữ ký, không rebuild hay ký lại.

- SHA256 APK DJI: `1da8d5b2ee5cdcb6002131b8f6535605e7445080d1ca6f8411067a0d1524ce0b`.
- SHA256 chứng thư DJI: `01a42c94aa87020f41e8c252598df98b86a0acf6c05ff61c75f18fa29cad1dd4`.
- SHA256 RRO vi3: `c1d9198c1abeca5022ee1bbc18c8c333f0619f2b188776878353c3a84edbeebf`.
- Gói dịch version 1.21.12-vi3/code 3, khoảng 2,9 MB, hasCode=false, không DEX/native code.

## Sử dụng EXE

1. Cài DJI Fly chính thức đúng bản hỗ trợ. EXE nhúng ADB/gói dịch, không nhúng bộ cài DJI Fly gốc.
2. Bật USB debugging, nối bằng cáp dữ liệu, chọn Allow. Trên máy root, cấp quyền su cho shell/ADB nếu trình quản lý root hỏi.
3. Mở EXE, chọn **Điện thoại Android** và đúng số sê-ri. Khi nhiều thiết bị, phải chọn trước khi thao tác.
4. Bấm **Kiểm tra tương thích** để đọc Android/Fly/root. Hiện chỉ áp dụng APK/hash ở bảng trên; chưa hỗ trợ điện thoại không root.
5. Khi không bay, giữ ở trang chủ Fly hoặc launcher, bấm **Bật / cập nhật tiếng Việt**, chờ báo đã đọc lại thành công rồi **Mở DJI Fly**. Nếu ứng dụng đang mở và chưa đổi chữ, thoát/mở lại khi không bay.
6. **Tắt bản dịch** trở lại tài nguyên gốc; không xóa Fly hay dữ liệu tài khoản. Mở lại Fly để xem thay đổi.
7. Chọn **Tay DJI RC 2** để dùng chức năng của tay. Không dùng APK/gói RC để thay APK điện thoại.

ADB tích hợp không thay thế driver Windows. Windows phải có giao diện ADB hoạt động; MTP không đủ. Trang Android không kill-server khi đóng, không tắt/revoke USB debugging.

## Cách tạo và áp dụng tiếng Việt

[Android runtime resource overlay](https://source.android.com/docs/core/runtime/rros) ánh xạ tài nguyên của Fly sang gói dịch riêng khi chạy. Chữ ký và mã DJI Fly giữ nguyên.

`scripts/build_phone_overlay.py` so sánh XML nguồn tiếng Anh RC 1.21.8 với APK điện thoại 1.21.12. Chỉ tái dùng bản dịch nếu tên, kiểu, thuộc tính, nội dung và cấu trúc con của nguồn khớp. Còn kiểm tra các biến thể vùng tiếng Anh, loại mục khác nguồn. Kết quả 11.068 tài nguyên; giữ bản gốc 80 mục khác biệt vùng. Đây là số tài nguyên đóng gói, không phải số màn hình đã quan sát. Bảy nhãn điều khoản/quyền riêng tư được sửa thêm theo màn hình thật; thuật ngữ Hệ thống cảm biến theo yêu cầu người dùng.

Builder dùng aapt2 và khóa riêng ngoài Git. Manifest điện thoại dùng SDK 35, targetName DJIFlyPhoneTranslation. ROM thực tế yêu cầu targetName khi chữ ký overlay khác DJI. Không cấp lại/thay chữ ký DJI Fly.

Luồng root kiểm tra SDK/version/code/hash, màn hình hiện tại và gói đã cài. Tạo idmap với --ignore-overlayable, kéo ra kiểm tra đúng schema v9, magic/policy, đường dẫn target/overlay, tên overlay và độ dài header; chỉ đổi flag enforce 0→1 sau khi các trường khớp. Chép vào cache của đúng APK overlay, chỉnh owner/mode/SELinux label, bật cho user 0 và đọc lại chuỗi mẫu. Nếu bật/readback thất bại, tắt overlay và phục hồi cache cũ hoặc xóa cache mới. Can thiệp nằm ở một idmap của gói dịch; không patch framework/kernel hay tạo module root khởi động.

SDK/format/hash khác sẽ bị chặn. Sau cập nhật Fly/ROM cần đối chiếu và kiểm chứng lại; không đổi pin để ép chạy. HTML/server, ảnh có chữ và chuỗi ngoài gói tài nguyên không được dịch bằng phương pháp này.

## Bằng chứng và giới hạn

- Cài Fly chính thức: ADB Success, đọc version/cert/hash trước khi cài.
- RRO STATE_ENABLED, lookup homepage_connect_drone_btn → Kết nối máy bay.
- Tắt → Connect to Aircraft; bật → Kết nối máy bay; bấm lại read-only already_enabled.
- ARTEMIS thấy trang chủ thật: Tìm kiếm, Hướng dẫn, Mô phỏng DJI, Trước khi bay, Truyền nhanh, Thư viện, Hồ sơ.
- [Ảnh trang chủ thật](phone-fly-vietnamese.jpg), [preview desktop](desktop-phone.png), [kiểm chứng nút GUI/worker thật](desktop-phone-live-verification.json).
- Chưa thử bay, độ ổn định nhiều giờ hoặc sau reboot điện thoại. Không tuyên bố dịch 100% hay hỗ trợ mọi ROM/máy không root. Release GitHub vẫn là bản cũ.

## Build và CLI

Build EXE theo docs/BUILD.md. Rebuild gói dịch cần Android SDK/build-tools 36.1.0, android-34, JDK, APK nguồn đã giải mã, nguồn XML 1.21.8 và khóa riêng ngoài Git:

```powershell
$env:RC2VI_PREVIOUS_SOURCE='C:\path\to\fly-1.21.8-source'
$env:RC2VI_SIGNING_DIR='C:\private\signing'
.\.venv\Scripts\python.exe -m scripts.build_phone_overlay
```

Builder đọc APK/nguồn tại phone-work (bị ignore). APK DJI gốc 720 MB, dữ liệu riêng và khóa ký không có trong EXE. Muốn build gói mới phải kiểm chứng nguồn/hash và cập nhật pin có chủ đích.

```powershell
.\dist\RC2-TiengViet.exe --phone-inspect --serial <serial> --report inspection.json
.\dist\RC2-TiengViet.exe --phone-verify --serial <serial> --report verification.json
```

--phone-inspect chỉ đọc. --phone-verify có thể cài/bật gói dịch, chỉ dùng khi không bay và ở màn hình an toàn. Report chứa số sê-ri/path thiết bị: xóa thông tin riêng trước khi chia sẻ.
