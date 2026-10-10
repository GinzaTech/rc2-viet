package local.rc2.hud;

import android.app.Activity;
import android.app.Application;
import android.app.Presentation;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.hardware.display.DisplayManager;
import android.os.Handler;
import android.view.Display;
import android.view.PixelCopy;
import android.view.SurfaceControl;
import android.view.SurfaceView;
import android.widget.FrameLayout;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;

/** Executes production renderer/owner code; fixtures model Android APIs, not app policy. */
public final class OutputLifecycleTest {
    private static void check(boolean value,String message) {
        if(!value)throw new AssertionError(message);
    }
    private static void reset() {
        Handler.reset();Context.reset();Context.manager=new DisplayManager();
        android.os.Bundle.afterHasPreviewWrite=null;
        Presentation.created.clear();Bitmap.allocated.clear();SurfaceControl.reset();PixelCopy.reset();
    }
    private static SurfaceView preview(Context context,int viewW,int viewH,int bufferW,int bufferH) {
        SurfaceView value=new SurfaceView(context);value.setId(77);value.setSize(viewW,viewH);
        value.holder.frame=new Rect(0,0,bufferW,bufferH);return value;
    }
    private static final class Owned {
        final Activity activity=new Activity();
        final SurfaceView source=preview(activity,640,480,1280,720);
        final FrameLayout root=new FrameLayout(activity);
        final ExternalOutput output=new ExternalOutput(new Application());
        Owned() {
            root.addView(source,new FrameLayout.LayoutParams(-1,-1));
            output.setWithHud(false);output.resume(activity,root);
        }
        CleanPresentation current() {
            for(int i=Presentation.created.size()-1;i>=0;i--) {
                Presentation candidate=Presentation.created.get(i);
                if(candidate.isShowing())return (CleanPresentation)candidate;
            }
            throw new AssertionError("no live output window");
        }
    }
    private static CleanPresentation renderer(SurfaceView source,List<String> statuses) {
        CleanPresentation value=new CleanPresentation(new Activity(),new Display(3),source,statuses::add);
        value.show();return value;
    }
    private static CleanPresentation.Status statusCallback(CleanPresentation renderer) throws Exception {
        Field field=CleanPresentation.class.getDeclaredField("status");field.setAccessible(true);
        return (CleanPresentation.Status)field.get(renderer);
    }
    private static void transactionFailure() {
        List<String> statuses=new ArrayList<>();
        CleanPresentation value=renderer(preview(new Activity(),640,480,1280,720),statuses);
        Handler.drain();check(SurfaceControl.liveMirrors()==1,"baseline mirror must succeed first");
        SurfaceControl.failNextGeometry=true;
        value.surfaceChanged(((SurfaceView)((FrameLayout)value.content()).getChildAt(0)).getHolder(),0,640,360);
        Handler.drain();
        check(SurfaceControl.liveMirrors()==0,"failed mirror must be released");
        check(PixelCopy.pending.size()==1,"later transaction failure must reach public fallback");
        PixelCopy.complete(PixelCopy.SUCCESS);Handler.drain();
        check(statuses.get(statuses.size()-1).contains("5 fps"),"fallback must publish rendered result");
        value.dismiss();check(Bitmap.liveCount()==0,"completed fallback resources must be released");
    }
    private static void dismissBeforeStartup() {
        List<String> statuses=new ArrayList<>();
        CleanPresentation value=renderer(preview(new Activity(),640,360,1280,720),statuses);
        // Hold the already-dequeued callback: removeCallbacks alone cannot prevent it.
        Runnable dequeued=Handler.nextReady();check(dequeued!=null,"startup must be queued");
        value.dismiss();dequeued.run();Handler.drain();
        check(statuses.isEmpty(),"dismissed startup must remain silent");
        check(SurfaceControl.mirrors.isEmpty() && PixelCopy.submitted==0,"no renderer allocation after dismiss");
        check(Bitmap.liveCount()==0,"no leaked startup buffers");
    }
    private static void staleStatus() throws Exception {
        Owned owned=new Owned();Handler.drain();
        CleanPresentation old=owned.current();CleanPresentation.Status oldCallback=statusCallback(old);
        owned.output.setWithHud(true);String hudStatus=owned.output.statusText();
        oldCallback.changed("obsolete renderer error");
        check(hudStatus.equals(owned.output.statusText()),"old renderer must not overwrite HUD selection");
        owned.output.setWithHud(false);Handler.drain();
        check(owned.current()!=old,"new generation must own a different renderer");
        String newStatus=owned.output.statusText();oldCallback.changed("obsolete renderer success");
        check(newStatus.equals(owned.output.statusText()),"old renderer must not overwrite new renderer");
        owned.output.close();oldCallback.changed("post-close result");
        check(Presentation.liveWindows()==0,"closed owner cannot reopen");
    }
    private static void bufferGeometry() {
        CleanPresentation value=renderer(preview(new Activity(),640,480,1280,720),new ArrayList<>());
        Handler.drain();
        check(SurfaceControl.lastCrop.width()==1280 && SurfaceControl.lastCrop.height()==720,
            "mirror crop must use buffer frame, not 640x480 view size");
        check("0,0,640,360".equals(SurfaceControl.lastDestination.toString()),
            "16:9 buffer must fill 16:9 sink without view-aspect letterboxing");
        value.dismiss();
    }
    private static void sourceResizeForwarded() {
        Owned owned=new Owned();Handler.drain();int before=SurfaceControl.geometries;
        owned.source.holder.resize(960,720);Handler.drain();
        check(SurfaceControl.geometries>before,"source callback must forward to current renderer");
        check("0,0,960,720".equals(SurfaceControl.lastCrop.toString()),"updated buffer crop required");
        check("80,0,560,360".equals(SurfaceControl.lastDestination.toString()),"4:3 buffer must fit within sink");
        check(Presentation.created.size()==1,"source resize must not add a second window");
        owned.output.close();
    }
    private static void intentional(String cause) {
        Owned owned=new Owned();Handler.drain();int before=Presentation.created.size();
        if(cause.equals("hud"))owned.output.setWithHud(true);
        else if(cause.equals("pause"))owned.output.pause(owned.activity);
        else owned.output.close();
        Handler.drain();
        check(Presentation.liveWindows()==0,"intentional dismissal must remain closed: "+cause);
        check(Presentation.created.size()==before,"OnDismiss must not reopen intentional dismissal: "+cause);
        check(SurfaceControl.liveMirrors()==0,"intentional dismissal must release mirror");
        if(cause.equals("close"))check(Context.manager.listenerCount()==0,"close must unregister display callbacks");
        else owned.output.close();
    }
    private static void metrics(boolean presentationFirst) throws Exception {
        Owned owned=new Owned();Handler.drain();CleanPresentation old=owned.current();
        CleanPresentation.Status oldCallback=statusCallback(old);
        Context.manager.changeMetrics(presentationFirst);Handler.drain();
        check(Presentation.liveWindows()==1,"metrics cancellation must recover exactly one window");
        check(owned.current()!=old,"metrics change must replace stale display context");
        String current=owned.output.statusText();oldCallback.changed("old metrics renderer");
        check(current.equals(owned.output.statusText()),"metrics restart must invalidate old status");
        check(SurfaceControl.liveMirrors()==1,"only replacement mirror may remain live");
        owned.output.close();Handler.drain();
    }
    private static void unexpectedDismiss() {
        Owned owned=new Owned();Handler.drain();CleanPresentation old=owned.current();
        old.cancel();check(Presentation.liveWindows()==0,"system cancellation removes old window first");
        Handler.drain();
        check(Presentation.liveWindows()==1 && owned.current()!=old,"unexpected OnDismiss must recover");
        owned.output.close();
    }
    private static void staleDismiss() {
        Owned owned=new Owned();Handler.drain();CleanPresentation old=owned.current();
        old.cancel(); // Defer the old OnDismiss while a replacement becomes current.
        owned.output.setWithHud(true);owned.output.setWithHud(false);
        CleanPresentation replacement=owned.current();int before=Presentation.created.size();Handler.drain();
        check(owned.current()==replacement,"queued old dismissal must not clear replacement");
        check(Presentation.created.size()==before,"queued old dismissal must not create extra window");
        owned.output.close();
    }
    private static void inflightDismiss() {
        SurfaceControl.mirrorFails=true;
        List<String> statuses=new ArrayList<>();
        CleanPresentation value=renderer(preview(new Activity(),640,480,1920,1080),statuses);Handler.drain();
        Bitmap destination=PixelCopy.pending.get(0).destination;int callbacks=statuses.size();
        check(destination.getWidth()<=960 && destination.getHeight()<=540,"fallback buffers must be bounded");
        value.dismiss();check(!destination.isRecycled(),"in-flight destination cannot be recycled on dismiss");
        PixelCopy.complete(PixelCopy.SUCCESS);Handler.drain();Handler.advance(2000);
        check(Bitmap.liveCount()==0,"late completion must recycle deferred buffers");
        check(statuses.size()==callbacks,"late completion must not update dismissed output");
        check(PixelCopy.submitted==1,"late completion cannot restart copy loop");
    }
    private static void inflightResize() {
        SurfaceControl.mirrorFails=true;
        SurfaceView source=preview(new Activity(),640,480,1280,720);
        CleanPresentation value=renderer(source,new ArrayList<>());Handler.drain();
        Bitmap old=PixelCopy.pending.get(0).destination;source.holder.frame=new Rect(0,0,1024,768);
        value.sourceChanged();Handler.drain();
        check(!old.isRecycled() && PixelCopy.submitted==1,"resize must await native copy completion");
        PixelCopy.complete(PixelCopy.SUCCESS);Handler.drain();Handler.advance(200);
        check(old.isRecycled(),"old buffers must be released before resized request");
        Bitmap next=PixelCopy.pending.get(0).destination;
        check(next.getWidth()==720 && next.getHeight()==540,"resize must use new 4:3 buffer aspect");
        value.dismiss();PixelCopy.complete(PixelCopy.SUCCESS);Handler.drain();
        check(Bitmap.liveCount()==0,"resized buffers must be released after close completion");
    }
    private static void fallbackResize() {
        SurfaceControl.mirrorFails=true;
        SurfaceView source=preview(new Activity(),640,480,1280,720);
        CleanPresentation value=renderer(source,new ArrayList<>());Handler.drain();
        Bitmap old=PixelCopy.pending.get(0).destination;
        PixelCopy.complete(PixelCopy.SUCCESS);Handler.drain();
        source.holder.frame=new Rect(0,0,1024,768);value.sourceChanged();Handler.drain();
        check(old.isRecycled(),"idle resize must recycle old buffers");
        check(PixelCopy.pending.size()==1,"sourceChanged must restart exactly one copy");
        check(Bitmap.liveCount()==2,"only two resized buffers may remain live");
        value.dismiss();PixelCopy.complete(PixelCopy.SUCCESS);Handler.drain();
    }
    private static void surfaceRecreate() {
        CleanPresentation value=renderer(preview(new Activity(),640,360,1280,720),new ArrayList<>());
        Handler.drain();SurfaceView sink=(SurfaceView)((FrameLayout)value.content()).getChildAt(0);
        sink.holder.destroy();check(SurfaceControl.liveMirrors()==0,"sink destruction must release mirror");
        sink.holder.create();sink.holder.create();Handler.drain();
        check(SurfaceControl.liveMirrors()==1,"duplicate startup must not leak or replace live mirror");
        value.dismiss();check(SurfaceControl.liveMirrors()==0,"recreated mirror must be released");
    }
    private static void probeState(ExternalOutput output,boolean owner,boolean preview,boolean valid) {
        android.os.Bundle state=output.probe(false);
        check(state.getBoolean("has_activity")==owner,"diagnostic activity identity must match lifecycle");
        check(state.getBoolean("has_preview")==preview,"diagnostic preview must reflect current binding");
        check(state.getBoolean("surface_valid")==valid,"diagnostic surface validity must match binding");
    }
    private static void latePreview(boolean validAtInflation) {
        Activity owner=new Activity();FrameLayout root=new FrameLayout(owner);
        ExternalOutput output=new ExternalOutput(new Application());output.setWithHud(false);
        output.resume(owner,root);Handler.drain();
        probeState(output,true,false,false);
        check(root.getViewTreeObserver().listenerCount()==1,"resume must observe later inflation");
        check(Presentation.liveWindows()==0,"no renderer before preview exists");
        SurfaceView added=preview(owner,640,480,1280,720);
        added.holder.getSurface().valid=validAtInflation;
        root.addView(added,new FrameLayout.LayoutParams(-1,-1));
        root.getViewTreeObserver().dispatchOnGlobalLayout();Handler.drain();
        probeState(output,true,true,validAtInflation);
        check(added.holder.callbacks.size()==1,"new preview must own exactly one holder callback");
        if(!validAtInflation) {
            check(Presentation.liveWindows()==0,"inflated invalid surface must wait without rendering");
            added.holder.create();Handler.drain();probeState(output,true,true,true);
        }
        check(Presentation.liveWindows()==1 && SurfaceControl.liveMirrors()==1,
            "late preview must render without another Activity resume");
        output.close();Handler.drain();
    }
    private static void previewReplacement() throws Exception {
        Owned owned=new Owned();Handler.drain();CleanPresentation old=owned.current();
        CleanPresentation.Status obsolete=statusCallback(old);
        SurfaceView replacement=preview(owned.activity,640,360,1024,768);
        owned.root.removeView(owned.source);owned.root.addView(replacement,new FrameLayout.LayoutParams(-1,-1));
        owned.root.getViewTreeObserver().dispatchOnGlobalLayout();Handler.drain();
        check(!old.isShowing() && owned.current()!=old,"new source identity must replace old renderer");
        check(owned.source.holder.callbacks.isEmpty(),"old source callback must be removed");
        check(replacement.holder.callbacks.size()==1,"replacement source must have one callback");
        check(SurfaceControl.liveMirrors()==1,"replacement must release old native mirror");
        check("0,0,1024,768".equals(SurfaceControl.lastCrop.toString()),"renderer must use replacement buffer");
        String status=owned.output.statusText();obsolete.changed("old preview result");
        check(status.equals(owned.output.statusText()),"old source status must be fenced");
        owned.source.holder.destroy();Handler.drain();
        check(Presentation.liveWindows()==1,"destroying unbound source must not close replacement");
        owned.output.close();check(replacement.holder.callbacks.isEmpty(),"close must unbind replacement");
    }
    private static void previewRemoval() {
        Owned owned=new Owned();Handler.drain();owned.root.removeView(owned.source);
        owned.root.getViewTreeObserver().dispatchOnGlobalLayout();Handler.drain();
        probeState(owned.output,true,false,false);
        check(Presentation.liveWindows()==0 && SurfaceControl.liveMirrors()==0,"removal must stop owned renderer");
        check(owned.source.holder.callbacks.isEmpty(),"removal must unbind source callbacks");
        SurfaceView replacement=preview(owned.activity,640,360,1280,720);
        owned.root.addView(replacement,new FrameLayout.LayoutParams(-1,-1));
        owned.root.getViewTreeObserver().dispatchOnGlobalLayout();Handler.drain();
        check(Presentation.liveWindows()==1,"a later reinflation must still be discovered");
        owned.output.close();
    }
    private static void samePreviewLayout() {
        Owned owned=new Owned();Handler.drain();CleanPresentation current=owned.current();
        int windows=Presentation.created.size(),geometry=SurfaceControl.geometries;
        for(int n=0;n<20;n++)owned.root.getViewTreeObserver().dispatchOnGlobalLayout();
        Handler.drain();
        check(owned.current()==current && Presentation.created.size()==windows,"unchanged preview must retain renderer");
        check(SurfaceControl.geometries==geometry,"unchanged identity must not issue extra geometry updates");
        check(owned.source.holder.callbacks.size()==1,"layout callbacks must not duplicate holder binding");
        owned.output.close();
    }
    private static void layoutCleanup(boolean close) {
        Owned owned=new Owned();Handler.drain();
        check(owned.root.getViewTreeObserver().listenerCount()==1,"owner must have one layout listener");
        // An unrelated Activity pause must not remove the current owner's listener.
        owned.output.pause(new Activity());
        check(owned.root.getViewTreeObserver().listenerCount()==1,"foreign pause must preserve owner");
        if(close)owned.output.close();else owned.output.pause(owned.activity);
        check(owned.root.getViewTreeObserver().listenerCount()==0,"pause/close must remove layout listener");
        check(owned.source.holder.callbacks.isEmpty(),"pause/close must remove surface callback");
        int windows=Presentation.created.size();
        owned.root.getViewTreeObserver().dispatchOnGlobalLayout();owned.output.onGlobalLayout();Handler.drain();
        probeState(owned.output,false,false,false);
        check(Presentation.liveWindows()==0 && Presentation.created.size()==windows,"late layout cannot reactivate paused/closed owner");
        if(!close) {
            owned.output.resume(owned.activity,owned.root);Handler.drain();
            check(owned.root.getViewTreeObserver().listenerCount()==1,"resume must restore exactly one listener");
            check(Presentation.liveWindows()==1,"resumed owner must render again");owned.output.close();
        }
    }
    private static void layoutOwnerReplacement() {
        Owned owned=new Owned();Handler.drain();Activity nextOwner=new Activity();
        FrameLayout nextRoot=new FrameLayout(nextOwner);
        owned.output.resume(nextOwner,nextRoot);Handler.drain();
        check(owned.root.getViewTreeObserver().listenerCount()==0,"resume new owner must detach old observer");
        check(nextRoot.getViewTreeObserver().listenerCount()==1,"new owner must observe late preview");
        check(owned.source.holder.callbacks.isEmpty(),"owner replacement must unbind old preview");
        owned.root.getViewTreeObserver().dispatchOnGlobalLayout();Handler.drain();
        probeState(owned.output,true,false,false);check(Presentation.liveWindows()==0,"old root cannot reactivate video");
        SurfaceView next=preview(nextOwner,640,360,1280,720);
        nextRoot.addView(next,new FrameLayout.LayoutParams(-1,-1));
        nextRoot.getViewTreeObserver().dispatchOnGlobalLayout();Handler.drain();
        check(Presentation.liveWindows()==1,"new owner's late preview must render");
        owned.output.pause(owned.activity);
        check(Presentation.liveWindows()==1,"old owner pause must not stop new owner");
        owned.output.close();check(nextRoot.getViewTreeObserver().listenerCount()==0,"close must detach current observer");
    }
    private static void publicCopy() {
        SurfaceView source=preview(new Activity(),640,480,1920,1080);
        List<String> statuses=new ArrayList<>();
        // Mirror remains available: a successful mirror would wrongly bypass this copy.
        CleanPresentation value=new CleanPresentation(new Activity(),new Display(3),source,statuses::add,false);
        value.show();Handler.drain();
        check(SurfaceControl.mirrorCalls==0,"explicit public-copy mode must never invoke mirrorSurface");
        check(SurfaceControl.mirrors.isEmpty() && SurfaceControl.geometries==0,"public-copy mode must not allocate a mirror transaction");
        check(PixelCopy.pending.size()==1,"explicit public-copy mode must submit PixelCopy");
        Bitmap first=PixelCopy.pending.get(0).destination;
        check(first.getWidth()==960 && first.getHeight()==540,"public-copy buffers must remain bounded");
        PixelCopy.complete(PixelCopy.SUCCESS);Handler.drain();
        check(statuses.get(statuses.size()-1).contains("5 fps"),"public-copy completion must report copy renderer");
        source.holder.frame=new Rect(0,0,1024,768);value.sourceChanged();Handler.drain();
        check(SurfaceControl.mirrorCalls==0,"source resize must stay in public-copy mode");
        check(PixelCopy.pending.size()==1,"resize must submit only one replacement copy");
        check(first.isRecycled(),"public-copy resize must release old completed buffers");
        Bitmap pending=PixelCopy.pending.get(0).destination;value.dismiss();
        check(!pending.isRecycled(),"dismiss must retain pending public-copy destination");
        PixelCopy.complete(PixelCopy.SUCCESS);Handler.drain();Handler.advance(1000);
        check(Bitmap.liveCount()==0,"public-copy close must release deferred buffers");
        check(SurfaceControl.mirrorCalls==0 && PixelCopy.submitted==2,"dismiss must neither mirror nor restart copy");
    }
    private static void diagnosticSnapshot() {
        Owned owned=new Owned();Handler.drain();
        // Binder diagnostics may overlap main-thread pause. Force that ordering
        // at Bundle assembly without relying on host thread timing or sleeps.
        android.os.Bundle.afterHasPreviewWrite=()->owned.output.pause(owned.activity);
        android.os.Bundle observed=owned.output.probe(false);
        check(observed.getBoolean("has_preview"),"snapshot must retain the initially observed preview");
        check(observed.getBoolean("surface_valid"),"validity must use the same observed preview after field is cleared");
        check(Presentation.liveWindows()==0,"injected pause must actually clear live output");
        check(owned.source.holder.callbacks.isEmpty(),"injected pause must unbind original preview");
        probeState(owned.output,false,false,false);
        check(android.os.Bundle.afterHasPreviewWrite==null,"interleaving hook must be one-shot");
        owned.output.close();Handler.drain();
    }
    public static void main(String[] args) throws Exception {
        reset();String scenario=args[0];
        switch(scenario) {
            case "late-transaction-failure":transactionFailure();break;
            case "dismiss-before-startup":dismissBeforeStartup();break;
            case "stale-status":staleStatus();break;
            case "buffer-geometry":bufferGeometry();break;
            case "source-resize-forwarded":sourceResizeForwarded();break;
            case "intentional-hud":intentional("hud");break;
            case "intentional-pause":intentional("pause");break;
            case "intentional-close":intentional("close");break;
            case "metrics-external-first":metrics(false);break;
            case "metrics-presentation-first":metrics(true);break;
            case "unexpected-dismiss":unexpectedDismiss();break;
            case "stale-dismiss":staleDismiss();break;
            case "inflight-dismiss":inflightDismiss();break;
            case "inflight-resize":inflightResize();break;
            case "fallback-resize":fallbackResize();break;
            case "surface-recreate":surfaceRecreate();break;
            case "late-preview-inflate":latePreview(true);break;
            case "late-preview-surface":latePreview(false);break;
            case "preview-replacement":previewReplacement();break;
            case "preview-removal":previewRemoval();break;
            case "same-preview-layout":samePreviewLayout();break;
            case "layout-listener-pause":layoutCleanup(false);break;
            case "layout-listener-close":layoutCleanup(true);break;
            case "layout-owner-replacement":layoutOwnerReplacement();break;
            case "public-copy":publicCopy();break;
            case "diagnostic-snapshot":diagnosticSnapshot();break;
            default:throw new AssertionError("unknown scenario "+scenario);
        }
        System.out.println("output_lifecycle_passed:"+scenario);
    }
}
