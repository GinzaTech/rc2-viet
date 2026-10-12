package local.rc2.hud;
import uav.sdk.keyvalue.UAVKeyManager;

/** Default radio factory uses the semantic SDK identity; never writes a radio. */
public final class SdkRadioIdentityTest {
    static void check(boolean value,String reason) { if(!value) throw new AssertionError(reason); }
    public static void main(String[] args) throws Exception {
        UAVKeyManager.reset();
        String serial="AIR3S123456789";
        UAVKeyManager.cache.put("SerialNumber",serial);
        SdkRadioSender.Factory factory=new SdkRadioSender.Factory(SdkRadioIdentityTest.class.getClassLoader());
        String identity=factory.identity();
        check(identity!=null && identity.matches("[0-9a-f]{64}"),"default factory resolves renamed SerialNumber");
        check(UAVKeyManager.field.equals("SerialNumber") && UAVKeyManager.subIndex==65534,
              "read identity through semantic stock key at its retained tuple");
        factory.remember(identity,0);
        check(Integer.valueOf(0).equals(factory.original(identity)),"radio baseline bound to actual aircraft");
        UAVKeyManager.cache.put("SerialNumber","OTHER123456");
        check(!identity.equals(factory.identity()) && factory.original(factory.identity())==null,
              "new aircraft cannot receive the previous baseline");
        UAVKeyManager.cache.put("SerialNumber","bad serial!");
        check(factory.identity()==null && factory.original(factory.identity())==null,"invalid identity is rejected");
        check(UAVKeyManager.writes==0,"identity checks never write any SDK key");
        System.out.println("sdk_radio_identity_passed");
    }
}
