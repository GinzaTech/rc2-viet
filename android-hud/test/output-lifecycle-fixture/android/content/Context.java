package android.content;
import android.content.res.Resources;
import android.hardware.display.DisplayManager;
import java.util.HashMap;
import java.util.Map;
public class Context {
    public static final String DISPLAY_SERVICE="display";
    public static DisplayManager manager;
    private static final Map<String,Prefs> preferences=new HashMap<>();
    private final Resources resources=new Resources();
    public Object getSystemService(String name){return DISPLAY_SERVICE.equals(name)?manager:null;}
    public SharedPreferences getSharedPreferences(String name,int mode){
        if(!preferences.containsKey(name))preferences.put(name,new Prefs());return preferences.get(name);
    }
    public Resources getResources(){return resources;}
    public static void reset(){preferences.clear();}
    private static final class Prefs implements SharedPreferences,SharedPreferences.Editor {
        private final Map<String,Boolean> values=new HashMap<>();
        public boolean getBoolean(String key,boolean fallback){return values.containsKey(key)?values.get(key):fallback;}
        public Editor edit(){return this;}
        public Editor putBoolean(String key,boolean value){values.put(key,value);return this;}
        public void apply(){}
    }
}
