# RC2 Auto Patch r13.1

Bộ cài Windows tự đọc APK DJI Fly từ DJI RC 2, nhận diện đúng phiên bản, patch tiếng Việt và menu local, ký APK rồi cài lại qua USB. Bản phát hành này chỉ hỗ trợ DJI Fly RC **1.21.8** và **1.21.10**.

## Chức năng

- Tự patch tiếng Việt; dùng “Gmail” ở các trường đăng nhập và câu khởi tạo tài nguyên đã được viết lại dễ đọc.
- Bật/tắt đèn càng.
- Chạm hai lần để ẩn hoặc hiện HUD.
- Xuất hình với HUD, không HUD, hoặc ép thử lại đường xuất hình.
- Chuyển profile sóng FCC hoặc `EC / gốc`; lựa chọn EC/gốc khôi phục cấu hình radio ban đầu đã đọc từ tay.
- `Tiện ích nâng cao` gồm đúng hai mục: `Nâng cao` và `Hiệu chỉnh gimbal`.
- Tạo lại phiên ADB khi USB gián đoạn mà không làm mất tiến độ build.

## Cách chạy

1. Tải [RC2-TuDong-Patch-r13.1.exe](dist/RC2-TuDong-Patch-r13.1.exe).
2. Bật RC 2, về Launcher/Settings, nối bằng cổng và cáp USB 3.x.
3. Mở EXE, chọn `Always allow` rồi `Allow` nếu tay hỏi quyền USB debugging.
4. Chỉ xác nhận bắt đầu khi máy bay đã hạ cánh và động cơ đã dừng.

Ứng dụng không cần cài Python, Java hay tải dữ liệu qua mạng. APK DJI Fly nguyên bản và khóa ký riêng không nằm trong EXE; APK nguồn được đọc trực tiếp từ tay khi chạy.

## Kiểm chứng phát hành

- EXE: `154401692` byte
- SHA-256: `224365cef7f15dfec5671293445376851a4d2ebe41f864cb7d80e5a733556546`
- Kiểm thử nguồn: `2490 passed, 3 skipped`
- Self-test EXE và smoke UI: `PASS`

Chi tiết máy đọc được ở [dist/r13.1-release-verification.json](dist/r13.1-release-verification.json) và [dist/SHA256SUMS.txt](dist/SHA256SUMS.txt). Các kiểm tra cuối là kiểm tra host/offline; EXE r13.1 cuối chưa được cài lại lên RC 2 vật lý trong bước phát hành này.

## Phạm vi mã nguồn

Nhánh `main` là cây phát hành r13.1 đã thu gọn: ứng dụng auto-patch, mã menu hiện tại, recipe cho hai phiên bản, tài nguyên dịch, bộ build và các test liên quan. Kho không chứa firmware, APK DJI Fly nguồn, bản sao lưu/khôi phục của người dùng, khóa ký riêng, thư mục nghiên cứu hoặc artifact cũ.

