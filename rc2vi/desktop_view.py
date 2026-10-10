"""Black desktop theme and responsive platform-specific panels."""
import tkinter as tk
from tkinter import ttk

from .desktop_material import BG,CARD,SURFACE,FG,MUTED,BORDER,ACCENT,RoundedCard,button_material


def theme(root):
    root.configure(background=BG)
    style=ttk.Style(root);style.theme_use('clam')
    style.configure('.',font=('Segoe UI',9),background=BG,foreground=FG)
    style.configure('TFrame',background=BG)
    style.configure('Card.TFrame',background=CARD)
    style.configure('TLabel',background=BG,foreground=FG)
    style.configure('Muted.TLabel',foreground=MUTED)
    style.configure('Card.TLabel',background=CARD)
    style.configure('CardMuted.TLabel',background=CARD,foreground=MUTED)
    style.configure('Title.TLabel',font=('Segoe UI',20,'bold'))
    style.configure('Heading.TLabel',font=('Segoe UI',10,'bold'),background=CARD)
    root._material_images=[]
    button_material(root,style,'TButton',SURFACE,'#293036',ACCENT)
    button_material(root,style,'Primary.TButton',ACCENT,'#db3444','#f5f7fa')
    button_material(root,style,'Tab.TButton','#121619','#252b30',ACCENT,base=BG)
    button_material(root,style,'Selected.Tab.TButton','#352027','#48262e',ACCENT,base=BG)
    button_material(root,style,'Report.TButton',SURFACE,'#293036',ACCENT,base=BG)
    style.configure('TButton',background=SURFACE,foreground=FG,padding=(10,4),borderwidth=0)
    style.map('TButton',foreground=[('disabled','#77818c')])
    style.configure('Primary.TButton',background=ACCENT,foreground=FG,font=('Segoe UI',9,'bold'))
    style.configure('Tab.TButton',padding=(12,4))
    style.configure('Selected.Tab.TButton',foreground=FG,padding=(12,4))
    style.configure('TCombobox',fieldbackground=SURFACE,background=SURFACE,foreground=FG,arrowcolor=FG,padding=4)
    style.map('TCombobox',fieldbackground=[('readonly',SURFACE)],foreground=[('readonly',FG)])
    root.option_add('*TCombobox*Listbox.background',SURFACE);root.option_add('*TCombobox*Listbox.foreground',FG)
    style.configure('TCheckbutton',background=BG,foreground=MUTED)
    style.map('TCheckbutton',background=[('active',BG)],foreground=[('active',FG)])
    style.configure('Card.TCheckbutton',background=CARD,foreground=MUTED)
    style.map('Card.TCheckbutton',background=[('active',CARD)],foreground=[('active',FG)])
    style.configure('Horizontal.TProgressbar',background=ACCENT,troughcolor=SURFACE,borderwidth=0,thickness=3)
    style.configure('Vertical.TScrollbar',background=BORDER,troughcolor=BG,arrowcolor=MUTED,width=10)


def card(parent,title,subtitle):
    box=RoundedCard(parent,padding=12)
    ttk.Label(box,text=title,style='Heading.TLabel').pack(anchor='w')
    if subtitle:ttk.Label(box,text=subtitle,style='CardMuted.TLabel',wraplength=800).pack(anchor='w',pady=(4,8))
    return box


def actions(parent,items,app):
    row=ttk.Frame(parent,style='Card.TFrame');row.pack(fill='x',pady=(2,0))
    for i,(label,command) in enumerate(items):
        ttk.Button(row,text=label,command=lambda c=command:app.send(c),
                   style='Primary.TButton' if command=='apply' else 'TButton').grid(row=0,column=i,sticky='w',padx=(0,6) if i<len(items)-1 else 0)


def build(app):
    root=app.root;root.title('RC2 Việt • DJI Fly trên Android và RC 2')
    height=min(740,root.winfo_screenheight()-100)
    root.geometry(f'960x{height}+30+20');root.minsize(860,min(580,height))
    theme(root)
    body=ttk.Frame(root);body.pack(fill='both',expand=True)
    canvas=tk.Canvas(body,background=BG,highlightthickness=0,yscrollincrement=24)
    sidebar=ttk.Scrollbar(body,command=canvas.yview);sidebar.pack(side='right',fill='y')
    canvas.configure(yscrollcommand=sidebar.set);canvas.pack(side='left',fill='both',expand=True)
    app.scroll_canvas=canvas
    main=ttk.Frame(canvas,padding=(20,12));window=canvas.create_window(0,0,anchor='nw',window=main)
    def fit(event=None):
        width=canvas.winfo_width();height=max(canvas.winfo_height(),main.winfo_reqheight())
        if int(float(canvas.itemcget(window,'width')))!=width or int(float(canvas.itemcget(window,'height')))!=height:
            canvas.itemconfigure(window,width=width,height=height)
        canvas.configure(scrollregion=(0,0,width,height))
    main.bind('<Configure>',fit);canvas.bind('<Configure>',fit)
    def wheel(event):
        if isinstance(event.widget,tk.Text):return
        canvas.yview_scroll(-int(event.delta/120),'units')
    root.bind('<MouseWheel>',wheel)
    header=ttk.Frame(main);header.pack(fill='x')
    ttk.Label(header,text='RC2 Việt',style='Title.TLabel').pack(side='left')
    ttk.Label(header,text='DJI FLY  /  USB',style='Muted.TLabel').pack(side='right')
    ttk.Label(main,text='Thiết bị · Tiếng Việt · Ứng dụng',style='Muted.TLabel').pack(anchor='w',pady=(2,12))
    tabs=ttk.Frame(main);tabs.pack(fill='x',pady=(0,10))
    app.tabs={}
    for mode,label in [('phone','Điện thoại Android'),('rc','Tay DJI RC 2')]:
        button=ttk.Button(tabs,text=label,style='Tab.TButton',command=lambda m=mode:app.set_mode(m))
        button.pack(side='left',padx=(0,8));app.tabs[mode]=button
    app.device_heading=tk.StringVar()
    device=card(main,'Kết nối USB','');device.pack(fill='x',pady=(0,12))
    row=ttk.Frame(device,style='Card.TFrame');row.pack(fill='x',pady=(8,0))
    ttk.Label(row,textvariable=app.device_heading,style='Card.TLabel').pack(side='left',padx=(0,12))
    app.selector=ttk.Combobox(row,state='readonly',width=32);app.selector.pack(side='left',fill='x',expand=True)
    app.selector.bind('<<ComboboxSelected>>',lambda e:app.send('select',app.selector.get()))
    ttk.Button(row,text='Kết nối lại',command=lambda:app.send('refresh')).pack(side='left',padx=(12,0))
    app.status=tk.StringVar(value='Đang khởi tạo…')
    ttk.Label(device,textvariable=app.status,style='Card.TLabel',wraplength=800).pack(anchor='w',pady=(10,6))
    app.progress=ttk.Progressbar(device,mode='indeterminate');app.progress.pack(fill='x')
    app.action_host=ttk.Frame(main);app.action_host.pack(fill='x')
    app.phone_actions=card(app.action_host,'DJI Fly trên điện thoại Android',
                          'Kiểm tra Android, quyền root và phiên bản DJI Fly trước khi bật bản dịch.')
    actions(app.phone_actions,[('Bật / cập nhật tiếng Việt','apply'),('Tắt bản dịch','disable'),('Mở DJI Fly','fly'),('Kiểm tra tương thích','inspect')],app)
    ttk.Label(app.phone_actions,text='Nếu chưa có DJI Fly, tải bản chính thức tại dji.com/downloads/djiapp/dji-fly.',style='CardMuted.TLabel',wraplength=840).pack(anchor='w',pady=(12,0))
    app.rc_actions=card(app.action_host,'DJI Fly trên tay DJI RC 2',
                       'DJI Fly 1.21.8 / Android 11. Cập nhật khi tay ở trang chủ hoặc RC Launcher.')
    actions(app.rc_actions,[('Bật / cập nhật tiếng Việt','apply'),('Tắt bản dịch','disable'),('Mở DJI Fly','fly'),('Mở RC Launcher','rc_launcher')],app)
    app.tools=ttk.Frame(app.rc_actions,style='Card.TFrame')
    app.tools.pack(fill='x',pady=(14,0))
    tools=ttk.Frame(app.tools,style='Card.TFrame');tools.pack(fill='x')
    for i,(label,command) in enumerate([('Cài RC Launcher','install_rc_launcher'),('Cài FreeFCC','install_freefcc'),('Đặt RC Launcher làm màn hình chính','home')]):
        ttk.Button(tools,text=label,command=lambda c=command:app.send(c)).grid(row=0,column=i,sticky='w',padx=(0,6))
    ttk.Button(app.tools,text='Bật chế độ nhà phát triển',command=app.open_developer_options).pack(anchor='w',pady=(10,0))
    hud=ttk.Frame(app.rc_actions,style='Card.TFrame');hud.pack(fill='x',pady=(14,0))
    ttk.Label(hud,text='Menu trên tay',style='Heading.TLabel').pack(anchor='w')
    ttk.Label(hud,text='Tự lấy DJI Fly từ RC 2, patch, ký và cài lại.',
              style='CardMuted.TLabel',wraplength=800).pack(anchor='w',pady=(3,6))
    hudrow=ttk.Frame(hud,style='Card.TFrame');hudrow.pack(fill='x')
    ttk.Button(hudrow,text='Cài / cập nhật menu',command=app.patch_menu,
               style='Primary.TButton').pack(anchor='w')
    app.auto=tk.BooleanVar(value=False)
    ttk.Checkbutton(app.rc_actions,text='Tự kiểm tra và bật tiếng Việt khi nhận RC 2',variable=app.auto,style='Card.TCheckbutton',
                    command=lambda:app.send('auto',app.auto.get())).pack(anchor='w',pady=(12,0))
    ttk.Label(main,text='Nếu thiết bị hiện “Allow USB debugging”, chọn Allow và lưu quyền cho máy tính này.',style='Muted.TLabel',wraplength=860).pack(anchor='w',pady=(12,12))
    logbox=card(main,'Nhật ký thao tác','');logbox.pack(fill='both',expand=True)
    logrow=ttk.Frame(logbox,style='Card.TFrame');logrow.pack(fill='both',expand=True,pady=(8,0))
    app.log=tk.Text(logrow,height=3,state='disabled',font=('Consolas',9),wrap='word',borderwidth=0,
                    background=CARD,foreground=MUTED,insertbackground=FG,selectbackground='#48262e')
    scroll=ttk.Scrollbar(logrow,command=app.log.yview);scroll.pack(side='right',fill='y')
    app.log.configure(yscrollcommand=scroll.set);app.log.pack(fill='both',expand=True)
    footer=ttk.Frame(root);footer.pack(fill='x',padx=24,pady=(7,12))
    ttk.Label(footer,text='ADB tích hợp  •  Không cần cài Python',style='Muted.TLabel').pack(side='left')
    ttk.Button(footer,text='Lưu báo cáo chẩn đoán',command=app.save_report,style='Report.TButton').pack(side='right')
