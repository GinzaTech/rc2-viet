# RC2 Studio

Patch tiếng Việt cho DJI Fly trên tay DJI RC 2, thêm menu tiện ích và tạo animation khởi động/tắt máy. Chạy trên Windows x64.

**[Tải bộ cài](https://github.com/GinzaTech/rc2-viet/releases/latest)** · [Hướng dẫn Animation](docs/ANIMATION_R14.md) · [Thông tin bản Fly 1.21.18](docs/FLY_12118.md)

## Cài lên RC 2

1. Tải EXE ở trang Releases rồi mở. Không cần cài thêm Python, Java hay ADB.
2. Bật tay, nối cáp USB dữ liệu. Đưa Fly về trang chủ; máy bay phải ở mặt đất, động cơ đã dừng.
3. Khi tay hỏi **Allow USB debugging**, tích **Always allow from this computer** rồi bấm **Allow**.
4. Chọn đúng tay và bấm **Patch tiếng Việt + menu và cài**. Giữ nguồn và cáp đến khi ứng dụng báo xong.

Nếu Windows chưa nhận tay, kiểm tra cáp và driver ADB/WinUSB. Nếu đã bỏ lỡ hộp thoại cấp quyền, bấm **Xin lại quyền USB** trong ứng dụng.

Bộ cài nhận diện đúng phiên bản và hash APK trước khi patch. Các bản Fly RC đang có profile:

| Phiên bản | Mã phiên bản | Trạng thái |
| --- | --- | --- |
| 1.21.8 | 3115809 | Có sẵn |
| 1.21.10 | 3115981 | Có sẵn |
| 1.21.16 | 3132286 | Có sẵn |
| 1.21.18 | 3132442 | Đã cài và kiểm tra menu trên RC 2 |

Fly **1.21.18** đã cài trên RC 2 và kiểm tra tiếng Việt, hai trang menu cùng nút quay lại. Mẫu boot animation đã chạy sau reboot, cấu hình và hash được đọc lại; chưa thử bay hoặc hiệu chuẩn gimbal. APK DJI Fly dành cho điện thoại không dùng thay APK trên RC 2.

APK đã patch dùng khóa ký riêng của bộ cài. Giữ khóa này trên PC để những lần cập nhật sau có thể cài đè cùng chữ ký. Khi chuyển từ Fly gốc ký DJI sang bản mod, có thể phải sao lưu rồi gỡ/cài lại; ứng dụng sẽ yêu cầu xác nhận vì thao tác này có thể mất dữ liệu Fly. Không thể giữ chữ ký DJI sau khi sửa APK nếu không có khóa ký riêng của họ.

## Bản vá có gì?

- Tiếng Việt tích hợp trong Fly, gồm các cách gọi **Báo mất flycam**, **DJI Cellular**, **Huỷ kết nối thiết bị** và **Phần mềm mới đã sẵn sàng**.
- Menu đèn càng, ẩn/hiện HUD bằng chạm hai lần, xuất hình và FCC/khôi phục vùng đã đọc.
- **Tiện ích nâng cao** giữ hai mục: **Nâng cao** và **Hiệu chỉnh gimbal**.
- Đã bỏ phần giải mã bản ghi.

Các chức năng liên quan máy bay còn phụ thuộc model, firmware và phản hồi SDK. Kiểm tra thành công trên PC không đồng nghĩa đã thử chức năng đó trên tay hoặc khi bay.

## Boot animation

Bấm **Mở Animation** để vào trình thiết kế trong cùng cửa sổ; **Quay lại** giữ bản nháp đang làm.

Thêm chữ, ảnh và nền; chỉnh từng lớp, font, màu, vị trí và thời điểm xuất hiện. Có sẵn mẫu sci-fi, kim loại, neon và các hiệu ứng như hiện từng chữ, trượt, glitch, quét sáng. Mỗi lớp dùng hiệu ứng và thời lượng riêng, nên có thể cho dòng trên chạy xong rồi mới tới dòng dưới.

Lưu thiết kế thành `.rc2anim` để sửa tiếp, hoặc xuất ZIP Android/GIF/ảnh xem trước. Có thể chọn một ZIP hợp lệ có sẵn để cài, không cần xuất lại thiết kế. Khởi động và tắt máy có nút cài/khôi phục riêng.

Mặc định **1920 × 1080, 24 fps**. Giới hạn: 15 giây, 30 fps, ZIP 512 MiB. Phần cài chỉ nhận **RC331 có thư viện DJI khớp hash đã đối chiếu**. Tạo/xuất được animation chưa phải bằng chứng nó đã chạy đúng lúc khởi động trên tay.

## Chạy và build từ mã nguồn

Dùng Python 3.12 trên Windows. Nếu clone bằng Git, chạy `git lfs pull` để lấy đủ asset và tệp lớn.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe auto_patch_app.py
```

Build EXE bằng thư mục làm việc mới:

```powershell
$rc2BuildDir = Join-Path 'local-artifacts' ('build-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
.\.venv\Scripts\python.exe scripts\build_auto_patch_exe.py --build-root $rc2BuildDir
```

Đầu ra hiện tại là `dist/RC2-TuDong-Patch-r14.6.1.exe`; báo cáo nằm trong thư mục build. Bộ cài không nhúng APK Fly đầy đủ hay khóa ký riêng.

Chạy kiểm tra bằng `python -m pytest`; các bài Android/JVM cần **JDK 17**, với `java` và `javac` trong `PATH`. EXE cũng có `--self-test`, `--animation-self-test` và `--animation-ui-self-test`; thêm `--work <thư mục mới>` để lưu kết quả. Các chế độ này kiểm tra trên PC, không mở USB.

Dự án độc lập, không thuộc DJI. Giấy phép các thành phần: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
