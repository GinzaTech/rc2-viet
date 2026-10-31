import sys

import pytest

from rc2vi.animation_package_ui_check import run_package_ui_check


@pytest.mark.skipif(sys.platform != 'win32', reason='Native HWND screenshots require Windows.')
def test_existing_package_flow_uses_real_validator_but_no_usb(tmp_path):
    report = run_package_ui_check(tmp_path)
    assert report['status'] == 'PASS', report['errors']
    for field in ('single_window', 'existing_zip_validated', 'install_without_fresh_project',
                  'invalid_form_does_not_block_zip', 'fresh_validation_before_install',
                  'back_reopen_path_preserved', 'restart_path_remembered', 'restart_revalidated',
                  'missing_zip_disabled', 'invalid_zip_disabled', 'usb_request_button_present',
                  'usb_request_callback_shared', 'controls_inside_window'):
        assert report[field], field
    assert len(report['install_callback_calls']) == 1
    assert report['usb_request_callback_calls'] == 1
    assert not report['usb_opened'] and report['usb_open_attempts'] == report['dialog_attempts'] == 0
    assert report['screenshot']['capture_mode'] == 'HWND'
