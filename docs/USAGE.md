# Hướng dẫn sử dụng RC2 Việt

## 1. Chuẩn bị

Tải EXE hoặc portable ZIP từ Releases. Portable ZIP cần giải nén trước khi chạy. Không cần cài Python/ADB riêng, nhưng Windows phải nhận giao diện ADB qua WinUSB và RC 2 phải đã bật USB debugging, cung cấp shell root như tay đã thử.

App không mở USB debugging khi chưa có ADB, không tự root tay và không thay firmware. Khi mới đặt lại tay, hoàn tất thiết lập ban đầu trước, rồi kiểm tra lại trạng thái USB debugging trên chính RC 2. Việc Windows thấy thiết bị truyền tệp không chứng minh ADB có thể dùng.

Thực hiện cài/đổi Home/đổi bản dịch khi máy bay đã hạ cánh hoặc tắt nguồn; giữ tay ở trang chủ DJI Fly hoặc ứng dụng ngoài màn hình camera.

## 2. Kết nối

1. Bật tay, dùng cáp có truyền dữ liệu, cắm vào PC.
2. Mở `RC2-TiengViet.exe`; chọn sê-ri nếu nhiều tay được nhận.
3. Nếu hiện Allow USB debugging trên tay, bấm Allow. Có thể chọn Always allow from this computer.
4. Chờ thông báo kết nối ADB, sau đó thông báo kiểm tra/bật tiếng Việt hoặc lỗi tương thích.

Không bấm Kết nối lại liên tục trong lúc đang chờ Allow. Nếu cần gửi lại sau khi timeout, dùng nút đó một lần, giữ tay bật/màn hình sáng và xem hộp thoại trên tay.

App tự kiểm tra tiếng Việt khi kết nối; có thể bỏ chọn **Tự kiểm tra và bật tiếng Việt khi nhận RC 2**. Nếu kiểm tra bản dịch lỗi do phiên bản DJI Fly, các chức năng độc lập như cài APK vẫn có điều kiện riêng; đọc thông báo trước khi thao tác tiếp.

## 3. Bật hoặc cập nhật tiếng Việt

Bấm **Bật / cập nhật tiếng Việt**. App kiểm tra model, SDK, root, DJI Fly 1.21.8/code/hash. Phiên bản khác dừng trước khi cài gói.

Nếu gói hiện tại đã đúng hash, đang bật và đọc lại mẫu đúng, kết quả là kiểm tra chỉ đọc. Nếu thiếu/gói cũ được nhận diện, app cài RRO, xử lý idmap, bật và đọc lại. Khi có thay đổi nhưng một màn hình DJI Fly đang giữ chuỗi cũ trong bộ nhớ, đóng/mở lại DJI Fly lúc không bay để màn hình đọc tài nguyên mới.

App không tự gỡ hoặc ký lại DJI Fly. Không chạy bản DJI Fly thử nghiệm ký lại để thay cho APK gốc.

## 4. Tắt bản dịch

Về trang chủ hoặc Lawnchair, bấm **Tắt bản dịch**. App tắt overlay và đọc lại trạng thái. Sau đó mở lại DJI Fly để giao diện đọc tài nguyên gốc.

Không tự bật lại ngay trong cùng phiên sau một lần tắt thủ công: worker đánh dấu thao tác đã xử lý. Một phiên kết nối mới vẫn có tùy chọn auto đang bật; bỏ chọn auto nếu muốn giữ bản dịch tắt qua lần kết nối mới.

## 5. Cài và mở Lawnchair

1. Kết nối ADB, về trang chủ/Settings khi không bay.
2. Bấm **Cài Lawnchair**, chờ cài và kiểm tra APK/component thành công.
3. Bấm **Mở Lawnchair**. Trên launcher, vuốt từ dưới lên để mở danh sách ứng dụng.

Đúng APK đã có: chỉ kiểm tra, không cài lại. APK khác: app dừng để tránh ghi đè. Không tự gỡ một bản khác có dữ liệu của người dùng.

## 6. Bật máy vào Lawnchair

Sau khi cài Lawnchair, bấm **Đặt Lawnchair làm màn hình chính**. Chức năng kiểm tra đúng services.jar/nhánh firmware, cài cầu `local.rc2.home`, chọn Home và đọc lại định tuyến. Nếu firmware/hash khác, không thay đổi Home.

Cầu khởi động chạy lúc Android chưa mở khóa dữ liệu, đợi dữ liệu người dùng sẵn sàng rồi mở Lawnchair. Nếu chưa mở được, có các nút thử mở Lawnchair hoặc DJI Fly.

Trước reset, đã quan sát Lawnchair ở foreground sau reboot trước khi gửi bất kỳ lệnh mở Home nào. Không suy rộng bằng chứng đó sang firmware khác hoặc sau reset chưa kiểm tra.

Lệnh phục hồi thuộc tính Home ban đầu, dành cho người đã có shell đúng RC 2:

```sh
setprop persist.dji.fw.home ''
```

Đây là lệnh **bên trong shell Android**, không phải lệnh PowerShell. Giữ cờ ép Home của DJI như bản gốc; không đổi tùy tiện `persist.dji.sysboot.set_fly_home`. Kiểm tra Home gốc hoạt động trước khi cân nhắc gỡ cầu Home.

## 7. Cài FreeFCC

1. Kết nối ADB, về trang chủ/Settings khi không bay.
2. Bấm **Cài FreeFCC** và đợi thông báo đã cài/kiểm tra.
3. Mở Lawnchair → vuốt lên danh sách ứng dụng → FreeFCC.

EXE dùng APK 1.5.5 có SHA256 khớp release upstream. Nút chỉ cài ứng dụng và kiểm tra component; không mở FreeFCC hoặc tác động nút Connect/FCC/4G/Auto-FCC. Trạng thái “đã cài” không có nghĩa đã bật FCC.

Nếu app báo APK trên tay khác bản đóng gói, không tự gỡ app để thử. Xem phiên bản/chữ ký theo [release upstream](https://github.com/doesthings/FreeFCC/releases/tag/v1.5.5) và quyết định việc giữ dữ liệu riêng; RC2 Việt không xử lý nâng cấp mọi bản FreeFCC.

## 8. Mở Developer options

Bấm **Bật chế độ nhà phát triển**. Cảnh báo yêu cầu giữ USB debugging/Developer options bật; mặc định Hủy. OK mới gửi thao tác, Hủy không gửi lệnh.

App dùng activity `com.android.settings.Settings$DevelopmentSettingsDashboardActivity` sẵn có, không sửa APK Settings. Developer options và USB debugging là hai trạng thái khác nhau. Nút mở Developer options không tự bootstrap ADB khi USB debugging đang tắt hoặc USB chỉ xuất MTP.

Cảnh báo về reset dùng “có thể phải” vì chưa chứng minh mọi lần tắt đều buộc reset. Khôi phục cài đặt gốc xóa dữ liệu/ứng dụng người dùng trong bộ nhớ trong. App không tự thực hiện reset.

## 9. Xử lý lỗi kết nối

| Biểu hiện | Điều đã biết / bước tiếp theo |
| --- | --- |
| Không có sê-ri trong app | Kiểm tra tay bật, cáp dữ liệu và giao diện USB. Cổng chỉ truyền tệp MTP không đáp ứng discovery ADB. |
| Windows gọi thiết bị là Google Nexus ADB Interface | Tên driver có thể gây hiểu nhầm: lần đã đo có `18D1:4EE1` nhưng chỉ một interface MTP `06/01/01`, không có ADB. |
| Offline | USB nhìn thấy nhưng phiên ADB chưa hoàn tất. Kết nối lại thử một phiên; không có công tắc “vô hiệu hóa offline”. |
| Không hiện Allow | Giữ tay hoàn tất setup, bật/màn hình sáng; rút cáp khoảng 5 giây rồi cắm lại. Không tắt USB debugging để thử nếu tay đã có hiện tượng không bật lại được. |
| Công tắc USB debugging tự tắt | Ghi rõ có hộp thoại xác nhận bật debugging không và đã xác nhận chưa. Chưa có một nguyên nhân được chứng minh cho mọi tay; PC không thể dùng shell nếu ADB chưa tồn tại. |
| Một phiên công cụ khác đang giữ RC 2 | Đóng phiên RC2 Việt/bridge khác rồi thử; mutex ngăn hai phiên của công cụ dùng cùng giao diện USB. |
| Server ADB không phản hồi / giao thức khác | App dừng để tránh thay một ADB server đang phục vụ thiết bị khác. Đóng đúng phiên xung đột thay vì kill mọi adb. |
| Tay không cung cấp root / SDK khác | Chưa nằm trong phạm vi hỗ trợ; công cụ dừng, không tự root/flash. |
| DJI Fly khác phiên bản/hash | Không áp dụng gói dịch. Cần bảng tài nguyên và kiểm chứng riêng cho phiên bản đó. |
| Đang ở màn hình camera | Về trang chủ hoặc Settings/Lawnchair khi không bay rồi thử lại thao tác cài/đổi. |
| APK khác hoặc hash không khớp | Dừng; không đổi pin hoặc xóa app chỉ để bỏ kiểm tra. |

Trong lần kiểm tra cuối, đã gửi CNXN/AUTH nhưng không nhận phản hồi; Windows từ chối restart giao diện USB do thiếu quyền. Các bước đó chưa bật thanh điều hướng hoặc sửa trạng thái trên tay.

## 10. Báo cáo và CLI

Nút **Lưu báo cáo chẩn đoán** lưu tối đa 200 dòng tiến trình trong phiên GUI. Không gửi báo cáo lên mạng tự động. Trước khi chia sẻ, kiểm tra số sê-ri/đường dẫn cá nhân.

```powershell
.\dist\RC2-TiengViet.exe --scan --report "$env:TEMP\rc2-scan.json"
```

`--scan` kiểm tra tài nguyên nhúng và quét USB, không ghép nối hay cài. `--gui-smoke` dựng GUI rồi thoát, không mở worker. `--verify-once` và `--enable-dev-mode` có thể thay đổi tay theo chức năng tương ứng; chỉ chạy khi đã hiểu phạm vi. Báo cáo JSON của CLI cần thư mục đích đã tồn tại.
