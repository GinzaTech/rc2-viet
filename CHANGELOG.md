# Changelog

## 0.7.0 — Việt hóa không khóa phiên bản DJI Fly (2026-10-10)

- Bỏ chặn phiên bản Fly trong luồng Việt hóa RC 2 và điện thoại. APK khác bản dựng sẵn được lấy từ thiết bị và xử lý bằng bộ dựng RRO thích ứng.
- Nhúng từ điển11.141 tài nguyên, kiểm tra kiểu/tên/văn bản nguồn/placeholder/mảng/số nhiều. Câu mới hoặc thay nghĩa giữ nguyên và báo số lượng; không tuyên bố dịch100% mọi phiên bản.
- Dựng, căn chỉnh và ký gói chỉ chứa tài nguyên bằng toolchain nhúng, giữ khóa riêng trên PC. Kiểm tra hash/serial xuyên suốt, phục hồi overlay khi thao tác lỗi.
- Bổ sung Java desktop phục vụ giải mã tài nguyên; không yêu cầu người dùng cài Java/SDK.
- Dựng/ký cục bộ thành công với nguồn Fly1.21.8 và1.21.12. Không kết nối hoặc kiểm tra thiết bị theo yêu cầu người dùng. Menu/HUD sửa mã vẫn giữ profile tương thích riêng.
- Kiểm chứng cuối: 1.114 test nguồn đạt, coverage Python `rc2vi` 88,40%; EXE tự dựng được gói dịch1.21.12/profileAndroid15 khi PATH chỉ có System32 và không có JAVA_HOME/CLASSPATH. Báo cáo ở `docs/translation-version-verification.json`.

## 0.6.3 — menu một nút và cập nhật EXE (2026-10-10)

- Bỏ toàn bộ hàng Nâng cao và các nút Tạo APK HUD, Cài APK HUD, Mở thư mục HUD, Chọn APK gốc. Đổi tiêu đề thành Menu trên tay.
- Chỉ giữ Cài / cập nhật menu tự lấy APK từ RC 2, patch, ký và cài lại; giữ xác nhận sao lưu/gỡ-cài khi khác chữ ký.
- Cập nhật hướng dẫn theo giao diện một nút.
- Gom các thay đổi menu/HUD và tự lấy APK từ các lượt 0.6.1/0.6.2 vào bản cập nhật source và EXE 0.6.3: phục hồi nguồn đã pin, patch/ký/kiểm chứng, cài đúng thiết bị và sao lưu/khôi phục khi thay chữ ký.
- LED Trước/Sau đảo trạng thái dựa trên GET mới, đọc ngay khi mở menu và giữ nguyên nhóm còn lại. Các kết quả kiểm tra thiết bị và giới hạn của FCC/xuất hình được lưu trong `docs/hud-installation-2026-10-09.json`; không coi kiểm tra host là xác nhận toàn bộ chức năng phần cứng.
- EXE 0.6.3 có SHA256 `d408b809cbdf7c588b9fc6be476858a7731bb0d8fd5e50a3d3130de3992ad30c`; đã chạy thử GUI từ bản đóng gói. Tệp EXE, checksum và metadata được cập nhật trực tiếp trong repository.
- Kiểm tra trước push: 908/908 test đạt, coverage toàn bộ module Python `rc2vi` 89,69%, 15 kiểm tra đóng gói đạt; dependency audit không phát hiện lỗ hổng đã biết. Rà soát source giới hạn ở luồng APK/khôi phục/controller/transport không phát hiện lỗi nghiêm trọng.

## 0.6.2 local — tự lấy APK từ RC 2 (2026-10-10)

- Nút chính Cài / cập nhật menu tự lấy APK DJI Fly qua ADB; không yêu cầu file trên PC. Giữ kiểm tra serial/model/API/foreground/hash trước và sau khi kéo.
- Template phục hồi1,6MB dựng lại đúng stock1.21.8 từ APK mod và các payload nén giữ nguyên. Không cần cache/khóa từ PC cũ; vẫn kiểm chứng recipe/payload/chữ ký APK kéo về và nguồn gốc toàn file trước patch.
- Dùng lại ADB thường khi đã sẵn sàng, không phá phiên Allow có sẵn. Thao tác dùng file thủ công chuyển sang hàng Nâng cao.

## Bổ sung cục bộ — LED toggle và menu dạng hàng (2026-10-10)

- Trước/Sau đổi trạng thái sau mỗi lần bấm, dựa trên GET mới trong giao dịch; không cần dùng Tắt hết để tắt riêng một nhóm. Rear/status bật một phần được hiển thị rõ và toggle về tắt. Các bit khác được giữ nguyên.
- Mở menu đọc trạng thái ngay; chưa có dữ liệu thì hiện chưa xác định và khóa LED. Giữ trạng thái thực trong lúc xử lý, GET lại sau cả thành công/thất bại; không cập nhật màu lạc quan. LED không cần dialog xác nhận mỗi lần bấm; kiểm tra mặt đất/động cơ dừng vẫn được giữ.
- Khóa toàn bộ đọc/đổi/ghi/readback để tránh yêu cầu Trước/Sau đè baseline; giữ late reconciliation sau hủy/timeout cho lệnh đã gửi.
- Giao diện một panel bo góc tối với các hàng điều khiển, nút tonal nhỏ, nhãn trạng thái độc lập, nút đóng48dp; bỏ header/footer mặc định và viền lớn. Không thêm blur, ảnh, runtime dependency hoặc polling.

## Bổ sung cục bộ — menu compact và patch một nút (2026-10-09)

- Tab Tay DJI RC 2 có nút Patch menu DJI Fly: chọn APK gốc1.21.8, tự dựng/căn chỉnh/ký/kiểm chứng rồi cài đúng receipt mới. Giữ cùng thiết bị qua các bước; lỗi/hủy/đổi tay chặn cài. Cập nhật cùng signer giữ dữ liệu; khác signer vẫn cần xác nhận sao lưu và gỡ/cài.
- Menu trên tay chuyển hai cột, LED2×2 Trước/Sau/Cả hai/Tắt hết; bật riêng một nhóm giữ nhóm còn lại. Gỡ icon LED khỏi màn hình bay. SDK Midware đọc/ghi/readback parameterLED một lần với deadline10giây; người dùng đã xác nhận all-off trước/sau không mất kết nối ở bản thử riêng.
- Xuất hình có/khôngHUD dùng Presentation của preview, nhận cả preview xuất hiện muộn, hotplug/cấu hình/vòng đời được dọn; mirror theo buffer với PixelCopy fallback tối đa5fps. Driver DP-1 đã quan sát; HDMI vật lý vẫn cần thử với màn hình/adapter.
- FCC dùng API setForceFcc và GET mới; vùng gốc chỉ khôi phục baseline thực đã lưu theo máy bay. Không có keepalive hoặc tuyên bố đo công suất RF.
- Tìm receipt APK cũ lọc metadata digest trước, vẫn kiểm chứng đầy đủ bản khớp; tránh kiểm chứng mọi APK cũ không liên quan. Thêm kiểm tra thực thi vòng đời output và chữ ký/cập nhật một nút.

## 0.6.0 local — 2026-10-09

- Menu RC cạnh trái nút Vào màn hình bay, checkbox chạm hai lần được lưu; icon LED trong HUD không có nền, cao hơn và ẩn cùng HUD.
- Loại đường ghi LED TCP/DUML khỏi runtime. Thử adapter SDK của Fly1.21.8 với kiểm tra kết nối/trạng thái bay/động cơ, giữ các cờ đèn khác, một lệnh ghi, đọc lại, deadline6giây và hủy khi Activity pause. Không xác nhận LED Air3S hoạt động chỉ từ test host.
- Tích hợp yêu cầu FCC/khôi phục vùng gốc trực tiếp trong APK mod, không cài/mở FreeFCC; profile/CRC được pin, ground gate/ACK/deadline/cancel. Khôi phục vùng gốc không luôn là CE; RF hiệu lực/duy trì chưa xác minh, không có keepalive tự chạy.
- Khóa mục xuất hình khi chưa có đường hỗ trợ. Thêm tests cho giao dịch LED, callback lặp/muộn, hủy, readback và SDK giá trị không hợp lệ.
- Giữ nâng cấp APK cùng khóa ký, các pin payload lịch sử chỉ dành cho nhận diện bản đang cài; EXE vẫn giải nén/patch/ký ngoại tuyến.

## Local0.4.1 — sửa luồng ADB khi cài thật (2026-10-09)

- Lấy đúng transport_id từ dòng thiết bị sẵn sàng trong `adb devices -l`; bỏ lệnh get-transport-id không có trong ADB nhúng. Vẫn khóa `-t` và kiểm tra physical serial trong cùng shell trước lệnh thay đổi.
- Chấp nhận dòng trống do toybox sha256sum và completion marker tạo ra; giữ kiểm tra đúng hash/path/marker và từ chối output dư.
- Đọc header ADB24byte rồi đúng phần payload còn thiếu qua WinUSB, tránh chờ một short packet sau payload đủ512byte. Có regression với512/1024/65536/65537byte và kiểm tra giới hạn read.
- APK chạm ba lần/LED giữ nguyên nội dung/hash từ0.4.0; chỉ công cụ PC thay đổi. Kết quả triển khai thực tế được ghi riêng, không coi source tests là đã cài thành công.

## Local0.4.0 — chạm ba lần và LED càng (2026-10-09)

- Bỏ nút con mắt; chạm nhanh ba lần gần nhau trong preview để ẩn/hiện HUD. Bỏ qua nút điều khiển, kéo, đa điểm, long-press, khoảng chạm quá dài; reset khi mất focus/rời Activity. Mọi callback/event/return/exception gốc vẫn được chuyển về DJI.
- Icon bóng đèn nhỏ cạnh trái phía dưới, vùng chạm48dp; giữ để ẩn/hiện HUD. Bấm gửi OFF/ON theo lần yêu cầu, tác vụ một lượt và hủy trên pause, không có polling nền.
- Đối chiếu FreeFCC1.5.5: LED profile qua proxy40007, hai trạng thái cố định,10lượt với100ms khoảng cách; không chạy FCC/4G. Air3S được upstream ghi LED chưa thử; kết quả chỉ là gửi lệnh, không phải readback trạng thái đèn.
- DEX framework-only khoảng25KB; thêm tests JVM nhận chạm, callback, golden frame, TCP giả, partial/cancel/permission/single-flight, compile platform30 và DEX-source equality.
- Bản EXE/ZIP0.4.0 cục bộ;547tests source và15tests package đạt. Không có RC kết nối: thao tác thật trên tay, LED Air3S, boot/reboot và bay với APK mới chưa được kiểm chứng. Không commit/push trong yêu cầu này.

## Local 0.3.0 — EXE tự tạo APK HUD (2026-10-09)

- Thêm ba nút gọn trong trang RC: Tạo APK HUD, Cài APK HUD, Mở thư mục HUD. Tạo APK chạy trên worker và không cần USB; trang điện thoại giữ luồng riêng.
- Nhúng Java17 tối thiểu, APKtool2.12.1, apksigner/zipalign36.1.0 và helper patch/ký. Chỉ nhận APK gốc RC Fly1.21.8/code3115809 có hash đã pin; tự giải nén, patch bootstrap/manifest, thêm classes23.dex, zipalign, ký v3 và kiểm tra recipe/bytes/chữ ký API30.
- Khóa riêng được tạo theo tài khoản Windows, mật khẩu bảo vệ bằng DPAPI, DACL chỉ chủ tài khoản/SYSTEM đọc. PC đang làm việc được nhập lại khóa cũ cục bộ; EXE không chứa khóa ký hoặc APK DJI Fly gốc.
- Installer thử cập nhật giữ dữ liệu trước. Khác chữ ký yêu cầu sao lưu đã kiểm tra và hộp thoại đồng ý ràng buộc với thiết bị/APK hiện tại. Có khôi phục, báo rõ kết quả, dọn staging riêng trên tay; giữ USB tới hết cài/khôi phục nếu đóng cửa sổ sau bước gỡ.
- Đã kiểm thử APK thật từ EXE khi PATH chỉ có Windows System32, không có JAVA_HOME/CLASSPATH. Không có RC kết nối trong lượt này: boot/reboot APK do pipeline mới tạo và installer trên thiết bị thật chưa được kiểm chứng. Bản HUD thủ công 0.2.1 có bằng chứng riêng; không dùng bằng chứng đó thay cho APK mới.
- Cập nhật EXE/ZIP/checksum cục bộ cùng phiên bản. Chưa commit, push hoặc phát hành GitHub trong lượt này.

## Local 0.2.1 — DJI Fly HUD APK (2026-10-08)

- Nhúng nút con mắt ẩn/hiện HUD vào DJI Fly RC2 1.21.8; APK đã cài thường và kiểm tra sau đóng/mở app, khởi động lại tay. Giữ gói tiếng Việt và thanh điều hướng.
- Khôi phục dữ liệu từ bản sao lưu sau khi người dùng đồng ý gỡ/cài lại do khác chữ ký; không hứa khôi phục khóa Keystore/phiên đăng nhập.
- App Windows chấp nhận chính xác hash APK HUD đã kiểm chứng. Build cục bộ 0.2.1; chưa phát hành GitHub.
- Thêm kiểm thử đóng gói ZIP, provider riêng tư, dữ liệu chữ ký và kiểm tra payload nén không đổi. Chưa kiểm thử bay hoặc hình camera từ máy bay sau lần cài cuối (máy bay không kết nối).

## Local: desktop VShop compact / launcher icon

- Desktop dùng nền đen, token VShop card18/button14, nhấn đỏ#c72232, nút30px và bố cục960x740; timer GUI được dọn khi đóng.
- Nhúng RC Launcher preview4/code4 có icon vector, pinRC/nhiệt độ pin/Wi-Fi; trên RC đã install/readback PASS.
- 142 testsPC pass,20 unit testsAndroid pass; releaseGitHub chưa thay đổi.


## Chưa phát hành — Android và desktop nền đen (2026-10-08)

- Nhúng RC Launcher preview3/code3 (APK135KB, package riêng) và nút cài/mở trong trang RC; đã kiểm tra installed hash/component trên tay. Launcher source ở project rc-launcher; dashboard tối giản, bỏ dock trùng native bar theo yêu cầu.

- Nền đen, thẻ tối, điểm nhấn mint, hai trang Android/RC 2; chọn thiết bị, trạng thái và lệnh tách riêng.
- Worker ADB chuẩn cho điện thoại; giữ thiết bị đã chọn khi mất USB, hiển thị offline/unauthorized, chặn lệnh RC trong trang Android.
- RRO 1.21.12-vi3 cho APK DJI chính thức Android 1.21.12 (3131451), SDK 35 có root. Tái sử dụng 11.068 tài nguyên nguồn khớp; giữ gốc 80 mục khác biệt theo vùng, sửa 7 nhãn điều khoản/quyền riêng tư.
- Redmi K60: cài APK DJI nguyên chữ ký, bật/tắt overlay có readback, trang chủ thật tiếng Việt, nút Apply qua GUI thật. Chưa kiểm thử bay, reboot điện thoại hoặc nội dung web/server.
- Thêm CLI --phone-inspect/--phone-verify, kiểm thử root/rollback/phân tách thiết bị, ảnh GUI và hướng dẫn Android. EXE nhúng APK tài nguyên điện thoại, không nhúng APK DJI Fly gốc 720 MB.
- Sửa Hệ thống nhạy cảm → Hệ thống cảm biến trong cả gói điện thoại và RC reviewed6/code 8.
- Giữ sửa cầu Home v2 và chức năng RC. GitHub v0.1.0 chưa thay đổi trong yêu cầu này.

## Chưa phát hành — sửa cầu Home v2

- Cầu Home 2.0 chuyển ngay khi Android sẵn sàng, dùng theme trong suốt, tắt starting preview và tự finish sau khi mở Lawnchair.
- Chỉ dựng màn fallback khi thực sự chờ unlock hoặc chưa mở được launcher; xử lý Home intent mới và hủy callback khi rời activity.
- Thêm 6 tình huống hồi quy Java và kiểm thử nâng đúng cầu v1 bằng install -r, giữ dữ liệu, không thay Home nếu đọc lại APK lỗi.
- APK cầu được cài/kiểm tra trên tay, ba lần Home từ Settings về Lawnchair; đã kiểm tra sau reboot vẫn vào Lawnchair.
- Bản local EXE có pin APK mới; release GitHub v0.1.0 chưa được thay trong yêu cầu này.

## v0.1.0 — 2026-10-06

- Tạo repository độc lập RC2 Việt, giao diện Windows tiếng Việt và EXE onefile có ADB/DLL nhúng.
- Kết nối RC 2 qua WinUSB/cầu ADB loopback, chọn đúng tay và giữ bước Allow USB debugging trên thiết bị.
- Bật/tắt/cập nhật RRO tiếng Việt reviewed5 cho đúng DJI Fly 1.21.8, kiểm tra hash/idmap/readback và phục hồi cache khi thất bại.
- Nhúng và cài Lawnchair 15 Beta 3, FreeFCC 1.5.5 bằng luồng APK đã kiểm tra.
- Mở Lawnchair/DJI Fly, cầu Home Direct Boot và nút đặt Lawnchair làm màn hình chính theo firmware được pin.
- Mở Developer options sẵn có với cảnh báo OK/Hủy về nguy cơ mất ADB khi tắt thủ công.
- Lưu đủ 7 APK trong thư mục dự án app, phân biệt 4 gói dùng được với APK trung gian/SystemUI tham chiếu.
- Bổ sung nguồn XML bản dịch, quy tắc rà, hướng dẫn sử dụng/build, SHA256 và ghi công upstream.
- Cập nhật pytest/setuptools/pip của môi trường build sau dependency audit; dùng capture Python-level cho test Tcl/Tk trên Windows.
- Ghi rõ các giới hạn: ADB offline sau reset, cài bằng nút mới sau reset chưa xác minh, thanh điều hướng ba nút chưa bật, chưa thử bay hay kích hoạt FCC.
