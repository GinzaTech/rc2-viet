"""Rounded controls retain hover while the editor repeats availability updates."""
import tkinter as tk

import pytest

from rc2vi import desktop_theme as ui


@pytest.fixture
def desktop():
    root = tk.Tk()
    root.geometry('520x240')
    ui.setup(root)
    try:
        yield root
    finally:
        for callback in root.tk.call('after', 'info'):
            root.tk.call('after', 'cancel', callback)
        root.destroy()


def observe_draws(button, monkeypatch):
    calls = []
    original = button._draw

    def draw(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(button, '_draw', draw)
    return calls


@pytest.mark.parametrize('variant', ['primary', 'secondary', 'ghost'])
def test_repeated_poll_state_keeps_hover_and_geometry(desktop, monkeypatch, variant):
    button = ui.button(desktop, 'Cài animation', lambda: None, variant=variant)
    button.pack(padx=20, pady=20)
    desktop.update()
    calls = observe_draws(button, monkeypatch)
    button._on_enter()
    hover = button._text_label.cget('bg')
    geometry = (button.winfo_x(), button.winfo_y(), button.winfo_width(), button.winfo_height())

    for _ in range(20):
        button.configure(state='normal')
        desktop.update_idletasks()

    assert calls == []
    assert button._text_label.cget('bg') == hover
    assert geometry == (button.winfo_x(), button.winfo_y(), button.winfo_width(), button.winfo_height())


def test_primary_state_changes_repaint_once_and_disabled_button_does_not_invoke(desktop, monkeypatch):
    invoked = []
    button = ui.button(desktop, 'Cài khởi động', lambda: invoked.append(True), variant='primary')
    button.pack(pady=20)
    desktop.update()
    calls = observe_draws(button, monkeypatch)

    button.configure(state='disabled')
    assert len(calls) == 1
    assert button.cget('fg_color') == '#354b46'
    assert button.invoke() is None
    assert invoked == []
    for _ in range(20):
        button.configure(state='disabled')
    assert len(calls) == 1

    button.configure(state='normal')
    assert len(calls) == 2
    assert button.cget('fg_color') == ui.ACCENT
    button.invoke()
    assert invoked == [True]


def test_identical_visual_options_are_inert_but_real_updates_and_forced_redraw_work(desktop, monkeypatch):
    button = ui.button(desktop, 'Xuất animation', lambda: None)
    button.pack(pady=20)
    desktop.update()
    calls = observe_draws(button, monkeypatch)
    same = {key: button.cget(key) for key in (
        'state', 'fg_color', 'hover_color', 'text_color', 'corner_radius',
        'border_width', 'border_color', 'anchor', 'width', 'height',
    )}
    for _ in range(20):
        button.configure(**same)
    assert calls == []

    button.configure(border_width=1, border_color=ui.ACCENT)
    assert len(calls) == 1
    assert button.cget('border_width') == 1
    button.configure(require_redraw=True, border_width=1, border_color=ui.ACCENT)
    assert len(calls) == 2
    button.configure(text='Đã xuất')
    assert button.cget('text') == 'Đã xuất'


def test_primary_created_disabled_has_dim_color(desktop):
    button = ui.button(desktop, 'Cài tắt máy', lambda: None, variant='primary', state='disabled')
    assert button.cget('state') == 'disabled'
    assert button.cget('fg_color') == '#354b46'
    button.configure(state='normal')
    assert button.cget('fg_color') == ui.ACCENT
