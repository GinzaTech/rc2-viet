# Báo cáo hoàn thành RC2 Việt 0.9.0

Ngày: **11/10/2026**. Dự án: [GinzaTech/rc2-viet](https://github.com/GinzaTech/rc2-viet), nhánh `codex/initial-release`.

Code, dữ liệu bản dịch và EXE 0.9.0 đã commit/push trong [26e0b9f](https://github.com/GinzaTech/rc2-viet/commit/26e0b9f7dc290a5e80d2c79d612fc55f03e396b3). Đã đọc lại metadata, hash bộ nhớ và nhãn sửa từ chính commit trên GitHub. Báo cáo này được bổ sung sau commit triển khai.

## 1. Yêu cầu đã xử lý

- Tiếp tục luồng tự lấy APK DJI Fly đang cài, phân tích, patch menu, ký và cài; bỏ điều kiện số phiên bản/hash nguồn cố định cho các bản dựng mới.
- Dựng bản dịch từ tài nguyên của APK đích, tận dụng các bản dịch tương thích và dịch bổ sung cục bộ.
- Lấy dữ liệu từ thư mục `C:\Users\kona\Desktop\rc2-viet-codex-initial-release` làm nguồn bổ sung.
- Sửa nhãn `Chế độ sin (tiểu thức chậm)` thành **Chế độ C (Tốc độ chậm)**.
- Truy cập trang RedFly, tải APK thực, kiểm tra checksum, giải nén và phân tích các phần bổ sung.
- Dựng EXE/Portable, cập nhật bản trong Downloads, cập nhật README/changelog và push GitHub.

Theo yêu cầu trước đó, lượt này **không kết nối ADB, không cài hoặc chạy APK trên RC 2/điện thoại và không gửi lệnh máy bay**. Các kiểm tra installer/ADB trong test là mô phỏng trên PC.

## 2. Menu thích nghi theo APK

Luồng mới đọc `AndroidManifest.xml`, Application và chuỗi lớp cha, DEX chứa điểm khởi động, ID giao diện Home/preview/HUD và vị trí DEX chưa dùng. Số phiên bản chỉ là metadata đối chiếu đúng nguồn đang cài.

Với bootstrap có thao tác đổi context, công cụ chèn sau các bước khởi động gốc đã nhận diện và giữ các lớp khác trong DEX. Với Application chuẩn, công cụ dùng provider riêng tư. Menu nhận diện vai trò màn hình qua view tree, có ưu tiên cho màn hình bay khi đồng thời gặp view Home. Application AppGuard chưa đổi context chờ hook cuối khởi động để tránh đăng ký callback quá sớm.

Mod mới mang profile và capsule phục hồi riêng tại `assets/rc2-menu/`. Capsule cho phép dựng lại đúng từng byte của nguồn từ phần dữ liệu nén không đổi. Sau phục hồi, công cụ còn dựng lại recipe và xác minh helper, manifest/DEX, các entry khác và chữ ký. Capsule không tự cấp quyền tin cậy. Template cũ chỉ phục vụ nhận diện menu 1.21.8 lịch sử.

Installer giữ kiểm tra RC331/Android11/root, serial, foreground, nguồn hiện hành và metadata. Khác chữ ký vẫn cần sao lưu/xác nhận; các cơ chế hủy, rollback và giữ backup khi phục hồi chưa chắc chắn được giữ nguyên.

| APK đầu vào thực | Application/đường khởi động | DEX helper tự chọn | Kết quả trên PC |
| --- | --- | --- | --- |
| Fly RC 1.21.8 / code3115809 | `AppGuard.QLVRK`, context-swap | `classes23.dex` | Dựng/ký/replay và phục hồi đúng SHA nguồn |
| Fly phone 1.21.12 / code3131451 | `AppGuard.RGTYT`, giữ bước `callBS` và 1.626 lớp khác | `classes2.dex` | Dựng/ký/replay và phục hồi đúng SHA nguồn |
| RedFly v5 1.21.10 / code3115981 | `DJIApplication` kế thừa `UAVApplication`, provider | `classes33.dex` | Dựng/ký/replay và phục hồi đúng SHA nguồn |

Đây là xác minh archive, mã bootstrap và chữ ký trên PC. Bản phone dùng làm đầu vào kiểm chứng cấu trúc; tab điện thoại hiện chưa có luồng cài menu. Cấu trúc mơ hồ hoặc tài nguyên chưa nhận diện được phải dừng trước cài. Chưa thể cam kết một firmware/API tương lai sẽ tương thích chỉ từ số phiên bản.

## 3. Bản dịch và dữ liệu bổ sung

Đối chiếu 11.923 dòng của catalog trong thư mục nền tảng:

| Kết quả nhập | Số lượng |
| --- | ---: |
| Cặp mới, có nguồn và hợp lệ contract | 7 |
| Cặp đã có trong bộ nhớ hiện tại, giữ bản hiện tại | 10.736 |
| Cặp lệch contract/placeholder/số hoặc đơn vị | 350 |
| Thiếu bản dịch hoặc thiếu cấu trúc nguồn đầy đủ | 830 |

Script nhập không đoán lại markup, mảng hoặc quantity của plural khi catalog cũ không lưu đủ thông tin. Bộ nhớ bổ sung có provenance/hash riêng. Không đưa các khóa phiên bản 1.21.8/1.21.10 của code trong thư mục cũ trở lại luồng hiện tại.

Đã sửa nhãn Cine trong XML, bộ nhớ RC/điện thoại, thuật ngữ và bảng sửa cách diễn đạt ưu tiên riêng. Ba nhãn đọc lại từ RRO đã biên dịch:

- `fpv_basic_flight_cinesmooth_mode_toast`: **Chế độ C (Tốc độ chậm)**.
- `fpv_setting_control_advance_flight_gear_c_description_title`: **Chế độ C (Tốc độ chậm):**.
- `fpv_setting_control_aircraft_mode_tripod_list`: **Chế độ C (Tốc độ chậm)**.

D-Cinelike vẫn được giữ là tên hồ sơ màu. Hash bộ nhớ và revision `complete-v3` được cập nhật để gói cache cũ không che mất thay đổi.

| Nguồn dịch thực | Tài nguyên cần dịch | Dùng lại/đã rà | Dịch bổ sung bằng CPU | Bỏ dở |
| --- | ---: | ---: | ---: | ---: |
| Fly RC 1.21.8 | 11.313 | 10.801 | 512 | 0 |
| Fly phone 1.21.12 | 11.315 | 10.801 | 514 | 0 |

Cả hai có `complete=true`, gói RRO chỉ chứa tài nguyên và có chữ ký hợp lệ. Các tài nguyên kỹ thuật/tham chiếu được giữ nguyên. Tính đầy đủ và contract không thay thế việc con người duyệt ngữ nghĩa mọi câu dịch máy.

## 4. RedFly tải về gì và có mã gì

Nguồn: [redfly.app/#download](https://redfly.app/#download). Hai APK RC2 tải được và khớp checksum công bố:

| Tệp | Package | Bytes |
| --- | --- | ---: |
| `RedFly-1.21.10-dev-56-build-136-RC2-red-v5-final.apk` | `dji.go.v5` | 481.976.101 |
| `RedFly-1.21.10-dev-56-build-136-RC2-red-v6-final.apk` | `dji.go.v6` | 482.078.501 |

Manifest: Fly1.21.10/code3115981; mỗi APK có 14.690 entry, 32 root DEX, ABI `armeabi-v7a`. V5 dùng package thay Fly; V6 dùng package riêng. Bản V5 xác minh được chữ ký v2/v3 của một chứng thư mod.

Đã tìm thấy mã bổ sung cho menu/điều khiển nhanh, đọc trạng thái GPS và vision, tùy chọn ATTI, bảo vệ hạ cánh, chạm hai lần ẩn HUD, hiển thị pin/nhiệt độ, video/telemetry qua LAN/Wi-Fi/hotspot/HTTP, nút tắt nguồn máy bay, tùy chọn khởi động và công cụ FlightRecord/JSON. Bằng chứng class/method được trình bày trong [báo cáo phân tích RedFly](REDFLY_ANALYSIS.md).

FCC/băng5.8GHz, LTE/HYBRID, RTH, bản đồ mở rộng và thay đổi giới hạn bay còn được website công bố. Lượt này chưa chứng minh đầy đủ chuỗi UI → SDK → ACK → readback của từng mục. Đường video qua mạng trong APK không chứng minh khả năng HDMI/DisplayPort trực tiếp của USB-C.

Không có APK Fly RC1.21.10 chính thức cùng version/code/ABI trong thư mục hiện tại để diff tương ứng. Do đó danh sách phân tích không được coi là danh sách đầy đủ mọi byte đã mod so với stock. Code/Smali của RedFly không được nhập vào payload RC2 Việt.

## 5. Kiểm chứng cuối

- Toàn bộ source suite: **1.822 ca đạt**, coverage Python **88,27%**.
- Java/UI/payload sau lần rà cuối: **60 ca đạt**, gồm phân loại màn hình bay khi có view Home và D8 so với payload nhúng.
- Đóng gói: **15 ca đạt**, gồm hash EXE/engine, danh mục ZIP, tài liệu, loại private file và giữ output cũ khi staging lỗi.
- Dependency audit của công cụ PC và engine: **0 lỗ hổng đã biết** trong các dependency được audit.
- GUI smoke bằng EXE cuối: đạt, worker kết nối thiết bị được tắt khi smoke.
- EXE cuối tự dựng menu bằng Java nhúng khi PATH chỉ có System32, không `JAVA_HOME`/`CLASSPATH`.
- EXE cuối dịch APK mẫu **99.0.1** với bộ nhớ dịch tắt: 4 mục dịch máy, 0 mục dùng lại, 0 bỏ dở.
- Ba APK thực ký/replay được và capsule phục hồi đúng SHA nguồn, dùng payload cuối `83362ab740c7522265d4fee876b2a75cc7f6fd0b7efe096ba92da21a5fbf5ba0`.
- Đã kiểm tra staged Git blob của EXE và từng memory khớp hash. Không đưa private signing, backup, APK/Smali phân tích hoặc log vào commit.

Chi tiết máy đọc được: [adaptive-menu-verification.json](adaptive-menu-verification.json).

## 6. Tệp bàn giao và cách dùng

EXE cuối: **94.321.373 byte**, SHA-256:

```text
5f394b2e5dbaaa54b0efb6306f921490e7b8566847e041f509629cb162eb819f
```

Các bản EXE đã được đối chiếu hash giống nhau:

- `C:\Users\kona\Desktop\Project\rc2-viet\dist\RC2-TiengViet.exe`.
- `C:\Users\kona\Downloads\RC2-TiengViet.exe`.
- `C:\Users\kona\Downloads\DJI_RC2_VIETNAMESE_APP\dist\RC2-TiengViet.exe`.

Portable ZIP có engine và hướng dẫn tại `dist/RC2-TiengViet-Portable.zip` và hai thư mục Downloads tương ứng. Giữ `translation-engine` cạnh EXE để dùng ngoại tuyến. Bản EXE độc lập có thể tải engine công khai đã pin về PC; nội dung cần dịch được xử lý trên PC.

APK RedFly tải về, dữ liệu giải nén và Smali nằm tại `C:\Users\kona\Desktop\Project\rc2-viet\phone-work\redfly\`. APK/RRO thử dựng giữ trong các thư mục `phone-work/adaptive-final-*`, `phone-work/wording-*` và thư mục cache cục bộ của app; không phải APK đã cài lên tay.

Sử dụng phần mềm:

1. Mở bản EXE mới trong Downloads hoặc giải nén Portable.
2. Chọn đúng tab **Tay DJI RC 2** hoặc **Điện thoại Android**, nối USB và chọn serial khi có nhiều thiết bị.
3. Với RC2, giữ tay ở trang chủ/Launcher khi không bay. Bấm **Cài / cập nhật menu** để phần mềm tự lấy APK, phân tích, patch, ký và kiểm chứng.
4. Nếu khác signer, đọc thông báo sao lưu/gỡ-cài và xác nhận theo nhu cầu. Giữ cáp/nguồn cho đến khi hoàn tất hoặc có kết quả khôi phục.
5. Bấm **Bật / cập nhật tiếng Việt** để dựng gói từ tài nguyên hiện tại. Gói thiếu hoặc lỗi contract phải dừng trước cài.

[README](../README.md), [hướng dẫn menu](HUD_APK.md), [cơ chế Việt hóa](VIETNAMESE.md).

## 7. Phần chưa được xác nhận

- Cài/mở/boot của APK menu cuối trên RC2 và điện thoại.
- LED/FCC, hiệu lực/duy trì radio, xuất HDMI và các chức năng vật lý của menu cuối trên Air3S.
- UI thực tế khi ghép menu với RedFly và mọi firmware/API tương lai.
- Ngữ nghĩa của toàn bộ câu dịch máy và độ phủ các chuỗi hardcode trong mã thay vì tài nguyên.

Bằng chứng của bản menu cũ được giữ trong tài liệu lịch sử. Không dùng chúng để đánh dấu các mục trên đã hoàn thành cho bản 0.9.0.
