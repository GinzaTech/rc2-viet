import sys

import pytest

from rc2vi.navigation_ui_check import run_navigation_check


@pytest.mark.skipif(sys.platform != 'win32', reason='Native HWND screenshots require Windows.')
def test_same_window_navigation_preserves_unfinished_draft_without_usb(tmp_path):
    report = run_navigation_check(tmp_path)
    assert report['status'] == 'PASS', report['errors']
    assert report['single_window'] and report['back_button_present']
    assert report['roundtrips'] == 3
    assert report['editor_reused'] and report['draft_preserved'] and report['invalid_draft_preserved']
    assert report['playback_paused_on_back'] and report['hidden_preview_renders'] == 0
    assert report['usb_opened'] is False and report['usb_open_attempts'] == 0
    assert report['dialogs_opened'] == 0 and report['dialog_attempts'] == 0
    assert report['screenshots']['animation']['hwnd'] == report['screenshots']['patch']['hwnd']
    assert report['screenshots']['animation']['capture_mode'] == 'HWND'
    assert (tmp_path / 'navigation-ui-check.json').is_file()
