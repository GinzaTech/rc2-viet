package android.util;
public class DisplayMetrics {
    public int widthPixels=640,heightPixels=360,densityDpi=160;
    public float density=1;
    public boolean equalsPhysical(DisplayMetrics other){return widthPixels==other.widthPixels && heightPixels==other.heightPixels && densityDpi==other.densityDpi;}
}
