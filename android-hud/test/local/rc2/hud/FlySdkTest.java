package local.rc2.hud;
import uav.sdk.keyvalue.UAVKeyManager;
import uav.sdk.keyvalue.value.flightcontroller.LEDsSettings;
public final class FlySdkTest {
    static void check(boolean ok,String reason) { if(!ok) throw new AssertionError(reason); }
    static final class Reply<T> implements LedJob.Reply<T> {
        T value; String error;
        public void success(T value) { this.value=value; }
        public void failure(String error) { this.error=error; }
    }
    public static void main(String[] args) throws Exception {
        FlySdk sdk=new FlySdk(FlySdkTest.class.getClassLoader());
        UAVKeyManager.value=true; check(sdk.cached("he").equals(true),"connection cached read");
        check(UAVKeyManager.field.equals("Connection"),"pinned connection key");
        check(UAVKeyManager.subIndex==65534,"working connection address unchanged");
        Reply<Object> flight=new Reply<>(); sdk.get("K",flight);
        check(flight.value.equals(true) && UAVKeyManager.field.equals("IsFlying"),"pinned flight read");
        UAVKeyManager.value=new LEDsSettings(true,true,false,true);
        Reply<LedJob.Lights> read=new Reply<>(); sdk.getLights(read);
        check(UAVKeyManager.subIndex==0,"LED address matches FlyModel infra tuple, not wildcard subIndex");
        check(read.error==null && read.value.front && read.value.status && !read.value.rear && read.value.navigation,
              "all LED fields correctly decoded");
        Reply<Boolean> set=new Reply<>(); sdk.setLights(read.value.front(false),set);
        LEDsSettings written=(LEDsSettings)UAVKeyManager.written;
        check(set.value.equals(true) && UAVKeyManager.field.equals("LEDsSettings") && UAVKeyManager.writes==1,"one pinned key write");
        check(!written.getFrontLEDsOn() && written.getStatusIndicatorOn() && !written.getRearLEDsOn()
            && written.getNavigationEnabled(),"constructor fields preserved");
        UAVKeyManager.cache.clear();
        UAVKeyManager.value=new LEDsSettings(true,null,true,true); read=new Reply<>(); sdk.getLights(read);
        check(read.value==null && read.error!=null,"unknown LED flag fails closed");
        UAVKeyManager.value="wrong type"; read=new Reply<>(); sdk.getLights(read);
        check(read.value==null && read.error!=null,"wrong SDK value rejected");
        UAVKeyManager.error=42; read=new Reply<>(); sdk.getLights(read);
        check(read.error.contains("42") && !read.error.contains("PRIVATE"),"safe useful error code");
        set=new Reply<>(); sdk.setLights(new LedJob.Lights(true,true,true,true),set);
        check(set.value==null && set.error!=null,"write failure not reported as success");
        Reply<Object> missing=new Reply<>(); sdk.get("missing",missing);
        check(missing.value==null && missing.error!=null,"missing mapping fails closed");
        System.out.println("fly_sdk_passed");
    }
}
