# Dùng RC2 Việt v0.2.0

1. Mở RC2-TiengViet.exe, nối USB dữ liệu và Allow trên thiết bị. Driver ADB/WinUSB vẫn cần ở Windows; ADB đã nhúng không thay driver.
2. Chọn Điện thoại Android hoặc Tay DJI RC2 và đúng serial. Không dùng gói RC lên điện thoại.
3. RC: Cài RC Launcher → Mở RC Launcher → Đặt RC Launcher làm màn hình chính. Thao tác khi không bay và giữ ở trang chủ/launcher/Settings.
4. Cài mới/updater RC chỉ dùng APK/hash đã pin. Các preview cũ đã biết có thể install-r giữ dữ liệu; bản lạ/sign khác bị chặn.
5. Home3.0 ưu tiên RC Launcher mới và còn Lawnchair làm fallback. Không xóa launcher cũ trước khi đã có đường khôi phục.
6. Tiếng Việt: Bật/cập nhật hoặc Tắt bản dịch; SDK/version/hash/root/foreground/idmap được kiểm tra. Với phone bấm Kiểm tra tương thích trước. Chi tiết docs/ANDROID_PHONE.md và VIETNAMESE.md.
7. FreeFCC chỉ được cài theo yêu cầu; launcher chỉ mở shortcut, không tự sửa RF/height/FCC. Developer options có cảnh báo trước khi mở/bật; không tắt USB debugging thủ công trên firmware đã gặp lỗi.
8. Dashboard RC dùng icon của app đã cài, giữ để ghim, menu⋮ để vào danh sách/cài đặt. CPU và Pin là hai nguồn driver khác nhau, không phải nhiệt vỏ.
9. Lưu báo cáo khi cần; report runtime có thể chứa serial/path, kiểm tra trước khi chia sẻ.

ADB offline có thể cần cáp/Allow hoặc firmware hỗ trợ. App không reset thiết bị hay xóa key để ép kết nối. Chưa thử bay/soak trên mọi firmware.
