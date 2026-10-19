package local.rc2.hud;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.Toast;
import java.util.Map;
import java.util.WeakHashMap;

/** Candidate-only bridge; no aircraft command is sent from installation. */
final class PortIntegration {
    private static final String TAG="RC2FeaturePort";
    private static boolean installed;
    private static final Map<View,Boolean> hiddenPowerTargets=new WeakHashMap<>();
    static void install(Application application) {
        if(installed)return;
        installed=true;
        PortHooks.initialize(application);
        SharedPreferences p=application.getSharedPreferences("mod_settings",0);
        // Keep the user's LED controls in the home menu and avoid duplicate HUD gestures.
        if(!p.contains("qt_led"))p.edit().putBoolean("qt_led",false).apply();
        if(!p.contains("enc_logs"))p.edit().putBoolean("enc_logs",true).apply();
        call(application,"rthguard.Guard","init",new Class<?>[]{Context.class},application);
        call(application,"lte4g.Auto","arm",new Class<?>[0]);
        if(p.getBoolean("fr_decrypt",false))call(application,"frtool.X","arm",new Class<?>[0]);
        Log.i(TAG,"feature_modules_registered");
    }
    static Object call(Context c,String type,String method,Class<?>[] signature,Object... args) {
        try {return Class.forName(type,false,c.getClassLoader()).getMethod(method,signature).invoke(null,args);}
        catch(ReflectiveOperationException|RuntimeException|LinkageError error){Log.e(TAG,"feature_call_failed:"+type+"."+method,error);return null;}
    }
    static boolean invoke(Context c,String type,String method,Class<?>[] signature,Object... args) {
        try {Class.forName(type,false,c.getClassLoader()).getMethod(method,signature).invoke(null,args);return true;}
        catch(ReflectiveOperationException|RuntimeException|LinkageError error){Log.e(TAG,"feature_call_failed:"+type+"."+method,error);return false;}
    }
    static void resumed(Activity a,int role) {
        View root=a.findViewById(android.R.id.content);
        if(role==1 && root!=null)call(a,"redfly.Power","bind",new Class<?>[]{View.class},root);
        if(a.getClass().getName().contains("FlightRecord"))call(a,"frtool.X","attach",new Class<?>[]{Activity.class},a);
        if(role==2) {
            call(a,"flyctl.Q","attach",new Class<?>[]{Activity.class},a);
            call(a,"rthguard.Guard","attach",new Class<?>[]{Activity.class},a);
            call(a,"frtool.X","attach",new Class<?>[]{Activity.class},a);
            if(root instanceof ViewGroup)call(a,"app.openfcc.battery.BatteryOverlay","attach",new Class<?>[]{ViewGroup.class},root);
        }
    }
    static void paused(Activity a) {
        View root=a.findViewById(android.R.id.content);
        if(root instanceof ViewGroup)call(a,"app.openfcc.battery.BatteryOverlay","detach",new Class<?>[]{ViewGroup.class},root);
        if(root instanceof ViewGroup)for(String tag:new String[]{"flyctl-qt","flyctl-qt-b"}) {
            View v=root.findViewWithTag(tag);
            if(v!=null && v.getParent() instanceof ViewGroup)((ViewGroup)v.getParent()).removeView(v);
        }
    }
    static void placePower(View power,float fallbackX,float fallbackY) {
        hiddenPowerTargets.remove(power);
        float x=fallbackX,y=fallbackY;
        if(power.getParent() instanceof ViewGroup) {
            ViewGroup root=(ViewGroup)power.getParent();
            View menu=root.findViewWithTag("rc2vi-home-menu");
            if(menu!=null && menu.isShown() && power.getWidth()>0 && power.getHeight()>0) {
                int[] menuOrigin=new int[2],rootOrigin=new int[2];
                menu.getLocationOnScreen(menuOrigin);root.getLocationOnScreen(rootOrigin);
                int gap=Math.round(8*root.getResources().getDisplayMetrics().density);
                int[] position=HomeActionPlacement.place(menuOrigin[0],menuOrigin[1],menu.getWidth(),menu.getHeight(),
                    rootOrigin[0],rootOrigin[1],root.getWidth(),root.getHeight(),power.getWidth(),power.getHeight(),gap,gap);
                if(position==null){hiddenPowerTargets.put(power,Boolean.TRUE);return;}
                x=position[0];y=position[1];
            }
        }
        if(power.getX()!=x)power.setX(x);
        if(power.getY()!=y)power.setY(y);
    }
    static void finishPowerVisibility(View power) {
        if(Boolean.TRUE.equals(hiddenPowerTargets.get(power)))power.setVisibility(View.INVISIBLE);
    }
    static int hideExtras(ViewGroup root,java.util.Map<View,Integer> original) {
        int changed=0;
        for(String tag:new String[]{"flyctl-qt","flyctl-qt-b","openfcc-battery-readout"}) {
            View view=root.findViewWithTag(tag);
            if(view==null || view==root || original.containsKey(view))continue;
            original.put(view,view.getVisibility());
            if(view.getVisibility()==View.VISIBLE){view.setVisibility(View.INVISIBLE);changed++;}
        }
        return changed;
    }
    static void hudHidden(Activity a,ViewGroup root,boolean hidden) {
        call(a,"app.openfcc.battery.BatteryOverlay",hidden?"detach":"attach",new Class<?>[]{ViewGroup.class},root);
    }
    static void radioUpdated(Context c,boolean fcc) {
        SharedPreferences.Editor edit=c.getSharedPreferences("mod_settings",0).edit();
        if(fcc)edit.putString("region","US");else edit.remove("region");
        edit.apply();
        try {
            java.lang.reflect.Field cached=Class.forName("flysettings.S",false,c.getClassLoader()).getDeclaredField("sRegion");
            cached.setAccessible(true);cached.set(null,null);
        } catch(ReflectiveOperationException|RuntimeException|LinkageError error){Log.e(TAG,"region_cache_clear_failed",error);}
    }
    static void addMenu(Activity activity,LinearLayout panel) {
        AdvancedSectionMenu.addEntry(activity,panel);
    }
}
