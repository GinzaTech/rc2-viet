package local.rc2.hud;
import uav.sdk.keyvalue.UAVKeyManager;
import uav.sdk.keyvalue.key.UAVKey;
import uav.sdk.keyvalue.key.UAVKeyInfoBase;
import uav.sdk.keyvalue.value.flightcontroller.LEDsSettings;
public final class FlySdkTest {
    static void check(boolean ok,String reason) { if(!ok) throw new AssertionError(reason); }
    static final class Reply<T> implements LedJob.Reply<T> {
        T value; String error; int calls; boolean live=true;
        public boolean active() { return live; }
        public void success(T value) { this.value=value; calls++; }
        public void failure(String error) { this.error=error; calls++; }
    }
    public static void main(String[] args) throws Exception {
        FlySdk sdk=new FlySdk(FlySdkTest.class.getClassLoader());
        if(args.length!=0) {
            contract(sdk,args[0]);
            System.out.println("fly_sdk_contract_passed:"+args[0]);
            return;
        }
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
        check(Boolean.FALSE.equals(written.getFrontLEDsOn()) && Boolean.TRUE.equals(written.getStatusIndicatorOn())
            && Boolean.FALSE.equals(written.getRearLEDsOn()) && Boolean.TRUE.equals(written.getNavigationEnabled()),
            "constructor fields preserved");
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
    private static void rejected(Reply<?> reply) {
        check(reply.calls==1 && reply.value==null && reply.error!=null,"one normalized rejection");
        check(!reply.error.contains("PRIVATE"),"SDK details never escape");
    }
    private static void contract(FlySdk sdk,String scenario) throws Exception {
        UAVKeyManager.reset();
        if("canonical".equals(scenario)) { canonical(sdk); return; }
        if("led-matrix".equals(scenario)) { ledMatrix(sdk); return; }
        if("callbacks".equals(scenario)) { callbacks(sdk); return; }
        if("exceptions".equals(scenario)) { exceptions(sdk); return; }
        if("null-factory".equals(scenario)) UAVKey.nullFactory=true;
        if("reject-cache".equals(scenario)) {
            boolean failed=false;
            try { sdk.cached("he"); }
            catch(ReflectiveOperationException | RuntimeException | LinkageError expected) { failed=true; }
            check(failed && UAVKeyManager.cachedReads==0,"bad cache contract rejected before manager call");
            return;
        }
        if("reject-get".equals(scenario) || "null-factory".equals(scenario)) {
            Reply<Object> reply=new Reply<>(); sdk.get("he",reply); rejected(reply);
            check(UAVKeyManager.reads.isEmpty(),"bad GET contract rejected before dispatch");
            return;
        }
        if("reject-led".equals(scenario) || "reject-led-read".equals(scenario)) {
            Reply<LedJob.Lights> read=new Reply<>(); sdk.getLights(read); rejected(read);
            check(UAVKeyManager.reads.isEmpty(),"bad LED contract rejected before GET");
            if("reject-led-read".equals(scenario)) return;
        }
        if("reject-led".equals(scenario) || "reject-set".equals(scenario)) {
            Reply<Boolean> set=new Reply<>(); sdk.setLights(new LedJob.Lights(false,true,false,true),set);
            rejected(set); check(UAVKeyManager.writes==0,"bad SET contract rejected before dispatch");
            return;
        }
        throw new AssertionError("unknown scenario "+scenario);
    }
    private static void canonical(FlySdk sdk) throws Exception {
        String[][] names={{"he","Connection"},{"J","AreMotorsOn"},{"K","IsFlying"}};
        UAVKeyManager.value=true;
        for(String[] pair:names) for(String name:pair) {
            check(Boolean.TRUE.equals(sdk.cached(name)),"cached semantic identifier/alias");
            check(pair[1].equals(UAVKeyManager.field) && UAVKeyManager.subIndex==65534,"ground wildcard factory retained");
            Reply<Object> read=new Reply<>(); sdk.get(name,read);
            check(Boolean.TRUE.equals(read.value) && read.calls==1,"GET semantic identifier/alias");
            check(pair[1].equals(UAVKeyManager.field) && UAVKeyManager.subIndex==65534,"GET ground address retained");
        }
        UAVKeyManager.value=new LEDsSettings(true,false,true,false);
        for(String name:new String[]{"U2","LEDsSettings"}) {
            check(sdk.cached(name) instanceof LEDsSettings,"LED identifier/alias cached read");
            check("LEDsSettings".equals(UAVKeyManager.field) && UAVKeyManager.subIndex==0,"LED tuple remains 0/0/0");
        }
        Reply<LedJob.Lights> read=new Reply<>(); sdk.getLights(read);
        check(read.calls==1 && read.value.front && !read.value.status && read.value.rear && !read.value.navigation,
            "typed four LED fields decode with distinct values");
        Reply<Boolean> set=new Reply<>(); sdk.setLights(read.value.front(false),set);
        LEDsSettings value=(LEDsSettings)UAVKeyManager.written;
        check(set.calls==1 && Boolean.TRUE.equals(set.value) && UAVKeyManager.writes==1 && UAVKeyManager.subIndex==0,
            "exactly one typed LED write at retained tuple");
        check(Boolean.FALSE.equals(value.getFrontLEDsOn()) && Boolean.FALSE.equals(value.getStatusIndicatorOn())
            && Boolean.TRUE.equals(value.getRearLEDsOn()) && Boolean.FALSE.equals(value.getNavigationEnabled()),
            "front change preserves the other three typed flags");
        int count=UAVKeyManager.reads.size(); Reply<Object> unknown=new Reply<>(); sdk.get("AircraftName",unknown);
        rejected(unknown); check(UAVKeyManager.reads.size()==count,"Basic whitelist rejects other controls");
    }
    private static UAVKey otherKey(String identifier) throws Exception {
        return (UAVKey)UAVKey.class.getMethod("i",UAVKeyInfoBase.class).invoke(null,new UAVKeyInfoBase(identifier));
    }
    private static void ledMatrix(FlySdk sdk) {
        for(int mask=0;mask<16;mask++) {
            boolean front=(mask&1)!=0,status=(mask&2)!=0,rear=(mask&4)!=0,navigation=(mask&8)!=0;
            UAVKeyManager.reset(); UAVKeyManager.value=new LEDsSettings(front,status,rear,navigation);
            Reply<LedJob.Lights> read=new Reply<>(); sdk.getLights(read);
            check(read.calls==1 && read.error==null && read.value.front==front && read.value.status==status
                && read.value.rear==rear && read.value.navigation==navigation,"all 16 typed LED layouts decode independently");
            for(int target=0;target<2;target++) {
                Reply<Boolean> set=new Reply<>(); sdk.setLights(read.value.front(target==1),set);
                LEDsSettings value=(LEDsSettings)UAVKeyManager.written;
                check(set.calls==1 && Boolean.TRUE.equals(set.value) && UAVKeyManager.writes==target+1
                    && UAVKeyManager.subIndex==0,"one exact LED tuple write per requested front value");
                check(Boolean.valueOf(target==1).equals(value.getFrontLEDsOn()) && Boolean.valueOf(status).equals(value.getStatusIndicatorOn())
                    && Boolean.valueOf(rear).equals(value.getRearLEDsOn()) && Boolean.valueOf(navigation).equals(value.getNavigationEnabled()),
                    "all 32 writes preserve status/rear/navigation independently");
            }
        }
        for(int missing=0;missing<4;missing++) {
            Boolean[] flags={true,false,true,false}; flags[missing]=null;
            UAVKeyManager.reset(); UAVKeyManager.value=new LEDsSettings(flags[0],flags[1],flags[2],flags[3]);
            Reply<LedJob.Lights> read=new Reply<>(); sdk.getLights(read); rejected(read);
            check(UAVKeyManager.writes==0,"any missing LED flag prevents a typed value");
        }
        UAVKeyManager.reset(); Reply<Boolean> missing=new Reply<>(); sdk.setLights(null,missing); rejected(missing);
        check(UAVKeyManager.writes==0,"missing typed LED input never writes");
    }
    private static void callbacks(FlySdk sdk) throws Exception {
        Reply<Object> read=new Reply<>(); read.live=false; sdk.get("he",read);
        check(read.calls==0 && UAVKeyManager.reads.isEmpty(),"inactive GET is not submitted");
        Reply<Boolean> set=new Reply<>(); set.live=false; sdk.setLights(new LedJob.Lights(true,false,true,false),set);
        check(set.calls==0 && UAVKeyManager.writes==0,"inactive SET is not submitted");
        Reply<LedJob.Lights> lights=new Reply<>(); lights.live=false; sdk.getLights(lights);
        check(lights.calls==0 && UAVKeyManager.reads.isEmpty(),"inactive typed LED GET is not submitted");

        UAVKeyManager.hold=true; read=new Reply<>(); sdk.get("he",read);
        read.live=false; UAVKeyManager.pending.b(UAVKeyManager.pendingKey,true);
        UAVKeyManager.pending.a(UAVKeyManager.pendingKey,42,"PRIVATE");
        check(read.calls==0,"cancelled GET ignores late completion and errors");
        read=new Reply<>(); sdk.get("he",read);
        Object callback=UAVKeyManager.pending;
        check(callback.equals(callback) && !callback.equals(new Object()) && callback.hashCode()==System.identityHashCode(callback),
            "proxy Object methods remain usable");
        check("RC2SdkCallback".equals(callback.toString()),"proxy description is safe");
        UAVKeyManager.pending.b(UAVKeyManager.pendingKey,true);
        UAVKeyManager.pending.b(UAVKeyManager.pendingKey,false);
        UAVKeyManager.pending.a(UAVKeyManager.pendingKey,42,"PRIVATE");
        check(read.calls==1 && Boolean.TRUE.equals(read.value) && read.error==null,"GET terminal callback accepted once");
        read=new Reply<>(); sdk.get("he",read);
        UAVKeyManager.pending.a(UAVKeyManager.pendingKey,-9,"PRIVATE");
        UAVKeyManager.pending.b(UAVKeyManager.pendingKey,true); rejected(read);
        check(read.error.contains("-9"),"SDK numeric error retained");
        read=new Reply<>(); sdk.get("he",read);
        UAVKeyManager.pending.b(otherKey("IsFlying"),true); rejected(read);
        read=new Reply<>(); sdk.get("he",read); UAVKeyManager.pending.b(null,true); rejected(read);

        UAVKeyManager.holdSet=true; set=new Reply<>(); sdk.setLights(new LedJob.Lights(false,true,false,true),set);
        set.live=false; UAVKeyManager.pendingSet.b(UAVKeyManager.pendingSetKey);
        check(set.calls==0,"cancelled SET ignores late completion");
        set=new Reply<>(); sdk.setLights(new LedJob.Lights(true,false,true,false),set);
        UAVKeyManager.pendingSet.b(UAVKeyManager.pendingSetKey);
        UAVKeyManager.pendingSet.b(UAVKeyManager.pendingSetKey);
        UAVKeyManager.pendingSet.a(UAVKeyManager.pendingSetKey,42,"PRIVATE");
        check(set.calls==1 && Boolean.TRUE.equals(set.value) && set.error==null,"SET terminal callback accepted once");
        set=new Reply<>(); sdk.setLights(new LedJob.Lights(true,true,true,true),set);
        UAVKeyManager.pendingSet.b(otherKey("Connection")); rejected(set);

        lights=new Reply<>(); sdk.getLights(lights); lights.live=false;
        UAVKeyManager.pending.b(UAVKeyManager.pendingKey,new LEDsSettings(true,true,true,true));
        check(lights.calls==0,"typed LED adapter preserves cancellation");
    }
    private static void exceptions(FlySdk sdk) throws Exception {
        UAVKeyManager.throwCache=true; boolean failed=false;
        try { sdk.cached("he"); } catch(ReflectiveOperationException expected) { failed=true; }
        check(failed,"cache errors do not produce valid state"); UAVKeyManager.throwCache=false;
        UAVKeyManager.throwGet=true; Reply<Object> read=new Reply<>(); sdk.get("he",read); rejected(read);
        UAVKeyManager.throwGet=false; UAVKeyManager.value=true; UAVKeyManager.throwAfterCallback=true;
        read=new Reply<>(); sdk.get("he",read);
        check(read.calls==1 && Boolean.TRUE.equals(read.value) && read.error==null,"throw after GET completion cannot redeliver");
        UAVKeyManager.throwAfterCallback=false; UAVKeyManager.throwSet=true;
        Reply<Boolean> set=new Reply<>(); sdk.setLights(new LedJob.Lights(true,true,true,true),set); rejected(set);
        UAVKeyManager.throwSet=false; UAVKeyManager.throwAfterCallback=true;
        set=new Reply<>(); sdk.setLights(new LedJob.Lights(true,true,true,true),set);
        check(set.calls==1 && Boolean.TRUE.equals(set.value) && set.error==null,"throw after SET completion cannot redeliver");
    }
}
