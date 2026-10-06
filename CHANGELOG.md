# Changelog

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
