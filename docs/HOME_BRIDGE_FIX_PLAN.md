# Home bridge v2 — bỏ màn trung gian không cần thiết

Người dùng báo thấy màn chờ của local.rc2.home khi boot và bấm Home giữa. Đã đọc versionCode1/versionName1.0, HOME property vẫn trỏ cầu, user0 RUNNING_UNLOCKED; bấm Home xong đã chuyển về Lawnchair. Source v1 tạo giao diện chờ trong onCreate trước khi kiểm tra sẵn sàng, không finish sau forward và không xử lý onNewIntent riêng.

Thiết kế sửa có giới hạn: theme trong suốt, tắt starting preview/animation; thử forward ngay, finish sau khi mở launcher; xử lý Home intent mới; tạo màn fallback sau độ trễ nếu dữ liệu vẫn khóa hoặc mở launcher lỗi. Giữ Direct Boot, component và quyền. Không đổi nav/radio/USB debugging.

- [x] Kiểm thử hồi quy xử lý retry/forward ở Java và nâng gói cầu cũ trong app PC.
- [x] Build APK cùng signer, cập nhật pin và manifest tài nguyên của bản local.
- [x] Cài -r, kiểm tra Home nhiều lần, Android unlock và ảnh màn hình; kiểm tra boot riêng nếu được thực hiện.
- [x] Build EXE local và cập nhật hướng dẫn/giới hạn. Chưa push hoặc thay release public trong yêu cầu này.
