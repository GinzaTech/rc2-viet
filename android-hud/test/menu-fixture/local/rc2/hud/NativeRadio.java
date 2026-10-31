package local.rc2.hud;
import java.util.ArrayList;import java.util.List;
final class NativeRadio {
 interface Result {void finished(boolean success,String message);}interface Cancel {void cancel();}interface Observer {void changed(Status status);}
 static final class Status {final boolean busy,locked;final String message;Status(boolean busy,boolean locked,String message){this.busy=busy;this.locked=locked;this.message=message;}}
 Status value=new Status(false,false,""); final List<Observer> observers=new ArrayList<>();final List<Boolean> calls=new ArrayList<>();int cancelled;
 Status status(){return new Status(value.busy,value.locked || (NativeLed.instance!=null && NativeLed.instance.mutationPending),value.message);} GroundGate state(){return NativeAircraft.gate;}
 Cancel observe(Observer observer){observers.add(observer);observer.changed(value);return ()->{observers.remove(observer);cancelled++;};}
 void publish(){for(Observer observer:new ArrayList<>(observers))observer.changed(value);}
 boolean request(boolean fcc,Result result){calls.add(fcc);return true;}
}
