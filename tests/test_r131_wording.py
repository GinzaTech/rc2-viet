from scripts.update_embedded_translation import WORDING


def test_initialization_wording_and_gmail_label_are_reviewed():
    assert WORDING['account_email_transfer_register_input_hint_title'] == 'Nhập Gmail'
    assert WORDING['account_guide_input_box_hint_subtitle'] == 'Nhập số điện thoại hoặc Gmail'
    assert WORDING['account_guide_subtitle'] == 'Nhập số điện thoại hoặc Gmail'
    assert WORDING['ABC_fly_launch_download_resource_success_initial_success_starting_title'] == (
        'Đã khởi tạo xong dữ liệu tài nguyên. Đang mở DJI Fly…')
    assert WORDING['ABC_fly_launch_resource_lack_quit_download_dialog_content'].endswith(
        'thoát và dừng tải xuống không?')
