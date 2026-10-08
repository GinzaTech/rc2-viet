"""Live GUI check, using its real phone worker and the real Apply button."""
import json
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk
from app import App
from scripts.preview_desktop import capture

ROOT=Path(__file__).resolve().parents[1]


def main():
    root=tk.Tk();app=App(root,ROOT/'assets',ROOT/'phone-work/gui-check',start_worker=True)
    app.set_mode('phone');deadline=time.monotonic()+25;clicked=False;result={}
    def tick():
        nonlocal clicked,result
        state=app.platforms['phone']
        if not clicked and app.phone_worker.adb and state['state']=='ready':
            def buttons(widget):
                for child in widget.winfo_children():
                    if isinstance(child,ttk.Button):yield child
                    yield from buttons(child)
            button=next(b for b in buttons(app.phone_actions) if b.cget('text')=='Bật / cập nhật tiếng Việt')
            button.invoke();clicked=True
        if clicked and 'đã bật và đọc lại thành công' in state['status']:
            result={'status':'passed','action':'real Tk Apply button / real phone worker',
                    'message':state['status']}
            try:
                capture(root,ROOT/'docs/desktop-phone-live.png')
                result['gui']='desktop-phone-live.png'
            except RuntimeError:result['screenshot']='not captured: own window was not foreground'
            app.close()
        elif time.monotonic()>deadline:
            result={'status':'failed','message':state['status']};app.close()
        if not app.closing:root.after(100,tick)
    root.after(100,tick);root.mainloop()
    (ROOT/'docs/desktop-phone-live-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    if result.get('status')!='passed':raise RuntimeError(result)


if __name__=='__main__':main()
