package local.rc2.hud;

import uav.sdk.keyvalue.UAVKeyManager;
import uav.midware.data.model.P3.DataFlycGetParams;
import uav.midware.data.model.P3.DataFlycSetParams;

public final class NativeLedPrepFailureTest {
    static void check(boolean yes,String why) { if(!yes)throw new AssertionError(why); }
    public static void main(String[] args) {
        UAVKeyManager.cache.put("Connection",true);UAVKeyManager.cache.put("IsFlying",false);UAVKeyManager.cache.put("AreMotorsOn",false);
        ClassLoader parent=NativeLedPrepFailureTest.class.getClassLoader();
        for(boolean failGet:new boolean[]{true,false}) {
            ClassLoader loader=failGet?parent:new ClassLoader(parent) {
                protected Class<?> loadClass(String name,boolean resolve) throws ClassNotFoundException {
                    if(name.equals("uav.midware.data.model.P3.DataFlycSetParams")) throw new ClassNotFoundException(name);
                    return super.loadClass(name,resolve);
                }
            };
            NativeLed led=new NativeLed(loader);int[] results={0},unlocks={0};
            NativeLed.Cancel observer=led.observe(()->unlocks[0]++);
            DataFlycGetParams.throwConstruct=failGet;int writes=DataFlycSetParams.starts;
            check(led.state().allowed(),"state comes from aircraft snapshot");
            led.request(false,(ok,message)->{check(!ok,"preparation failure is not success");results[0]++;});
            if(!failGet) {
                check(MutationFence.hardware().pending() && results[0]==0,"reserve while fresh read pending");
                DataFlycGetParams.last.succeed(new byte[]{0,(byte)0xa2,0x59,(byte)0xce,(byte)0xed,(byte)239});
            }
            check(results[0]==1 && !MutationFence.hardware().pending() && unlocks[0]==1,"uncommitted GET/write preparation failure releases and notifies once");
            check(DataFlycSetParams.starts==writes && UAVKeyManager.writes==0,"preparation never dispatches a write");
            observer.cancel();led.close();DataFlycGetParams.throwConstruct=false;
        }
        check(!UAVKeyManager.reads.contains("LEDsSettings"),"no typed LED GET dependency");
        System.out.println("native_led_preparation_failure_passed");
    }
}
