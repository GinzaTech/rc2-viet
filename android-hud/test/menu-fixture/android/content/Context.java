package android.content;
import java.util.HashMap; import java.util.Map;
public class Context {
 private final android.content.res.Resources resources=new android.content.res.Resources();
 private final Map<String,Prefs> preferences=new HashMap<>();
 public android.content.res.Resources getResources(){return resources;}
 public ClassLoader getClassLoader(){return getClass().getClassLoader();}
 public SharedPreferences getSharedPreferences(String name,int mode){return preferences.computeIfAbsent(name,k->new Prefs());}
 private static final class Prefs implements SharedPreferences,SharedPreferences.Editor {
  final Map<String,Boolean> values=new HashMap<>();
  public boolean getBoolean(String key,boolean fallback){return values.getOrDefault(key,fallback);}
  public Editor edit(){return this;} public Editor putBoolean(String key,boolean value){values.put(key,value);return this;} public void apply(){}
 }
}
