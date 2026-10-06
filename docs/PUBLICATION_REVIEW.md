# Review bản bàn giao độc lập

Phạm vi: tên RC2 Việt, README/hướng dẫn, nguồn độc lập, đủ APK trong thư mục app Windows và EXE có thể tải từ GitHub. Không thêm tính năng trên tay hoặc tiếp tục kiểm tra navigation trong công việc xuất bản.

## Nguồn và artifact

- Mã app giữ luồng cài/activation/USB như bản đã thử; đổi tên GUI và bổ sung cấu hình pytest phù hợp Tcl/Tk trên Windows.
- Android builders dùng thư mục signing do biến môi trường chỉ định; không giữ đường dẫn cá nhân hoặc khóa ký.
- 7 APK đối chiếu SHA256 với inventory nguồn; 4 APK dùng được khác rõ với 2 intermediate và 1 SystemUI tham chiếu.
- Nguồn XML được dọn whitespace cuối dòng; tên/thuộc tính và văn bản XML sau chuẩn hóa khoảng trắng không thay đổi. APK signed được giữ nguyên byte/hash.
- License/notice giữ nội dung, chỉ chuẩn hóa khoảng trắng và có liên kết đúng nguồn/tag.

## Kiểm tra

88 tests app, 9 tests dịch; coverage 94,52% của phạm vi được đo. GUI startup và kiểm tra assets trong EXE đạt. Các ví dụ build đã dùng trong môi trường .venv mới của repository độc lập. pip-audit đã tìm các bản công cụ cũ, được cập nhật và audit lại không còn lỗ hổng đã biết; báo cáo chỉ áp dụng dependency Python.

Tệp xuất bản được kiểm tra khóa ký/khóa ADB/token GitHub, số sê-ri và đường dẫn cá nhân. Git không chứa .venv, dữ liệu DJI Fly, backup, log/trace hoặc dump framework. Git author dùng GitHub noreply. Các ZIP được tạo từ danh sách tệp xuất bản, không sao chép toàn bộ thư mục làm việc.

## Giới hạn được ghi rõ

Không gọi bản dịch là DJI Fly mod thực thi; không gọi FreeFCC đã kích hoạt; không gọi offline đã hết hoặc navigation đã bật. Lịch sử trước reset khác trạng thái sau reset. Không hứa không cần Allow trên mọi lần khởi động, không hứa ổn định trong bay hoặc firmware khác.

Không có phát hiện critical/high trong phạm vi mã/tệp được review. Đây không phải audit độc lập toàn bộ firmware, các APK third party hoặc chứng nhận an toàn bay.
