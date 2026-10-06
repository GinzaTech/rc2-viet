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
| DJI SystemUI tham chiếu | Bản trích từ tay đã phân tích | APK gốc DJI ở artifacts/reference chỉ để lưu dấu vết phân tích; không phải bản mod hoặc bản hệ thống được RC2 Việt cung cấp để cập nhật thiết bị. |
| Tài nguyên tiếng Việt DJI Fly | reviewed5 / versionCode 7 | Bản dịch/tài nguyên đích là tài liệu làm việc với DJI Fly 1.21.8; không cấp lại quyền đối với mã/tài nguyên DJI. |

Source của FreeFCC và Lawnchair được liên kết đúng tag thay vì trỏ một bản HEAD có thể đổi. Các APK upstream không được sửa hoặc ký lại. SHA256 và phân loại từng APK ở docs/APK_INVENTORY.json.

Dự án chưa lựa chọn một giấy phép nguồn mở riêng cho mã RC2 Việt. Không áp dụng giấy phép bên thứ ba cho toàn bộ repository theo suy đoán.
