package android.widget;
import android.content.Context;
import android.graphics.Bitmap;
public class ImageView extends android.view.View {
    public enum ScaleType {FIT_CENTER}
    public Bitmap bitmap;
    public ImageView(Context context){super(context);}
    public void setScaleType(ScaleType type){}
    public void setImageBitmap(Bitmap value){if(value.isRecycled())throw new AssertionError("displayed recycled bitmap");bitmap=value;}
    public void setImageDrawable(Object drawable){bitmap=null;}
}
