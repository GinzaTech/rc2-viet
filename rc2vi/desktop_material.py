"""Small native rounded surfaces, mapped from RC2 Việt's card/button tokens."""
import tkinter as tk
from tkinter import ttk

BG='#000000';CARD='#11181c';SURFACE='#1c2024';FG='#f5f7fa';MUTED='#a0a7ad';BORDER='#293036';ACCENT='#c72232'


class RoundedCard(ttk.Frame):
    def __init__(self,parent,**kwargs):
        super().__init__(parent,style='TFrame',**kwargs)
        self.surface=tk.Canvas(self,background=BG,highlightthickness=0,borderwidth=0,takefocus=False)
        self.surface.place(x=0,y=0,relwidth=1,relheight=1,bordermode='outside')
        self.surface.tk.call('lower',self.surface._w)
        self.bind('<Configure>',self.paint,add='+')

    def paint(self,event):
        w=event.width-1;h=event.height-1;r=min(18,w/2,h/2)
        self.surface.delete('surface')
        points=[r,1,w-r,1,w,1,w,r,w,h-r,w,h,w-r,h,r,h,1,h,1,h-r,1,r,1,1]
        self.surface.create_polygon(points,smooth=True,splinesteps=20,fill=CARD,outline=BORDER,tags='surface')


def rounded_image(root,fill,border,base):
    size=30;r=14
    image=tk.PhotoImage(master=root,width=size,height=size)
    def inside(x,y,inset):
        radius=r-inset;lo=inset;hi=size-1-inset
        cx=min(max(x,lo+radius),hi-radius);cy=min(max(y,lo+radius),hi-radius)
        return lo<=x<=hi and lo<=y<=hi and (x-cx)**2+(y-cy)**2<=radius**2
    for y in range(size):
        start=0;previous=None
        for x in range(size+1):
            color=((fill if inside(x,y,1) else border) if inside(x,y,0) else base) if x<size else None
            if color!=previous:
                if previous:image.put(previous,to=(start,y,x,y+1))
                start=x;previous=color
    return image


def button_material(root,style,name,fill,hover,focus_border,base=CARD):
    images=[rounded_image(root,fill,BORDER,base),rounded_image(root,hover,BORDER,base),
            rounded_image(root,hover,focus_border,base),rounded_image(root,'#161a1d','#20262b',base)]
    root._material_images.extend(images)
    element=name+'.background'
    style.element_create(element,'image',images[0],('pressed',images[1]),('active',images[1]),
                         ('focus',images[2]),('disabled',images[3]),border=14,padding=0,sticky='nsew')
    style.layout(name,[(element,{'sticky':'nsew','children':[('Button.padding',{'sticky':'nsew',
                  'children':[('Button.label',{'sticky':'nsew'})]})]})])
