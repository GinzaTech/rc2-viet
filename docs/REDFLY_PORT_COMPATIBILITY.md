# Đối chiếu trước khi tích hợp RedFly vào APK gốc

Ngày 11/10/2026. **Đã dựng/ký APK thử nghiệm trên nền stock1.21.8; chưa kiểm chứng thiết bị và chưa chuyển phần bỏ hạn chế đăng nhập.** [Báo cáo patch và tệp bàn giao](REDFLY_FEATURE_PATCH.md).

## Đầu vào hiện có

- Bản Fly gốc trên PC: RC1.21.8/code3115809, AppGuard, 22 root DEX, SHA256 `cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e`.
- Gói tham chiếu: RedFly RC1.21.10/code3115981/dev56/build136, 32 root DEX. Phân tích chỉ đọc, không chạy code trong APK.
- Các APK lớn đã kiểm tra trong cache/sao lưu và thư mục nền tảng đều là1.21.8; chưa tìm thấy stock RC1.21.10 trong các nguồn đã kiểm tra. APK hiện đang cài trên RC2 chưa được đọc lại ở lượt này.

## Kết quả có bằng chứng

Stock có 176.045 class definitions; RedFly có 553 tên class chưa có trong stock này. Số này gồm cả thay đổi phiên bản và mô-đun mod, nên không được coi toàn bộ là tính năng mới.

Các namespace mod tìm thấy gồm `flyctl`, `flysettings`, `gimcal`, `gpskill`, `homequick`, `landing`, `lanstream`, `lte4g`, `mapsrc`, `modi18n`, `modinfo`, `paramedit`, `probe42`, `redfly`, `redprefs`, `rthguard`, `rxspeed`, `screenrecguard`, `cleanview`, `fpvextras`, `frtool` và `app/openfcc/battery`. Namespace `ridkill` không nằm trong danh sách tính năng người dùng vừa trao đổi, nên không tự đưa vào phạm vi.

| DEX bổ sung | Class | Tham chiếu SDK chưa tìm thấy trực tiếp trong definitions của stock |
| --- | ---: | --- |
| classes30.dex | 57 | 0 method, 0 field, 0 type |
| classes31.dex | 60 | 3 method; 0 field, 0 type |
| classes32.dex | 17 | 0 method, 0 field, 0 type |

Ba tham chiếu còn lại là `FlyBinderObservable.getOrNull`, `FlySubscriptionObservable.getOrNull` và `FlySubscriptionObservable.cancel`; cần đối chiếu thêm lớp cha/interface. Không coi chúng là đã giải quyết chỉ vì class tồn tại.

Stock có đúng các class/prototype encoder mà mô-đun LAN tham chiếu: `LiveStreamVideoEncoder`, `LiveStreamDataListener`, `LiveStreamBitrate`, `LiveStreamResolution`, constructor và các method H/J/K/h/x. Các bảng key stock có `FCGPSEnabled`, `LandingProtectionEnabled`, `SmartBatteryRTHEnabled`, thông tin điện áp/cell/nhiệt độ và nhiều key chế độ bay. Sự hiện diện/chữ ký không chứng minh quyền ghi hoặc hiệu lực trên firmware máy bay.

Trong tập Smali chọn lọc đã đọc, tìm thấy 8 method host chứa điểm gọi mô-đun RedFly. Bảy method có definition tương ứng trong stock và không mang cờ native; một method `DJIDeviceActivity.onNewIntent` chưa tìm thấy definition trực tiếp. Các điểm đã thấy liên quan UI hạ cánh/RTH, launch/trang chủ và intent. Đây không phải danh sách đầy đủ mọi hook của RedFly.

## Điều kiện để ghép đúng

1. Chốt chính APK nguồn người dùng muốn giữ, thay vì tự lấy RedFly làm nền và đổi tên thành bản gốc.
2. Phân biệt thêm mô-đun với các thay đổi trong method gốc, tài nguyên, manifest và cấu hình. Một menu chứa tùy chọn không đủ chứng minh tính năng đã được nối vào đúng luồng.
3. Kiểm tra dependency kế thừa, quyền ghi của SDK, enum/lệnh và callback/readback theo source/firmware hiện hành.
4. Giữ các sửa tiếng Việt, guard trạng thái bay/động cơ và rollback; không tự loại cơ chế hạ cánh pin tới hạn.
5. Sau khi có APK nguồn và quyền kiểm tra thiết bị, dựng/ký/replay rồi kiểm tra từng mục trên tay ở trạng thái mặt đất. Trước đó chỉ được ghi nhận mức build/static.

## Phạm vi kiểm tra hiện tại

Người dùng đã xác nhận chỉ patch trước trên PC, sáng mai tự kiểm tra. Không có câu hỏi xin quyền còn chờ cho công việc PC. Chưa chạy ADB, chưa cài APK và chưa gửi lệnh máy bay trong lượt này.

Scanner đầy đủ tìm 38 class host/61 hàng tham chiếu tới tiện ích, bổ sung các điểm vùng radio, bản đồ, log và nút tùy chỉnh mà tập dump chọn lọc trước bỏ sót. Bản cuối ghép44 method trong31 class của11 DEX. Dependency của650 class helper/tiện ích đã được đối chiếu trực tiếp và theo kế thừa:0 unresolved. Năm resource ID trực tiếp đã được đối chiếu bằng AAPT2 với cả hai APK và đều khớp tên/type/ID. Gói recovery đã tái tạo lại chính xác stock.

Method UI độ cao trả `IntMinMax` từ SDK thay vì chặn120 m đã được đối chiếu ở cả hai đầu vào và chuyển riêng. Không suy ra mở giới hạn firmware từ thay đổi này. Phần ghi UID tổng hợp trong activation, `ridkill` và thay thế native/SDK khác phiên bản không được chuyển.

Inventory và các kết quả phân tích chi tiết nằm tại `phone-work/redfly-port/`, được ignore khỏi Git; không đưa Smali hoặc dữ liệu người dùng vào repo.
