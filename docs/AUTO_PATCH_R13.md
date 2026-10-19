# RC2 Auto Patch r13.1

R13.1 thay nhãn nhập `Thư điện tử` bằng `Gmail`, hai lời nhắc đăng nhập thành `Số điện thoại hoặc Gmail`, đồng thời sửa các câu ở màn khởi tạo/tải tài nguyên cho tự nhiên hơn. Các chức năng menu và hai profile phiên bản giữ nguyên từ r13.

`RC2-TuDong-Patch-r13.1.exe` tự lấy APK DJI Fly từ tay RC2, nhận diện đúng nguồn rồi mới patch. Hai đầu vào được phép là:

- Fly RC 1.21.8, code 3115809, SHA-256 `cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e`.
- Fly RC 1.21.10, code 3115981, SHA-256 `f6c11267d465c303e2aecb737fe4f6b41b54da083368cac497404f4c9a464f98`.

Menu nhanh gồm **Đèn càng**, **Chạm 2 lần để ẩn / hiện HUD**, **Xuất hình** và **Profile sóng** với FCC cùng EC/gốc. Mục EC/gốc khôi phục đúng baseline radio đã đọc và giữ theo định danh máy bay; nó không ghi một giá trị EC suy đoán. LED và radio chỉ cho thao tác khi máy bay kết nối, ở mặt đất và động cơ dừng; kết quả chỉ được báo sau ACK/readback.

Trong **Tiện ích nâng cao** có đúng hai trang **Nâng cao** và **Hiệu chỉnh gimbal**. Cả hai trang nằm trong vùng cuộn có giới hạn, dùng khoảng cách và cỡ chữ compact để nội dung dài vẫn truy cập được trên màn RC2.

## Kiểm chứng build

- Recipe 1.21.8: `be517b4e3de6ac99bcc6dee29bbc53616c54879520414370f3b0a1041d0f886d`.
- Recipe 1.21.10: `e8342bd9e479318bfff88fa19fcc8afedda3481e718526c9d8cce4ab7a9d6acb`.
- Mỗi recipe giữ nguyên 175 lớp bridge không thuộc giao diện và giữ nguyên DEX tính năng.
- Dựng, ký, kiểm tra APK và phục hồi byte-exact nguồn đều đạt với cả hai APK stock.
- APK được đọc trực tiếp từ tay serial `6UZTP72001YYBE` là 1.21.8/code 3115809, 468.097.711 byte, đúng SHA-256 stock; bước đọc không sửa thiết bị.
- APK r13.1 dựng từ chính tệp đọc trên tay có SHA-256 `264ec4f055e3156b5cb4e9838b0ed3fea715e908c950e661d8aa5e0169c09fed`.
- Regression: 2.489 đạt, 3 bỏ qua theo điều kiện. EXE self-test và smoke GUI đạt; metadata file/product version là 13.0.0.0.

Windows có thể lỗi giải nén toolchain khi người dùng ép thư mục làm việc vào đường dẫn quá dài. EXE dùng `%LOCALAPPDATA%\RC2AutoPatch`, là đường dẫn ngắn cố định để tránh lỗi này.

Kiểm thử host/JVM xác nhận luồng và readback nhưng không thay cho quan sát vật lý: đèn thật, tín hiệu màn ngoài và thay đổi phổ/công suất RF chỉ được coi là đạt sau khi thử trên RC2 với Air 3S ở trạng thái an toàn.
