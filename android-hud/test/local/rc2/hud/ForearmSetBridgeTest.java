package local.rc2.hud;
import uav.midware.data.model.P3.DataFlycSetParams;
public final class ForearmSetBridgeTest {
    static final class Reply implements ForearmLedJob.WriteReply {
        boolean active=true,allow=true;
        int begins,successes,failures;
        public boolean active() { return active; }
        public boolean submit(ForearmLedJob.Submission action) throws ReflectiveOperationException {
            begins++; if(!allow)return false; action.run();return true;
        }
        public void success(Boolean value) { if(!Boolean.TRUE.equals(value))throw new AssertionError(); successes++; }
        public void failure(String value) {
            if(value.contains("PRIVATE"))throw new AssertionError("private error leaked");
            if(value.contains("SET"))throw new AssertionError("product error exposes transport jargon");
            failures++;
        }
    }
    static void check(boolean value,String message) { if(!value)throw new AssertionError(message); }
    public static void main(String[] args) {
        ClassLoader loader=ForearmSetBridgeTest.class.getClassLoader();
        Reply good=new Reply(); NativeForearmLed.writeRaw(loader,206,good);
        check(good.begins==1 && good.successes==1 && good.failures==0,"one dispatch one completion");
        check(DataFlycSetParams.name.equals(ForearmParamProbe.NAME) && DataFlycSetParams.value.intValue()==206,"fixed parameter and target");
        int before=DataFlycSetParams.starts;
        Reply cancelled=new Reply(); cancelled.active=false; NativeForearmLed.writeRaw(loader,239,cancelled);
        Reply invalid=new Reply(); NativeForearmLed.writeRaw(loader,256,invalid);
        Reply denied=new Reply(); denied.allow=false; NativeForearmLed.writeRaw(loader,239,denied);
        check(DataFlycSetParams.starts==before && cancelled.begins==0 && invalid.failures==1 && denied.begins==1,"no SET before active dispatch");
        for(String mode:new String[]{"failure","throw"}) {
            DataFlycSetParams.mode=mode;
            Reply reply=new Reply(); NativeForearmLed.writeRaw(loader,239,reply);
            check(reply.begins==1 && reply.successes==0 && reply.failures==1,"failure surfaced once");
        }
        DataFlycSetParams.mode="wrongThenTrue";
        Reply malformed=new Reply(); NativeForearmLed.writeRaw(loader,239,malformed);
        check(malformed.successes==1 && malformed.failures==0,"ignore foreign callback before genuine callback");
        System.out.println("forearm_set_bridge_passed");
    }
}
