# Patch menu theo cấu trúc APK, không theo khóa phiên bản

Yêu cầu: cùng luồng tự lấy APK, phân tích, dựng/ký/cài cho ngôn ngữ và menu. Không kiểm tra/cài trên thiết bị ở lượt này theo ràng buộc đã có. Tiếp tục build, commit/push sau kiểm chứng cục bộ.

- Thay khóa số phiên bản/hash nguồn của menu bằng kế hoạch phân tích APK: package/application, DEX chứa bootstrap, điểm khởi động đã nhận diện, slot DEX còn trống, tài nguyên/UI và contract SDK.
- Giữ toàn bộ ZIP payload không liên quan, bản gốc và thông tin phục hồi của đúng APK. Mod mới mang dữ liệu đảo patch để bản EXE sau tự lấy/phục hồi từ tay, không cần gói stock riêng1.21.8.
- Không giả định một tên Application obfuscate hoặc classes23.dex. Hook AppGuard chỉ khi nhận diện được mẫu khởi động/context swap; app chuẩn dùng provider bootstrap. Cấu trúc mơ hồ phải trả báo cáo chưa tương thích, không bỏ kiểm tra rồi cài.
- Khả năng menu/HUD dựa trên cấu trúc và resource thực tế. LED/radio phải giữ kiểm tra chữ ký API, trạng thái mặt đất, một lệnh và readback; không đoán lệnh khi API đổi. Nêu đúng mức khả năng được phát hiện và chưa được chạy trên thiết bị.
- Receipt và installer kiểm tra digest/version/code của nguồn hiện hành theo kế hoạch đã dựng, vẫn sao lưu/xác nhận khi khác signer. Gói hoàn chỉnh ngôn ngữ0.8 tiếp tục tự dựng từ APK.
- Chứng cứ: hai APK thực có sẵn, fixture đổi tên lớp/DEX index/version, round-trip phục hồi, chữ ký, ràng buộc chống trùng/không sửa entry khác; không ADB/ARTEMIS trên thiết bị.
- Thành công cục bộ không chứng minh mọi firmware/phiên bản tương lai hoặc các chức năng vật lý đã hoạt động. Không tuyên bố tương thích tuyệt đối khi chưa xác định được cấu trúc/API.

## Bổ sung ngày 2026-10-11

Nguồn dữ liệu người dùng chỉ định là `Desktop/rc2-viet-codex-initial-release` (có bản lồng nhau giống nhau). Chỉ nhập dữ liệu có nguồn tiếng Anh đối chiếu được; giữ bản dịch hiện tại khi nguồn trùng và không đưa khóa phiên bản của nhánh cũ trở lại.

- [x] Kiểm thử và sửa `Cine mode (slow speed)` thành `Chế độ C (Tốc độ chậm)` trong XML, bộ nhớ RC/điện thoại và bảng thuật ngữ.
- [x] Nhập bộ nhớ bổ sung từ dữ liệu 1.21.10, kiểm tra cấu trúc/placeholder và ghi nguồn gốc.
- [x] Thêm phân tích manifest/DEX theo Application thực tế, chèn provider riêng tư, cấp slot DEX động; kiểm thử đổi tên lớp, slot và version.
- [x] Tạo capsule phục hồi của chính APK đầu vào, kiểm chứng round-trip và từ chối payload bị sửa.
- [x] Dùng receipt schema mới để bind source/plan/helper/signature; installer bỏ chặn số phiên bản nhưng giữ nhận dạng thiết bị, snapshot và sao lưu.
- [x] Tải/giải nén hai APK RedFly, phân tích code/tài nguyên; ghi riêng bằng chứng tĩnh, suy luận và phần chưa chạy.
- [x] Chạy suite/coverage, dựng APK thực và EXE đóng băng cục bộ, cập nhật README/changelog, đóng gói.

Ruling: Không dùng lại giới hạn hash 1.21.10 từ thư mục bổ sung vì trái với yêu cầu tự thích nghi. Không kiểm tra thiết bị theo ràng buộc của người dùng. RedFly chỉ là dữ liệu phân tích; không tự cài, thực thi, sao chép cơ chế điều khiển bay hay khóa cấp phép của bên thứ ba.

Bằng chứng cuối: `docs/adaptive-menu-verification.json`, `docs/REDFLY_ANALYSIS.md`; 1.822 tests, coverage 88,27%, 60 kiểm tra Java/payload sau rà cuối, hai dependency audit không có lỗ hổng đã biết. EXE đóng băng dựng menu bằng Java nhúng và dịch APK 99.0.1 không có bộ nhớ dịch. Thực thi/cài trên thiết bị không nằm trong lượt này.
