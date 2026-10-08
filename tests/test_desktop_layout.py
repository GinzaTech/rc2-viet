from pathlib import Path
import tkinter as tk
from tkinter import ttk
from app import App


def test_small_window_can_scroll_to_all_rc_actions_and_footer(tmp_path):
    root=tk.Tk()
    try:
        app=App(root,tmp_path,tmp_path,start_worker=False);root.geometry('860x580');root.update()
        app.set_mode('rc');root.update()
        canvas=app.scroll_canvas
        assert canvas.cget('background')=='#000000'
        assert canvas.yview()[1]<1
        canvas.yview_moveto(1);root.update()
        assert canvas.yview()[1]==1
        footer=root.winfo_children()[-1]
        assert footer.winfo_ismapped() and footer.winfo_height()>=footer.winfo_reqheight()
        assert footer.winfo_y()+footer.winfo_height()<=root.winfo_height()
        app.set_mode('phone');root.update()
        assert not app.rc_actions.winfo_ismapped()
        assert app.phone_actions.winfo_ismapped()
    finally:root.destroy()
