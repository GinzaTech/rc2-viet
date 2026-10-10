package local.rc2.hud;

/** Read-only access to telemetry from this pinned Fly SDK. Missing APIs/data fail closed. */
final class NativeAircraft {
    private final ClassLoader loader;
    private final FlySdk sdk;
    NativeAircraft(ClassLoader loader) { this(loader,new FlySdk(loader)); }
    NativeAircraft(ClassLoader loader,FlySdk sdk) { this.loader=loader; this.sdk=sdk; }
    GroundGate snapshot() {
        try {
            Class<?> type=Class.forName("uav.midware.data.model.P3.DataOsdGetPushCommon",false,loader);
            Object osd=type.getMethod("getInstance").invoke(null);
            byte[] bytes=(byte[])type.getMethod("getRecData").invoke(osd);
            boolean valid=Boolean.TRUE.equals(type.getMethod("isGetted").invoke(osd)) && bytes!=null && bytes.length>=36;
            boolean fresh=!Boolean.TRUE.equals(type.getMethod("isPushLosed").invoke(osd));
            boolean motors=Boolean.TRUE.equals(type.getMethod("isMotorUp").invoke(osd));
            Boolean connected=readBoolean("he");
            Boolean flying=readBoolean("K");
            Boolean sdkMotors=readBoolean("J");
            valid=valid && Boolean.TRUE.equals(connected) && sdkMotors!=null && flying!=null;
            return new GroundGate(valid,fresh,motors || !Boolean.FALSE.equals(sdkMotors),flying);
        } catch (ReflectiveOperationException | RuntimeException | LinkageError error) { return GroundGate.unknown(); }
    }
    private Boolean readBoolean(String field) throws ReflectiveOperationException {
        Object value=sdk.cached(field);
        return value instanceof Boolean ? (Boolean)value : null;
    }
    void readGround(LedJob.Reply<GroundGate> reply) {
        bool("he",reply,connected->bool("K",reply,flying->bool("J",reply,motors->{
            GroundGate live=snapshot();
            reply.success(new GroundGate(live.valid && connected,live.fresh,live.motorsOn || motors,flying));
        })));
    }
    interface BooleanValue { void ready(boolean value); }
    private void bool(String field,LedJob.Reply<GroundGate> reply,BooleanValue next) {
        if(!reply.active()) return;
        java.util.concurrent.atomic.AtomicBoolean answered=new java.util.concurrent.atomic.AtomicBoolean();
        sdk.get(field,new LedJob.Reply<Object>() {
            public void failure(String message) {
                if(reply.active() && answered.compareAndSet(false,true)) reply.failure("Không đọc được trạng thái bay mới nhất. "+message);
            }
            public void success(Object value) {
                if(!reply.active() || !answered.compareAndSet(false,true)) return;
                if(!(value instanceof Boolean)) { reply.success(GroundGate.unknown()); return; }
                next.ready((Boolean)value);
            }
        });
    }
}
