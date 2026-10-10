package local.rc2.hud;

import uav.sdk.keyvalue.UAVKeyManager;
import uav.midware.data.model.P3.DataFlycGetParams;
import uav.midware.data.model.P3.DataFlycSetParams;

/** Reflective adapter integration with independent fresh GET and verification responses. */
public final class NativeLedToggleTest {
    static void check(boolean yes,String why) { if(!yes)throw new AssertionError(why); }
    static byte[] frame(int raw) { return new byte[]{0,(byte)0xa2,0x59,(byte)0xce,(byte)0xed,(byte)raw}; }
    static void toggle(NativeLed led,boolean front,int baseline,int expected) {
        int[] results={0}; int gets=DataFlycGetParams.starts,sets=DataFlycSetParams.starts;
        NativeLed.Result result=(ok,message)->{
            check(ok,"actual matching readback required: "+message);
            check(!message.contains("SET"),"product message avoids transport jargon");results[0]++;
        };
        check(front?led.toggleFront(result):led.toggleRear(result),"toggle accepted");
        check(DataFlycGetParams.starts==gets+1 && DataFlycSetParams.starts==sets,"fresh parameter read first");
        DataFlycGetParams baselineRead=DataFlycGetParams.last;
        baselineRead.succeed(frame(baseline));
        check(DataFlycSetParams.starts==sets+1 && DataFlycSetParams.value.intValue()==expected,"selected mask written from fresh value");
        check(results[0]==0 && MutationFence.hardware().pending(),"ack alone does not report success or release");
        check(DataFlycGetParams.last!=baselineRead && DataFlycGetParams.starts==gets+2,"independent readback GET");
        DataFlycGetParams.last.succeed(frame(expected));
        check(results[0]==1 && !MutationFence.hardware().pending(),"actual readback releases and reports once");
    }
    static void explicitRequests(ClassLoader loader) {
        NativeLed led=new NativeLed(loader),contender=new NativeLed(loader);
        for(int group=0;group<3;group++) {
            int selected=group==0?33:group==1?6:39;
            int[] results={0}; int before=DataFlycSetParams.starts;
            NativeLed.Result result=(ok,message)->{check(ok,"explicit action verified");results[0]++;};
            check(group==0?led.request(false,result):group==1?led.requestRear(false,result):led.requestAll(false,result),"explicit pinned request admitted");
            int gets=DataFlycGetParams.starts;
            check(!contender.toggleRear((ok,message)->check(!ok,"busy")) && DataFlycGetParams.starts==gets,"explicit baseline excludes another group");
            DataFlycGetParams.last.succeed(frame(239));
            check(DataFlycSetParams.starts==before+1 && DataFlycSetParams.value.intValue()==(239&~selected),"explicit pinned mask preserves outside bits");
            check(results[0]==0 && MutationFence.hardware().pending(),"explicit success waits for readback");
            DataFlycGetParams.last.succeed(frame(239&~selected));
            check(results[0]==1 && !MutationFence.hardware().pending(),"explicit readback releases once");
        }
        int before=DataFlycSetParams.starts; led.request(false,(ok,message)->check(ok,"explicit no-op"));
        DataFlycGetParams.last.succeed(frame(206));
        check(DataFlycSetParams.starts==before && !MutationFence.hardware().pending(),"explicit no-op does not write");
        led.close(); contender.close();
    }
    static void freshInspect(ClassLoader loader) {
        NativeLed probe=new NativeLed(loader); UAVKeyManager.error=1;
        for(int raw:new int[]{237,206}) {
            int before=DataFlycGetParams.starts,sets=DataFlycSetParams.starts; int[] reads={0};
            probe.inspect(new LedJob.Reply<LedJob.Lights>() {
                public void success(LedJob.Lights actual) {
                    check(actual.front==((raw&33)==33) && actual.rear==((raw&2)!=0)
                        && actual.status==((raw&4)!=0) && actual.navigation==((raw&16)!=0),"initial state from fresh parameter response");
                    reads[0]++;
                }
                public void failure(String message) { throw new AssertionError(message); }
            });
            check(DataFlycGetParams.starts==before+1 && reads[0]==0,"initial state waits for fresh read");
            DataFlycGetParams.last.succeed(frame(raw));
            check(reads[0]==1 && DataFlycSetParams.starts==sets && !MutationFence.hardware().pending(),"initial inspection reads only");
        }
        UAVKeyManager.error=0; probe.close();
    }
    public static void main(String[] args) {
        UAVKeyManager.cache.put("Connection",true);
        UAVKeyManager.cache.put("IsFlying",false);
        UAVKeyManager.cache.put("AreMotorsOn",false);
        ClassLoader loader=NativeLedToggleTest.class.getClassLoader();
        explicitRequests(loader);
        freshInspect(loader);
        NativeLed led=new NativeLed(loader);
        // The SDK/UI cached flags disagree with every fresh baseline here.
        toggle(led,true,239,206); toggle(led,true,206,239);
        toggle(led,false,239,233); toggle(led,false,233,239);
        toggle(led,false,235,233); toggle(led,false,237,233);
        toggle(led,true,255,222);
        int[] results={0};
        led.toggleFront((ok,message)->results[0]++);
        int gets=DataFlycGetParams.starts;
        check(!led.toggleRear((ok,message)->check(!ok,"rear rejected during front baseline read")),"cross-job exclusion");
        check(DataFlycGetParams.starts==gets,"busy rear never reads same baseline");
        DataFlycGetParams late=DataFlycGetParams.last; int sets=DataFlycSetParams.starts;
        led.close(); late.succeed(frame(239));
        check(DataFlycSetParams.starts==sets && results[0]==0 && !MutationFence.hardware().pending(),"closed baseline read never writes or reports");
        check(!led.toggleFront((ok,message)->results[0]++) && !led.toggleRear((ok,message)->results[0]++),"closed toggles rejected");
        check(results[0]==0,"closed toggles suppress disposed result");
        check(!led.request(false,(ok,message)->results[0]++) && !led.requestRear(false,(ok,message)->results[0]++)
            && !led.requestAll(false,(ok,message)->results[0]++) && results[0]==0,"closed explicit APIs also suppress disposed results");
        NativeLed next=new NativeLed(NativeLedToggleTest.class.getClassLoader());
        check(!next.toggleFront(null) && !next.toggleRear(null) && !next.request(false,null)
            && !next.requestRear(false,null) && !next.requestAll(false,null),"all null callbacks rejected");
        toggle(next,false,200,206); next.close();
        check(UAVKeyManager.writes==0,"toggles exclusively use pinned forearm adapter");
        System.out.println("native_led_toggle_passed");
    }
}
