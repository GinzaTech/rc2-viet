package local.rc2.hud;

public final class GroundGateTest {
    public static void main(String[] args) {
        if(!new GroundGate(true,true,false,false).allowed()) throw new AssertionError("ground with stopped motors");
        if(new GroundGate(true,true,false,true).allowed()) throw new AssertionError("airborne");
        if(new GroundGate(true,true,true,false).allowed()) throw new AssertionError("armed motors");
        if(new GroundGate(false,true,false,false).allowed()) throw new AssertionError("invalid");
        if(new GroundGate(true,false,false,false).allowed()) throw new AssertionError("stale");
        if(new GroundGate(true,true,false,null).allowed()) throw new AssertionError("unknown flight state");
        if(GroundGate.unknown().allowed()) throw new AssertionError("missing telemetry");
        System.out.println("ground_gate_passed");
    }
}
