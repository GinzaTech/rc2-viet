import tkinter as tk
from tkinter import ttk
from app import App


def test_compact_compact_theme_has_black_background_and_small_buttons(tmp_path):
    root=tk.Tk()
    try:
        app=App(root,tmp_path,tmp_path,False);root.update()
        style=ttk.Style(root)
        assert root.cget('background')=='#000000'
        assert style.lookup('Primary.TButton','background')=='#c72232'
        def buttons(w):
            for child in w.winfo_children():
                if isinstance(child,ttk.Button) and child.winfo_ismapped():yield child
                yield from buttons(child)
        found=list(buttons(root));assert found
        assert max(b.winfo_height() for b in found)<=36
        apply=next(b for b in found if b.cget('text')=='Bật / cập nhật tiếng Việt')
        assert apply.winfo_width()<320
        assert root.winfo_reqwidth()<1100
    finally:root.destroy()
