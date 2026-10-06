# RC2 Việt v0.1.0

Ứng dụng Windows hỗ trợ DJI RC 2 qua USB: Việt hóa DJI Fly 1.21.8 bằng RRO riêng, cài Lawnchair 15 Beta 3 và FreeFCC 1.5.5, đặt Lawnchair làm Home theo firmware đã kiểm chứng, mở Developer options với cảnh báo trước thao tác.

## Tệp tải

- RC2-TiengViet.exe: EXE onefile có Python runtime, ADB/DLL và bốn APK dùng được.
- RC2-TiengViet-Portable.zip: EXE, README, hướng dẫn chi tiết, ghi công và kiểm chứng.
- RC2-TiengViet-Source.zip: mã nguồn độc lập, nguồn XML/quy tắc dịch và đủ 7 APK hiện có trong thư mục dự án app.
- vietnamese-resources.apk, home-bridge.apk, lawnchair.apk, freefcc.apk: các gói được app sử dụng.
- unsigned.apk, aligned.apk, dpad_systemui.apk: tệp build trung gian/tham chiếu, không dùng như APK để cài hệ thống.
- SHA256SUMS.txt: hash để đối chiếu tất cả tệp bàn giao.

## Kiểm chứng

88 kiểm thử app và 9 kiểm thử quy tắc dịch đạt; coverage phần lõi/dịch vụ 94,52%. Đã kiểm tra EXE khởi động, ADB nhúng khi không có SDK trong PATH, asset hash và bố cục 10 nút ở kích thước tối thiểu. Dependency audit của môi trường build không còn lỗ hổng đã biết trong các package được audit.

## Điều kiện và giới hạn

Yêu cầu Windows x64/WinUSB, RC2 rc331 Android 11 có USB debugging và root sẵn có. Bản dịch và Home được pin đúng phiên bản/hash, không phải hỗ trợ mọi firmware.

Cài FreeFCC không kích hoạt FCC. Trước reset đã kiểm tra cài/mở các app, RRO và Home qua reboot; luồng nút mới sau reset chưa xác minh trên tay. ADB offline/không hiện Allow chưa được xử lý vĩnh viễn. Thanh điều hướng ba nút chưa được bật. Chưa thử bay hoặc chứng minh ổn định mọi tình huống.

Hướng dẫn đầy đủ và các nguồn FreeFCC/Lawnchair ở README.md cùng docs/USAGE.md, docs/VIETNAMESE.md, docs/BUILD.md và docs/VERIFICATION.md.
