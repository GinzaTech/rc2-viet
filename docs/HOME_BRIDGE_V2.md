# Cầu Home 2.0: bỏ màn chờ trên đường vào Lawnchair

Màn người dùng thấy thuộc `local.rc2.home`, không phải màn Lawnchair. Trên bản 1.0, onCreate dựng giao diện chờ trước khi kiểm tra UserManager.isUserUnlocked; onResume sau đó mới chuyển sang launcher, không finish activity cầu. Vì HOME vẫn trỏ vào cầu hỗ trợ Direct Boot, màn này có thể xuất hiện lại khi bật máy hoặc bấm nút Home.

Bản 2.0 thử forward ngay, theme trong suốt với windowDisablePreview, không tạo content view trong trường hợp sẵn sàng. Mở Lawnchair thành công thì finish và bỏ animation. onNewIntent xử lý lại lần bấm Home. Khi dữ liệu chưa mở khóa hoặc ứng dụng chưa mở được, các lần thử được giới hạn và màn hỗ trợ chỉ được tạo sau độ trễ; có nút thử lại và mở DJI Fly.

Các cờ Direct Boot/device-protected storage, component Home, quyền và định tuyến firmware được giữ. Không đặt cầu Home thành app nền thường trực, không xin quyền mới.

APK versionCode 2 / versionName 2.0, SHA256 `c1d5685aa7e15b5ac57fbf4957afa9deb736fafc288c190607b953c9e0a8594e`. App Windows local nhận hash cũ v1 và nâng bằng install -r, giữ package/data. Hash khác không được ghi đè; hash installed được đọc lại trước khi đổi Home.

Kiểm chứng: chính sách Java qua 6 trường hợp (sẵn sàng, Direct Boot rồi unlock, khóa kéo dài, thiếu launcher và retry, pause/resume, timeout). Bộ app đạt 91 tests, core/service coverage 94,44%; không coi đó là coverage mọi callback Android.

Trên tay đã cài APK đúng hash/code, Home property không đổi, ba lần bấm Home từ Settings đều về Lawnchair và không còn HomeActivity của cầu nằm trong activity history. Sau reboot đã đọc boot_completed=1, RUNNING_UNLOCKED, đúng APK v2 và Lawnchair foreground trước mọi lệnh mở ứng dụng của lượt xác minh; kiểm tra Home sau reboot cũng đạt. Bản mới chưa có trong release public v0.1.0.
