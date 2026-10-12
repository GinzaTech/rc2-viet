# Dùng RC2 Việt Basic 0.10.1

Bản public dành cho Việt hóa và menu LED/HUD/xuất hình/radio. Trong tab **Tay DJI RC 2**, **Cài / cập nhật menu** và **Bật / cập nhật tiếng Việt** là hai thao tác riêng. Bản thử Advanced ở sibling cục bộ `rc2-viet-advanced-local` không được xuất bản hoặc phân phối trong EXE public; không có bước chọn Advanced.

## Kết nối và kiểm tra

1. Mở EXE Basic hoặc giải nén Portable, giữ thư mục `translation-engine` cạnh EXE. Đối chiếu version/hash với metadata của đúng artifact; tên file không chứng minh đó là bản 0.10.1 cuối.
2. Nối USB dữ liệu và bấm **Allow USB debugging** trên thiết bị nếu được hỏi. Driver ADB/WinUSB vẫn cần ở Windows; ADB nhúng không thay driver.
3. Chọn **Điện thoại Android** hoặc **Tay DJI RC 2** và đúng serial, nhất là khi có nhiều thiết bị. Không dùng profile RC lên điện thoại.
4. RC yêu cầu model DJI RC 2, device `rc331`, Android 11/API 30 và quyền shell root sẵn có. Điện thoại dùng profile Việt hóa Android 15/API 35 có root; bấm **Kiểm tra tương thích** trước. Công cụ không tự root.
5. Giữ RC ở trang chủ/Launcher khi không bay. Nếu cần, dùng **Cài RC Launcher → Mở RC Launcher → Đặt RC Launcher làm màn hình chính**. Giữ launcher dự phòng đến khi có đường khôi phục.

Discovery hỗ trợ DJI USB **VID 2CA3 / PID 1021** và Android chỉ ADB **VID 18D1 / PID 4EE7**. Chế độ chỉ ADB được nhận diện sau cập nhật trong bối cảnh người dùng cung cấp; VID/PID không xác nhận đó là RC 2 được phép áp dụng. Model/device/SDK/root/serial/foreground và metadata/hash APK vẫn phải khớp.

ADB offline có thể cần cáp dữ liệu, Allow hoặc firmware hỗ trợ. Công cụ không reset thiết bị hay xóa khóa để ép kết nối. Không tắt USB debugging thủ công trên firmware đã gặp lỗi; Developer options có cảnh báo trước thao tác.

## Cài hoặc cập nhật menu Basic

1. Bấm **Cài / cập nhật menu** trong tab RC. App tự lấy APK `dji.go.v5` đang cài, kiểm tra nguồn, phục hồi nguồn nếu nhận diện được menu cũ, rồi patch/căn chỉnh/ký/kiểm chứng.
2. Cấu trúc APK, SDK hoặc nguồn phục hồi không nhận diện được phải dừng trước cài. Số phiên bản chỉ là metadata; không sửa pin để ép tương thích.
3. Cùng signer có thể cập nhật giữ dữ liệu. Khác signer, đọc báo cáo sao lưu và xác nhận gỡ/cài theo nhu cầu; khóa Keystore/đăng nhập có thể không khôi phục được.
4. Giữ cáp/nguồn đến kết quả cuối. Nếu phục hồi chưa hoàn tất, giữ backup và làm theo báo cáo lỗi.
5. Mở menu trên trang chủ để dùng LED, cử chỉ HUD, xuất hình và radio. LED/radio vẫn yêu cầu dữ liệu thực, mặt đất/động cơ dừng và kiểm tra lại sau ghi. Cài menu không tự bật FCC.

Tab điện thoại hiện dành cho Việt hóa; không có luồng cài menu điện thoại. Chi tiết và giới hạn từng mục ở [HUD_APK.md](HUD_APK.md).

## Bật hoặc cập nhật tiếng Việt

1. Bấm **Bật / cập nhật tiếng Việt** để dựng RRO tài nguyên riêng từ đúng APK hiện hành. Nếu vừa cài menu, chạy bước này sau khi app đã đọc lại APK mới.
2. Pipeline so khớp bộ nhớ dịch theo nguồn/contract và dịch bổ sung cục bộ. Bộ nhớ từ `C:\Users\kona\Desktop\rc2-viet-codex-initial-release` là dữ liệu người dùng cung cấp; không phải APK Fly nguồn và không phải gói cố định áp dụng cho mọi phiên bản.
3. Giữ các sửa diễn đạt đã rà, gồm **Chế độ C (Tốc độ chậm)**. Placeholder/markup/array/plural sai hoặc mục cần dịch còn bỏ dở phải chặn cài.
4. **Tắt bản dịch** ngừng áp dụng overlay; luồng RRO giữ APK/chữ ký/mã thực thi của Fly.

RRO không dịch HTML/server, chữ trong ảnh hay toàn bộ literal hardcode. Đủ tài nguyên và đúng cấu trúc không đồng nghĩa 100% UI hoặc mọi câu dịch máy đều đúng nghĩa. Xem [cơ chế Việt hóa](VIETNAMESE.md) và [profile điện thoại](ANDROID_PHONE.md).

## Giới hạn và báo cáo

**Basic 0.10.1 trên Fly RC 1.21.10: build/cài/boot/runtime chưa xác minh.** APK nguồn đã đọc gần nhất từ thiết bị vẫn là stock 1.21.8; nguồn 1.21.10 thực đang chờ lấy. Yêu cầu cài private 1.21.10 sau cập nhật đang được xử lý riêng. Dữ liệu nguồn, fixture SDK hoặc nhánh phục hồi legacy chỉ giúp đối chiếu, không chứng minh đầy đủ 1.21.10. Lần thử cấu trúc 1.21.10 trong 0.9.0 dùng RedFly đã mod, chỉ là lịch sử/tham chiếu và không xác nhận Fly chính thức hoặc bản public hiện tại.

Xuất hình USB-C/HDMI và HDR vật lý, công suất FCC, duy trì/khôi phục radio, thử bay và soak dài vẫn cần bằng chứng riêng. LED và launcher có quan sát ở các bản cũ; không tự chuyển kết quả đó sang payload/APK hiện hành. FreeFCC chỉ được cài/mở theo yêu cầu, không tự kích hoạt RF hay giới hạn độ cao.

Lưu báo cáo chẩn đoán khi cần; report runtime có thể chứa serial/path hoặc dữ liệu cá nhân, hãy kiểm tra trước khi chia sẻ. [Trạng thái bằng chứng](adaptive-menu-verification.json) và [báo cáo public](BAO_CAO_0.9.0.md) tách dữ liệu lịch sử khỏi các bước còn chờ xác minh.

Android 11 trên RC 2 dùng `cmd overlay lookup PACKAGE PACKAGE:TYPE/NAME`, không có `--user`; Android 15 giữ `--user 0`. 0.10.1 sửa chọn cú pháp theo SDK để gói dịch đúng không bị rollback do lệnh đọc lại sai. Sau cài menu, giữ tay ở **Settings/RC Launcher** trong lúc Việt hóa; mở lại DJI Fly sau khi có kết quả thành công.
