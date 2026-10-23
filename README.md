# RC2 Studio r14.6.1

Công cụ Windows cho DJI RC 2: tự lấy APK DJI Fly trên tay, patch tiếng Việt và menu nâng cao; thiết kế và cài animation khởi động/tắt máy.

Bản ứng dụng: **r14.6.1** · Bản cập nhật bản dịch: **r14.6.1-vi3** · [Bản phát hành mới nhất](https://github.com/GinzaTech/rc2-viet/releases/latest) · [RC2-TuDong-Patch-r14.6.1.exe](dist/RC2-TuDong-Patch-r14.6.1.exe) · Windows x64.

Đã hoàn tất rà nghĩa toàn bộ bản dịch Fly RC 1.21.16: **11.994 tài nguyên / 8.786 nhóm câu**, sửa **3.052 tài nguyên**. Bản vi3 đổi thêm **3 nhãn nhập tài khoản** sang **Gmail** theo yêu cầu, đưa danh mục lên **3.055 mục đã chỉnh**; chức năng kiểm tra tài khoản vẫn chấp nhận email từ các nhà cung cấp khác. **933 bài kiểm tra nghiệm thu phát hành đạt** trong 30 mô-đun; EXE tự kiểm cả ba profile và dựng thành công từ APK gốc lẫn vi2. Gmail vi3 chưa cài lên tay vì Windows mất kết nối USB với RC 2. [Báo cáo vi3](dist/r14.6.1-vi3-12116-verification.json) ghi kết quả mới; [báo cáo vi2](dist/r14.6.1-vi2-12116-verification.json) và [báo cáo trước đợt rà toàn bộ](dist/r14.6.1-12116-verification.json) giữ nguyên bằng chứng lịch sử.

EXE được lưu bằng Git LFS. Nếu lấy dự án bằng Git, cài Git LFS rồi chạy `git lfs pull` để tải tệp chạy đầy đủ. [SHA-256](dist/SHA256SUMS.txt).

## Sử dụng

1. Mở EXE. Không cần cài Python, Java hoặc ADB riêng; Windows cần driver ADB/WinUSB phù hợp.
2. Bật RC 2, nối cáp USB dữ liệu và giữ tay ở Launcher/Settings. Chọn đúng serial rồi xác nhận máy bay đã hạ cánh, động cơ dừng.
3. Khi tay hỏi **Allow USB debugging**, chọn **Always allow** rồi **Allow**.
4. Bấm **Patch tiếng Việt + menu và cài**. App đọc APK, nhận diện nguồn, patch, ký, kiểm tra rồi cài; giữ cáp và nguồn đến khi có kết quả.
5. Bấm **Mở Animation** để thiết kế trong cùng cửa sổ. **Quay lại** trở về trang tiếng Việt/menu, giữ bản nháp và tác vụ xuất đang chạy.

Profile APK được hỗ trợ: **Fly RC 1.21.8 / 1.21.10 / 1.21.16**, đối chiếu phiên bản, mã phiên bản và SHA-256 nguồn. Bản 1.21.16 dùng recipe menu và bảng dịch riêng, lấy từ APK gốc trên RC 2; không dùng APK điện thoại thay thế. Đợt rà 11.994 tài nguyên và ba nhãn Gmail mới chỉ áp dụng cho **1.21.16**; hai profile cũ vẫn dùng bảng dịch riêng đã có.

APK đã sửa được ký bằng khóa mod lưu riêng trên PC, không phải khóa DJI. Các bản mod cùng khóa có thể cập nhật giữ dữ liệu theo điều kiện của Android; APK chính thức của DJI không cài đè trực tiếp lên bản mod qua cơ chế cập nhật thông thường. Chứng chỉ trong APK không chứa khóa ký riêng để tái ký thành DJI. Chỉ bật tùy chọn gỡ/cài lại khi chấp nhận xóa dữ liệu Fly nếu khác chữ ký. [Chi tiết bản 1.21.16 và chữ ký](docs/FLY_12116.md).

**Xin lại quyền USB** có ở cả hai trang. Có thể xin riêng trước khi cài hoặc bấm lại khi đang chờ Allow. Sau 10 giây chưa được chấp thuận, app tạo phiên chờ mới bằng cùng khóa ADB; tổng thời gian chờ tối đa 120 giây. Phiên đã được cấp quyền không bị ngắt bởi cơ chế này. Nút xin quyền không bỏ qua xác nhận trên RC 2.

## Tiếng Việt và menu

Bản r14.6 bổ sung Fly RC **1.21.16 / 3132286**. Bản r14.6.1 sửa nút menu không xuất hiện trên trang chủ khi Fly đổi tên điểm neo giao diện. Giữ thay đổi từ r14.5: gỡ nút ATTI, tắt GPS và phần hiển thị điện áp từng cell pin của menu đặc biệt khỏi màn hình bay. Mục **Giải mã bản ghi** cùng cơ chế giải mã tự động và thủ công cũng được gỡ.

Cập nhật bản dịch ngày 23/10/2026: giữ **Aircraft Flyaway → Báo mất flycam**, **Phần mềm mới đã sẵn sàng**, tên thương hiệu **DJI Cellular**, **Cellular Data → Dữ liệu di động** và hai nút **Unbind devices → Huỷ kết nối thiết bị**. [Phạm vi sửa thuật ngữ ban đầu](docs/FLYAWAY_WORDING.md).

Theo yêu cầu, hai nhãn **Enter phone number or email / Enter Phone Number or Email** đổi thành **Nhập số điện thoại hay Gmail**; nhãn **Enter email** đổi thành **Nhập Gmail**. Đây là lựa chọn chữ hiển thị trên ba ô nhập tài khoản của 1.21.16; không thay mọi từ “email” trong ứng dụng hoặc hạn chế loại địa chỉ người dùng nhập.

Đợt rà toàn bộ đối chiếu nghĩa từng nhóm câu Anh/Việt cùng tên tài nguyên: **11.984 chuỗi, 4 mảng và 6 nhóm số nhiều**; đã sửa **3.048 chuỗi, 3 mảng và 1 nhóm số nhiều**. Các sửa đổi xử lý sai nghĩa, đảo phủ định, thiếu cảnh báo/chỉ dẫn, sai hướng bay, nút hành động và trạng thái; khôi phục tên sản phẩm, thuật ngữ và định danh kỹ thuật bị dịch nhầm. Placeholder, số liệu, đơn vị, URL, style và cấu trúc tài nguyên được kiểm tra riêng. Đây là rà nghĩa bằng AI và kiểm tra cấu trúc trên PC; chưa kiểm chứng bố cục, câu ghép hoặc cách hiển thị của toàn bộ bản dịch trên RC 2. [Chi tiết phạm vi và bằng chứng](docs/FLY_12116.md).

Tiến độ được lưu riêng theo recipe và bản dịch, giữ các tệp r14.4 để đối chiếu. Nếu APK trên tay khớp toàn bộ recipe hiện tại, app kiểm tra lại gói và báo hoàn tất mà không ký hoặc cài lại.

Với bản mod r14.6 đã phát hành cho Fly RC 1.21.16, r14.6.1 nhận diện recipe cũ, kiểm tra và khôi phục APK nguồn chính xác rồi dựng bản sửa. Luồng này đã được kiểm chứng với đúng APK r14.6; không tự nhận mọi APK cùng số phiên bản. Cập nhật cùng khóa r14.6 → r14.6.1 trên tay thử nghiệm giữ dữ liệu ứng dụng.

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

[Hướng dẫn Animation và kiểm chứng r14.5](docs/ANIMATION_R14.md).

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
$rc2BuildDir = Join-Path 'local-artifacts' ('build-r14.6.1-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
.\.venv\Scripts\python.exe scripts\build_auto_patch_exe.py --build-root $rc2BuildDir
```

Đầu ra: `dist/RC2-TuDong-Patch-r14.6.1.exe`; hash, inventory và thông tin đóng gói ở `build-report.json` trong thư mục build vừa tạo.

Đợt rà nghĩa 1.21.16 có [danh mục công khai](assets/translation/fly12116-reviewed.json) và lệnh tái áp dụng từ bảng lưu trữ, không cần cache hoặc mô hình dịch máy. [Hướng dẫn tái áp dụng và giới hạn biên soạn ban đầu](docs/FLY_12116.md) dùng `--work` ngắn ngoài cây dự án để kiểm tra AAPT2 trên Windows.

## Kiểm tra ngoại tuyến

Các lệnh sau không mở USB hoặc sửa thiết bị. Dùng đường dẫn làm việc ngắn để tránh giới hạn đường dẫn Windows; báo cáo được ghi trong thư mục `--work`:

```powershell
$rc2Check = Join-Path $env:LOCALAPPDATA 'RC2Check'
.\dist\RC2-TuDong-Patch-r14.6.1.exe --self-test --work "$rc2Check\tools"
.\dist\RC2-TuDong-Patch-r14.6.1.exe --animation-self-test --work "$rc2Check\export"
.\dist\RC2-TuDong-Patch-r14.6.1.exe --animation-ui-self-test --work "$rc2Check\editor"
.\dist\RC2-TuDong-Patch-r14.6.1.exe --navigation-ui-self-test --work "$rc2Check\navigation"
.\dist\RC2-TuDong-Patch-r14.6.1.exe --animation-package-ui-self-test --work "$rc2Check\package"
```

`--smoke-ui` và `--smoke-animation-ui` mở giao diện, chụp đúng cửa sổ và ghi báo cáo; chỉ kiểm kê thiết bị Windows, không mở phiên USB. Có thể chỉ định `--report <tệp.json>` cho mọi chế độ kiểm tra.

Xuất thiết kế từ dòng lệnh:

```powershell
.\dist\RC2-TuDong-Patch-r14.6.1.exe --animation-export .\mau.rc2anim --work .\local-artifacts\export
```

## Phạm vi kiểm chứng

- Kiểm thử nguồn, GUI và backend lấy từ EXE xác minh hành vi trên PC; USB/ADB giả lập không thay thế kiểm thử RC 2 thật.
- **r14.5 đã cập nhật giữ dữ liệu và kiểm tra trực tiếp trên RC 2 / Fly 1.21.8 khi máy bay đã hạ cánh, động cơ dừng.** Màn hình bay, menu Nâng cao và thao tác ẩn/hiện HUD đều không còn các thành phần đã gỡ. Fly 1.21.10 đã dựng và kiểm chứng offline; chưa chạy trên tay trong đợt này.
- Bản 1.21.16 được lấy trực tiếp từ RC 2 sau cập nhật, kiểm chữ ký DJI và hash trước/sau. Đã sao lưu rồi gỡ/cài mod với sự cho phép do chữ ký khác DJI; lần cập nhật tiếp theo r14.6 → r14.6.1 trước khi sửa tên DJI Cellular giữ nguyên UID và không xóa dữ liệu. Trên APK đó đã kiểm tra giao diện tiếng Việt, nút menu trang chủ, Tiện ích nâng cao, trang Nâng cao và nút quay lại.
- r14.6: 814 bài kiểm tra nguồn đạt; EXE phát hành đã tự kiểm tra cả ba profile và dựng APK 1.21.16 có nội dung khớp bản dựng từ mã nguồn. Chữ ký V3 trên SDK 30 đúng khóa mod cũ; phục hồi APK gốc khớp byte. [Bằng chứng](dist/r14.6-12116-verification.json).
- Đợt sửa 14 chuỗi r14.6.1 trước đây đã kiểm tra nguồn, phục hồi APK gốc và tự kiểm EXE trên ba profile; APK dựng từ stock và các mod cũ có nội dung ZIP khớp bản dựng từ nguồn. [Bằng chứng trước đợt rà toàn bộ](dist/r14.6.1-12116-verification.json) và [release r14.6](https://github.com/GinzaTech/rc2-viet/releases/tag/r14.6) được giữ làm lịch sử.
- r14.6.1-vi2: **907 bài kiểm tra nghiệm thu phát hành đạt** trong 29 mô-đun từ bản xuất nguồn sạch, không lỗi hoặc bỏ qua. EXE tự kiểm cả ba profile và dựng thành công từ bốn đầu vào đã pin: APK gốc, bản r14.6.1 đã phát hành (`91e03284…`), bản từng cài trên tay (`741a1909…`) và bản r14.6 (`5e9dac81…`). Các nội dung ZIP khớp bản dựng từ nguồn; phục hồi APK gốc khớp byte. Kiểm tra tài nguyên sau nhúng đối chiếu 266.594 cấu hình, xác nhận 47.678 cấu hình đổi thuộc đúng 3.052 tài nguyên đã sửa; ID, tập cấu hình và giá trị/style ngoài phạm vi được giữ. [Bằng chứng phát hành vi2](dist/r14.6.1-vi2-12116-verification.json) giữ nguyên trạng thái thiết bị tại thời điểm phát hành.
- Sau khi phát hành vi2, đã sao lưu **390.326.272 byte** dữ liệu trên RC 2 rồi gỡ Fly gốc ký DJI và cài vi2 theo sự cho phép trước đó. Đây là lần gỡ/cài do khác chữ ký; không phải cập nhật giữ dữ liệu. Bản Gmail vi3 dùng cùng khóa mod để cập nhật nối tiếp.
- r14.6.1-vi3: **933 bài kiểm tra nghiệm thu phát hành đạt** trong 30 mô-đun từ bản xuất nguồn sạch, không lỗi hoặc bỏ qua. Đã đối chiếu 14 tệp thay đổi và xác nhận 297 tệp nguồn không đổi sau kiểm thử. EXE tự kiểm ba profile, dựng từ APK gốc và đúng APK vi2 đã cài trên tay; cả hai phục hồi nguồn khớp byte, dùng cùng khóa mod và có 15.747 mục ZIP payload khớp bản dựng từ mã nguồn. Đây là kiểm chứng trên PC; Gmail vi3 chưa được cài hoặc kiểm tra runtime vì Windows không còn nhận RC 2 qua USB. [Bằng chứng vi3](dist/r14.6.1-vi3-12116-verification.json).
- Lần kiểm thử thăm dò toàn kho mã của vi2 có 1.493 ca: 1.491 đạt và 2 lỗi ngoài 29 mô-đun nghiệm thu, thuộc kiểm tra asset Android 1.21.12 và JVM DisplayPort retry. Cả hai lỗi được tái hiện trên commit nền chưa áp thay đổi và được ghi riêng trong báo cáo vi2; không chạy lại toàn kho mã cho vi3.
- Trên APK trước khi sửa tên DJI Cellular, đã mở màn hình bay khi không nối máy bay và đối chiếu XML/ảnh: không còn nút ATTI, tắt GPS, lớp điện áp cell của mod hoặc mục giải mã bản ghi trong các màn hình đã xem. Đã trở lại trang chủ, đọc lại hash APK đã cài và xác nhận tiến trình còn chạy.
- Trên cùng APK đó, trang Hiệu chỉnh gimbal đã hiển thị; khi không nối máy bay, nút bắt đầu bị vô hiệu hóa. Chưa thử hiệu chuẩn hoặc chuyển động gimbal; SDK có báo `REQUEST_HANDLER_NOT_FOUND` trong lần mở trang này.
- Cài animation chỉ hỗ trợ thư viện DJI đã đối chiếu hash trên RC331/V14; firmware khác cần khảo sát riêng.
- Công cụ không tự root, mở khóa bootloader, remount phân vùng hệ thống hay tự khởi động lại tay.
- Đèn thật, xuất hình vật lý, RF, độ ổn định dài hạn và thử bay cần đánh giá riêng trên thiết bị.

Dự án độc lập, không phải ứng dụng chính thức của DJI. Thông tin giấy phép của các thành phần ở [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
