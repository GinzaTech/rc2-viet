# Kiểm chứng và trạng thái bàn giao

## Bằng chứng trước reset

| Hạng mục | Đã quan sát | Giới hạn |
| --- | --- | --- |
| Root/Android/đích | RC2 rc331, SDK 30, shell uid 0, DJI Fly 1.21.8/code 3115809 và đúng hash. | Một tay/firmware đã thử, không phải mọi RC 2. |
| RRO tiếng Việt | Package/state/resource lookup đúng; các câu theo yêu cầu đọc lại trên tay; stock Fly đúng hash. | Không kiểm tra mọi màn hình hoặc bay thử. |
| Reboot / Home | RRO giữ bật; cầu Home giữ property; Lawnchair foreground trước thao tác Home sau boot. | Trước reset, framework được pin. |
| Lawnchair | APK chính thức đã cài và mở. | Luồng nút cài mới sau reset chưa chạy trên tay. |
| FreeFCC | APK 1.5.5 cài, hash/chữ ký hợp lệ, cold launch/foreground đúng. | Chưa bấm Connect/FCC/Auto-FCC/4G. |
| Developer options | Bật cờ/kích hoạt component/mở activity và đọc lại; bản EXE trước từng chạy được trên tay. | Bản EXE hiện tại chưa kiểm tra lại phần cứng sau reset. |
| Trust USB | Key PC đã có, thời gian hết hạn quyền đặt 0. | Không chứng minh không cần Allow qua mọi boot; bridge vẫn có thể xin lại. |

Bản ghi được che số sê-ri/đường dẫn cá nhân trong historical-evidence.json. Bản đó là lịch sử, không phải live state tại thời điểm tải repo.

## Kiểm thử phần mềm

88 test app bao gồm protocol/target/path/hash/idmap, không sửa trên camera, đọc lại/rollback, worker chọn đúng tay, không tự bật lại ngay sau disable, các lỗi cài APK và cleanup, nút Tk thật, cảnh báo chấp nhận/hủy/mỗi lần bấm. Coverage đã đo 94,52% cho các module lõi/dịch vụ; USB Windows và toàn bộ GUI không nằm trong mẫu số đó.

9 kiểm thử rà bản dịch xác minh phủ định/ngữ cảnh đã biết, không đoán câu lạ, biến/số/đơn vị, dữ liệu kỹ thuật và ngoại lệ nhãn do người dùng yêu cầu. Thống kê bảng tài nguyên không phải coverage UI.

Bản giao độc lập sẽ ghi kết quả chạy lại và hash build ở release-verification.json. Kiểm tra EXE GUI startup và assets nhúng không thay thế thiết bị/flight runtime proof.

## Chưa hoàn tất

- Chưa sửa triệt để ADB offline hoặc bảo đảm hộp thoại Allow luôn hiện.
- Chưa bật thanh điều hướng ba nút trên RC 2; chưa thay config navigation hoặc SystemUI.
- Chưa chứng minh ổn định trong bay, firmware khác hoặc mọi loại máy bay.
- Chưa chạy luồng cài từ nút Lawnchair/FreeFCC trên tay sau reset.
- Không có auto-allow cho máy tính lạ hoặc app Settings đã mod; chỉ mở component Settings có sẵn.

## Những gì không đưa lên GitHub

Khóa ký Android/mật khẩu, adbkey của PC, log tài khoản, backup DJI Fly, dump framework lớn và các môi trường Python. APK SystemUI nguyên bản được giữ vì yêu cầu đủ APK trong thư mục dự án, nhưng chỉ là tệp tham chiếu; các bản DJI Fly thử nghiệm/backup ở thư mục nghiên cứu khác không thuộc repository app này.
