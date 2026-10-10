# Chi tiết gói tiếng Việt DJI Fly

## Từ 0.8.0: bộ dựng theo APK đích

Luồng áp dụng luôn đọc toàn bộ nguồn tài nguyên của APK hiện tại. Không cần một APK Việt hóa hoặc catalog của phiên bản cố định. Các gói/memory đã rà được so sánh về nội dung và contract; mâu thuẫn không tự chọn bừa. Không tìm được bản dịch phù hợp thì engine CPU bổ sung từ nguồn Anh hoặc Trung. Bộ nhớ có thể vắng mặt hoàn toàn.

Báo cáo phân biệt `reviewed`, `machine`, `preserved` và `unresolved`. Chỉ khi `complete=true`, `unresolved=0` và `reviewed+machine=eligible_total` mới dựng/cài. `preserved` là tài nguyên kỹ thuật hoặc tham chiếu được giữ nguyên, không được che mục giao diện chưa dịch bằng nhãn này. `machine_meaning_verified=false` nói rõ kiểm tra cấu trúc không chứng minh ngữ nghĩa máy dịch hoàn hảo.

Engine/model nằm riêng trong `artifacts/translation-engine/<id>` và được kiểm chứng theo `assets/translation/engine.json`. Portable đặt payload ở `translation-engine/<id>` cạnh EXE. EXE đơn lẻ tự tải payload đã pin nếu chưa có; suy luận luôn chạy trên PC. Hai model nguồn OPUS-MT là [en-vi](https://huggingface.co/Helsinki-NLP/opus-mt-en-vi) và [zh-vi](https://huggingface.co/Helsinki-NLP/opus-mt-zh-vi), có provenance/license kèm payload. Không cần dịch vụ online hoặc khóa API.

`assets/translation/memories.json` liệt kê các memory tùy chọn. Thiếu memory thì dùng engine; memory bị thay đổi trái hash thì báo lỗi. Cache output gắn với source APK, các memory thực sự có mặt, engine, pipeline và profile Android. Gói partial0.7 không được tái dùng/cài như bản hoàn chỉnh0.8.

Các phần dưới mô tả lịch sử0.7 và gói cố định; đường cài RRO cố định không còn được chọn từ giao diện0.8.


## Từ 0.7.0: không khóa số phiên bản DJI Fly

Nút Bật / cập nhật tiếng Việt nhận các phiên bản DJI Fly bất kỳ có cấu trúc APK nguyên khối đọc được trên nền tảng đang hỗ trợ. App lấy APK từ đúng thiết bị, kiểm tra nguồn không đổi, chọn bản dịch theo tài nguyên, dựng và ký RRO riêng rồi bật/đọc lại. APK DJI Fly không bị thay hoặc ký lại trong luồng Việt hóa.

- Nguồn từ điển: `assets/translation/catalog.json`, 11.141 mục dùng lại từ XML reviewed6 và nguồnRC1.21.8. Selector so sánh kiểu/tên/văn bản gốc, thứ tự mảng, quantity của plurals, placeholder và markup. Bảy ứng viên phần trăm mơ hồ được loại bảo thủ khi dựng từ điển.
- Không dịch đoán câu mới. App báo số tài nguyên đã dịch và giữ nguyên; số lượng này không phải coverage màn hình UI. Không cần mô hình lớn, dịch vụ dịch online hay API key.
- Java/AAPT2/framework/APKtool đã nhúng. Java bổ sung module desktop cho bộ giải mã tài nguyên. Khóa RRO tạo riêng trên PC và được Windows DPAPI bảo vệ.
- RRO mới có tên `local.dji.fly.vi.auto.r<source>c<catalog>s<signer>`. Không ghi đè gói cùng tên khác hash. Gói cũ chỉ được tắt trong giao dịch bật gói mới; lỗi đọc lại sẽ phục hồi cache và trạng thái trước đó.
- Giữ yêu cầu RC331/Android11/root và điện thoại Android15/root tương ứng hai định dạng idmap đã xử lý. Không tự root, không bỏ qua Allow USB debugging.
- Kiểm chứng cục bộ: Fly1.21.8 có11.141/11.923 tài nguyên khớp, Fly1.21.12 có11.141/11.925; cả hai dựng, căn chỉnh và ký gói không có DEX/native thành công. Không thực hiện kiểm tra trên thiết bị ở lượt cập nhật này theo yêu cầu người dùng.

Phần dưới mô tả gói dựng sẵn dành cho nguồn đã biết; đây là đường nhanh, không còn là danh sách khóa phiên bản của luồng Việt hóa thích ứng.


## Tài nguyên, không thay mã DJI Fly

Mục tiêu là `dji.go.v5` 1.21.8, code 3115809 và hash APK đã pin. Gói thay thế là `local.dji.fly.vietnamese`, reviewed6/code 8, SHA256 `3cad71fd887edab20b5ff89a742766766e9dddf2ed45546ad05c42e66f1de048`.

APK này có manifest, bảng tài nguyên và dữ liệu XML biên dịch; `hasCode=false`, không DEX và không thư viện native. APK DJI Fly đích vẫn dùng chữ ký DJI. Cơ chế RRO được Android mô tả tại [AOSP](https://source.android.com/docs/core/runtime/rros); phần xử lý cache dưới đây là cách đặc thù đã dùng trên tay, không phải một trình cài RRO chuẩn cho mọi firmware.

## Nguồn và cấu hình ngôn ngữ

Thư mục `translation/review-round2/overlay/res` có strings.xml, arrays.xml, plurals.xml trong `values`, `values-en`, `values-en-rUS`, `values-vi`. Cùng bản dịch được đưa vào những qualifier này để khớp lúc DJI Fly chọn locale khác tiếng Việt. Thay một qualifier riêng có thể để tài nguyên đích ở qualifier cụ thể hơn thắng khi Android chọn tài nguyên.

Manifest overlay có targetPackage `dji.go.v5`, targetName `DJIFlyLocalTranslation`, isStatic false, priority 999 và application hasCode false. Gói cài độc lập nên có thể tắt bằng OverlayManager mà không gỡ DJI Fly.

Các dữ liệu làm việc được giữ trong repository:

- XML cuối reviewed6, manifest và báo cáo summary/changes.
- Gói XML nền versionCode 3 ở `translation/overlay-full/res/values-vi` để đối chiếu lượt rà.
- `localize_resources.py`: tách văn bản/biến được bảo vệ và kiểm tra định dạng.
- `review-round2/review.py`: ghép câu đã rà, thuật ngữ và dữ liệu kỹ thuật theo các điều kiện giới hạn.
- Bảng TSV và JSON sửa câu, `user_wording.py` và 9 kiểm thử quy tắc rà.

Không có mô hình dịch lớn hoặc APK DJI Fly gốc trong repository này. Những scripts tạo lại lượt rà từ đầu cần bộ XML gốc được trích từ đúng DJI Fly đặt ở `translation/fly-1.21.8-source/res`; `translation-catalog.json` lưu danh mục đã lập nhưng không thay thế hoàn toàn cây XML nguồn mà `entries()` đọc. Build RRO từ XML cuối không cần chạy lại mô hình dịch hoặc lượt rà.

## Bảo vệ ý nghĩa và định dạng

Đợt dịch nháp từng sai ngữ cảnh và chia nhỏ câu, nên đã rà câu/cụm đầy đủ. Ví dụ sửa Shutter thành tốc độ màn trập, Copied thành đã sao chép, Timed Shot thành chụp theo khoảng thời gian; phân biệt nhật ký bay, ghi âm và ghi hình.

Các bộ kiểm tra giữ placeholder có thứ tự, số, đơn vị, mã, xuống dòng và thẻ. Không dịch API key/identifier kỹ thuật hoặc giữ một ứng viên khi không kiểm tra được ý nghĩa. Dữ liệu mã quốc gia và cubic-bezier được trả về tài nguyên gốc. Mảng và plurals giữ cấu trúc; không ghép câu mới từ những mệnh đề chưa có bản dịch đã kiểm tra.

Ngoại lệ `Metric (km)` → `Hệ kilomet(Km)` được giới hạn đúng nhãn theo yêu cầu; không cho phép tùy tiện đổi `5 km` thành `5 Km`. Các câu do chủ tay yêu cầu được ghi trong user_wording.py. Cách diễn đạt “vị trí ban đầu” là lựa chọn của bản này, không chứng minh Home Point của mọi chế độ luôn cố định.

Summary cuối: 11.923 mục quét, 11.148 mục hoạt động, 4.133 mục thay đổi so với nền, 3.866 thay đổi theo câu/cụm, 263 thay đổi thuật ngữ, 17 mục kỹ thuật loại khỏi overlay. Các loại số đếm không phải một phân hoạch cộng đúng của toàn bộ thay đổi; một số sửa ngữ cảnh/định dạng được xử lý riêng. Danh sách pending/rejected của lượt rà hiện bằng 0. Không coi đó là coverage UI 100% hoặc bằng chứng đã bay thử.

## Luồng cài trong app

1. Đọc model, device, SDK và `id`. Yêu cầu RC2/rc331, SDK 30 và uid 0 có sẵn.
2. Đọc version/code/path/hash APK DJI Fly. Không gỡ hoặc cài DJI Fly.
3. Kiểm tra gói RRO đã có. Hash hiện tại đúng + state enabled + mẫu tiếng Việt đúng thì kết thúc chỉ đọc.
4. Trước mọi thay đổi tài nguyên, kiểm tra activity. Nếu Fly không ở trang chủ đã biết, hoặc không đọc được foreground, dừng.
5. Nếu thiếu hoặc gói cũ thuộc danh sách hash đã biết, push APK và cài `pm install -r --user 0`, đọc lại path/hash. APK không rõ không bị thay thế.
6. Tạo idmap, kiểm tra/sửa tiêu đề, lưu bản cache trước đó, đưa cache vào đúng đường dẫn và metadata.
7. Bật RRO cho user 0, đọc state và mẫu `homepage_connect_drone_btn`.
8. Nếu kiểm tra thất bại, tắt RRO và thử khôi phục cache; nếu phục hồi cũng lỗi, báo rõ cả lỗi phục hồi.

## idmap Android 11 v4 đã dùng

Lệnh tạo ánh xạ, với đường dẫn được xác định/kiểm tra từ PackageManager:

```sh
idmap2 create --target-apk-path <DJI_FLY_APK> \
  --overlay-apk-path <RRO_APK> --idmap-path <STAGING_MAP> \
  --policy public --ignore-overlayable
```

Đây là lệnh minh họa **bên trong shell RC 2**. Không thay các placeholder bằng đường dẫn đoán. App thực hiện qua phiên ADB của đúng tay.

`approve_idmap()` trong core.py kiểm tra:

| Thành phần | Điều kiện |
| --- | --- |
| Độ dài | Ít nhất 537 byte. |
| Magic/version | `0x504d4449`, version 4. |
| Policy và cờ | Policy public = 1, enforce ban đầu = 0. |
| Target path | Chuỗi NUL-terminated 256 byte ở offset 21 khớp path DJI Fly đã chọn. |
| Overlay path | Chuỗi NUL-terminated 256 byte ở offset 277 khớp path RRO đã chọn. |
| Đường dẫn APK | Chỉ đường dẫn `/data/app/...apk` hợp lệ, không traversal. |

Sau khi đạt, app đổi **byte offset 20** từ 0 sang 1. Dữ liệu ánh xạ được tạo với `--ignore-overlayable`; việc đổi cờ tiêu đề để cache được chấp nhận là can thiệp đặc thù cơ chế enforcement, không làm DJI Fly tự khai báo cho phép overlay và không phải thủ tục chuẩn của AOSP.

File cache đích có dạng `/data/resource-cache/<overlay path đổi / thành @>@idmap`; owner root:system, mode 644 và restorecon. Không ghi /system hoặc sửa jar/APK framework. Cache phụ thuộc đường dẫn cài, APK và phiên bản; không sao chép một idmap từ tay này sang tay khác hoặc dùng với APK cập nhật.

## Ảnh hưởng và giới hạn

Không đổi mã thực thi giảm phạm vi thay đổi so với ký lại DJI Fly, nhưng tài nguyên vẫn có thể ảnh hưởng ứng dụng và quyết định của người đọc. Sai biến/đơn vị/ý nghĩa vẫn có rủi ro; không khẳng định “ổn định tuyệt đối”. Các cổng kiểm tra và bản dịch đã rà không thay thế thử nghiệm mọi cảnh báo, máy bay hoặc tình huống bay.

Nội dung web, chuỗi sinh trong native/online hoặc tài nguyên không khớp qualifier/name có thể còn tiếng Anh. Nếu DJI Fly đổi hash/version, cần trích/rà/build và kiểm chứng riêng, không chỉ tắt kiểm tra hash.

Tắt bản dịch qua GUI hoặc, khi đã có shell đúng RC 2, `cmd overlay disable --user 0 local.dji.fly.vietnamese`, rồi mở lại Fly lúc không bay để màn hình đọc lại tài nguyên. Tắt RRO không phải tắt USB debugging.
