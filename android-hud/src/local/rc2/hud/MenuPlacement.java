package local.rc2.hud;

/** Align to the anchor's complete layout rectangle, not a system-inset clipped visible rect. */
final class MenuPlacement {
    static int[] place(int anchorX,int anchorY,int anchorHeight,int rootX,int rootY,
                       int rootWidth,int rootHeight,int size,int gap,int padding) {
        int left=anchorX-rootX-size-gap;
        int top=anchorY-rootY+(anchorHeight-size)/2;
        return new int[]{Math.max(padding,Math.min(left,rootWidth-size-padding)),
                         Math.max(padding,Math.min(top,rootHeight-size-padding))};
    }
}
