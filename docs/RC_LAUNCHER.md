# RC Launcher và Home mới

Source: https://github.com/GinzaTech/rc-launcher . APK nhúng là RC Launcher1.0-preview6/code6, package dev.rclauncher.rc2.debug, Android Debug signed, min30/target32, ABI-neutral.

App PC dùng Cài/Mở/Đặt RC Launcher làm Home. Lawnchair không còn là lựa chọn chính trên giao diện; gói upstream giữ cho fallback/khôi phục. Cầu Home3.0 đã upgrade cùng signer, ưu tiên debug RC Launcher, rồi release, rồi mới Lawnchair nếu ứng dụng mới không mở được.

Đã quan sát native Home về RC Launcher và sau reboot tự foregroundRC Launcher trên RC331/V14.00.00.04 test-keys. Chỉ ghi nhận trường hợp firmware đã đo, không bảo đảm mọi RC2. Xem home-rc-switch-verification.json.

App icon được lấy từ LauncherActivityInfo/ứng dụng đã cài; không có app thì không dựng icon giả. CPU đọc cpuss sysfs nếu app đọc được; pin theo Android driver. Kernel từng báoCPU87–95C trong khi driverpin30C. Chưa xác minh hiệu chuẩn hoặc nhiệt vỏ.

App runtime không root/shell/input injection. PC Home installer dùng đường ADB/root sẵn có và firmware services.jar hash đã pin; không flash/sửa framework. Điều hướng Accessibility optional/off; user hiện dùng nativeAndroid3bar. Không tự cấp service hoặc claim global navigation PASS.

Khôi phục: mở Lawnchair từ app icon khi cần; nếu gỡ RC thì Homebridge còn fallbackLawnchair. Không gỡ/disable DJI hoặc pmclear/xóa flight logs. APK releaseunsigned của source launcher phải ký trước khi cài; EXE nhúng debugAPK đã ký.
