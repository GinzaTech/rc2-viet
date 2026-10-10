# HUD, menu RC và FCC trong APK mod

EXE0.7.0 mở khóa số phiên bản cho **Việt hóa tài nguyên**. Profile patch mã menu/HUD mô tả dưới đây vẫn dành riêng cho FlyRC1.21.8.

Bản cục bộ0.6.3 dành cho DJI Fly RC2 1.21.8/code3115809 trên RC331/Android11/API30. EXE nhúng Python, ADB, Java, APKtool, apksigner và zipalign; không cần cài riêng các công cụ đó. Windows vẫn cần driver USB phù hợp và tay phải cho phép USB debugging. Chưa có profile HUD điện thoại.

## Tạo và cài

Nút chính **Cài / cập nhật menu** tự lấy APK DJI Fly đang cài trên RC 2 qua ADB. Không mở hộp chọn file. Hỗ trợ APK gốc1.21.8 có SHA256 `cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e`, hoặc bản HUD/menu đúng recipe và payload đã pin. Phiên bản khác, bản mod không nhận diện được, cấu trúc hoặc hash khác bị từ chối trước cài.

Với bản mod đã kiểm chứng, EXE dùng phần dữ liệu nén giữ nguyên trong APK trên tay và template1592400byte chứa header/đuôi ZIP cùng hai đầu vào đã sửa để tái tạo APK gốc đúng hash. EXE không nhúng toàn bộ APK468MB. Nguồn phục hồi phải khớp từng payload nén và hash toàn file; sau đó còn kiểm tra recipe HUD và chữ ký Android11 của APK kéo về. Không cần APK gốc hay cache từ PC cũ. PC mới có khóa ký khác vẫn phải xác nhận sao lưu/gỡ-cài.

Trong EXE chỉ còn nút **Cài / cập nhật menu**; đã bỏ hàng Nâng cao, Tạo APK HUD, Cài APK HUD, Mở thư mục HUD và Chọn APK gốc.

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

## LED trước và sau

SDK typed LEDsSettings trả-9 trên Air3S, nhưng đường Midware của chính Fly đọc được parameter `g_config.misc_cfg.forearm_lamp_ctrl_0`: hash0xedce59a2, size1/typeUINT8/index1327, response6byte/status0. Luồng mới đọc parameter qua SDK, kiểm tra telemetry hợp lệ/còn mới, Connection=true, IsFlying=false, AreMotorsOn=false, rồi dùng DataFlycSetParams.setInfo/start đúng chữ ký stock để ghi một lần và GET mới đối chiếu. Không socket40007, burst, retry hay rollback.

Encoder LEDsSettings native stock xác định front ở mask0x21, rear/status ở0x06. Yêu cầu mới gộp thành mask0x27: OFF239→200, ON200→239; giữ mọi bit ngoài mask, gồm navigation và các bit không được diễn giải. Chỉ layout front nhất quán được bật. Deadline monotonic10giây, callback được kiểm tra identity/type trước khi chiếm terminal; close cùng ranh giới SDK submission; readback sau SET có thể hoàn tất muộn để giải phóng đúng token mà không gọi UI đã đóng. Thiếu dữ liệu/motors bật/đang bay chặn ghi.

Bản sửa toggle2026-10-10 giữ khóa giao dịch ngay trước phần đọc thay vì chỉ tại lúc ghi. Vì thế hai yêu cầu Trước/Sau chồng nhau không thể cùng đọc baseline cũ rồi ghi đè nhóm còn lại. GET lỗi, hủy hoặc timeout trước ghi giải phóng khóa; đã gửi ghi thì chỉ readback phù hợp mới giải phóng. Không có vòng lặp ghi hay polling nền.

Mọi đường đọc và thay đổi LED dùng tham số forearm đã pin, giúp trạng thái ban đầu và toggle cùng nguồn dữ liệu. Không còn đường typed LED setter dự phòng. Khi readback đến muộn đối chiếu được lệnh trước, sự kiện reconciliation yêu cầu menu hiện hành đọc lại và mở các nút phù hợp. Observer được gỡ trước khi đóng adapter; không giữ owner monitor khi chờ child job đóng.

Kiểm chứng đã có: front-only239→206 và all-off239→200, SDK ACK và GET mới khớp. Người dùng xác nhận LED trước và sau đều tắt, kết nối giữ ổn định. Các lựa chọn bật riêng từng nhóm của menu compact phải có kết quả kiểm tra riêng.

## Xuất hình trực tiếp

Có HUD dùng phản chiếu bình thường của Android khi màn hình ngoài được nhận. Không HUD tạo Presentation chỉ chứa SurfaceView video của Fly, giữ HUD trên tay. Đường SurfaceControl mirror dùng crop theo kích thước buffer; nếu API không khả dụng hoặc transaction lỗi thì dùng PixelCopy, hai buffer ARGB không quá960×540 và giới hạn5fps. Fallback có thể kém mượt hơn feed gốc và được ghi rõ trong trạng thái.

Vòng đời theo Activity và DisplayManager: pause, rút màn, đổi lựa chọn hoặc đóng app dọn renderer; đổi cấu hình màn ngoài tạo lại presentation. Callback của renderer cũ bị bỏ qua. Không thay nguồn preview, lệnh LED hay radio. Kiểm tra compositor riêng dùng virtual display private, tự dừng sau4giây, chỉ đếm buffer/mẫu có màu; không lưu hoặc xuất video. Kết quả virtual display không chứng minh adapter HDMI thật hoạt động.

Kết quả hiện tại trên tay: đã nhận preview xuất hiện muộn và surface hợp lệ. Probe mirror và probe riêng đường PixelCopy đều nhận6buffer đen, chưa có hình sạch được chứng minh. Vì vậy chưa xác nhận tính năng Không HUD hoạt động trên màn ngoài; phải thử và xử lý tiếp với adapter/màn hình thực. Lưu lựa chọn không đồng nghĩa đã xuất được video.

## FCC tích hợp

Runtime sử dụng API stock `DataOsdSetSdrAssitantWrite.setForceFcc()` trong tiến trình Fly, cùng GET mới qua `DataOsdSetSdrAssitantRead` để đối chiếu override tại0xffff0048. Không cài/mở/gọi FreeFCC. Profile42frame và codec cũ vẫn được pin/kiểm thử như bằng chứng lịch sử; gửi đủ frame hoặc ACK không được báo như RF mode đã xác nhận.

- **FCC:** chỉ yêu cầu khi mặt đất/động cơ dừng. Đọc baseline, dùng SDK và đọc lại override2; nếu đã là2 thì không ghi lặp.
- **Khôi phục:** chỉ dùng baseline đọc trước lần bật FCC trong phiên, giữ nguyên baseline và gắn với hash serial máy bay. Không có baseline phù hợp thì từ chối đoán CE. Khôi phục giá trị không đồng nghĩa đã ép CE trên mọi vùng/firmware.
- Không tự ghi khi boot/reconnect/mở menu; chưa tạo keepalive. Độ bền qua camera/reboot và RF power/range cần kiểm chứng riêng.
- Hủy/timeout tách cleanup sender/worker khỏi owner monitor; regression thực thi real guard cùng close/timeout để chặn deadlock. Callback terminal muộn chỉ giải phóng đúng token sau readback hợp lệ.

Trên Air3S đã nối: getter override0xffff0048=2,0xffff0063=0, country sky/groundVN/ac704. Không có process/keepalive FreeFCC chạy. Biểu đồ Truyền tín hiệu có đường ngang dưới mốc≈1km, phù hợp ảnh FCC của [nguồn FreeFCC v1.5.5](https://github.com/doesthings/FreeFCC/tree/v1.5.5). Đây là chỉ báo UI và đọc lại override, không phải đo công suất RF hoặc thử tầm bay. CountryVN không tự chứng minh CE/FCC. Kết quả menu apply/restore và baseline phải ghi riêng.

## Patch, ký và khóa

1. Kiểm tra hash APK/toolchain và từng tệp giải nén.
2. Trích manifest/classes.dex, thêm hook được pin vào QLVRK.onCreate, giữ loader/native hiện có.
3. Thêm provider riêng local.rc2.hud.HudProvider, exported=false, và classes23.dex. Chỉ tiến trình Fly chính đăng ký callback Activity; chuyển nguyên event/kết quả/exception cho Window.Callback gốc.
4. Dựng APK, giữ tài nguyên/native và DEX2–22, kiểm tra cả bytes nén entry không đổi.
5. Zipalign, ký v3 bằng khóa riêng Windows, kiểm tra signer API30. Phần v2 gốc giữ làm đầu vào native loader, không được mô tả là chữ ký hợp lệ của APK mod.
6. Receipt ghi hash nguồn/đầu ra/toolchain/payload/chứng thư công khai. Trước cài, dựng lại recipe và xác minh manifest/DEX/signer. Payload lịch sử được pin chỉ nhận diện bản đang cài khi nâng cấp; ứng viên mới phải dùng payload hiện tại.

Khóa ở `%LOCALAPPDATA%\RC2Vietnamese\hud-signing`, ngoài EXE/repo; DPAPI bảo vệ mật khẩu, quyền chỉ chủ tài khoản và SYSTEM. Không chia sẻ khóa/backup/log thiết bị. APK của PC khác có thể khác hash.

## Kiểm tra

Tests Python dùng desktop Tk thật, fake ADB và fixture cho worker/USB/dịch/launcher/dev mode, APK/signature/recipe, backup/consent/cancel/rollback và đóng gói. JVM tests kiểm tra cử chỉ, placement, SDK field/type, callback lặp/muộn, timeout/hủy, khóa ghi qua lifecycle, CRC/ACK/TCP loopback radio. Radio fixtures lấy từ APK công khai có pin, không cần phone-work. Tests host không gửi lệnh máy bay.

Source Android compile platform30/D8 được so bytes với payload nhúng. Coverage Python không đại diện coverage Java/UI/flight. Tay thật dùng cập nhật cùng chữ ký giữ dữ liệu, kiểm tra hash/UID/foreground; RRO bật-tắt-bật, Developer options và nút Home đã quan sát. Báo cáo [hud-installation-2026-10-09.json](hud-installation-2026-10-09.json) mô tả bản0.6 đã cài và các chức năng còn lỗi, chưa xác nhận hoàn thành toàn bộ menu. Các ứng viên chẩn đoán mới chỉ được ghi nhận là build trên PC cho đến khi cài và kiểm tra riêng; các JSON0.3/0.4 là lịch sử.

LED vật lý, FCC hiệu lực/duy trì, HDMI ngoài, mọi firmware và thử bay/soak dài cần bằng chứng riêng. Điện thoại không cắm trong lượt này chỉ có kiểm thử host.

## CLI

EXE windowed ghi JSON; thư mục báo cáo phải tồn tại:

```powershell
$task = Start-Process -FilePath '.\RC2-TiengViet.exe' -ArgumentList '--hud-build "C:\APK\DJI_FLY.apk" --report "C:\APK\hud-result.json"' -WindowStyle Hidden -Wait -PassThru
$task.ExitCode
Get-Content -LiteralPath 'C:\APK\hud-result.json'
```

Exit0/hud_built xác nhận build/kiểm tra trên PC, chưa đồng nghĩa cài hoặc mở trên tay.
