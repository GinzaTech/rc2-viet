package android.graphics;
import java.util.ArrayList;
import java.util.List;
public class Bitmap {
    public enum Config {ARGB_8888}
    public static final List<Bitmap> allocated=new ArrayList<>();
    private final int width,height;private boolean recycled;
    private Bitmap(int w,int h){width=w;height=h;allocated.add(this);}
    public static Bitmap createBitmap(int w,int h,Config config){if(w<=0 || h<=0)throw new IllegalArgumentException();return new Bitmap(w,h);}
    public int getWidth(){return width;}public int getHeight(){return height;}
    public boolean isRecycled(){return recycled;}
    public void recycle(){recycled=true;}
    public static int liveCount(){int n=0;for(Bitmap b:allocated)if(!b.recycled)n++;return n;}
}
