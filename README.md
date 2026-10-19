# RC2 Auto Patch r13.1 + DJI Fly Android 1.21.12

Bộ cài Windows tự đọc APK DJI Fly từ DJI RC 2, nhận diện đúng phiên bản, patch tiếng Việt và menu local, ký APK rồi cài lại qua USB. Bản phát hành này chỉ hỗ trợ DJI Fly RC **1.21.8** và **1.21.10**.

## Chức năng

- Tự patch tiếng Việt
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

## APK dành cho điện thoại Android

Release `r13.1` còn có `DJI-Fly-Android-1.21.12-Vietnamese-Menu-r13.1.apk`. Đây là APK DJI Fly **1.21.12 dành cho điện thoại Android**, không phải APK cài lên RC 2. Bản này đã nhúng trực tiếp tiếng Việt, các chuỗi Gmail/khởi tạo tài nguyên và menu r13.1.

APK được ký bằng khóa của dự án nên Android không thể cập nhật đè lên DJI Fly chính thức có chữ ký DJI. Hãy sao lưu dữ liệu cần thiết, gỡ DJI Fly chính thức rồi cài APK này. Kiểm tra host xác nhận APK hợp lệ, giữ loader AppGuard và phục hồi đúng từng byte về nguồn chính thức; việc mở ứng dụng và các thao tác phần cứng RC 2 trong menu chưa được kiểm thử trên điện thoại thật.

## Kiểm chứng phát hành

- EXE: `154401692` byte
- SHA-256: `224365cef7f15dfec5671293445376851a4d2ebe41f864cb7d80e5a733556546`
- APK Android 1.21.12: `727481653` byte
- SHA-256 APK: `6328e7679143163de8ef16034943ab99e86410891c058dffa99c8729a6ffe896`
- Kiểm thử nguồn: `2490 passed, 3 skipped`
- Self-test EXE và smoke UI: `PASS`
- APK Android: ZIP, chữ ký SDK 30, loader V2 và khôi phục nguồn chính xác đều `PASS`

Chi tiết máy đọc được ở [dist/r13.1-release-verification.json](dist/r13.1-release-verification.json) và [dist/SHA256SUMS.txt](dist/SHA256SUMS.txt). Các kiểm tra cuối là kiểm tra host/offline; EXE r13.1 cuối chưa được cài lại lên RC 2 vật lý trong bước phát hành này.

## Phạm vi mã nguồn

Nhánh `main` là cây phát hành r13.1 đã thu gọn: ứng dụng auto-patch, mã menu hiện tại, recipe cho hai phiên bản RC, tài nguyên Android 1.21.12 đã biên dịch, bộ build và các test liên quan. Kho không chứa firmware, APK DJI Fly nguồn, bản sao lưu/khôi phục của người dùng, khóa ký riêng, thư mục nghiên cứu hoặc artifact cũ.

