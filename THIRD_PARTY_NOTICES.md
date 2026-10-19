# Thành phần bên thứ ba

RC2 Việt tập hợp công cụ và APK từ nhiều tác giả. Việc đưa tệp vào repository không đổi giấy phép, tác giả hoặc chữ ký của tệp đó.

| Thành phần | Phiên bản | Nguồn và giấy phép |
| --- | --- | --- |
| FreeFCC | 1.5.5 | [Mã nguồn cùng phiên bản](https://github.com/doesthings/FreeFCC/tree/v1.5.5), [giấy phép upstream](https://github.com/doesthings/FreeFCC/blob/v1.5.5/LICENSE); bản sao ở [docs/FREEFCC_LICENSE.txt](docs/FREEFCC_LICENSE.txt). |
| Lawnchair | 15 Beta 3 | [Mã nguồn cùng phiên bản](https://github.com/LawnchairLauncher/lawnchair/tree/v15.0.0-beta3.0), [giấy phép upstream](https://github.com/LawnchairLauncher/lawnchair/blob/v15.0.0-beta3.0/LICENSE.txt); bản sao ở [docs/LAWNCHAIR_LICENSE.txt](docs/LAWNCHAIR_LICENSE.txt). |
| ADB / Android Platform Tools | 37.0.0 | [Trang tải Google](https://developer.android.com/tools/releases/platform-tools); thông báo đi kèm ở [docs/ANDROID_PLATFORM_TOOLS_NOTICE.txt](docs/ANDROID_PLATFORM_TOOLS_NOTICE.txt). |
| PyInstaller | 6.16.0 | [Nguồn và giấy phép PyInstaller](https://github.com/pyinstaller/pyinstaller/blob/v6.16.0/COPYING.txt). |
| Python | 3.11 | [Python license](https://docs.python.org/3.11/license.html); runtime được PyInstaller đóng gói. |
| Tcl/Tk | Theo Python Windows runtime | [Tcl/Tk license](https://www.tcl.tk/software/tcltk/license.html), dùng qua Tkinter. |
| Microsoft Build of OpenJDK | 17.0.20, runtime tối thiểu | [Microsoft OpenJDK](https://learn.microsoft.com/java/openjdk/); GPLv2 với Classpath Exception. Thông báo/license theo module được giữ trong `java/legal/` của `assets/hud/toolchain.zip`. |
| APKtool | 2.12.1 | [iBotPeaches/Apktool](https://github.com/iBotPeaches/Apktool), Apache2.0; LICENSE và NOTICE trong `licenses/` của toolchain. |
| Android Build Tools | 36.1.0, apksigner và zipalign | [Android SDK Build Tools](https://developer.android.com/tools/releases/build-tools); `licenses/ANDROID_BUILD_TOOLS_NOTICE.txt` trong toolchain giữ thông báo cho các thành phần được nhúng. |
| DJI SystemUI tham chiếu | Bản trích từ tay đã phân tích | APK gốc DJI ở artifacts/reference chỉ để lưu dấu vết phân tích; không phải bản mod hoặc bản hệ thống được RC2 Việt cung cấp để cập nhật thiết bị. |
| Tài nguyên tiếng Việt DJI Fly | reviewed5 / versionCode 7 | Bản dịch/tài nguyên đích là tài liệu làm việc với DJI Fly 1.21.8; không cấp lại quyền đối với mã/tài nguyên DJI. |

Source của FreeFCC và Lawnchair được liên kết đúng tag thay vì trỏ một bản HEAD có thể đổi. Các APK upstream không được sửa hoặc ký lại. SHA256 và phân loại từng APK ở docs/APK_INVENTORY.json.

HUD sửa APK DJI Fly lấy từ tay của người dùng. EXE không chứa toàn bộ APK DJI Fly gốc hoặc khóa riêng. Template phục hồi nhỏ chứa header/đuôi archive và dữ liệu gốc của AndroidManifest.xml/classes.dex từ APK1.21.8 đã pin; phần còn lại được đọc từ APK trên tay. Thành phần đó vẫn thuộc DJI, không được cấp lại quyền bằng license của RC2 Việt hay Java/APKtool/SDK. Toolchain có thông báo giấy phép; receipt chỉ ghi hash/chứng thư công khai, không ghi mật khẩu hoặc khóa.

LED handler0.4.0 là triển khai Java riêng, đối chiếu trường giao thức từ [led_off.json](https://github.com/doesthings/FreeFCC/blob/v1.5.5/app/src/main/assets/profiles/led_off.json), [led_on.json](https://github.com/doesthings/FreeFCC/blob/v1.5.5/app/src/main/assets/profiles/led_on.json) và mô tả CRC/transport trong source FreeFCC1.5.5. Không nhúng source Kotlin của FreeFCC vào DJI Fly; APK FreeFCC riêng vẫn giữ nguyên tác giả/license AGPL3 upstream. Air3S LED được README upstream ghi chưa thử.

Đường LED0.4 nêu trên là lịch sử, đã loại khỏi runtime sau báo cáo mất kết nối. Từ0.6, LED dùng SDK có readback; Air3S trả lỗiSDK -9 khi đọc nên chưa ghi LED theo đường này.

Các lớp NativeRadio.java, RadioProtocol.java, RadioTransport.java và tests radio mang SPDX AGPL-3.0-only, ghi nguồn lệnh FreeFCC1.5.5/commit597157bd52120dfeb9677f79a8ad46b6027ce8dc. License ở docs/FREEFCC_LICENSE.txt; source ở android-hud/src và android-hud/test. Lệnh FCC/khôi phục vùng gốc nhúng trực tiếp vào helper, không cần APK FreeFCC riêng. EXE không nhúng APK Fly gốc.

Dự án chưa lựa chọn một giấy phép nguồn mở riêng cho phần mã RC2 Việt còn lại. Không áp dụng giấy phép bên thứ ba cho toàn bộ repository theo suy đoán.


## Engine dịch cục bộ0.8.0

- [Helsinki-NLP/opus-mt-en-vi](https://huggingface.co/Helsinki-NLP/opus-mt-en-vi), revision `989c9fb9ec63987901022baf0182dcec3e149be6`, Apache2.0; chuyển đổi tại máy build sang CTranslate2 int8.
- [Helsinki-NLP/opus-mt-zh-vi](https://huggingface.co/Helsinki-NLP/opus-mt-zh-vi), revision `67ea2dbfbaf13a16772a40346d3d72b59e591443`, Apache2.0; chuyển đổi sang CTranslate2 int8, không dùng prefix `>>vie<<` của model Anh.
- CTranslate2 4.8.2 (MIT), SentencePiece 0.2.1 (Apache2), NumPy 2.4.6 và các thư viện runtime có license/provenance đầy đủ trong `artifacts/translation-engine/<id>/LICENSE.runtime.txt`, `LICENSE.model.txt`, `provenance.json`.

Hai model chạy CPU trên PC; văn bản không được gửi tới dịch vụ dịch online. Dịch máy chưa được xác nhận hoàn hảo về ngữ nghĩa; chương trình kiểm tra cấu trúc và chặn lỗi đã nhận diện, không coi test host là chứng minh an toàn bay.
