"""Capture only this utility's own foreground window for visual review."""
import base64
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import tkinter as tk
import time
from app import App

ROOT=Path(__file__).resolve().parents[1]


def capture(root,path):
    user=ctypes.WinDLL('user32')
    user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];user.GetAncestor.restype=wintypes.HWND
    user.GetForegroundWindow.restype=wintypes.HWND
    window=user.GetAncestor(root.winfo_id(),2)
    root.focus_force();root.update()
    foreground=user.GetForegroundWindow()==window
    rectangle=wintypes.RECT();user.GetClientRect(window,ctypes.byref(rectangle))
    origin=wintypes.POINT(0,0);user.ClientToScreen(window,ctypes.byref(origin))
    left,top=origin.x,origin.y;w=rectangle.right;h=rectangle.bottom
    print_window=f'''Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class OwnWindowCapture {{ [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr window, IntPtr dc, uint flags); }}'
$dc=$graphics.GetHdc()
try {{ if(-not [OwnWindowCapture]::PrintWindow([IntPtr]{int(window)},$dc,3)) {{ throw 'Own window render failed' }} }} finally {{ $graphics.ReleaseHdc($dc) }}
'''
    capture_step=f'$graphics.CopyFromScreen({left},{top},0,0,$image.Size)' if foreground else print_window
    script=f'''Add-Type -AssemblyName System.Drawing
$image=New-Object System.Drawing.Bitmap({w},{h})
$graphics=[System.Drawing.Graphics]::FromImage($image)
{capture_step}
$image.Save('{str(path).replace("'","''")}',[System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$image.Dispose()
'''
    command=base64.b64encode(script.encode('utf-16le')).decode()
    process=subprocess.Popen(['powershell','-NoProfile','-EncodedCommand',command],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    deadline=time.monotonic()+12
    while process.poll() is None:
        root.update();time.sleep(0.01)
        if time.monotonic()>deadline:
            process.kill();process.communicate();raise RuntimeError('Own window capture timed out')
    _,stderr=process.communicate()
    if process.returncode:raise RuntimeError(stderr.decode(errors='replace')[:300])


def main():
    root=tk.Tk();app=App(root,ROOT/'assets',ROOT/'phone-work',start_worker=False)
    for mode in ['phone','rc']:
        app.set_mode(mode)
        if mode=='phone':
            app.emit_for(mode,'devices',('Điện thoại đang kết nối',))
            app.emit_for(mode,'ready','Android 15 · DJI Fly 1.21.12 · Đã bật và kiểm tra tài nguyên tiếng Việt')
        else:app.emit_for(mode,'waiting','Cắm RC 2 bằng cáp USB và bật nguồn.')
        app.poll();root.update()
        capture(root,ROOT/'docs'/f'desktop-{mode}.png')
    root.destroy()


if __name__=='__main__':main()
