package local.rc2.hud;

/** Place a separate action beside the menu without overlapping either touch target. */
final class HomeActionPlacement {
    static int[] place(int menuX,int menuY,int menuWidth,int menuHeight,int rootX,int rootY,
                       int rootWidth,int rootHeight,int width,int height,int gap,int padding) {
        if(width<=0 || height<=0 || menuWidth<=0 || menuHeight<=0)return null;
        int maxX=rootWidth-width-padding,maxY=rootHeight-height-padding;
        if(maxX<padding || maxY<padding)return null;
        int x=menuX-rootX,y=menuY-rootY;
        int centeredY=Math.max(padding,Math.min(y+(menuHeight-height)/2,maxY));
        int centeredX=Math.max(padding,Math.min(x+(menuWidth-width)/2,maxX));
        int left=x-width-gap;
        if(left>=padding && left<=maxX)return new int[]{left,centeredY};
        int above=y-height-gap;
        if(above>=padding && above<=maxY)return new int[]{centeredX,above};
        int right=x+menuWidth+gap;
        if(right>=padding && right<=maxX)return new int[]{right,centeredY};
        int below=y+menuHeight+gap;
        if(below>=padding && below<=maxY)return new int[]{centeredX,below};
        return null;
    }
}
