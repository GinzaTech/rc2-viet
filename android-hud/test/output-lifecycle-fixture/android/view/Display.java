package android.view;
import android.util.DisplayMetrics;
public class Display {
    public static final int DEFAULT_DISPLAY=0,STATE_OFF=1,STATE_ON=2;
    private final int id;public boolean valid=true;public int state=STATE_ON,width=640,height=360,version;
    public Display(int id){this.id=id;}
    public int getDisplayId(){return id;}
    public boolean isValid(){return valid;}
    public int getState(){return state;}
    public void getMetrics(DisplayMetrics metrics){metrics.widthPixels=width;metrics.heightPixels=height;}
    public void getRealMetrics(DisplayMetrics metrics){getMetrics(metrics);}
}
