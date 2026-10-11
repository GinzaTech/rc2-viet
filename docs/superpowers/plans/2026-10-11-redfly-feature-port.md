# Tích hợp chức năng RedFly vào APK Fly gốc của người dùng

## Mục tiêu và phạm vi

Người dùng yêu cầu đưa toàn bộ nhóm tính năng đã trao đổi của RedFly vào APK gốc, giữ nền Fly của họ và các sửa tiếng Việt. Đầu vào có sẵn là Fly RC1.21.8/code3115809, SHA256 `cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e`. RedFly tham chiếu là RC1.21.10/dev56/build136. Không thay nền bằng RedFly rồi đổi tên thành bản gốc. Không chạy/cài APK hoặc gửi lệnh thiết bị ở lượt này theo ràng buộc trước.

## Cách thực hiện

Tách tính năng theo contract. Trước hết xác định API, tài nguyên, điểm hook và dependency có thật trong đúng nguồn. Thực hiện phần độc lập bằng payload nguồn RC2 Việt; chỉ thay entry gốc khi xác định và replay được thay đổi. Không đưa nút chỉ lưu lựa chọn để giả là đã điều khiển máy bay. Tính năng chỉ được báo thành công sau ACK/readback hoặc dữ liệu đã quan sát; chưa có bằng chứng runtime phải ghi riêng.

Không tự bỏ RTH pin tới hạn, bảo vệ kết nối/động cơ hoặc cơ chế rollback. Chức năng cấu hình liên quan máy bay dùng dữ liệu trạng thái mới nhất và từ chối trạng thái chưa xác định. Không thêm các thay đổi Remote ID/DroneID ngoài danh sách người dùng vừa yêu cầu trong cuộc trao đổi.

## Các phần việc và bằng chứng

- [x] Lập inventory class/method/field/dependency giữa stock1.21.8 và RedFly1.21.10; chưa tìm thấy stock1.21.10 trong các nguồn cục bộ đã kiểm tra.
- [x] Đối chiếu các nhóm tiện ích; tách riêng phần login/activation chưa chuyển và phần độ cao chỉ thay giao diện.
- [x] Nhận diện38 class host/61 hàng tham chiếu; ghép44 method trong31 class của11 DEX; kiểm tra650 class bổ sung,0 unresolved.
- [x] Bổ sung test contract/guard/anchor, mapping resource và kế thừa; giữ cleanup các view khi pause và một bộ chạm hai lần. Snapshot bộ test đầy đủ1854 ca đạt; sửa cuối có kiểm tra mục tiêu.
- [x] Dựng/ký/capsule từ stock chính xác, phục hồi lại đúng SHA256 nguồn; báo cáo ở `docs/REDFLY_FEATURE_PATCH.md`.
- [x] Bàn giao APK/báo cáo cục bộ theo phạm vi PC người dùng xác nhận. Runtime/ACK/readback trên RC2 và Air3S vẫn NOT VERIFIED.

## Nhật ký quyết định

- Nguồn stock1.21.8 dùng AppGuard và 22 root DEX; RedFly1.21.10 dùng 32 root DEX/Application chuẩn. Mã SDK của các bản có thể khác tên và chữ ký, nên không copy hàng loạt DEX.
- Các bản sao APK lớn trong cache/sao lưu đã kiểm tra đều là1.21.8; chưa tìm thấy stock RC1.21.10 trong các thư mục đã kiểm tra.
- Stock có class `com.uav.livestream.core.video.LiveStreamVideoEncoder` và các key GPS/landing trong bảng chuỗi, là cơ sở để đối chiếu contract tiếp theo; sự hiện diện này chưa chứng minh interface của RedFly khớp.
- Người dùng chốt «chỉ patch trước, sáng mai kiểm tra»: không chạy ADB/cài/gửi lệnh; không còn cần hỏi lại quyền làm công việc PC.
- Loại nhánh GPS gửi UDP lặp sau SDK, không thêm nút LED riêng trên HUD. Có239 vị trí chữ UI được Việt hóa bằng từ điển đã rà; các khóa/protocol/tên file giữ nguyên.
- Giữ AppGuard và logic tài khoản stock. Không chuyển đường UID tổng hợp, `ridkill` hoặc native/SDK khác phiên bản. Bản thử không được coi là tích hợp toàn bộ RedFly đã kiểm chứng; chưa đưa vào EXE/payload phát hành.
