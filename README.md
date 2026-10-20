# RC2 Studio r14.4

Công cụ Windows cho DJI RC 2: tự lấy APK DJI Fly trên tay, patch tiếng Việt và menu nâng cao; thiết kế và cài animation khởi động/tắt máy.

Bản hiện tại: **r14.4** · [Tải RC2-TuDong-Patch-r14.4.exe](dist/RC2-TuDong-Patch-r14.4.exe) · Windows x64.

EXE được lưu bằng Git LFS. Nếu lấy dự án bằng Git, cài Git LFS rồi chạy `git lfs pull` để tải tệp chạy đầy đủ. [SHA-256](dist/SHA256SUMS.txt).

## Sử dụng

1. Mở EXE. Không cần cài Python, Java hoặc ADB riêng; Windows cần driver ADB/WinUSB phù hợp.
2. Bật RC 2, nối cáp USB dữ liệu và giữ tay ở Launcher/Settings. Chọn đúng serial rồi xác nhận máy bay đã hạ cánh, động cơ dừng.
3. Khi tay hỏi **Allow USB debugging**, chọn **Always allow** rồi **Allow**.
4. Bấm **Patch tiếng Việt + menu và cài**. App đọc APK, nhận diện nguồn, patch, ký, kiểm tra rồi cài; giữ cáp và nguồn đến khi có kết quả.
5. Bấm **Mở Animation** để thiết kế trong cùng cửa sổ. **Quay lại** trở về trang tiếng Việt/menu, giữ bản nháp và tác vụ xuất đang chạy.

Profile APK được hỗ trợ: **Fly RC 1.21.8 / 1.21.10**, đối chiếu phiên bản và SHA-256 nguồn. Mặc định cập nhật giữ dữ liệu khi cùng chữ ký. Chỉ bật tùy chọn gỡ/cài lại khi chấp nhận xóa dữ liệu Fly nếu khác chữ ký.

**Xin lại quyền USB** có ở cả hai trang. Có thể xin riêng trước khi cài hoặc bấm lại khi đang chờ Allow. Sau 10 giây chưa được chấp thuận, app tạo phiên chờ mới bằng cùng khóa ADB; tổng thời gian chờ tối đa 120 giây. Phiên đã được cấp quyền không bị ngắt bởi cơ chế này. Nút xin quyền không bỏ qua xác nhận trên RC 2.

## Tiếng Việt và menu

- Tiếng Việt tích hợp vào APK được dựng từ đúng nguồn đã nhận diện.
- Đèn càng; chạm hai lần ẩn/hiện HUD; xuất hình; FCC và khôi phục vùng gốc đã đọc trong phiên.
- **Tiện ích nâng cao** gồm **Nâng cao** và **Hiệu chỉnh gimbal**.
- Kiểm tra trạng thái an toàn, phản hồi và đọc lại trước khi báo thao tác thành công.

[Chi tiết pipeline và profile APK](docs/AUTO_PATCH_R13.md).

## Animation

- Nhiều lớp chữ/ảnh, sắp xếp và nhân bản; chỉnh font, màu, cỡ, vị trí, độ rõ, thời điểm và thời lượng từng lớp.
- Nền màu, gradient hoặc ảnh; 5 mẫu **Sci-fi nổi**, **Kim loại nổi**, **Neon**, **Tối giản**, **Công nghệ xanh**.
- 16 hiệu ứng xuất hiện: hiện ngay, mờ dần, từng chữ, trượt trái/phải/lên/xuống, phóng to, nảy, glitch, quét sáng, xoay, sóng ký tự, neon, lau ngang, lấy nét.
- 6 kiểu lặp: đứng yên, nhịp sáng, lơ lửng, ánh sáng lướt, xoay nhẹ, sóng ngang.
- Xem trước khi nhập chữ, phát/dừng, kéo lớp trên khung hình và chỉnh timeline.
- Lưu nhiều thiết kế `.rc2anim`, kèm ảnh/font để mở trên máy khác; xuất ZIP Android, GIF, poster và SHA-256.
- Chọn ZIP animation có sẵn để cài độc lập với thiết kế đang mở. App kiểm tra ZIP/PNG và bản sao đầu vào trước khi mở USB.
- Cài/khôi phục riêng cho khởi động và tắt máy; lưu cấu hình trước đó, kiểm tra quyền và hash sau khi chép.

Mặc định 1920×1080, 24 fps. Giới hạn xuất: tổng 15 giây, tối đa 30 fps, ảnh giải mã của đoạn lặp tối đa 256 MiB, ZIP tối đa 512 MiB.

[Hướng dẫn Animation và kiểm chứng r14.4](docs/ANIMATION_R14.md).

## Chạy từ mã nguồn

Dùng **Python 3.12 trên Windows**. Cài dependency từ thư mục dự án:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe auto_patch_app.py
```

Các asset công cụ, recipe và tài nguyên đã pin phải có trong `assets/`. Build kiểm tra manifest/hash; không đổi pin để ép nhận nguồn chưa hỗ trợ. EXE chứa runtime và công cụ cần thiết, không nhúng toàn bộ APK Fly hoặc khóa ký riêng.

Tạo thư mục build mới cho mỗi lần dựng:

```powershell
$rc2BuildDir = Join-Path 'local-artifacts' ('build-r14.4-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
.\.venv\Scripts\python.exe scripts\build_auto_patch_exe.py --build-root $rc2BuildDir
```

Đầu ra: `dist/RC2-TuDong-Patch-r14.4.exe`; hash, inventory và thông tin đóng gói ở `build-report.json` trong thư mục build vừa tạo.

## Kiểm tra ngoại tuyến

Các lệnh sau không mở USB hoặc sửa thiết bị. Dùng đường dẫn làm việc ngắn để tránh giới hạn đường dẫn Windows; báo cáo được ghi trong thư mục `--work`:

```powershell
$rc2Check = Join-Path $env:LOCALAPPDATA 'RC2Check'
.\dist\RC2-TuDong-Patch-r14.4.exe --self-test --work "$rc2Check\tools"
.\dist\RC2-TuDong-Patch-r14.4.exe --animation-self-test --work "$rc2Check\export"
.\dist\RC2-TuDong-Patch-r14.4.exe --animation-ui-self-test --work "$rc2Check\editor"
.\dist\RC2-TuDong-Patch-r14.4.exe --navigation-ui-self-test --work "$rc2Check\navigation"
.\dist\RC2-TuDong-Patch-r14.4.exe --animation-package-ui-self-test --work "$rc2Check\package"
```

`--smoke-ui` và `--smoke-animation-ui` mở giao diện, chụp đúng cửa sổ và ghi báo cáo; chỉ kiểm kê thiết bị Windows, không mở phiên USB. Có thể chỉ định `--report <tệp.json>` cho mọi chế độ kiểm tra.

Xuất thiết kế từ dòng lệnh:

```powershell
.\dist\RC2-TuDong-Patch-r14.4.exe --animation-export .\mau.rc2anim --work .\local-artifacts\export
```

## Phạm vi kiểm chứng

- Kiểm thử nguồn, GUI và backend lấy từ EXE xác minh hành vi trên PC; USB/ADB giả lập không thay thế kiểm thử RC 2 thật.
- **r14.4 chưa kiểm thử xin quyền USB hoặc cài animation trên RC 2 thật.** Không suy ra kết quả phần cứng từ self-test.
- Cài animation chỉ hỗ trợ thư viện DJI đã đối chiếu hash trên RC331/V14; firmware khác cần khảo sát riêng.
- Công cụ không tự root, mở khóa bootloader, remount phân vùng hệ thống hay tự khởi động lại tay.
- Đèn thật, xuất hình vật lý, RF, độ ổn định dài hạn và thử bay cần đánh giá riêng trên thiết bị.

Dự án độc lập, không phải ứng dụng chính thức của DJI. Thông tin giấy phép của các thành phần ở [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
