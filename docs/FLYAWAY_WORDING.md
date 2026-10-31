# Bản dịch Báo mất flycam — 23/10/2026

Revision nguồn cũ: `r14.5-flyaway-firmware-wording`. Bản 1.21.16 được đối chiếu lại trong [r14.6](FLY_12116.md).

Đổi nhãn **Aircraft Flyaway** từ “Máy bay đang bay.” thành **Báo mất flycam**. Rà và sửa 30 chuỗi trong toàn bộ luồng: điều khoản, xác nhận đã mất, cảnh báo ngừng sử dụng, trạng thái xử lý, kết quả gửi báo cáo, liên hệ hỗ trợ, quyền lợi DJI Care và các mô tả liên quan đến liên kết thiết bị/nhật ký.

Hai thông báo “New firmware available” dùng **Phần mềm mới đã sẵn sàng**, thay cho cách dịch “phần mềm cứng”. Tổng cộng 32 tên tài nguyên được rà trong đợt sửa này.

Một số nhãn sau khi sửa:

| Mục | Bản dịch |
| --- | --- |
| Aircraft Flyaway | Báo mất flycam |
| Confirm Flyaway Aircraft for Reporting | Xác nhận báo mất flycam |
| Confirmed lost | Xác nhận đã mất |
| The Flyaway Report is in progress... | Đang xử lý báo cáo mất flycam… |
| Flyaway aircraft report confirmed | Đã xác nhận báo cáo mất flycam |
| Flyaway Service | Dịch vụ hỗ trợ mất flycam |

Các điều kiện và hậu quả của văn bản nguồn được giữ tại từng màn: cấm sử dụng/bay sau khi xác nhận; điều khoản về hủy báo cáo khi chưa sử dụng quyền lợi; chuyển quyền sở hữu sang DJI khi đã sử dụng. Giữ thương hiệu DJI Care/DJI Care Refresh, các mục thông tin thu thập và placeholder liên kết `%1$s`. Đây là bản dịch văn bản trong APK nguồn đã hỗ trợ, không phải diễn giải chính sách DJI mới.

Ba chuỗi Dolly Zoom “Fly away first”, “Fly Away Before Zooming” và mô tả bay ra xa trước khi zoom giữ nguyên nghĩa thao tác quay phim.

## Nguồn và bản dựng

- Bản dịch đã rà: `rc2vi/flyaway_wording.py`.
- Catalog và bộ nhớ dịch: `assets/translation/catalog.json`, `memory/phone.json`, `wording.json`; cập nhật manifest/hash pin đồng bộ. Bảng sửa câu được ưu tiên trước bộ nhớ dịch cũ.
- XML RC2: bốn qualifier `values`, `values-en`, `values-en-rUS`, `values-vi` trong `translation/review-round2/overlay/res`.
- Bảng tài nguyên cho hai profile cũ: `assets/auto12110/vietnamese.arsc`, sửa cả 128 cấu hình của 32 chuỗi. Pin tại `rc2vi/auto_patch.py`. Bản 1.21.16 có bảng và pin riêng trong `assets/auto12116` và `rc2vi/fly_versions.py`.
- Luồng này không dựng lại APK Android điện thoại; bản EXE RC2 nhúng tài nguyên cho hai profile RC 1.21.8/1.21.10.

Script cập nhật kiểm mọi đầu ra trước khi ghi, lưu bản cũ và báo cáo vào thư mục mới:

```powershell
python -X utf8 scripts/update_flyaway_translation.py --work local-artifacts/flyaway-wording-new
python scripts/build_auto_patch_exe.py --build-root local-artifacts/flyaway-build-new
```

Giữ bản cũ để kiểm sự khác biệt. Script kiểm semantic toàn bộ compiled table và từ chối thay đổi tài nguyên ngoài 32 tên đã rà. Dùng escape Android để giữ xuống dòng, dấu nháy và hợp đồng định dạng khi chuyển giữa XML/canonical text/compiled table.

Hai APK r14.5 cũ được kiểm độc lập trước khi cập nhật tài nguyên; chỉ thêm đúng cặp hash APK/signer đã đạt vào danh sách cho phép nâng cấp. Không mở rộng cho APK không rõ nguồn.

Kết quả của đợt sửa chữ r14.5: **496 kiểm thử nguồn đạt**. Chính EXE qua `--self-test` và dựng lại thành công từ hai APK r14.5 đã kiểm trên PC cho Fly RC **1.21.8 và 1.21.10**. Mỗi APK có đủ 32 chuỗi đúng ở 633 cấu hình tương ứng; AAPT2 xác nhận giữ nguyên ID tài nguyên. DEX, thư viện native và manifest khớp từng byte với APK r14.5 trước đợt sửa chữ; chữ ký và phục hồi stock đã được kiểm trong luồng dựng. Chưa cài đợt sửa chữ này lên RC 2.

Báo cáo cục bộ ở `local-artifacts/flyaway-wording-20261023`: `prior-r145-verified.json`, báo cáo cập nhật, `source-tests.xml`, báo cáo build EXE và kiểm chứng bằng EXE. Kiểm tra trên PC không thay thế cài và xem trực tiếp trên tay. Không gửi báo mất thật trong quá trình kiểm tra.
