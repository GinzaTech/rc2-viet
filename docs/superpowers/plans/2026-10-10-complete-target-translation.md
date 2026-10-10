# Dựng bản dịch từ APK đích, không phụ thuộc gói Việt hóa cố định

Yêu cầu sửa lại: kiểm tra toàn bộ nguồn dịch có sẵn với APK đích, dịch bổ sung mục còn thiếu, dựng một gói hoàn chỉnh cho APK đó. Không dùng gói dựng sẵn hay tên phiên bản làm điều kiện. Không kiểm tra/cài trên thiết bị theo yêu cầu đã có. Tiếp tục build, commit và push khi hoàn tất.

1. Bộ dựng luôn đọc APK đích. Kho bản dịch đã rà chỉ là bộ nhớ tùy chọn; so khớp theo nguồn/ngữ cảnh/kiểu và contract, hỗ trợ thay tên resource. Nguồn mâu thuẫn không được tự chọn bừa.
2. Phân loại rõ văn bản cần dịch, mục kỹ thuật phải giữ nguyên, tham chiếu và cấu trúc. Dùng máy dịch Anh→Việt CPU cục bộ cho văn bản chưa có. Bảo toàn định dạng, placeholder, số/đơn vị, tên sản phẩm, markup/mảng/plurals.
3. Chỉ xuất trạng thái hoàn chỉnh khi mọi mục đủ điều kiện đã có đầu ra hợp lệ, các tham chiếu được giải quyết và không còn lỗi. Nếu model thất bại/contract sai thì giữ báo cáo, không đưa một RRO thiếu vào thiết bị. Hoàn chỉnh cấu trúc không đồng nghĩa bản dịch máy hoàn hảo về ngữ nghĩa.
4. Dùng model OPUS-MT en-vi đã có (revision pin) và CT2 int8. Bộ chạy độc lập không yêu cầu Python trên máy người dùng. Tệp model/runtime được quản lý theo hash, đặt cạnh bản portable hoặc tự tải từ repo khi chưa có; văn bản APK không gửi tới dịch vụ dịch online.
5. Loại đường nhanh dùng RRO đã dựng sẵn khỏi thao tác Việt hóa của cả hai tab; giữ nhận diện gói cũ chỉ để tắt/phục hồi. Mỗi output có khóa cache phụ thuộc nguồn, bộ nhớ, engine và profile, kiểm chứng ký/đọc lại như trước.
6. Kiểm chứng source và EXE bằng APK có sẵn, thêm ca thay tên, thêm câu chưa có trong bộ nhớ và dựng với bộ nhớ rỗng. Không dùng ADB/ARTEMIS trên thiết bị.
7. Cập nhật tài liệu, provenance, kiểm thử, EXE, portable và GitHub; chỉ báo mức đã kiểm chứng thực tế.


## Kiểm chứng thực hiện

- Đã thêm engine Anh/Trung→Việt, model/runtime theo hash, không truyền văn bản ra mạng.
- Hai APK thật dựng/ký đủ các mục đủ điều kiện; APK giả lập không memory cũng dựng/ký thành công từ EXE.
- EXE không chứa hai APK RRO dịch cũ; hai wrapper luôn chọn bộ dựng thích ứng.
- Full source suite1.794 ca đạt, coverage89,17%; không kiểm tra thiết bị.
- Báo cáo chi tiết: `docs/complete-translation-verification.json`.
