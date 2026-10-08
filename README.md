# RC2 Việt — công cụ Windows và launcher cho DJI RC 2

Bản phát hành **v0.2.0**, ngày 08/10/2026. App Windows có nền đen, nút compact và hai trang riêng **Điện thoại Android** / **Tay DJI RC 2**. Launcher mặc định của luồng RC là **RC Launcher mới**, thay Lawnchair trên giao diện PC và đường Home/khởi động trên tay đã kiểm chứng.

![Desktop RC2 Việt](docs/desktop-rc.png)

## Tải và dùng

- [RC2-TiengViet.exe](https://github.com/GinzaTech/rc2-viet/releases/latest/download/RC2-TiengViet.exe): Windows x64, Python runtime/ADB/DLL và APK đã nhúng.
- [Portable ZIP kèm hướng dẫn](https://github.com/GinzaTech/rc2-viet/releases/latest/download/RC2-TiengViet-Portable.zip).
- [Source ZIP](https://github.com/GinzaTech/rc2-viet/releases/latest/download/RC2-TiengViet-Source.zip).
- [Releases và APK riêng](https://github.com/GinzaTech/rc2-viet/releases).
- [SHA256SUMS](dist/SHA256SUMS.txt).

1. Bật tay/điện thoại, nối USB dữ liệu, mở EXE. Không cần cài Python hoặc ADB; Windows vẫn phải có driver ADB/WinUSB phù hợp.
2. Bấm Allow USB debugging trên thiết bị nếu được hỏi; chọn đúng trang và sê-ri. Công cụ không tự bỏ qua xác nhận này.
3. Với RC: bấm **Cài RC Launcher**, **Mở RC Launcher**, rồi **Đặt RC Launcher làm màn hình chính** khi không bay và tay ở launcher/trang chủ/Settings.
4. **Bật / cập nhật tiếng Việt** áp dụng đúng gói theo platform/SDK/APK hash. **Tắt bản dịch** phục hồi tài nguyên gốc; không xóa DJI Fly/tài khoản.
5. Với điện thoại: **Kiểm tra tương thích** trước khi bật dịch. Bản đang hỗ trợ Android15 có root, Fly chính thức1.21.12/code3131451. Không tự root điện thoại.
6. Có nút cài FreeFCC và mở Developer options. Cài FreeFCC không tự kích hoạt FCC. Cảnh báo trước Developer options nói rõ nguy cơ mất ADB nếu tắt thủ công.

[Hướng dẫn](docs/USAGE.md) · [Android](docs/ANDROID_PHONE.md) · [RC Launcher/Home](docs/RC_LAUNCHER.md) · [Việt hóa](docs/VIETNAMESE.md) · [Build](docs/BUILD.md).

## RC Launcher mới

Source: [GinzaTech/rc-launcher](https://github.com/GinzaTech/rc-launcher), adaptation của Lawnchair/Launcher3, package riêng dev.rclauncher.rc2.debug. Icon trên dashboard lấy từ ứng dụng đã cài/chọn, không phải bộ glyph giả. Chạm mở đúng app, giữ để ghim. Menu ⋮ vào danh sách/cài đặt. Thanh trên hiển thị pinRC/Wi-Fi và **CPU / Pin** riêng.

CPU được đọc từ sensor cpuss/sysfs nếu app có quyền đọc; Pin là giá trị Android/driver pin báo. Đã thấy CPU khoảng87–95°C trong kernel trong khi pin báo30°C; chưa xác minh hiệu chuẩn firmware và không đo nhiệt độ vỏ. Không coi30°C là nhiệt độ toàn bộ tay hay chứng nhận không nóng.

Cầu Home3.0 ưu tiên RC Launcher debug, sau đó release; Lawnchair cũ chỉ là fallback nếu launcher mới không mở được. Đã kiểm tra Home từ Settings và sau reboot trên RC331/V14.00.00.04 test-keys, API30. Công cụ kiểm tra services.jar và APK trước khi đổi đường Home; không flash/sửa framework. Không gỡ Lawnchair tự động để giữ đường khôi phục.

## Gói nhúng

| Tệp | Vai trò / bản |
| --- | --- |
| rc-launcher.apk | RC Launcher mới, APK debug đã ký; version/hash trong manifest báo cáo phát hành |
| home-bridge.apk | Home3.0, đưa boot/Home vào launcher mới, có fallback |
| vietnamese-resources.apk | RRO RC Fly1.21.8, reviewed6/code8; Hệ thống cảm biến đã sửa |
| phone-vietnamese-resources.apk | RRO điện thoại Fly1.21.12-vi3; nguồn/hash riêng |
| freefcc.apk | FreeFCC1.5.5, tiện ích ngoài; chỉ cài/mở theo người dùng |
| lawnchair.apk | Lawnchair15 Beta3 upstream, chỉ giữ cho dự phòng/khôi phục |
| adb/ | Platform-tools nhúng + DLL, không phải driver tự cài |

APK debug launcher cài được. APK release unsigned của repo launcher phải ký trước khi cài; không nhúng bản unsigned vào EXE. Các APK intermediate và SystemUI reference trong artifacts/reference không dùng để cài hệ thống.

## Việt hóa DJI Fly

DJI Fly giữ nguyên APK/chữ ký/mã thực thi. App cài một runtime resource overlay riêng, ánh xạ chuỗi/plural/array, không re-sign DJI Fly. RC dùng idmapv4/Android11; điện thoại dùng idmapv9/Android15. Mỗi profile kiểm tra phiên bản/code/hash, root, foreground và schema/path trước khi áp dụng; lỗi có rollback cache.

RC: Fly1.21.8/code3115809, stock SHA pinned. Phone: Fly chính thức1.21.12/code3131451. Builder điện thoại chỉ dùng lại bản dịch khi toàn bộ cây nguồn tiếng Anh khớp, giữ gốc các mục thay đổi theo vùng. Chi tiết và hash ở docs/VIETNAMESE.md, docs/ANDROID_PHONE.md.

Không dịch HTML/server hoặc chữ nằm trong ảnh bằng RRO. Đây là bản dịch đã rà và kiểm chứng một số màn hình, không tuyên bố100% UI/độ ổn định bay. Phone vi2 đã quan sát; vi3 có trong EXE để cập nhật, chưa áp dụng dòng mới trên điện thoại sau khi người dùng chuyển cáp sang RC.

## Kiểm chứng và giới hạn

- PC có unit/integration guards, nút Tk thật, layout ở cửa sổ nhỏ và EXE smoke; kết quả mới ở docs/release-verification.json.
- RC: cài/mở launcher, chọn/mở Fly, icon app thật, tìm kiếm, pin/Wi-Fi/CPU-Pin; Home vào RC Launcher và boot đã quan sát.
- Global navigation optional/off. User đang dùng native Android3bar; không tuyên bố service/Recents/gesture toàn hệ thống đã test.
- Chưa thử bay, soak dài, benchmark release đầy đủ hoặc mọi firmware. Giữ đúng SDK/hash được pin; không thay pin để ép tương thích.
- ADB offline của firmware không được vô hiệu hóa vĩnh viễn; cầu WinUSB có thể cần người dùng Allow sau kết nối/reboot.

## Build

Windows, Python3.11 và JDK17 cho kiểm thử Java Home. Android SDK/khóa riêng chỉ cần để rebuild APK; build EXE dùng APK đã có.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\build.ps1
```

Keys/.env/adbkey/phone-work/backups/cache không có trong Git/source ZIP. Xem docs/BUILD.md để build RRO/Home bằng khóa riêng ngoài repo và nguồn đã kiểm chứng.

## Nguồn và ghi công

- [RC Launcher source](https://github.com/GinzaTech/rc-launcher), [Lawnchair upstream](https://github.com/LawnchairLauncher/lawnchair), base78873fa3a8872eaee3e10211174cb5338c021a4f.
- [Lawnchair15 Beta3](https://github.com/LawnchairLauncher/lawnchair/releases/tag/v15.0.0-beta3.0), Apache2.0.
- [FreeFCC](https://github.com/doesthings/FreeFCC), [v1.5.5](https://github.com/doesthings/FreeFCC/releases/tag/v1.5.5), [website](https://freefcc.pages.dev/).
- [DJI Fly chính thức](https://www.dji.com/downloads/djiapp/dji-fly).

Dự án độc lập, không phải ứng dụng chính thức của DJI/Lawnchair. Giữ LICENSE/THIRD_PARTY_NOTICES.md và license của từng gói.
