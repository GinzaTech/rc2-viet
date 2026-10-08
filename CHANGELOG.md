# Changelog

## Local: desktop VShop compact / launcher icon

- Desktop dùng nền đen, token VShop card18/button14, nhấn đỏ#c72232, nút30px và bố cục960x740; timer GUI được dọn khi đóng.
- Nhúng RC Launcher preview4/code4 có icon vector, pinRC/nhiệt độ pin/Wi-Fi; trên RC đã install/readback PASS.
- 142 testsPC pass,20 unit testsAndroid pass; releaseGitHub chưa thay đổi.


## Chưa phát hành — Android và desktop nền đen (2026-10-08)

- Nhúng RC Launcher preview3/code3 (APK135KB, package riêng) và nút cài/mở trong trang RC; đã kiểm tra installed hash/component trên tay. Launcher source ở project rc-launcher; dashboard tối giản, bỏ dock trùng native bar theo yêu cầu.

- Nền đen, thẻ tối, điểm nhấn mint, hai trang Android/RC 2; chọn thiết bị, trạng thái và lệnh tách riêng.
- Worker ADB chuẩn cho điện thoại; giữ thiết bị đã chọn khi mất USB, hiển thị offline/unauthorized, chặn lệnh RC trong trang Android.
- RRO 1.21.12-vi3 cho APK DJI chính thức Android 1.21.12 (3131451), SDK 35 có root. Tái sử dụng 11.068 tài nguyên nguồn khớp; giữ gốc 80 mục khác biệt theo vùng, sửa 7 nhãn điều khoản/quyền riêng tư.
- Redmi K60: cài APK DJI nguyên chữ ký, bật/tắt overlay có readback, trang chủ thật tiếng Việt, nút Apply qua GUI thật. Chưa kiểm thử bay, reboot điện thoại hoặc nội dung web/server.
- Thêm CLI --phone-inspect/--phone-verify, kiểm thử root/rollback/phân tách thiết bị, ảnh GUI và hướng dẫn Android. EXE nhúng APK tài nguyên điện thoại, không nhúng APK DJI Fly gốc 720 MB.
- Sửa Hệ thống nhạy cảm → Hệ thống cảm biến trong cả gói điện thoại và RC reviewed6/code 8.
- Giữ sửa cầu Home v2 và chức năng RC. GitHub v0.1.0 chưa thay đổi trong yêu cầu này.

## Chưa phát hành — sửa cầu Home v2

- Cầu Home 2.0 chuyển ngay khi Android sẵn sàng, dùng theme trong suốt, tắt starting preview và tự finish sau khi mở Lawnchair.
- Chỉ dựng màn fallback khi thực sự chờ unlock hoặc chưa mở được launcher; xử lý Home intent mới và hủy callback khi rời activity.
- Thêm 6 tình huống hồi quy Java và kiểm thử nâng đúng cầu v1 bằng install -r, giữ dữ liệu, không thay Home nếu đọc lại APK lỗi.
- APK cầu được cài/kiểm tra trên tay, ba lần Home từ Settings về Lawnchair; đã kiểm tra sau reboot vẫn vào Lawnchair.
- Bản local EXE có pin APK mới; release GitHub v0.1.0 chưa được thay trong yêu cầu này.

## v0.1.0 — 2026-10-06

- Tạo repository độc lập RC2 Việt, giao diện Windows tiếng Việt và EXE onefile có ADB/DLL nhúng.
- Kết nối RC 2 qua WinUSB/cầu ADB loopback, chọn đúng tay và giữ bước Allow USB debugging trên thiết bị.
- Bật/tắt/cập nhật RRO tiếng Việt reviewed5 cho đúng DJI Fly 1.21.8, kiểm tra hash/idmap/readback và phục hồi cache khi thất bại.
- Nhúng và cài Lawnchair 15 Beta 3, FreeFCC 1.5.5 bằng luồng APK đã kiểm tra.
- Mở Lawnchair/DJI Fly, cầu Home Direct Boot và nút đặt Lawnchair làm màn hình chính theo firmware được pin.
- Mở Developer options sẵn có với cảnh báo OK/Hủy về nguy cơ mất ADB khi tắt thủ công.
- Lưu đủ 7 APK trong thư mục dự án app, phân biệt 4 gói dùng được với APK trung gian/SystemUI tham chiếu.
- Bổ sung nguồn XML bản dịch, quy tắc rà, hướng dẫn sử dụng/build, SHA256 và ghi công upstream.
- Cập nhật pytest/setuptools/pip của môi trường build sau dependency audit; dùng capture Python-level cho test Tcl/Tk trên Windows.
- Ghi rõ các giới hạn: ADB offline sau reset, cài bằng nút mới sau reset chưa xác minh, thanh điều hướng ba nút chưa bật, chưa thử bay hay kích hoạt FCC.
