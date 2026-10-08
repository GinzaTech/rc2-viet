# Desktop nền đen và DJI Fly trên điện thoại

Ngày: 2026-10-08. Phạm vi: repository rc2-viet, không sửa RC2 Việt.

## Thiết kế và hành vi

- Nền #000000, mặt thẻ #101419, chữ sáng; Segoe UI; điểm nhấn xanh mint.
- Hai chế độ rõ ràng: Điện thoại Android và Tay DJI RC 2. Mỗi chế độ giữ riêng số sê-ri, trạng thái và tiến trình; lệnh luôn gửi đúng worker.
- Các công cụ Lawnchair, FreeFCC, cầu Home và cảnh báo Developer options thuộc trang RC 2. Điện thoại chỉ có kiểm tra tương thích, Việt hóa, tắt dịch và mở DJI Fly.
- Không tự áp dụng gói RC lên điện thoại. Kiểm tra phiên bản/hash APK, Android, root và tài nguyên trước khi ghi; không sửa chữ ký/code DJI Fly.
- GUI co giãn, nút có trạng thái focus/disabled, log cuộn và báo cáo có nhãn nền tảng. Không chạy ADB trên luồng UI.

## Các bước và bằng chứng cần đạt

1. Kiểm tra máy Android đang cắm qua ADB và ARTEMIS; xác định root và bản Fly thật. Đã quan sát launcher điện thoại, Android 15, root KernelSU; chưa có DJI Fly ở user 0/999.
2. Tải APK chính thức theo lựa chọn người dùng, kiểm tra signer/version/hash và tài nguyên; tạo profile điện thoại riêng nếu runtime hỗ trợ.
3. Viết test trước cho phân tách thao tác/thiết bị, parser và kiểm tra tương thích. Giữ toàn bộ test RC/Home hiện có.
4. Làm GUI nền đen và worker điện thoại. Thử nút và kích thước cửa sổ thật.
5. Chỉ kết luận Việt hóa hoạt động khi overlay lookup và màn hình thực tế xác nhận. Nếu phiên bản/ROM không hỗ trợ, hiển thị nguyên nhân cụ thể.
6. Chạy suite, build EXE, cập nhật hướng dẫn và bằng chứng cục bộ. Không công bố release mới trong bước này.

## Kết quả local

Desktop nền đen, hai nền tảng và nút cài/mở RC Launcher hoàn tất; 141 tests/95,72% core coverage, EXE smoke/imports/assets PASS. Phone Fly1.21.12 + vi2 đã chứng minh qua ARTEMIS/ADB; vi3 với Hệ thống cảm biến đã build, chưa cài vì phone đã ngắt USB. RC reviewed6 đã cài và lookup đúng Hệ thống cảm biến. RC Launcher preview3 đã cài/quan sát; user sửa scope sang ít chữ/ít RAM và bỏ dock trùng native3bar. Toàn bộ thay đổi mới là local, chưa cập nhật release GitHub.
