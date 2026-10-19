package flysettings;
import android.content.Context;
public final class S {
    public static Context sCtx;
    public static int advancedCalls,gimbalCalls,basicCalls,controlCalls,safetyCalls;
    public static final class Columns extends android.widget.LinearLayout {
        public Columns(Context context){super(context);}
        public void setAvailHeight(int value){}
    }
    private static Columns tabAdvanced(Context context){advancedCalls++;return new Columns(context);}
    private static Columns gimbalPage(Context context){gimbalCalls++;return new Columns(context);}
    private static Columns tabBasic(Context context){basicCalls++;return new Columns(context);}
    private static Columns tabControl(Context context){controlCalls++;return new Columns(context);}
    private static Columns tabSafety(Context context){safetyCalls++;return new Columns(context);}
}
