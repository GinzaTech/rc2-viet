package local.rc2.hud;

import android.content.Context;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

/** Root/own-UID private provider calls request bounded sequential GETs only. */
final class CapabilityAudit {
    private static CapabilityAudit current;
    private static final String[][] KEYS={
        {"FlightController","Connection"},{"FlightController","IsFlying"},{"FlightController","AreMotorsOn"},
        {"FlightController","RcDynamicHomePointExisted"},{"RemoteController","RcDynamicHomePointExisted"},
        {"RemoteController","IsSupportDynamicHome"},{"FlightController","DynamicHomePointEnabled"},
        {"FlightController","DynamicHomePointState"},{"FlightController","HomeLocationType"},
        {"FlightController","IsHomeLocationSet"},{"FlightAssistant","DynamicHomeEnable"},
        {"FlightAssistant","IsFixedSpeedNavigationSupport"},{"FlightAssistant","NavigationCanEnterFixedSpeed"},
        {"FlightAssistant","IsFixedSpeedSupport"},{"FlightController","TerrainFollowModeEnabled"},
        {"FlightController","TerrainFollowingMode"},{"FlightController","VirtualStickControlModeEnabled"},
        {"FlightController","NavigationModeEnabled"},{"Gimbal","PitchRangeExtensionEnabled"},
        {"Gimbal","GimbalVerticalShotEnabledIsSupport"},{"Gimbal","IsVerticalShotStandardSupport"},
        {"RemoteController","IsSupportRCControllerMode"},{"RemoteController","IsHdmiPresentationSupported"},
        {"Camera","CameraHDMIOutputState"},{"Camera","CameraOpticalZoomSupported"},
        {"Camera","ApertureIsSupport"},{"Camera","IsFixedApertureSupport"},{"Camera","CameraFocusModeSettable"}
    };
    private final Handler main=new Handler(Looper.getMainLooper());
    private final CapabilityReader reader;
    private final Map<String,String> results=new LinkedHashMap<>();
    private volatile boolean busy;
    private long started;
    private int finished;
    private CapabilityAudit(ClassLoader loader){reader=new CapabilityReader(loader);}
    static synchronized Bundle call(Context context,boolean start){
        if(current==null)current=new CapabilityAudit(context.getApplicationContext().getClassLoader());
        if(start&&!current.busy){
            CapabilityAudit job=current;
            synchronized(job){job.busy=true;job.finished=0;job.started=SystemClock.elapsedRealtime();job.results.clear();}
            job.main.post(()->job.read(0));
        }
        return current.snapshot();
    }
    private synchronized Bundle snapshot(){
        Bundle out=new Bundle();out.putBoolean("busy",busy);out.putInt("finished",finished);out.putInt("total",KEYS.length);
        out.putString("source","SDK_GET_only");out.putLong("elapsed_ms",started==0?0:SystemClock.elapsedRealtime()-started);
        for(Map.Entry<String,String> row:results.entrySet())out.putString(row.getKey(),row.getValue());
        return out;
    }
    private void read(int index){
        if(index==KEYS.length){synchronized(this){busy=false;}return;}
        String[] key=KEYS[index];String name=key[0]+"."+key[1];AtomicBoolean done=new AtomicBoolean();
        Runnable timeout=()->complete(index,name,"TIMEOUT",done);
        main.postDelayed(timeout,2500);
        reader.get(key[0],key[1],new LedJob.Reply<Object>(){
            public boolean active(){return !done.get();}
            public void failure(String message){main.post(()->{main.removeCallbacks(timeout);complete(index,name,message,done);});}
            public void success(Object value){
                String text;
                if(value instanceof Boolean)text="VALUE:"+value;
                else if(value instanceof Enum<?>)text="VALUE:"+((Enum<?>)value).name();
                else if(value instanceof Number&&Double.isFinite(((Number)value).doubleValue()))text="VALUE:"+value;
                else text="UNEXPECTED_TYPE";
                final String result=text;main.post(()->{main.removeCallbacks(timeout);complete(index,name,result,done);});
            }
        });
    }
    private void complete(int index,String name,String result,AtomicBoolean done){
        if(!done.compareAndSet(false,true))return;
        synchronized(this){results.put(name,result);finished=index+1;}
        main.post(()->read(index+1));
    }
}
