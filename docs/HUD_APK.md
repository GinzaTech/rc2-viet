# Menu Basic, HUD, xuất hình và radio — 0.10.1

Bản public **Basic 0.10.1** giữ menu LED/HUD/xuất hình/radio và luồng Việt hóa riêng. Menu và ngôn ngữ phân tích APK đầu vào; số phiên bản Fly không phải danh sách cho phép. Bản thử Advanced ở sibling `rc2-viet-advanced-local` là cục bộ và không được xuất bản. Source/payload/khóa của bản riêng không thuộc EXE public.

**Trạng thái xác minh — 13/10/2026:** EXE public 0.10.1 đã build và thử dựng/ký menu, Việt hóa từ APK gốc RC **1.21.8 và 1.21.10**. Basic 1.21.10 đã cài cùng chữ ký/giữ dữ liệu trên RC 2; menu không có Tiện ích SDK. Gói Việt hóa do chính EXE dựng đã được bật và đọc lại đúng tài nguyên trên tay. Công suất RF, xuất hình vật lý, thử bay và độ ổn định dài hạn chưa được xác minh.

Nút cài menu dành cho model DJI RC 2 / device rc331 / Android 11 / API 30 có quyền shell root sẵn có. EXE nhúng Python, ADB, Java, APKtool, apksigner và zipalign; Windows cần driver USB phù hợp và tay phải cho phép USB debugging. Discovery nhận cả DJI `2CA3:1021` và Android chỉ ADB `18D1:4EE7`; VID/PID không thay guard model/device/SDK/root/serial/foreground/APK. Tab điện thoại hiện dành cho Việt hóa, chưa có luồng cài menu điện thoại.

## Tạo và cài

Nút chính **Cài / cập nhật menu** tự lấy APK `dji.go.v5` đang cài trên RC 2 qua ADB. App đối chiếu hash/metadata/serial, tìm Application và các lớp cha trong DEX, kiểm tra điểm khởi động, ID Home/preview/HUD và vị trí DEX còn trống. Cấu trúc mơ hồ, helper lạ hoặc tài nguyên chưa nhận diện được bị dừng trước cài với lỗi tương thích.

Mod mới mang `assets/rc2-menu/profile.json` và `assets/rc2-menu/recovery.zip`. Capsule lưu header/đuôi ZIP và các payload gốc đã sửa; phần còn lại được lấy từ các bytes nén không đổi của APK. Phục hồi phải khớp SHA-256 của đúng đầu vào. Capsule tự nó không cấp quyền tin cậy: app tiếp tục dựng lại toàn bộ recipe, đối chiếu helper/entry/signature. Template 1.592.400 byte cũ chỉ dùng nhận diện các bản menu 1.21.8 lịch sử. PC mới có khóa ký khác vẫn phải xác nhận sao lưu/gỡ-cài.

Trong tab RC, **Cài / cập nhật menu** là thao tác menu; **Bật / cập nhật tiếng Việt** là thao tác riêng dựng RRO từ APK hiện hành. Public chỉ có Basic, không có bộ chọn bản nâng cấp hoặc thao tác APK thủ công.

1. Nối RC 2 bằng USB, bấm Allow USB debugging nếu được hỏi. Giữ tay ở trang chủ/Launcher khi máy bay đã hạ cánh hoặc tắt nguồn.
2. Chọn **Tay DJI RC 2 → Cài / cập nhật menu**. App tự lấy APK, phục hồi nguồn nếu cần, patch, căn chỉnh, ký, kiểm chứng rồi cài lại. Khi ADB thường đã sẵn sàng, app dùng lại đúng serial, không restart server hoặc gửi yêu cầu ghép mới.
3. Cùng chữ ký, app cập nhật giữ dữ liệu. Khác chữ ký, app kiểm tra sao lưu rồi yêu cầu xác nhận gỡ/cài; bước này có thể mất đăng nhập và khóa Keystore.
4. Giữ cáp/nguồn đến khi có kết quả. Khi gỡ đã bắt đầu, đóng cửa sổ vẫn phải chờ hoàn tất/khôi phục. Nếu kết nối mất hoặc phục hồi chưa chắc chắn, app báo cần khôi phục và giữ backup. Kết quả build nằm trong `%LOCALAPPDATA%\RC2Vietnamese\hud\builds`.

## Menu và HUD

Trong EXE, chọn tab **Tay DJI RC 2** và bấm **Cài / cập nhật menu**. Worker tự lấy APK từ tay, đối chiếu hash/phiên bản/serial trước và sau khi kéo, phục hồi nguồn gốc nếu cần, dựng menu/HUD, căn chỉnh, ký bằng khóa riêng của PC, kiểm chứng receipt rồi cài đúng APK vừa tạo. Giữ tay ở trang chủ hoặc RC Launcher. Kéo hoặc phục hồi lỗi, hủy tác vụ, nguồn không được hỗ trợ hay thiết bị đổi/mất kết nối sẽ chặn bước cài. Cùng signer dùng install-r giữ dữ liệu; khác signer vẫn qua sao lưu và xác nhận gỡ/cài.

Luồng một nút không tự bật FreeFCC hay thay vùng radio của máy bay; đó là thao tác riêng trong menu sau khi cài.

Nút menu ba gạch nằm bên trái **Vào màn hình bay** hoặc **Kết nối máy bay**. Menu vẫn hiện khi chưa nối máy bay. Nền tối, chữ sáng, tự cuộn.

- **Chạm hai lần** ẩn/hiện HUD trong preview; tùy chọn được lưu. Kéo, đa điểm, chạm nút hoặc mất focus đặt lại bộ đếm. HUD đang ẩn vẫn có đường khôi phục khi tùy chọn bị tắt.
- **Icon LED trong màn hình bay đã gỡ hoàn toàn.** Điều khiển LED chỉ có trong menu trang chủ.
- **LED trước / sau:** bấm để đảo Bật ↔ Tắt của nhóm đã chọn, giữ nguyên nhóm còn lại. Đích được tính từ GET mới trong giao dịch, không dùng trạng thái UI cũ. Sau gồm rear/status; bật một phần được hiển thị “Một phần”, bấm sẽ tắt cả nhóm sau. Bật hết / Tắt hết vẫn có riêng.
- Khi mở menu, LED hiện đang đọc/chưa xác định và các thao tác LED bị khóa đến khi đọc thành công. Trong lúc ghi, giữ trạng thái thực đã đọc và khóa bấm lặp; đọc lại sau kết quả để hiển thị trạng thái thực. Không bật màu như đã thành công trước readback. LED bấm trực tiếp, vẫn kiểm tra mặt đất/động cơ dừng ở giao dịch; confirmation radio giữ nguyên.
- **Xuất hình:** Có HUD / Không HUD, lưu lựa chọn và hiển thị trạng thái kết nối. RC đang có driver DRM DP-1 và Qualcomm external-display nhưng chưa gắn màn hình/adapter để xác minh tín hiệu USB-C/HDMI vật lý. Không thay bằng xuất qua PC.

## Cầu SDK Basic và dữ liệu 1.21.10

Cầu Basic tìm descriptor SDK theo identifier `Connection`, `IsFlying`, `AreMotorsOn`, `LEDsSettings`. Tên field obfuscation có thể đổi; kiểu/quyền key và chữ ký method/callback vẫn phải khớp. Thiếu key, identifier trùng, callback/giá trị không hợp lệ hoặc telemetry cũ/không rõ phải dừng, không suy ra máy bay đã hạ cánh hay động cơ đã tắt.

Guard kết nối, telemetry đủ/còn mới, `IsFlying=false`, `AreMotorsOn=false` và trạng thái motor từ Midware được giữ. Fixture field rename chỉ xác minh tìm key và guard trên PC; không chứng minh ABI/radio/LED của 1.21.10 thực.

Đã lấy APK gốc RC 1.21.10/code 3115981 qua USB và tính lại đúng SHA-256 f6c11267d465c303e2aecb737fe4f6b41b54da083368cac497404f4c9a464f98. EXE cuối dựng/replay menu Basic và RRO; Basic đã cập nhật cùng signer, tiếng Việt đã bật và đọc lại trên tay. Thư mục người dùng cung cấp bổ sung bộ nhớ dịch/template lịch sử. Xem [bằng chứng](adaptive-menu-verification.json).

## LED trước và sau

Ở lượt chẩn đoán bản cũ trên Air3S, SDK typed LEDsSettings trả -9, nhưng đường Midware của chính Fly đọc được parameter `g_config.misc_cfg.forearm_lamp_ctrl_0`: hash0xedce59a2, size1/typeUINT8/index1327, response6byte/status0. Luồng mới đọc parameter qua SDK, kiểm tra telemetry hợp lệ/còn mới, Connection=true, IsFlying=false, AreMotorsOn=false, rồi dùng DataFlycSetParams.setInfo/start đúng chữ ký stock để ghi một lần và GET mới đối chiếu. Không socket40007, burst, retry hay rollback.

Encoder LEDsSettings native stock xác định front ở mask0x21, rear/status ở0x06. Yêu cầu mới gộp thành mask0x27: OFF239→200, ON200→239; giữ mọi bit ngoài mask, gồm navigation và các bit không được diễn giải. Chỉ layout front nhất quán được bật. Deadline monotonic10giây, callback được kiểm tra identity/type trước khi chiếm terminal; close cùng ranh giới SDK submission; readback sau SET có thể hoàn tất muộn để giải phóng đúng token mà không gọi UI đã đóng. Thiếu dữ liệu/motors bật/đang bay chặn ghi.

Bản sửa toggle2026-10-10 giữ khóa giao dịch ngay trước phần đọc thay vì chỉ tại lúc ghi. Vì thế hai yêu cầu Trước/Sau chồng nhau không thể cùng đọc baseline cũ rồi ghi đè nhóm còn lại. GET lỗi, hủy hoặc timeout trước ghi giải phóng khóa; đã gửi ghi thì chỉ readback phù hợp mới giải phóng. Không có vòng lặp ghi hay polling nền.

Mọi đường đọc và thay đổi LED dùng tham số forearm đã pin, giúp trạng thái ban đầu và toggle cùng nguồn dữ liệu. Không còn đường typed LED setter dự phòng. Khi readback đến muộn đối chiếu được lệnh trước, sự kiện reconciliation yêu cầu menu hiện hành đọc lại và mở các nút phù hợp. Observer được gỡ trước khi đóng adapter; không giữ owner monitor khi chờ child job đóng.

Bằng chứng lịch sử của bản cũ: front-only 239→206 và all-off 239→200, SDK ACK và GET mới khớp; người dùng xác nhận LED trước/sau tắt, kết nối giữ ổn định. Không dùng kết quả này xác nhận payload hiện hành hoặc Basic 0.10.1 trên 1.21.10. Từng thao tác toggle/bật nhóm vẫn cần kiểm tra riêng.

## Xuất hình trực tiếp

Có HUD dùng phản chiếu bình thường của Android khi màn hình ngoài được nhận. Không HUD tạo Presentation chỉ chứa SurfaceView video của Fly, giữ HUD trên tay. Đường SurfaceControl mirror dùng crop theo kích thước buffer; nếu API không khả dụng hoặc transaction lỗi thì dùng PixelCopy, hai buffer ARGB không quá960×540 và giới hạn5fps. Fallback có thể kém mượt hơn feed gốc và được ghi rõ trong trạng thái.

Vòng đời theo Activity và DisplayManager: pause, rút màn, đổi lựa chọn hoặc đóng app dọn renderer; đổi cấu hình màn ngoài tạo lại presentation. Callback của renderer cũ bị bỏ qua. Không thay nguồn preview, lệnh LED hay radio. Kiểm tra compositor riêng dùng virtual display private, tự dừng sau4giây, chỉ đếm buffer/mẫu có màu; không lưu hoặc xuất video. Kết quả virtual display không chứng minh adapter HDMI thật hoạt động.

Kết quả ở lượt chẩn đoán bản cũ trên tay: đã nhận preview xuất hiện muộn và surface hợp lệ. Probe mirror và probe riêng đường PixelCopy đều nhận6buffer đen, chưa có hình sạch được chứng minh. Vì vậy chưa xác nhận tính năng Không HUD hoạt động trên màn ngoài; phải thử và xử lý tiếp với adapter/màn hình thực. Lưu lựa chọn không đồng nghĩa đã xuất được video. USB-C/HDMI và HDR vật lý vẫn chưa xác minh; driver hoặc capability không phải bằng chứng tín hiệu thực.

## FCC tích hợp

Runtime sử dụng API stock `DataOsdSetSdrAssitantWrite.setForceFcc()` trong tiến trình Fly, cùng GET mới qua `DataOsdSetSdrAssitantRead` để đối chiếu override tại0xffff0048. Không cài/mở/gọi FreeFCC. Profile42frame và codec cũ vẫn được pin/kiểm thử như bằng chứng lịch sử; gửi đủ frame hoặc ACK không được báo như RF mode đã xác nhận.

- **FCC:** chỉ yêu cầu khi mặt đất/động cơ dừng. Đọc baseline, dùng SDK và đọc lại override2; nếu đã là2 thì không ghi lặp.
- **Khôi phục:** chỉ dùng baseline đọc trước lần bật FCC trong phiên, giữ nguyên baseline và gắn với hash serial máy bay. Không có baseline phù hợp thì từ chối đoán CE. Khôi phục giá trị không đồng nghĩa đã ép CE trên mọi vùng/firmware.
- Không tự ghi khi boot/reconnect/mở menu; chưa tạo keepalive. Độ bền qua camera/reboot và RF power/range cần kiểm chứng riêng.
- Hủy/timeout tách cleanup sender/worker khỏi owner monitor; regression thực thi real guard cùng close/timeout để chặn deadlock. Callback terminal muộn chỉ giải phóng đúng token sau readback hợp lệ.

Bằng chứng lịch sử trên Air3S: getter override 0xffff0048=2, 0xffff0063=0, country sky/ground VN/ac704; không có process/keepalive FreeFCC chạy và biểu đồ Truyền tín hiệu có chỉ báo UI phù hợp FCC. Đây là UI/readback của bản cũ, không phải đo công suất RF, thử tầm bay hoặc xác nhận duy trì radio. Country VN không tự chứng minh CE/FCC. Kết quả apply/restore và baseline của Basic hiện hành phải ghi riêng.

## Patch, ký và khóa

1. Kiểm tra hash APK/toolchain và từng tệp giải nén.
2. Đọc Application/chuỗi kế thừa; với loader có context-swap, chèn sau các bước khởi động gốc vào normal return đã xác định, giữ lớp khác trong DEX. App chuẩn dùng provider bootstrap.
3. Thêm provider riêng `local.rc2.hud.HudProvider`, `exported=false`, và DEX tiếp theo vị trí cao nhất hiện có. Chỉ tiến trình Fly chính đăng ký callback; wrapper AppGuard chưa đổi context chờ hook cuối khởi động. Chuyển nguyên event/kết quả/exception cho Window.Callback gốc.
4. Dựng APK và capsule nguồn, giữ bytes tài nguyên/native/DEX khác và kiểm tra cả dữ liệu nén entry không đổi.
5. Zipalign, ký v3 bằng khóa riêng Windows, kiểm tra signer API30. Phần v2 gốc giữ làm đầu vào native loader, không được mô tả là chữ ký hợp lệ của APK mod.
6. Receipt schema2 ghi hash nguồn/đầu ra/toolchain/payload/capsule, identity và plan theo cấu trúc. Trước cài, dựng lại recipe và xác minh manifest/DEX/signer. Payload lịch sử chỉ nhận diện bản đang cài khi nâng cấp; ứng viên mới phải dùng payload hiện tại.

Snapshot 0.9.0 trên PC: Fly RC 1.21.8 dùng Application `QLVRK`/DEX23; phone 1.21.12 dùng `RGTYT`, giữ bước `callBS` và 1.626 lớp khác/DEX2. Đầu vào 1.21.10/DEX33 của lần thử đó là **RedFly v5 đã mod**, chỉ là lịch sử/tham chiếu, được loại khỏi bằng chứng tương thích Fly RC 1.21.10 chính thức/Basic 0.10.1 và không làm nguồn Việt hóa hiện tại. [Phân loại bằng chứng](adaptive-menu-verification.json). Ký/replay/khôi phục archive trên PC không xác nhận cài/LED/FCC/HDMI trên tay.

Khóa ở `%LOCALAPPDATA%\RC2Vietnamese\hud-signing`, ngoài EXE/repo; DPAPI bảo vệ mật khẩu, quyền chỉ chủ tài khoản và SYSTEM. Không chia sẻ khóa/backup/log thiết bị. APK của PC khác có thể khác hash.

## Kiểm tra

Tests Python dùng desktop Tk thật, fake ADB và fixture cho worker/USB/dịch/launcher/dev mode, APK/signature/recipe, backup/consent/cancel/rollback và đóng gói. JVM tests kiểm tra cử chỉ, placement, SDK field/type, callback lặp/muộn, timeout/hủy, khóa ghi qua lifecycle, CRC/ACK/TCP loopback radio. Radio fixtures lấy từ APK công khai có pin, không cần phone-work. Tests host không gửi lệnh máy bay.

Ở các snapshot cũ, source Android compile platform30/D8 được so bytes với payload nhúng; thiết bị có quan sát cập nhật cùng chữ ký giữ dữ liệu, hash/UID/foreground, RRO bật-tắt-bật, Developer options và Home. Coverage Python không đại diện coverage Java/UI/flight. Việc cài bản thử riêng cùng signer giữ dữ liệu không xác nhận bản public Basic hiện hành đã cài. Báo cáo [hud-installation-2026-10-09.json](hud-installation-2026-10-09.json) mô tả bản0.6 đã cài và các chức năng còn lỗi, chưa xác nhận hoàn thành toàn bộ menu. Các ứng viên chẩn đoán mới chỉ được ghi nhận là build trên PC cho đến khi cài và kiểm tra riêng; các JSON0.3/0.4 là lịch sử.

LED vật lý của payload mới, FCC hiệu lực/công suất/duy trì/khôi phục, HDMI/HDR ngoài, mọi firmware và thử bay/soak dài cần bằng chứng riêng. Lượt cập nhật tài liệu không chạy ADB, cài APK hoặc gửi lệnh thiết bị.

## CLI

EXE windowed ghi JSON; thư mục báo cáo phải tồn tại:

```powershell
$task = Start-Process -FilePath '.\RC2-TiengViet.exe' -ArgumentList '--hud-build "C:\APK\DJI_FLY.apk" --menu-variant basic --report "C:\APK\hud-result.json"' -WindowStyle Hidden -Wait -PassThru
$task.ExitCode
Get-Content -LiteralPath 'C:\APK\hud-result.json'
```

Exit0/hud_built xác nhận build/kiểm tra trên PC, chưa đồng nghĩa cài hoặc mở trên tay.

Android 11 trên RC 2 dùng `cmd overlay lookup PACKAGE PACKAGE:TYPE/NAME`, không có `--user`; Android 15 giữ `--user 0`. 0.10.1 sửa chọn cú pháp theo SDK để gói dịch đúng không bị rollback do lệnh đọc lại sai. Sau cài menu, giữ tay ở **Settings/RC Launcher** trong lúc Việt hóa; mở lại DJI Fly sau khi có kết quả thành công.
