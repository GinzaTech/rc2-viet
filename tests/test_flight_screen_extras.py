"""Execute the production lifecycle bridge on inert Android-shaped JVM stubs.

This verifies that saved special-menu preferences cannot add flight-screen
controls or reappear after HUD restore. It does not verify Android rendering.
"""
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def flight_bridge(tmp_path_factory):
    stage = tmp_path_factory.mktemp("flight-extras")
    sources = {
        "android/R.java": "package android; public final class R { public static class id { public static final int content=1; } }",
        "android/util/Log.java": "package android.util; public class Log { public static int i(String t,String m){return 0;} public static int e(String t,String m,Throwable e){return 0;} }",
        "android/util/DisplayMetrics.java": "package android.util; public class DisplayMetrics { public float density=1; }",
        "android/content/res/Resources.java": "package android.content.res; public class Resources { public android.util.DisplayMetrics getDisplayMetrics(){return new android.util.DisplayMetrics();} }",
        "android/content/SharedPreferences.java": """package android.content;
            public interface SharedPreferences { boolean contains(String k); boolean getBoolean(String k,boolean d);
            String getString(String k,String d); java.util.Map<String,?> getAll(); Editor edit();
            interface Editor { Editor putBoolean(String k,boolean v); Editor putString(String k,String v); Editor remove(String k); void apply(); } }""",
        "android/content/Context.java": """package android.content; import java.util.*;
            public class Context { private final Map<String,Prefs> prefs=new HashMap<>();
            public ClassLoader getClassLoader(){return getClass().getClassLoader();}
            public android.content.res.Resources getResources(){return new android.content.res.Resources();}
            public SharedPreferences getSharedPreferences(String n,int m){return prefs.computeIfAbsent(n,k->new Prefs());}
            static class Prefs implements SharedPreferences,SharedPreferences.Editor { final Map<String,Object> v=new HashMap<>();
            public boolean contains(String k){return v.containsKey(k);} public boolean getBoolean(String k,boolean d){return (Boolean)v.getOrDefault(k,d);}
            public String getString(String k,String d){return (String)v.getOrDefault(k,d);} public Map<String,?> getAll(){return v;}
            public SharedPreferences.Editor edit(){return this;} public SharedPreferences.Editor putBoolean(String k,boolean b){v.put(k,b);return this;}
            public SharedPreferences.Editor putString(String k,String b){v.put(k,b);return this;} public SharedPreferences.Editor remove(String k){v.remove(k);return this;}
            public void apply(){} } }""",
        "android/content/Intent.java": "package android.content; public class Intent {}",
        "android/app/Application.java": "package android.app; public class Application extends android.content.Context {}",
        "android/app/Activity.java": """package android.app; public class Activity extends android.content.Context {
            public android.view.View root; @SuppressWarnings("unchecked") public <T extends android.view.View>T findViewById(int i){return (T)root;} }""",
        "android/view/View.java": """package android.view; public class View {
            public static final int VISIBLE=0,INVISIBLE=4; protected final android.content.Context context;
            ViewGroup parent; Object tag; int visibility=0; float x,y;
            public View(android.content.Context c){context=c;} public Object getTag(){return tag;} public void setTag(Object t){tag=t;}
            public Object getParent(){return parent;} public boolean isShown(){return visibility==0;} public int getVisibility(){return visibility;}
            public void setVisibility(int v){visibility=v;} public int getWidth(){return 100;} public int getHeight(){return 50;}
            public android.content.res.Resources getResources(){return context.getResources();} public void getLocationOnScreen(int[] a){}
            public float getX(){return x;} public float getY(){return y;} public void setX(float f){x=f;} public void setY(float f){y=f;}
            @SuppressWarnings("unchecked") public <T extends View>T findViewWithTag(Object t){return t.equals(tag)?(T)this:null;} }""",
        "android/view/ViewGroup.java": """package android.view; import java.util.*; public class ViewGroup extends View {
            final List<View> children=new ArrayList<>(); public ViewGroup(android.content.Context c){super(c);}
            public void addView(View v){children.add(v);v.parent=this;} public void removeView(View v){children.remove(v);v.parent=null;}
            public int getChildCount(){return children.size();} public View getChildAt(int i){return children.get(i);}
            public <T extends View>T findViewWithTag(Object t){T v=super.findViewWithTag(t);if(v!=null)return v;
            for(View child:children){v=child.findViewWithTag(t);if(v!=null)return v;}return null;} }""",
        "android/widget/Button.java": "package android.widget; public class Button extends android.view.View { public Button(android.content.Context c){super(c);} }",
        "android/widget/LinearLayout.java": "package android.widget; public class LinearLayout extends android.view.ViewGroup { public LinearLayout(android.content.Context c){super(c);} }",
        "android/widget/Toast.java": "package android.widget; public class Toast { public static final int LENGTH_LONG=1; public static Toast makeText(android.content.Context c,String s,int l){return new Toast();} public void show(){} }",
        "android/os/Looper.java": "package android.os; public class Looper { public static Looper getMainLooper(){return new Looper();} }",
        "android/os/Handler.java": "package android.os; public class Handler { public Handler(Looper l){} public boolean post(Runnable r){r.run();return true;} }",
        "local/rc2/hud/HomeActionPlacement.java": "package local.rc2.hud; class HomeActionPlacement { static int[] place(int... v){return new int[]{0,0};} }",
        "local/rc2/hud/AdvancedSectionMenu.java": "package local.rc2.hud; class AdvancedSectionMenu { static int entries; static void addEntry(android.app.Activity a,android.widget.LinearLayout p){entries++;} }",
        "local/rc2/hud/NativeAircraft.java": "package local.rc2.hud; class NativeAircraft { NativeAircraft(ClassLoader c){} GroundGate snapshot(){return GroundGate.unknown();} }",
        "local/rc2/hud/NativeLed.java": "package local.rc2.hud; class NativeLed { NativeLed(ClassLoader c){} void close(){} void inspect(LedJob.Reply<LedJob.Lights> r){} boolean requestAll(boolean b,LedJob.Result r){return false;} }",
        "flyctl/Q.java": "package flyctl; public class Q { public static int attaches; public static void attach(android.app.Activity a){attaches++;} }",
        "flyctl/F.java": "package flyctl; public class F { public static int calls; public static void addToggles(android.view.View v){calls++;} }",
        "app/openfcc/battery/BatteryOverlay.java": """package app.openfcc.battery; public class BatteryOverlay {
            public static int attaches,detaches; public static boolean polling=true;
            public static void attach(android.view.ViewGroup v){attaches++;polling=true;}
            public static void detach(android.view.ViewGroup v){detaches++;polling=false;} }""",
        "rthguard/Guard.java": "package rthguard; public class Guard { public static int attaches; public static void attach(android.app.Activity a){attaches++;} }",
        "frtool/X.java": "package frtool; public class X { public static int attaches,arms; public static void attach(android.app.Activity a){attaches++;} public static void arm(){arms++;} }",
        "redfly/Power.java": "package redfly; public class Power { public static int binds; public static void bind(android.view.View a){binds++;} }",
        "local/rc2/hud/FlightExtrasTest.java": """package local.rc2.hud;
            import android.app.*; import android.view.*; import android.widget.*; import java.util.*;
            import app.openfcc.battery.BatteryOverlay;
            public class FlightExtrasTest {
            static class FlightRecordActivity extends Activity { }
            static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
            public static void main(String[] args){
                Activity a=new Activity(); ViewGroup root=new ViewGroup(a),nested=new ViewGroup(a); a.root=root;root.addView(nested);
                View stock=new View(a);stock.setTag("stock-gps-status");nested.addView(stock);
                for(String tag:new String[]{"flyctl-qt","flyctl-qt-b","openfcc-battery-readout","flyctl-qt"}){
                    View v=new View(a);v.setTag(tag);nested.addView(v);
                }
                for(String key:new String[]{"qt_gps","qt_atti","qt_atti_sport","qt_rc_gps","qt_tof_off","qt_vis","battery_cells_temperature_enabled"})
                    a.getSharedPreferences("mod_settings",0).edit().putBoolean(key,true).apply();
                Map<View,Integer> restore=new HashMap<>(); String scenario=args[0];
                if(scenario.equals("resume")){for(int i=0;i<3;i++)PortIntegration.resumed(a,2);
                    check(rthguard.Guard.attaches==3&&frtool.X.attaches==0,"preserve RTH without decrypt service");}
                else if(scenario.equals("hide"))PortIntegration.hudHidden(a,root,true);
                else if(scenario.equals("restore"))PortIntegration.hudHidden(a,root,false);
                else if(scenario.equals("pause"))PortIntegration.paused(a);
                else if(scenario.equals("restore-map"))check(PortIntegration.hideExtras(root,restore)==0,"no restorable special views");
                else if(scenario.equals("decrypt-disabled")){
                    Application app=new Application();
                    app.getSharedPreferences("mod_settings",0).edit().putBoolean("fr_decrypt",true).apply();
                    PortIntegration.install(app);
                    PortIntegration.resumed(a,1);PortIntegration.resumed(a,2);
                    FlightRecordActivity records=new FlightRecordActivity();records.root=new ViewGroup(records);
                    PortIntegration.resumed(records,0);PortIntegration.resumed(records,2);
                    check(frtool.X.arms==0&&frtool.X.attaches==0,"saved enabled decryption must never start or add a button");
                    check(rthguard.Guard.attaches==2,"preserve RTH lifecycle");return;
                }
                else if(scenario.equals("menu")){
                    PortIntegration.addMenu(a,new LinearLayout(a));PortIntegration.resumed(a,1);
                    check(AdvancedSectionMenu.entries==1&&redfly.Power.binds==1,"preserve home menu/power");
                    check(root.getChildCount()==1&&nested.getChildCount()==5,"home unrelated to flight cleanup");return;
                } else if(scenario.equals("compatibility-hook")){
                    PortHooks.initialize(new Application());PortHooks.gpsControls(stock);PortHooks.gpsControls(null);
                    check(flyctl.F.calls==0,"old host hook must be inert");return;
                }
                check(nested.getChildCount()==1&&nested.getChildAt(0)==stock,"remove every special view, preserve stock telemetry");
                check(stock.isShown()&&restore.isEmpty(),"stock HUD and restore map unchanged");
                check(flyctl.Q.attaches==0&&BatteryOverlay.attaches==0,"no attach even with saved settings enabled");
                if(!scenario.equals("restore-map"))check(BatteryOverlay.detaches>0&&!BatteryOverlay.polling,"cancel old subscriptions");
                PortIntegration.hudHidden(a,root,false);PortIntegration.resumed(a,2);
                check(nested.getChildCount()==1&&flyctl.Q.attaches==0&&BatteryOverlay.attaches==0,"remain absent after HUD restore and resume");
            } }""",
    }
    files = []
    for name, content in sources.items():
        path = stage / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        files.append(path)
    files += [ROOT / "android-hud/feature-port/local/rc2/hud" / f"{name}.java"
              for name in ("PortIntegration", "PortHooks")]
    files += [ROOT / "android-hud/src/local/rc2/hud" / f"{name}.java"
              for name in ("GroundGate", "LedJob")]
    classes = stage / "classes"
    classes.mkdir()
    result = subprocess.run(["javac", "-source", "8", "-target", "8", "-encoding", "UTF-8",
                             "-d", str(classes), *map(str, files)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return classes


@pytest.mark.parametrize("scenario", ["resume", "hide", "restore", "pause", "restore-map", "menu", "compatibility-hook", "decrypt-disabled"])
def test_special_controls_stay_off_flight_screen(flight_bridge, scenario):
    result = subprocess.run(["java", "-cp", str(flight_bridge), "local.rc2.hud.FlightExtrasTest", scenario],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
