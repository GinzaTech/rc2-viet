"""Shared rounded desktop controls; the established RC2 dark/mint palette."""
import customtkinter as ctk


BG = '#171b22'
SURFACE = '#1e242e'
PANEL = '#252d38'
FIELD = '#171e27'
LINE = '#33404d'
FG = '#f4f6f9'
MUTED = '#aab7c7'
ACCENT = '#80e1bf'

ctk.set_appearance_mode('dark')


def setup(window):
    """Also support existing Tk roots so offline CLI modes stay independent."""
    if isinstance(window, (ctk.CTk, ctk.CTkToplevel)):
        window.configure(fg_color=BG)
    else:
        window.configure(bg=BG)


class Button(ctk.CTkButton):
    _IDEMPOTENT_OPTIONS = frozenset({
        'state', 'fg_color', 'hover_color', 'border_color', 'text_color',
        'text_color_disabled', 'background_corner_colors', 'bg_color',
        'corner_radius', 'border_width', 'border_spacing', 'anchor',
        'compound', 'width', 'height', 'hover',
    })

    def __init__(self, *args, **kwargs):
        self._mint_primary = kwargs.get('fg_color') == ACCENT
        if self._mint_primary and kwargs.get('state') == 'disabled':
            kwargs['fg_color'] = '#354b46'
        super().__init__(*args, **kwargs)
        # CTk buttons draw on a canvas; explicitly retain keyboard activation.
        self._text_label.configure(takefocus=lambda *_: self.cget('state') != 'disabled')
        self._canvas.configure(takefocus=0)
        self.bind('<Return>', lambda _: self.invoke())
        self.bind('<space>', lambda _: self.invoke())
        self.bind('<FocusIn>', lambda _: self.configure(border_width=1, border_color=FG))
        self.bind('<FocusOut>', lambda _: self.configure(border_width=0))

    def configure(self, require_redraw=False, **kwargs):
        if 'state' in kwargs and self._mint_primary and 'fg_color' not in kwargs:
            kwargs['fg_color'] = '#354b46' if kwargs['state'] == 'disabled' else ACCENT
        # CTk redraws even an unchanged state, clearing the hover color on each
        # editor poll. Keep recurring control updates inert until values change.
        for option in self._IDEMPOTENT_OPTIONS.intersection(kwargs):
            if kwargs[option] == self.cget(option):
                kwargs.pop(option)
        if not kwargs and not require_redraw:
            return None
        return super().configure(require_redraw=require_redraw, **kwargs)

    def __getitem__(self, key):
        return self.cget(key)

    def __setitem__(self, key, value):
        self.configure(**{key: value})


class Combo(ctk.CTkComboBox):
    def __getitem__(self, key):
        return self.cget(key)

    def __setitem__(self, key, value):
        self.configure(**{key: value})


def frame(parent, color='transparent', radius=0, **kwargs):
    options = dict(fg_color=color, corner_radius=radius, border_width=0)
    options.update(kwargs)
    return ctk.CTkFrame(parent, **options)


def label(parent, text='', muted=False, size=13, bold=False, **kwargs):
    options = dict(text=text, text_color=MUTED if muted else FG,
                   font=('Segoe UI', size, 'bold' if bold else 'normal'),
                   anchor='w')
    options.update(kwargs)
    return ctk.CTkLabel(parent, **options)


def button(parent, text, command, variant='secondary', width=120, height=36, **kwargs):
    primary = variant == 'primary'
    options = dict(text=text, command=command, width=width, height=height,
                   corner_radius=14, border_width=0,
                   fg_color=ACCENT if primary else ('transparent' if variant == 'ghost' else PANEL),
                   hover_color='#a4efd5' if primary else '#303c49',
                   text_color='#102b23' if primary else FG,
                   text_color_disabled='#6c7b89',
                   font=('Segoe UI', 13, 'bold' if primary else 'normal'),
                   anchor='center')
    options.update(kwargs)
    return Button(parent, **options)


def entry(parent, variable, width=160, height=34, **kwargs):
    options = dict(textvariable=variable, width=width, height=height,
                   corner_radius=10, border_width=1, border_color=LINE,
                   fg_color=FIELD, text_color=FG,
                   font=('Segoe UI', 13))
    options.update(kwargs)
    widget = ctk.CTkEntry(parent, **options)
    widget.bind('<FocusIn>', lambda _: widget.configure(border_color=ACCENT), add='+')
    widget.bind('<FocusOut>', lambda _: widget.configure(border_color=LINE), add='+')
    return widget


def combo(parent, variable, values=(), width=160, height=34, command=None, **kwargs):
    options = dict(variable=variable, values=list(values), command=command,
                   state='readonly', width=width, height=height,
                   corner_radius=10, border_width=1, border_color=LINE,
                   fg_color=FIELD, button_color=FIELD, button_hover_color='#303c49',
                   text_color=FG, text_color_disabled='#6c7b89',
                   dropdown_fg_color=PANEL, dropdown_hover_color='#3c6b61',
                   dropdown_text_color=FG, font=('Segoe UI', 13),
                   dropdown_font=('Segoe UI', 13))
    options.update(kwargs)
    return Combo(parent, **options)


def check(parent, text, variable, command=None, **kwargs):
    options = dict(text=text, variable=variable, command=command,
                   width=20, height=28, checkbox_width=18, checkbox_height=18,
                   corner_radius=6, border_width=1, border_color='#536275',
                   fg_color=ACCENT, hover_color='#a4efd5', checkmark_color='#102b23',
                   text_color=FG, text_color_disabled='#6c7b89',
                   font=('Segoe UI', 12))
    options.update(kwargs)
    widget = ctk.CTkCheckBox(parent, **options)
    widget._text_label.configure(takefocus=lambda *_: widget.cget('state') != 'disabled')
    widget.bind('<space>', lambda _: widget.toggle() if widget.cget('state') != 'disabled' else None)
    widget.bind('<FocusIn>', lambda _: widget.configure(border_color=ACCENT))
    widget.bind('<FocusOut>', lambda _: widget.configure(border_color='#536275'))
    return widget
