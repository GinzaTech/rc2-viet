package local.rc2.hud;
import uav.sdk.keyvalue.UAVKeyManager;
import uav.sdk.keyvalue.callback.IGetCallback;
import uav.sdk.keyvalue.key.UAVKey;
public final class NativeAircraftTest {
    static void check(boolean yes,String why) { if(!yes) throw new AssertionError(why); }
    static final class Reply implements LedJob.Reply<GroundGate> {
        boolean active=true; int calls;
        public boolean active() { return active; }
        public void success(GroundGate gate) { calls++; }
        public void failure(String message) { calls++; }
    }
    public static void main(String[] args) {
        NativeAircraft aircraft=new NativeAircraft(NativeAircraftTest.class.getClassLoader());
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
}
