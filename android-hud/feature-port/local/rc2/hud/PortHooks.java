package local.rc2.hud;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;
import android.view.View;
import java.util.ArrayList;

/** Public host entry points with stock fallback and no startup aircraft writes. */
public final class PortHooks {
    private static volatile Application application;
    private PortHooks() { }
    public static void placePower(View power,float fallbackX,float fallbackY) { PortIntegration.placePower(power,fallbackX,fallbackY); }
    public static void finishPowerVisibility(View power) { PortIntegration.finishPowerVisibility(power); }
    static void initialize(Application app) { application=app; }
    private static Object call(String type,String name,Class<?>[] sig,Object... args) {
        Application app=application;
        return app==null?null:PortIntegration.call(app,type,name,sig,args);
    }
    private static Object map(String name,Class<?>[] sig,Object... args) { return call("mapsrc.M",name,sig,args); }
    private static SharedPreferences settings(String file) {
        Application app=application;
        return app==null?null:app.getSharedPreferences(file,0);
    }
    private static boolean mapsSelected() {
        SharedPreferences p=settings("mapsrc");return p!=null && !p.getAll().isEmpty();
    }
    public static int mapEngine(int original) {
        if(!mapsSelected())return original;
        Object v=map("eng",new Class<?>[]{int.class},original);return v instanceof Integer?(Integer)v:original;
    }
    private static String style(String original,int slot,boolean next) {
        if(!mapsSelected())return original;
        Object value=map((next?"next":"cur")+slot,new Class<?>[0]);
        return value instanceof String && !((String)value).isEmpty()?(String)value:original;
    }
    public static String styleCurrent0(String original) { return offlineStyle(original); }
    public static String styleCurrent1(String original) { return style(original,1,false); }
    public static String styleCurrent2(String original) { return style(original,2,false); }
    public static String styleNext0(String original) { return style(original,0,true); }
    public static String styleNext1(String original) { return style(original,1,true); }
    public static String styleNext2(String original) { return style(original,2,true); }
    private static String offlineStyle(String original) {
        if(!mapsSelected())return original;
        Object v=map("styleUri",new Class<?>[0]);return v instanceof String?(String)v:original;
    }
    private static Object builder(Object builder,String original,int slot,boolean next) {
        String chosen=style(original,slot,next);
        try {
            return builder.getClass().getMethod(chosen.equals(original)?"g":"f",String.class).invoke(builder,chosen);
        } catch(ReflectiveOperationException|RuntimeException|LinkageError error) {
            Log.e("RC2FeaturePort","map_style_failed",error);
            try {return builder.getClass().getMethod("g",String.class).invoke(builder,original);}
            catch(ReflectiveOperationException|RuntimeException|LinkageError fallback){Log.e("RC2FeaturePort","map_style_fallback_failed",fallback);return builder;}
        }
    }
    public static Object styleBuilderCurrent0(Object b,String s) { return builder(b,s,0,false); }
    public static Object styleBuilderCurrent1(Object b,String s) { return builder(b,s,1,false); }
    public static Object styleBuilderCurrent2(Object b,String s) { return builder(b,s,2,false); }
    public static Object styleBuilderNext0(Object b,String s) { return builder(b,s,0,true); }
    public static Object styleBuilderNext1(Object b,String s) { return builder(b,s,1,true); }
    public static Object styleBuilderNext2(Object b,String s) { return builder(b,s,2,true); }
    public static void tuneManager(Object manager) { if(mapsSelected())map("tuneManager",new Class<?>[]{Object.class},manager); }
    public static void tuneBuilder(Object builder) { if(mapsSelected())map("tune",new Class<?>[]{Object.class},builder); }
    public static void wireMap(View v) { map("addSrcButton",new Class<?>[]{View.class},v); }
    public static void wireFindMap(View v) { map("addSrcButtonColEnd",new Class<?>[]{View.class},v); }
    public static void wireOffline(View v) { map("wireOfflineButtons",new Class<?>[]{View.class},v); }
    public static void wireFlightRecord(Object v) { map("wireFlightRecordButton",new Class<?>[]{Object.class},v); }
    public static void offlineHint(Object v,Object map) { if(mapsSelected())map("hint",new Class<?>[]{Object.class,Object.class},v,map); }
    public static void estimate(Object bounds,double min,double max) { if(mapsSelected())map("estimate",new Class<?>[]{Object.class,double.class,double.class},bounds,min,max); }
    public static String region(String original) {
        SharedPreferences p=settings("mod_settings");
        if(p==null || !p.contains("region"))return original;
        String value=p.getString("region",original);
        return value!=null && value.matches("[A-Z]{2}")?value:original;
    }
    public static boolean encryptLogs() {
        SharedPreferences p=settings("mod_settings");return p==null || p.getBoolean("enc_logs",true);
    }
    public static boolean recordStartupGuard() {
        SharedPreferences p=settings("mod_settings");return p==null || p.getBoolean("screen_record_startup_guard",true);
    }
    public static boolean stopMainPage(Activity a) {
        return Boolean.TRUE.equals(PortIntegration.call(a,"redfly.Startup","stopMainPage",new Class<?>[]{Activity.class},a));
    }
    public static boolean stopSystemLaunch(Activity a) {
        return Boolean.TRUE.equals(PortIntegration.call(a,"redfly.Startup","stopSystemLaunch",new Class<?>[]{Activity.class},a));
    }
    public static void noteIntent(Activity a,Intent i) { PortIntegration.call(a,"redfly.Startup","noteIntent",new Class<?>[]{Activity.class,Intent.class},a,i); }
    public static void gpsControls(View v) { call("flyctl.F","addToggles",new Class<?>[]{View.class},v); }
    public static String buttonName(int value) {
        Object v=call("flyctl.B","name",new Class<?>[]{int.class},value);return v instanceof String?(String)v:null;
    }
    public static boolean runButton(Object action,Activity a) {
        if(!(action instanceof Enum) || a==null)return false;
        String name=((Enum<?>)action).name();
        if(!name.matches("CUSTOM10[0-5]"))return false;
        int index=Integer.parseInt(name.substring(6))-100;
        if(index==2) { toggleLights(a);return true; }
        return PortIntegration.invoke(a,"flyctl.B","run",new Class<?>[]{int.class,Activity.class},index,a);
    }
    public static void requireGround() {
        Application app=application;
        GroundGate state=app==null?GroundGate.unknown():new NativeAircraft(app.getClassLoader()).snapshot();
        if(!state.allowed())throw new IllegalStateException(state.explanation());
    }
    public static void toggleLights(Context context) {
        final NativeLed led=new NativeLed(context.getClassLoader());
        led.inspect(new LedJob.Reply<LedJob.Lights>() {
            public void failure(String message) { led.close();toast(context,message); }
            public void success(LedJob.Lights current) {
                boolean target=!(current.front || current.rear || current.status);
                boolean started=led.requestAll(target,(success,message)->{led.close();toast(context,message);});
                if(!started)led.close();
            }
        });
    }
    private static void toast(Context c,String value) {
        new android.os.Handler(android.os.Looper.getMainLooper()).post(()->android.widget.Toast.makeText(c,value,android.widget.Toast.LENGTH_LONG).show());
    }
    public static void appendLanTile(ArrayList<?> rows) { call("lanstream.LanUI","appendTile",new Class<?>[]{ArrayList.class},rows); }
    public static boolean bindLanTile(Object adapter,Object holder,int position) {
        try {
            ClassLoader loader=adapter.getClass().getClassLoader();
            Class<?> a=Class.forName("com.uav.component.fpv.widget.setting.ui.liveview.livestreaming.SettingLiveStreamingRecyclerViewAdapter",false,loader);
            Class<?> h=Class.forName("com.uav.component.fpv.widget.setting.ui.liveview.livestreaming.SettingLiveStreamingItemViewHolder",false,loader);
            return Boolean.TRUE.equals(call("lanstream.LanUI","bindTile",new Class<?>[]{a,h,int.class},adapter,holder,position));
        } catch(ReflectiveOperationException|RuntimeException|LinkageError error){Log.e("RC2FeaturePort","lan_tile_failed",error);return false;}
    }
    public static void manualRth() { call("rthguard.Guard","manual",new Class<?>[0]); }
    public static boolean suppressRth(Object info) {
        return info!=null && Boolean.TRUE.equals(call("rthguard.Guard","suppress",new Class<?>[]{Object.class},info));
    }
    public static boolean suppressNotification(Object notification,Context c) {
        try {
            PortIntegration.call(c,"rthguard.Guard","init",new Class<?>[]{Context.class},c);
            java.lang.reflect.Field f=notification.getClass().getDeclaredField("c");f.setAccessible(true);
            return suppressRth(f.get(notification));
        } catch(ReflectiveOperationException|RuntimeException|LinkageError error){Log.e("RC2FeaturePort","rth_notification_failed",error);return false;}
    }
}
