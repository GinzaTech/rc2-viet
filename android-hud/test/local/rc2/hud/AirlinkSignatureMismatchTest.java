package local.rc2.hud;

import uav.sdk.keyvalue.UAVKeyManager;

public final class AirlinkSignatureMismatchTest {
    public static void main(String[] args) {
        AirlinkInspection p = new AirlinkInspection(AirlinkSignatureMismatchTest.class.getClassLoader());
        final int[] results = {0};
        p.inspect(result -> {
            if (result.sky.status != AirlinkInspection.Status.SDK_BINDING_ERROR
                || result.ground.status != AirlinkInspection.Status.SDK_BINDING_ERROR)
                throw new AssertionError("signature drift must remain unknown");
            results[0]++;
        });
        p.close();
        if (results[0] != 1 || !UAVKeyManager.calls.isEmpty() || UAVKeyManager.writes != 0)
            throw new AssertionError("signature mismatch cannot dispatch GET or write");
        System.out.println("airlink_signature_mismatch_passed");
    }
}
