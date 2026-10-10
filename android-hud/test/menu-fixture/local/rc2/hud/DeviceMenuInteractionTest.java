package local.rc2.hud;

import android.app.Activity;
import android.app.AlertDialog;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.TextView;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** Drives the real menu via its public attach/dispose and actual UI listeners. */
public final class DeviceMenuInteractionTest {
    private static void require(boolean value,String message) {
        if(!value) throw new AssertionError(message);
    }
    private static String text(TextView view) { return view.getText().toString(); }
    private static List<View> widgets(View root) {
        List<View> result=new ArrayList<>(); result.add(root);
        if(root instanceof ViewGroup) {
            ViewGroup group=(ViewGroup)root;
            for(int i=0;i<group.getChildCount();i++) result.addAll(widgets(group.getChildAt(i)));
        }
        return result;
    }
    private static Button groupButton(AlertDialog dialog,String group) {
        for(View view:widgets(dialog.view)) if(view instanceof Button) {
            Button button=(Button)view;
            String description=String.valueOf(button.getContentDescription());
            if(description.toLowerCase(Locale.ROOT).startsWith("led "+group.toLowerCase(Locale.ROOT)) || text(button).startsWith(group)) return button;
        }
        throw new AssertionError("missing LED "+group+" control");
    }
    private static Button button(AlertDialog dialog,String label) {
        for(View view:widgets(dialog.view)) if(view instanceof Button && text((Button)view).equals(label)) return (Button)view;
        throw new AssertionError("missing button "+label);
    }
    private static String visibleText(AlertDialog dialog) {
        StringBuilder result=new StringBuilder();
        for(View view:widgets(dialog.view)) if(view instanceof TextView && view.isShown()) result.append(text((TextView)view)).append(" | ");
        return result.toString().toLowerCase(Locale.ROOT);
    }
    private static String snapshot(AlertDialog dialog) {
        StringBuilder result=new StringBuilder();
        for(View view:widgets(dialog.view)) {
            result.append(view.mutations).append(':').append(view.isEnabled()).append(':').append(view.isSelected()).append(':')
                .append(view.getContentDescription()).append(':').append(view.getStateDescription());
            if(view instanceof TextView) result.append(':').append(text((TextView)view));
            result.append('|');
        }
        return result.toString();
    }
    private static final class Menu implements AutoCloseable {
        final Activity activity=new Activity(); final FrameLayout root=new FrameLayout(activity);
        final NativeRadio radio=new NativeRadio(); final ExternalOutput output=new ExternalOutput();
        final DeviceMenu menu; final View opener; final NativeLed led; AlertDialog dialog;
        Menu() { this(640); }
        Menu(int width) {
            root.setSize(width,360);
            NativeAircraft.gate=new GroundGate(true,true,false,false);
            AlertDialog.shown.clear();
            View anchor=new View(activity); anchor.setId(77); anchor.setSize(160,48); root.addView(anchor);
            menu=new DeviceMenu(activity,root,radio,output); led=NativeLed.instance; menu.attach();
            require(root.getChildCount()==2,"attach must add menu opener"); opener=root.getChildAt(1);
            require(opener.isShown(),"menu must be available beside home anchor"); open();
        }
        void open() { opener.userClick(); dialog=AlertDialog.latest(); require(dialog.isShowing(),"menu must open"); }
        Button front() { return groupButton(dialog,"Trước"); } Button rear() { return groupButton(dialog,"Sau"); }
        void actual(boolean front,boolean status,boolean rear) { led.actual(front,status,rear); activity.drain(); }
        void known() { actual(false,false,false); }
        void enabled(boolean enabled) {
            require(front().isEnabled()==enabled && rear().isEnabled()==enabled,"front/rear enabled state must follow known state and gate");
            require(button(dialog,"Bật hết").isEnabled()==enabled && button(dialog,"Tắt hết").isEnabled()==enabled,"explicit all ON/OFF enabled state must follow known state and gate");
        }
        void timeoutPending() {
            known();direct(front(),"toggleFront");led.mutationPending=true;led.complete(false);
            require(led.reads.size()==2,"timeout must request actual GET despite unresolved fence");
            actual(false,true,false);state(this,false,true,"tắt","một phần");enabled(false);
            require(!button(dialog,"Bật hết").isEnabled()&&!button(dialog,"Tắt hết").isEnabled(),"pending fence also disables explicit all ON/OFF");
            front().performClick();rear().performClick();
            button(dialog,"Bật hết").performClick();button(dialog,"Tắt hết").performClick();
            require(led.calls.size()==1,"known read while fence pending must still block new commands");
        }
        Runnable observer() {
            require(led.observers.size()==1,"attached menu owns exactly one LED reconciliation listener");
            return led.observers.get(0);
        }
        void direct(Button button,String expected) {
            int dialogs=AlertDialog.shown.size(),calls=led.calls.size(); button.userClick();
            require(AlertDialog.shown.size()==dialogs,"LED click must be direct, without a confirmation modal");
            require(led.calls.size()==calls+1,"one LED click must dispatch one backend command");
            require(led.calls.get(calls).equals(expected),"expected "+expected+", got "+led.calls.get(calls));
        }
        public void close() { menu.dispose(); activity.drain(); }
    }
    private static void state(Menu m,boolean front,boolean rear,String frontLabel,String rearLabel) {
        require(m.front().isSelected()==front,"front selection must match independently read front field");
        require(m.rear().isSelected()==rear,"rear selection must match independently read rear/status group");
        require(text(m.front()).toLowerCase(Locale.ROOT).equals("trước: "+frontLabel),"front button must expose actual state: "+text(m.front()));
        require(text(m.rear()).toLowerCase(Locale.ROOT).equals("sau: "+rearLabel),"rear button must expose actual state: "+text(m.rear()));
    }
    private static void scenario(String name,Menu m) {
        switch(name) {
        case "late-reconciliation":
            m.observer();m.timeoutPending();m.led.reconcile();
            require(m.led.reads.size()==3,"late reconciliation must perform fresh GET without reopening menu");m.enabled(false);
            require(m.led.calls.size()==1,"reconciliation event must never automatically issue a write");
            require(!m.front().isSelected()&&!m.rear().isSelected(),"released fence alone must not render guessed ON states");
            m.actual(true,false,false);state(m,true,false,"bật","tắt");m.enabled(true);
            require(m.led.calls.size()==1,"reconciliation read must never automatically issue a write");
            m.direct(m.rear(),"toggleRear");require(m.led.calls.size()==2,"only a new user press starts the second LED command");return;
        case "reconciliation-closed": {
            m.timeoutPending();m.dialog.dismiss();String before=snapshot(m.dialog);m.led.reconcile();m.activity.drain();
            require(m.led.reads.size()==2,"reconciliation must not GET while popup closed");
            require(snapshot(m.dialog).equals(before),"closed popup widgets must remain untouched by fence release");return;
        }
        case "reconciliation-disposed": {
            m.timeoutPending();Runnable captured=m.observer();m.menu.dispose();String before=snapshot(m.dialog);
            require(m.led.cancelled==1&&m.led.observers.isEmpty()&&m.led.observersAtClose==0,"cancel LED listener before backend close");
            m.led.reconcile();captured.run();m.activity.drain();
            require(m.led.reads.size()==2&&snapshot(m.dialog).equals(before),"even captured callback delivered after disposal must not GET or mutate UI");return;
        }
        case "reconciliation-reopen": {
            m.timeoutPending();AlertDialog old=m.dialog;old.dismiss();String before=snapshot(old);m.led.reconcile();
            require(m.led.reads.size()==2,"fence release while closed must not GET");m.open();
            require(m.led.reads.size()==3&&m.led.observers.size()==1,"reopening keeps one listener and starts its own GET");
            m.actual(false,true,true);state(m,false,true,"tắt","bật");m.enabled(true);
            require(snapshot(old).equals(before),"reopened menu must not mutate old widgets");
            m.led.publish();require(m.led.reads.size()==4,"existing observer must serve reopened menu");
            m.actual(true,false,false);state(m,true,false,"bật","tắt");return;
        }
        case "reconciliation-reopen-reading": {
            m.timeoutPending();AlertDialog old=m.dialog;old.dismiss();m.open();String before=snapshot(old);
            require(m.led.reads.size()==3,"reopened popup must begin its own inspect");m.led.reconcile();m.led.publish();
            require(m.led.reads.size()==3,"reconcile while reopened GET pending must not duplicate inspect");
            m.actual(true,false,false);state(m,true,false,"bật","tắt");m.enabled(true);
            require(snapshot(old).equals(before),"reconciliation during reopened GET leaves old popup untouched");return;
        }
        case "reconciliation-busy":
            m.observer();m.known();m.direct(m.front(),"toggleFront");m.led.mutationPending=true;m.led.reconcile();m.led.publish();
            require(m.led.reads.size()==1,"fence event while command busy must not start GET");m.enabled(false);
            require(!m.front().isSelected(),"event while busy must not optimistically select front");m.led.complete(true);
            require(m.led.reads.size()==2,"busy completion performs exactly one fresh GET");
            m.actual(true,false,false);state(m,true,false,"bật","tắt");m.enabled(true);return;
        case "reconciliation-reading":
            m.observer();m.led.publish();m.led.publish();
            require(m.led.reads.size()==1,"events during opening GET must not duplicate inspect");m.enabled(false);
            m.known();m.led.publish();require(m.led.reads.size()==2,"idle event must GET actual LED state");
            m.led.publish();require(m.led.reads.size()==2,"events during reconciliation GET must not duplicate inspect");
            m.actual(false,true,true);state(m,false,true,"tắt","bật");m.enabled(true);return;
        case "reconciliation-burst":
            m.timeoutPending();m.activity.defer=true;m.led.reconcile();for(int i=0;i<12;i++)m.led.publish();
            require(m.led.reads.size()==2,"observer must dispatch through UI queue");m.activity.drain();
            require(m.led.reads.size()==3,"queued reconciliation burst must coalesce behind one pending GET");
            m.actual(true,false,false);state(m,true,false,"bật","tắt");m.enabled(true);return;
        case "reconciliation-queued-dismiss": case "reconciliation-queued-dispose": {
            m.timeoutPending();m.activity.defer=true;m.led.reconcile();
            require(m.led.reads.size()==2,"reconciliation callback waits for UI dispatch");
            if(name.endsWith("dispose"))m.menu.dispose();else m.dialog.dismiss();
            String before=snapshot(m.dialog);m.activity.drain();
            require(m.led.reads.size()==2&&snapshot(m.dialog).equals(before),"queued event must recheck closed/disposed owner before GET and widget updates");return;
        }
        case "reconciliation-read-failure":
            m.timeoutPending();m.led.reconcile();require(m.led.reads.size()==3,"fence release starts fresh GET");
            m.led.reads.get(2).failure("reconciliation GET failed");m.enabled(false);
            require(visibleText(m.dialog).contains("chưa đọc được led"),"failed reconciliation read must show LED-specific failure feedback");
            m.led.publish();require(m.led.reads.size()==4,"subsequent idle observer event can recover failed GET");
            m.actual(false,true,true);state(m,false,true,"tắt","bật");m.enabled(true);return;
        case "unknown":
            require(m.led.reads.size()==1,"opening must request exactly one actual LED inspect");
            m.enabled(false);
            for(View view:widgets(m.dialog.view)) if(view instanceof Button) {
                String label=text((Button)view);
                if(label.equals("Bật hết")||label.equals("Tắt hết"))require(!view.isEnabled(),"all ON/OFF must also be disabled when unknown");
            }
            require(!m.front().isSelected()&&!m.rear().isSelected(),"unknown is not selected ON");
            m.front().userClick(); m.rear().userClick();m.front().performClick();m.rear().performClick();
            require(m.led.calls.isEmpty(),"unknown controls and handler guards must not write"); return;
        case "independent-front": m.actual(true,false,false); state(m,true,false,"bật","tắt"); m.enabled(true); return;
        case "independent-rear": m.actual(false,true,true); state(m,false,true,"tắt","bật"); m.enabled(true); return;
        case "all-off":
            require(!button(m.dialog,"Bật hết").isEnabled()&&!button(m.dialog,"Tắt hết").isEnabled(),"explicit ON/OFF must wait for actual GET");
            m.known();state(m,false,false,"tắt","tắt");m.enabled(true);
            require(button(m.dialog,"Bật hết").isEnabled()&&button(m.dialog,"Tắt hết").isEnabled(),"actual all-OFF read enables explicit actions");
            require(!button(m.dialog,"Bật hết").isSelected()&&!button(m.dialog,"Tắt hết").isSelected(),"explicit commands are actions, not optimistic state indicators");return;
        case "all-on": m.actual(true,true,true); state(m,true,true,"bật","bật"); m.enabled(true); return;
        case "partial-rear-status":
        case "partial-rear-tail":
            m.actual(false,name.endsWith("status"),name.endsWith("tail"));
            state(m,false,true,"tắt","một phần"); m.enabled(true);
            require(visibleText(m.dialog).contains("một phần"),"partial rear must visibly show mixed state"); return;
        case "front-repeat":
        case "rear-repeat": {
            boolean front=name.startsWith("front"); m.known();
            m.direct(front?m.front():m.rear(),front?"toggleFront":"toggleRear"); m.led.complete(true);
            m.actual(front,!front,!front); m.direct(front?m.front():m.rear(),front?"toggleFront":"toggleRear");
            require(m.led.calls.size()==2,"each press, including ON-to-OFF, must toggle"); return;
        }
        case "pending":
            m.actual(false,true,true); m.direct(m.front(),"toggleFront"); m.enabled(false);
            require(!m.front().isSelected()&&m.rear().isSelected(),"pending write must preserve actual selected state");
            require(text(m.front()).equalsIgnoreCase("Trước: Tắt")&&text(m.rear()).equalsIgnoreCase("Sau: Bật"),"pending must not optimistically change labels");
            require(m.led.reads.size()==1,"do not perform completion GET before backend answers"); return;
        case "success-readback":
        case "failure-readback":
            m.known(); m.direct(m.front(),"toggleFront");int toasts=android.widget.Toast.shows;
            m.led.complete(name.startsWith("success"));
            if(name.startsWith("failure"))require(android.widget.Toast.shows==toasts+1,"failed command retains visible failure Toast");
            require(m.led.reads.size()==2,"both completion and failure must request a fresh actual GET");
            m.enabled(false); require(!m.front().isSelected(),"command result alone cannot select ON");
            m.actual(false,true,true); state(m,false,true,"tắt","bật"); m.enabled(true); return;
        case "rejected-no-callback": case "rejected-inline-failure":
            m.known();m.led.accept=false;if(name.endsWith("failure"))m.led.inlineResult=false;
            m.direct(m.front(),"toggleFront");
            require(m.led.pending==null,"rejected submission must not retain any later command completion");
            require(m.led.reads.size()==2,"rejected submission must request exactly one fresh GET even with inline failure");
            m.actual(true,false,false);state(m,true,false,"bật","tắt");m.enabled(true);return;
        case "completion-get-failure":
            m.known();m.direct(m.front(),"toggleFront");m.led.complete(true);
            m.led.reads.get(1).failure("readback unavailable");m.enabled(false);
            require(!m.front().isSelected()&&!m.rear().isSelected(),"failed readback must not fabricate success");return;
        case "read-failure-reopen": {
            LedJob.Reply<LedJob.Lights> failed=m.led.reads.get(0);failed.failure("initial GET failure");m.enabled(false);
            m.dialog.dismiss();m.open();require(m.led.reads.size()==2,"reopen after read failure must issue fresh GET");m.enabled(false);
            String before=snapshot(m.dialog);failed.success(new LedJob.Lights(true,true,true,true));m.activity.drain();
            require(snapshot(m.dialog).equals(before),"failed previous menu callback must not answer new menu GET");
            m.actual(true,false,false);state(m,true,false,"bật","tắt");m.enabled(true);return;
        }
        case "inspect-failure":
            m.led.reads.get(0).failure("injected GET failure"); m.enabled(false);
            require(visibleText(m.dialog).contains("chưa"),"failed GET must visibly report unknown state");
            m.front().userClick();require(m.led.calls.isEmpty(),"GET failure must not allow a guessed write"); return;
        case "ground-disconnected": case "ground-motors": case "ground-flying": case "ground-stale":
            m.known();
            NativeAircraft.gate=name.endsWith("disconnected")?GroundGate.unknown():
                new GroundGate(true,!name.endsWith("stale"),name.endsWith("motors"),name.endsWith("flying"));
            m.radio.publish();m.enabled(false);m.front().userClick();m.rear().userClick();
            require(m.led.calls.isEmpty(),"unsafe/disconnected/stale aircraft must block LED");return;
        case "ground-click-race":
            m.known(); NativeAircraft.gate=GroundGate.unknown();
            m.front().performClick();m.rear().performClick();
            require(m.led.calls.isEmpty(),"handler must recheck ground when connection disappears after enable");return;
        case "rapid-click":
            m.known();m.direct(m.front(),"toggleFront");
            for(int i=0;i<12;i++){m.front().performClick();m.rear().performClick();}
            require(m.led.calls.size()==1,"rapid listener delivery must remain single-flight across LED groups");return;
        case "radio-busy": case "radio-locked":
            m.known();m.radio.value=new NativeRadio.Status(name.endsWith("busy"),name.endsWith("locked"),"");
            m.radio.publish();m.enabled(false);m.front().userClick();m.front().performClick();m.rear().performClick();
            require(m.led.calls.isEmpty(),"radio fence must block LED writes even with stale listener delivery");return;
        case "dismiss-read": {
            LedJob.Reply<LedJob.Lights> callback=m.led.reads.get(0);m.dialog.dismiss();String before=snapshot(m.dialog);
            require(!callback.active(),"dismiss must invalidate inspect callback"); callback.success(new LedJob.Lights(true,true,true,true));
            callback.failure("late failure");m.activity.drain();require(snapshot(m.dialog).equals(before),"late inspect must not touch closed widgets");return;
        }
        case "dismiss-write": {
            m.known();m.direct(m.front(),"toggleFront");m.dialog.dismiss();String before=snapshot(m.dialog);
            m.led.complete(true);m.activity.drain();require(m.led.reads.size()==1,"dismissed write callback must not launch GET");
            require(snapshot(m.dialog).equals(before),"late write callback must not update closed widgets");return;
        }
        case "queued-dismiss": {
            m.activity.defer=true;m.led.actual(true,true,true);m.dialog.dismiss();String before=snapshot(m.dialog);
            m.activity.drain();require(snapshot(m.dialog).equals(before),"UI callback queued before dismissal must recheck lifecycle");return;
        }
        case "queued-write-dismiss": {
            m.known();m.direct(m.front(),"toggleFront");m.activity.defer=true;m.led.complete(false);
            m.dialog.dismiss();String before=snapshot(m.dialog);m.activity.drain();
            require(snapshot(m.dialog).equals(before)&&m.led.reads.size()==1,"queued write completion must not touch dismissed widgets or GET");return;
        }
        case "ui-close": {
            Button close=null;
            for(View view:widgets(m.dialog.view))if(view instanceof Button && "Đóng menu".contentEquals(String.valueOf(view.getContentDescription())))close=(Button)view;
            require(close!=null,"menu must expose its close control");close.userClick();
            require(!m.dialog.isShowing()&&!m.led.reads.get(0).active(),"actual close button must dismiss and invalidate callback");return;
        }
        case "narrow-interactive":
            m.known();state(m,false,false,"tắt","tắt");m.direct(m.rear(),"toggleRear");return;
        case "reopen-stale-read": {
            LedJob.Reply<LedJob.Lights> old=m.led.reads.get(0);AlertDialog first=m.dialog;
            first.dismiss();m.open();String before=snapshot(m.dialog);old.success(new LedJob.Lights(true,true,true,true));
            m.activity.drain();require(snapshot(m.dialog).equals(before),"old revision callback must not populate reopened menu");
            m.actual(false,true,true);state(m,false,true,"tắt","bật");return;
        }
        case "dispose": case "dispose-pending": {
            LedJob.Reply<LedJob.Lights> callback=m.led.reads.get(0);
            if(name.endsWith("pending")){m.known();m.direct(m.front(),"toggleFront");}
            m.menu.dispose();String before=snapshot(m.dialog);
            require(!m.dialog.isShowing(),"dispose dismisses dialog");require(m.root.getChildCount()==1,"dispose removes menu button");
            require(m.root.getViewTreeObserver().listenerCount()==0,"dispose removes layout listener");
            require(m.radio.observers.isEmpty()&&m.output.observers.isEmpty(),"dispose removes backend observers");
            require(m.radio.cancelled==1&&m.output.cancelled==1,"dispose cancels both subscriptions");
            require(m.led.cancelled==1&&m.led.observers.isEmpty()&&m.led.observersAtClose==0,"dispose cancels LED listener before closing LED backend");
            require(m.led.closeCount==1&&ForearmParamProbe.instance.closeCount==1&&AirlinkInspection.instance.closeCount==1&&SdrRadioProbe.instance.closeCount==1,"dispose closes owned backend readers");
            callback.success(new LedJob.Lights(true,true,true,true));if(m.led.pending!=null)m.led.complete(false);
            m.radio.publish();m.output.publish();m.root.getViewTreeObserver().dispatchOnGlobalLayout();m.opener.performClick();m.activity.drain();
            require(snapshot(m.dialog).equals(before),"disposed menu ignores all late callbacks");
            require(m.led.reads.size()==1,"disposed opener/result must not request fresh reads");return;
        }
        case "explicit-all-on": case "explicit-all-off":
            m.known();m.direct(button(m.dialog,name.endsWith("on")?"Bật hết":"Tắt hết"),"requestAll:"+name.endsWith("on"));return;
        case "radio-confirmation": case "radio-restore-confirmation":
            m.known();boolean fcc=name.equals("radio-confirmation");int dialogs=AlertDialog.shown.size();button(m.dialog,fcc?"FCC":"Vùng gốc").userClick();
            require(AlertDialog.shown.size()==dialogs+1&&m.radio.calls.isEmpty(),"radio must retain explicit confirmation before dispatch");
            AlertDialog.latest().clickPositive();require(m.radio.calls.size()==1&&m.radio.calls.get(0)==fcc,"confirmed FCC must dispatch radio request");return;
        default: throw new AssertionError("unknown scenario "+name);
        }
    }
    public static void main(String[] args) {
        require(args.length==1,"one scenario required");
        try(Menu menu=new Menu(args[0].equals("narrow-interactive")?320:640)) {
            scenario(args[0],menu);
            if(args[0].startsWith("reconciliation-")) {
                int writes=args[0].equals("reconciliation-reading")?0:1;
                require(menu.led.calls.size()==writes,"reconciliation events/GET callbacks must not dispatch implicit LED commands");
            }
        }
        System.out.println("device_menu_passed:"+args[0]);
    }
}
