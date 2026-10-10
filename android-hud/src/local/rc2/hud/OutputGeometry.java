package local.rc2.hud;

/** Aspect-preserving output; fallback buffers never exceed 960x540. */
final class OutputGeometry {
    static int[] fit(int sourceWidth,int sourceHeight,int targetWidth,int targetHeight) {
        if(sourceWidth<=0 || sourceHeight<=0 || targetWidth<=0 || targetHeight<=0)
            throw new IllegalArgumentException("Positive frame dimensions required");
        double scale=Math.min((double)targetWidth/sourceWidth,(double)targetHeight/sourceHeight);
        int width=Math.min(targetWidth,Math.max(1,(int)Math.round(sourceWidth*scale)));
        int height=Math.min(targetHeight,Math.max(1,(int)Math.round(sourceHeight*scale)));
        return new int[]{(targetWidth-width)/2,(targetHeight-height)/2,width,height};
    }
    static int[] copySize(int sourceWidth,int sourceHeight) {
        int[] fitted=fit(sourceWidth,sourceHeight,960,540);
        return new int[]{fitted[2],fitted[3]};
    }
}
