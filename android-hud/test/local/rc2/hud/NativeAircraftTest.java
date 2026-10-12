package local.rc2.hud;
import uav.sdk.keyvalue.UAVKeyManager;
import uav.sdk.keyvalue.callback.IGetCallback;
import uav.sdk.keyvalue.key.UAVKey;
import uav.midware.data.model.P3.DataOsdGetPushCommon;
public final class NativeAircraftTest {
    static void check(boolean yes,String why) { if(!yes) throw new AssertionError(why); }
    static final class Reply implements LedJob.Reply<GroundGate> {
        boolean active=true; int calls; GroundGate gate;
        public boolean active() { return active; }
        public void success(GroundGate gate) { calls++; this.gate=gate; }
        public void failure(String message) { calls++; }
    }
    public static void main(String[] args) {
        NativeAircraft aircraft=new NativeAircraft(NativeAircraftTest.class.getClassLoader());
        if(args.length>0 && "guards".equals(args[0])) {
            guards(aircraft); System.out.println("native_aircraft_guards_passed"); return;
        }
        UAVKeyManager.hold=true;
        Reply reply=new Reply(); aircraft.readGround(reply);
        IGetCallback connection=UAVKeyManager.pending; UAVKey key=UAVKeyManager.pendingKey;
        reply.active=false; connection.b(key,true);
        check(UAVKeyManager.reads.size()==1,"cancel before connection callback starts no flight read");

        UAVKeyManager.reads.clear(); reply=new Reply(); aircraft.readGround(reply);
        connection=UAVKeyManager.pending; key=UAVKeyManager.pendingKey;
        connection.b(key,true); IGetCallback flying=UAVKeyManager.pending; UAVKey flightKey=UAVKeyManager.pendingKey;
        connection.b(key,true); connection.a(key,1,"late error");
        check(UAVKeyManager.reads.size()==2,"duplicate intermediate callback accepted once");
        reply.active=false; flying.b(flightKey,false);
        check(UAVKeyManager.reads.size()==2,"cancel before flying callback starts no motor read");

        UAVKeyManager.reads.clear(); reply=new Reply(); aircraft.readGround(reply);
        connection=UAVKeyManager.pending; key=UAVKeyManager.pendingKey;
        connection.a(key,1,"failure"); connection.b(key,true);
        check(reply.calls==1 && UAVKeyManager.reads.size()==1,"success after failure cannot resume chain");
        System.out.println("native_aircraft_passed");
    }
    private static void guards(NativeAircraft aircraft) {
        UAVKeyManager.reset();
        UAVKeyManager.cache.put("Connection",true); UAVKeyManager.cache.put("IsFlying",false);
        UAVKeyManager.cache.put("AreMotorsOn",false);
        check(aircraft.snapshot().allowed(),"valid fresh ground cache retained");
        Reply reply=new Reply(); aircraft.readGround(reply);
        check(reply.calls==1 && reply.gate.allowed(),"fresh GET plus valid OSD gate retained");
        check(UAVKeyManager.reads.equals(java.util.Arrays.asList("Connection","IsFlying","AreMotorsOn")),
            "semantic ground GET order retained");
        check(UAVKeyManager.subIndex==65534,"ground wildcard address retained");
        DataOsdGetPushCommon.lost=true; check(!aircraft.snapshot().allowed(),"stale OSD rejected");
        reply=new Reply(); aircraft.readGround(reply); check(!reply.gate.allowed(),"fresh GET cannot bypass stale OSD");
        DataOsdGetPushCommon.lost=false; DataOsdGetPushCommon.got=false;
        check(!aircraft.snapshot().allowed(),"missing OSD receipt rejected"); DataOsdGetPushCommon.got=true;
        for(int length:new int[]{35,-1}) {
            DataOsdGetPushCommon.length=length; check(!aircraft.snapshot().allowed(),"invalid OSD frame rejected");
        }
        DataOsdGetPushCommon.length=36; DataOsdGetPushCommon.motors=true;
        check(!aircraft.snapshot().allowed(),"OSD running motors rejected"); DataOsdGetPushCommon.motors=false;
        UAVKeyManager.cache.put("Connection",false); check(!aircraft.snapshot().allowed(),"disconnected aircraft rejected");
        UAVKeyManager.cache.put("Connection",true); UAVKeyManager.cache.put("IsFlying",true);
        check(!aircraft.snapshot().allowed(),"flying aircraft rejected"); UAVKeyManager.cache.put("IsFlying",false);
        UAVKeyManager.cache.put("AreMotorsOn",true); check(!aircraft.snapshot().allowed(),"SDK motors rejected");
        UAVKeyManager.cache.put("AreMotorsOn",false); UAVKeyManager.cache.put("IsFlying",null);
        check(!aircraft.snapshot().allowed(),"missing flight state rejected");
        reply=new Reply(); aircraft.readGround(reply); check(reply.gate!=null && !reply.gate.allowed(),"unknown GET value fails closed");
        UAVKeyManager.cache.put("IsFlying",false); UAVKeyManager.cache.put("AreMotorsOn","false");
        check(!aircraft.snapshot().allowed(),"untyped motor state rejected");
        UAVKeyManager.cache.put("AreMotorsOn",false); UAVKeyManager.throwCache=true;
        check(!aircraft.snapshot().allowed(),"cache exception fails closed");
        UAVKeyManager.throwCache=false;
    }
}
