# RC2 r14.5 — Animation

Mở **Animation** ở góc trên cửa sổ EXE. Animation hiển thị ngay trong cửa sổ hiện tại. Bấm **← Quay lại** ở góc trên bên trái để về phần patch tiếng Việt và menu. Thiết kế đang sửa, ô nhập chưa hoàn tất và tác vụ xuất được giữ khi chuyển trang; phần xem trước tạm dừng khi quay lại. Thiết kế, xem trước và xuất gói được cả khi chưa nối RC2.

Bản r14.1 dùng thẻ và nút bo góc, khoảng cách thoáng, bảng chỉnh sửa theo nhóm; giữ màu nền tối và xanh mint. Cửa sổ chính cũng dùng cùng kiểu giao diện. Tệp thiết kế `.rc2anim` của r14 mở lại được trên bản mới.

Bản r14.2 cập nhật chữ trong khi gõ, giữ một khung xem trước liên tục và bỏ vẽ lại nút khi trạng thái không đổi. Khi không thao tác và không phát animation, khung xem trước không tự render lại. Từ r14.4, ô thiết kế nhập dở chỉ chặn thao tác xuất thiết kế đó; gói ZIP hợp lệ được chọn riêng vẫn cài được.

Bản r14.3 sửa bước đặt quyền gói sau khi truyền: ADB từ Windows có thể đổi quyền tệp thành `666`. App đặt lại chủ sở hữu `0:0` và quyền `644` cho tệp tạm do phiên đó tạo, rồi mới kiểm tra SHA-256, kích thước và quyền. Nếu còn sai lệch, thông báo chỉ rõ mục không khớp và dừng trước khi đổi cấu hình animation.

Bản r14.4 thêm **Xin lại quyền USB** tại trang chính và Animation. Khi đã chọn tay, có thể xin quyền riêng trước khi cài. Nếu đang chờ Allow mà chưa được chấp thuận sau 10 giây, app đóng phiên chờ cũ và tạo phiên mới với cùng khóa ADB; có thể bấm nút để xin lại sớm hơn. Tổng thời gian chờ mỗi lần kết nối tối đa 120 giây. Khi đã kết nối, cơ chế này dừng; app không tự ngắt phiên đang truyền hoặc đang ghi cấu hình. Hộp thoại xuất hiện hay không còn phụ thuộc trạng thái cho phép của Android trên tay; vẫn phải chọn Allow khi được hỏi.

Bản r14.5 cập nhật recipe Fly để gỡ nút ATTI, tắt GPS và điện áp từng cell pin của menu đặc biệt khỏi màn hình bay. Bản này cũng gỡ mục **Giải mã bản ghi** và cơ chế giải mã tự động, thủ công. Các chức năng thiết kế và cài animation giữ nguyên.

## Các kiểu hiệu ứng

**16 kiểu xuất hiện:** hiện ngay, mờ dần vào, hiện từng chữ, trượt từ trái, trượt từ phải, trượt từ dưới lên, trượt từ trên xuống, phóng to, nảy đàn hồi, nhiễu kỹ thuật số (glitch), quét sáng, xoay vào, sóng ký tự, bật sáng neon, lau ngang, lấy nét.

**6 chuyển động giữ lặp:** đứng yên, nhịp sáng, lơ lửng, ánh sáng lướt, xoay nhẹ, sóng ngang.

**5 mẫu:** Sci-fi nổi, kim loại nổi, neon, tối giản, công nghệ xanh. Kiểu chữ có phẳng, kim loại nổi và neon.

## Thiết kế chữ, ảnh và background

1. Chọn mẫu rồi bấm **Dùng mẫu này**, hoặc bấm **+ Mới**.
2. **+ Chữ** thêm dòng độc lập; **+ Ảnh** nhập logo/hình PNG, JPEG, WebP hoặc BMP.
3. Chọn lớp bên trái. Chỉnh nội dung, font TTF/OTF, cỡ chữ, màu chữ/ánh sáng, độ rõ, góc xoay, bề ngang và vị trí. Kéo lớp đang chọn trực tiếp trên khung xem trước để đặt vị trí.
4. Tab **Hiệu ứng**: mỗi lớp có kiểu xuất hiện, thời điểm bắt đầu, thời gian hiện và chuyển động giữ lặp riêng. Tab **Nội dung** chỉnh chữ/ảnh, diện mạo và vị trí. Có thể nhân bản, xóa và đổi thứ tự lớp.
5. Muốn GinzaTech hiện xong rồi đến DJI Modder: đặt thời điểm bắt đầu dòng dưới sau thời điểm bắt đầu cộng thời gian hiện của dòng trên. Mẫu mặc định đã làm vậy, với dòng phụ nhỏ hơn.
6. Tab **Nền**: màu phẳng, gradient hai màu hoặc ảnh nền; ảnh có căn phủ/giữ trọn.
7. Tab **Cảnh**: kích thước, FPS, thời lượng mở đầu và đoạn lặp. RC2 mặc định 1920×1080, 24 fps.
8. **Phát** hoặc kéo thanh thời gian để xem cả mở đầu và lặp.

## Nhiều thiết kế và xuất gói

- **Lưu thiết kế**, **Lưu thành…**, **Mở…**, **Nhân bản thiết kế** và thư viện bên trái hỗ trợ nhiều dự án.
- Tệp **.rc2anim** chứa cấu hình cùng ảnh/font nhập vào để mở lại. Thư viện mặc định nằm dưới LOCALAPPDATA/RC2AutoPatch/animation/projects.
- **Xuất animation** tạo ZIP Android, GIF, poster và biên bản SHA-256. Khi chọn tên ZIP, các tệp xem trước có cùng tiền tố nên không đè tệp của thiết kế khác.
- Xuất chạy nền, có tiến trình và **Hủy xuất**. Gói cũ được giữ nếu xuất thất bại hoặc bị hủy.
- Ô đường dẫn ZIP cho phép chọn hoặc dán đường dẫn tới gói animation đã có sẵn. Gói được kiểm tra nền trước khi bật nút cài, kể cả khi vừa mở lại EXE. Thay đổi thiết kế không sửa nội dung của ZIP đã chọn; muốn cài phiên bản thiết kế mới thì xuất lại hoặc chọn gói mới.
- Trước khi cài, EXE kiểm tra lại gói ZIP/PNG và tạo bản sao đã xác minh trước khi mở USB. Đường dẫn sai, tệp bị xóa hoặc gói không hợp lệ sẽ không được cài.
- Giới hạn xuất: tổng thời gian tối đa 15 giây, tối đa 30 fps, đoạn lặp tối đa 256 MiB ảnh giải mã, ZIP tối đa 512 MiB. Khi vượt giới hạn, giảm đoạn lặp/FPS/kích thước. Nền đen cho phép cắt vùng ảnh trống để tiết kiệm.

## Cài và khôi phục trên RC2

1. Mở **Kết nối RC2 & cài đặt**, nối đúng tay, **Quét lại**, chọn serial và xác nhận máy bay đã hạ cánh, động cơ dừng. Có thể thu gọn mục này khi thiết kế để khung xem trước rộng hơn. **Xin lại quyền USB** hoạt động trước khi cài hoặc khi đang chờ Allow.
2. Xuất dự án hoặc chọn đường dẫn tới gói ZIP có sẵn. Khi kiểm tra gói hoàn tất, bấm **Cài lúc khởi động** hoặc **Cài lúc tắt máy**. App nhớ đường dẫn gói hợp lệ đã chọn và kiểm tra lại khi mở lần sau.
3. Chọn Allow USB debugging trên tay nếu được hỏi. EXE kiểm tra đúng RC331, root và thư viện DJI đã được khảo sát.
4. EXE chép vào vùng dữ liệu, đặt và kiểm tra quyền sau khi chép, đối chiếu SHA-256, lưu cấu hình trước đó và thay đúng property boot/shutdown. Hai loại có biên nhận riêng. Bấm **Quay lại** để theo dõi nhật ký và tiến trình ở trang chính.
5. **Khôi phục khởi động / Khôi phục tắt máy** quay lại cấu hình trước khi EXE cài, hoặc cấu hình mặc định khi phù hợp. Không ghi đè tùy biến không xác định của công cụ khác.
6. EXE không tự reboot, không mở khóa bootloader và không ghi đè /product. Cấu hình được cài thành công cần quan sát thêm ở lần bật/tắt máy thật.

Cài đặt chỉ hỗ trợ thư viện DJI có SHA-256 đã được xác minh trên RC331/V14. Firmware khác cần khảo sát lại.

## Kiểm chứng

Đã kiểm tra bộ dựng, dự án di động, ảnh/chữ/nền, giao diện Tk thật, ZIP và luồng cài/khôi phục bằng ADB giả lập. EXE được kiểm tra khởi chạy và xuất ngoại tuyến riêng. Bản r14.2 còn có bài thử gõ liên tục và giữ nút đứng yên trên chính EXE đã đóng gói. Cơ chế boot GinzaTech từng được cấu hình trên tay, nhưng chưa coi đó là phép thử mọi hiệu ứng và nút cài của các bản r14 trên thiết bị thật.

Bản r14.3 đạt 187 kiểm thử nguồn; 102 kiểm thử backend cài đặt cũng đạt khi chạy mã lấy trực tiếp từ EXE. Kiểm tra giao diện trên EXE xác nhận ba lượt đi/về giữ cùng cửa sổ Windows và bản nháp, không mở USB, không render khi trang Animation ẩn. Bài thử nhập chữ giữ phản hồi trung vị khoảng 35 ms, không vẽ lại nút khi để yên. Lỗi quyền `666` được tái hiện bằng ADB giả lập dựa trên nhật ký RC2 đã lưu. Bản r14.3 chưa cài thử lại lên RC2 thật.

Bản r14.4 đạt 385 kiểm thử nguồn. Thêm 187 kiểm thử chạy mã backend lấy từ EXE với USB/ADB giả lập; mã các module này được đối chiếu giữ nguyên trong bản đóng gói cuối. Các bài thử trên chính EXE xác nhận chọn ZIP có sẵn, kiểm tra trước cài, nhớ và kiểm tra lại đường dẫn sau khi tạo lại editor, nút xin quyền USB chung và bố cục cửa sổ. Kiểm thử mô phỏng đồng hồ xác minh mốc 10 giây, bấm xin lại, hủy, giới hạn tổng 120 giây và không ngắt phiên đã được cấp quyền. Trên máy dùng MSIX, đường dẫn lưu thiết lập được đưa về thư mục vật lý để tránh lỗi đổi tên qua hai ổ đĩa. Bản r14.4 chưa kiểm thử xin quyền hoặc cài lên RC2 thật.
