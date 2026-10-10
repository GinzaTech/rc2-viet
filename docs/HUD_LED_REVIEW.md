# Rà soát HUD và LED — 09/10/2026

## Bản sửa sau0.6 — đang kiểm tra thiết bị

Chạm hai lần ẩn/hiện HUD được giữ. Theo yêu cầu mới, icon LED và hộp thoại LED của màn hình bay đã gỡ hoàn toàn; LED chỉ còn trong menu trang chủ. Menu hỗ trợ cả nút GoFly và nút kết nối khi máy bay chưa nối, căn theo tâm đầy đủ. Guard cử chỉ vẫn cho khôi phục HUD đang ẩn khi tùy chọn cử chỉ bị tắt. Không còn thao tác giữ icon LED.

Trên Air3S đã kết nối/mặt đất/động cơ dừng, SDK typedU2 vẫn trả-9 nhưng Midware GET tham số forearm thành công: hash0xedce59a2, response6byte/status0, raw239. Luồng mới thử typedGET trước rồi fallback GET có kiểm chứng để bật nút. Ghi một lần qua DataFlycSetParams.setInfo/start, chỉ đổi mask0x21 và giữ mọi bit khác; raw239→206 khi OFF,206→239 khi ON. Chỉ layout có hai bit front nhất quán được bật. GET trước, kiểm tra mặt đất mới, SET và GET đối chiếu; không socket/burst/rollback. Hành vi đèn vật lý và việc giữ đường truyền vẫn cần kiểm tra riêng sau cài.

Các lỗi review được tái hiện/khắc phục: callback sai instance không chiếm slot terminal; deadline monotonic chặn SET dù Timer chạy trễ; ranh giới SDK submission cùng lock với close nhưng không giữ lifecycle monitor trong callback; readback muộn giải phóng đúng token mà không gọi UI đã đóng. NativeRadio cũng tách cleanup sender/worker ra ngoài owner monitor để tránh đảo thứ tự lock với guard. Regression tích hợp thực thi cả close và timeout của owner.

Đường ghi LED TCP/DUML0.4 dưới đây đã loại khỏi runtime. SDK adapter dùng GET bốn cờ, chỉ đổi front, một SET và đọc lại. Mọi callback flight-state chặn lặp/muộn và kiểm tra active. Deadline sau dispatch không cho lệnh mới chồng lên kết quả chưa rõ; MutationFence tồn tại qua Activity recreation. Probe menu là GET-only và hủy callback/timer khi dispose.

SDK error -9 là PARAMETERS_GET_ERROR, không phải bằng chứng FEATURE_NOT_SUPPORTED. Static audit exact APK cfbf67368fa812c6e7d51430a07518ab47d056605bf373fcc69277e540caa32e xác định: UAVKey.i(U2) dùng subComponentIndex65534; đường FlyModel infra dùng subComponentIndex0. Adapter chỉ đổi LED sang UAVKey.l(U2,0,0,0), giữ các key connection/flying/motors đã kiểm chứng ở factory i. GET biến thể này và LED vật lý cần kiểm chứng riêng; không suy từ fixture.

Hash0xedce59a2 trong profile LED cũ ứng với g_config.misc_cfg.forearm_lamp_ctrl_0, index1327/typeINT08U/size1 trong R.raw.flyc_param_infos (APK entryres/fg0). Lệnh0xf9 thay toàn bộ byte00/ef, không merge/read-before-write. Chưa biết mask front-only cho Air3S hoặc nguyên nhân mất kết nối; không dùng raw fallback. Đây là mapping tĩnh của exact APK, không xác nhận firmware/mask tương thích.

Tests RED→GREEN đã tái hiện/hạ ba finding về timeout sau SET, gesture tắt nhưng vẫn long-press ẩn, và ground callback tiếp tục sau dispose. Tests thêm key tuple, GET-only, late probe, readback, giữ ba cờ khác và lock qua menu/camera. Coverage Python không bao gồm Java/hardware.

## Bằng chứng native bổ sung — chưa bật raw SET

Exact stock `libsdk_jni.so` SHA256 `821ec8c9d411401b801a959d3134222ed5044ac6f9b7adbadcda236b31b0dfd9`: `GetConfigValueHandler<LEDsSettings>` VA `0x02664ae0` giải mã bit0/front, bit1/rear, bit2/status và bit4/navigation. `SetConfigValueHandler<LEDsSettings>` VA `0x02664b60` mã hóa `front | rear<<1 | status<<2 | navigation<<4 | front<<5`. Vì vậy encoder SDK dùng mask `0x21` cho front, gồm bit0 và bit5; decoder đọc front từ bit0. Thứ tự trường được đối chiếu constructor/serialization trong `libsdk_key_value.so` SHA256 `dee424e3458a92f6f9e8cbf3642d44a458f3e34507ad9fc07b2016d8df13ffca` và lớp Java exact APK.

Chưa chứng minh Air3S ánh xạ parameter `g_config.misc_cfg.forearm_lamp_ctrl_0` vào handler này. Mask native và parameter cùng xuất hiện trong APK không đủ để cho phép raw SET. Nếu ánh xạ được xác nhận thì phép đổi front bảo toàn các bit khác là `current & 0xde` / `current | 0x21`, sau GET mới hợp lệ; hiện chỉ có probe GET được đưa vào ứng viên. Bit5 chưa có ý nghĩa vật lý độc lập được xác minh.

Profile cũ OFF00 xóa toàn bộ bit; ONEF còn đổi các bit ngoài front, gửi lặp10lần và có thể chạy cùng keepalive FCC. Đây là bằng chứng không phải thao tác front-only; chưa xác định riêng nguyên nhân gây mất đường truyền. Không khôi phục đường ghi đó khi chưa có readback và kiểm tra kết nối thực tế.

## Lịch sử0.4 — không dùng làm hướng dẫn runtime hiện tại

Mục tiêu: thay nút con mắt bằng ba lần chạm trong preview, thêm icon LED nhỏ bên trái trong handler hiện có và tiếp tục dùng pipeline EXE đã kiểm tra. Các lớp Java riêng tách nhận dạng chạm, forwarding callback, trường LED cố định và transport một lượt; không thêm thư viện Android/SDK DJI hoặc service polling.

Đã rà thời gian/vùng chạm, reset khi kéo/đa điểm/mất focus/pause, chuyển nguyên event/kết quả/exception của Window.Callback, trả callback cũ khi vẫn là wrapper của mình, trả visibility, hủy socket/job và bỏ callback UI sau dispose. Icon LED có vùng chạm48dp và long-click thay thế để khôi phục HUD. Native preview/mission/warning layers vẫn theo recipe HUD đã có.

Khắc phục trong quá trình rà: đặt icon xuống phía dưới cạnh trái để tránh vùng waypoint/cất-hạ cánh ở hierarchy lịch sử; reset bộ đếm trên mất focus; bắt lỗi permission transport để không thoát thread với exception làm Fly crash; báo số lượt gửi và readback=false thay vì coi LED đã được xác nhận. DEX phải được compile và so byte với source trong test, tránh đóng gói source mới nhưng payload cũ.

JVM tests kiểm tra nhận dạng chạm/timeout/drag/multitouch/ineligible/longpress/reset/cooldown, callback delegation/fault/original exception, golden frame theo FreeFCC1.5.5, TCP loopback server giả, partial/disconnect/permission/cancellation/single-flight. Test source Android compile platform30/D8 và so DEX nhúng. Các tests này không gửi lệnh tới thiết bị thật.

Không thấy vấn đề source mức Critical/High còn tồn tại trong phạm vi đã đọc. Điểm chưa đóng: hành vi trên Android thật, các layout hoặc callback bị Fly thay muộn, việc LED thực sự đổi trên Air3S, và độ ổn định sau restart/reboot/bay cần chứng cứ thiết bị riêng. Coverage Python của pipeline không đại diện coverage UI Android. Đánh giá chỉ phê duyệt build cục bộ để kiểm tra, không chứng nhận vận hành bay.

Nguồn đối chiếu: [FreeFCC tag1.5.5](https://github.com/doesthings/FreeFCC/tree/v1.5.5), commit `597157bd52120dfeb9677f79a8ad46b6027ce8dc`, [bảng tương thích Air3S LED chưa thử](https://github.com/doesthings/FreeFCC/blob/v1.5.5/README.md#compatibility), [Window.Callback](https://developer.android.com/reference/android/view/Window.Callback).
