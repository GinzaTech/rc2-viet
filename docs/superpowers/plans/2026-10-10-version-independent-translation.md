# Việt hóa không khóa số phiên bản DJI Fly

Yêu cầu: EXE cho phép Việt hóa các phiên bản ngoài 1.21.8. Người dùng không cho phép kết nối/kiểm tra trên thiết bị ở lượt này; chỉ sửa, build và kiểm chứng cục bộ.

- Giữ đường nhanh cho các APK và gói RRO đã biết. Các APK khác dùng đường thích ứng: lấy APK đang cài, đọc tài nguyên, chọn bản dịch khớp nguồn và kiểu dữ liệu, dựng/ký gói RRO riêng. Không thay APK DJI Fly để Việt hóa.
- Không dùng số phiên bản hoặc hash allowlist để từ chối bản dịch thích ứng. Hash vẫn dùng để chống đổi APK giữa lúc lấy, dựng và cài.
- Gói thích ứng chỉ chứa tài nguyên, tên package gắn với nguồn/từ điển/chứng thư để không ghi đè gói do PC khác ký. Khi bật gói mới phải tránh để gói cũ áp dụng đồng thời; khi lỗi khôi phục trạng thái overlay trước đó.
- Dùng APKtool, AAPT2, framework và Java từ toolchain đã nhúng, không yêu cầu cài SDK/Java. Từ điển chỉ tái dùng bản dịch khi văn bản nguồn, kiểu, thứ tự mảng, số nhiều và placeholder phù hợp. Câu mới/đổi nghĩa giữ nguyên và được thống kê; không tuyên bố dịch đầy đủ mọi bản tương lai.
- Tab RC 2 giữ yêu cầu RC331/Android11/root; tab điện thoại giữ cấu trúc idmap/Android đã hỗ trợ. Phạm vi thay đổi là phiên bản DJI Fly, không tự mở rộng firmware/Android hay patch menu/HUD phụ thuộc mã máy.
- Kiểm chứng cục bộ: selector, tài nguyên hỏng, đổi thiết bị/APK, rollback overlay; build tài nguyên với APK RC1.21.8 và APK Android1.21.12 có sẵn. Không ADB/ARTEMIS hoặc tác vụ thiết bị.
- Build EXE mới, cập nhật hướng dẫn/changelog/metadata và thay bản ở các đường dẫn người dùng đang dùng. Ghi rõ chưa kiểm tra thực tế trên thiết bị theo yêu cầu.
