package android.os;
import java.util.HashMap;
public class Bundle extends HashMap<String,Object> {
    /** One-shot scheduling seam for a lifecycle change midway through diagnostics. */
    public static Runnable afterHasPreviewWrite;
    public void putString(String key,String value){put(key,value);}
    public void putInt(String key,int value){put(key,value);}
    public void putBoolean(String key,boolean value){
        put(key,value);
        if("has_preview".equals(key) && afterHasPreviewWrite!=null){
            Runnable change=afterHasPreviewWrite;afterHasPreviewWrite=null;change.run();
        }
    }
    public boolean getBoolean(String key){return Boolean.TRUE.equals(get(key));}
}
