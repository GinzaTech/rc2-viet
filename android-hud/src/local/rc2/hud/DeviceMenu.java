package local.rc2.hud;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.graphics.drawable.ColorDrawable;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.ViewTreeObserver;
import android.view.Window;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

/** Small home-page controller menu; no recurring poll and no automatic aircraft/radio mutations. */
final class DeviceMenu implements ViewTreeObserver.OnGlobalLayoutListener {
    private static final int BACKGROUND=0xff171b22,SURFACE=0xff2a303a;
    private static final int FOREGROUND=0xfff4f6f9,MUTED=0xffb0b9c8,ACCENT=0xff80e1bf;
    private boolean wideMenu;
    private final Activity activity;
    private final FrameLayout root;
    private final View button;
    private final SharedPreferences options;
    private final NativeLed led;
    private final NativeAircraft aircraft;
    private final NativeRadio radio;
    private final ExternalOutput output;
    private final ForearmParamProbe forearm;
    private final AirlinkInspection airlink;
    private final SdrRadioProbe sdr;
    private final Rect bounds=new Rect();
    private final int[] origin=new int[2];
    private final int[] anchorOrigin=new int[2];
    private AlertDialog dialog;
    private AlertDialog confirmation;
    private TextView radioStatus;
    private TextView ledStatus;
    private TextView outputStatus;
    private Button[] ledActions;
    private Button[] outputActions;
    private Button[] radioActions;
    private LedJob.Lights lights;
    private boolean ledBusy;
    private boolean ledReading;
    private volatile int menuRevision;
    private volatile boolean menuOpen;
    private Integer forceFlag;
    private NativeRadio.Cancel radioWatch;
    private NativeLed.Cancel ledWatch;
    private ExternalOutput.Cancel outputWatch;
    private volatile boolean active;
    DeviceMenu(Activity activity, FrameLayout root,NativeRadio radio,ExternalOutput output) {
        this.activity=activity; this.root=root;
        this.radio=radio; this.output=output;
        forearm=new ForearmParamProbe(activity.getClassLoader());
        airlink=new AirlinkInspection(activity.getClassLoader());
        sdr=new SdrRadioProbe(activity.getClassLoader());
        options=activity.getSharedPreferences("local_rc2_hud",0);
        led=new NativeLed(activity.getClassLoader()); aircraft=new NativeAircraft(activity.getClassLoader());
        button=new View(activity) {
            final Paint ink=new Paint(Paint.ANTI_ALIAS_FLAG);
            protected void onDraw(Canvas canvas) {
                super.onDraw(canvas); ink.setColor(0xffffffff); ink.setStrokeWidth(getWidth()/22f);
                for(int n=0;n<3;n++) canvas.drawLine(getWidth()*.22f,getHeight()*(.3f+n*.2f),getWidth()*.78f,getHeight()*(.3f+n*.2f),ink);
            }
        };
    }
    private int dp(int size) { return Math.round(size*activity.getResources().getDisplayMetrics().density); }
    void attach() {
        active=true;
        FrameLayout.LayoutParams params=new FrameLayout.LayoutParams(dp(48),dp(48));
        button.setContentDescription("Menu RC: LED, HUD, xuất hình và radio");
        button.setClickable(true); button.setFocusable(true); button.setElevation(dp(8));
        button.setOnClickListener(v->show()); button.setVisibility(View.INVISIBLE);
        root.addView(button,params); root.getViewTreeObserver().addOnGlobalLayoutListener(this);
        ledWatch=led.observe(()->activity.runOnUiThread(()->{
            if(!active)return;
            if(menuOpen && !ledBusy && !ledReading)readLights(menuRevision);
            refreshControls();
        }));
        radioWatch=radio.observe(status->activity.runOnUiThread(()->{
            if(active) refreshControls();
        }));
        outputWatch=output.observe(()->activity.runOnUiThread(()->{
            if(active) refreshOutput();
        }));
        onGlobalLayout();
    }
    public void onGlobalLayout() {
        if(!active) return;
        View anchor=null;
        for(String name:new String[]{"main_page_ui_state_startfly_btn","main_page_ui_device_disconnect_state_button",
                "direct_enter_fpv_view","layout_direct_enter_fpv","connection_guide_enter_fpv_button"}) {
            int id=activity.getResources().getIdentifier(name,"id","dji.go.v5");
            View found=id==0?null:root.findViewById(id);
            if(found!=null && found.isShown() && found.getGlobalVisibleRect(bounds) && bounds.width()>dp(48)) { anchor=found; break; }
        }
        if(anchor==null) { button.setVisibility(View.INVISIBLE); return; }
        anchor.getLocationOnScreen(anchorOrigin); root.getLocationOnScreen(origin);
        int[] position=MenuPlacement.place(anchorOrigin[0],anchorOrigin[1],anchor.getHeight(),origin[0],origin[1],
            root.getWidth(),root.getHeight(),dp(48),dp(8),dp(8));
        int left=position[0],top=position[1];
        FrameLayout.LayoutParams params=(FrameLayout.LayoutParams)button.getLayoutParams();
        if(params.leftMargin!=left || params.topMargin!=top) { params.leftMargin=left; params.topMargin=top; button.setLayoutParams(params); }
        button.setVisibility(View.VISIBLE);
    }
    private TextView text(LinearLayout panel,String value,int size) {
        TextView label=new TextView(activity); label.setText(value); label.setTextSize(size);
        label.setTextColor(FOREGROUND); panel.addView(label); return label;
    }
    private TextView status(LinearLayout panel,String value) {
        TextView label=text(panel,value,12); label.setTextColor(MUTED);
        label.setMaxLines(2); label.setEllipsize(TextUtils.TruncateAt.END);
        label.setPadding(0,dp(4),0,0); label.setMinHeight(dp(18)); return label;
    }
    private LinearLayout control(LinearLayout panel,String title) {
        LinearLayout row=new LinearLayout(activity);
        row.setOrientation(wideMenu?LinearLayout.HORIZONTAL:LinearLayout.VERTICAL);
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);
        params.topMargin=dp(8); panel.addView(row,params);
        TextView heading=new TextView(activity); heading.setText(title); heading.setTextSize(13);
        heading.setTextColor(MUTED); heading.setGravity(Gravity.CENTER_VERTICAL);
        row.addView(heading,new LinearLayout.LayoutParams(wideMenu?dp(72):-1,wideMenu?dp(48):-2));
        LinearLayout area=new LinearLayout(activity); area.setOrientation(LinearLayout.VERTICAL);
        row.addView(area,new LinearLayout.LayoutParams(wideMenu?0:-1,-2,wideMenu?1:0));
        return area;
    }
    private Button[] actions(LinearLayout panel,String[] labels,String[] descriptions,Runnable[] tasks) {
        Button[] items=new Button[labels.length];
        int columns=wideMenu?labels.length:Math.min(2,labels.length);
        LinearLayout row=null;
        for(int index=0;index<labels.length;index++) {
            if(index%columns==0) {
                row=new LinearLayout(activity); row.setOrientation(LinearLayout.HORIZONTAL);
                LinearLayout.LayoutParams rowParams=new LinearLayout.LayoutParams(-1,dp(48));
                rowParams.topMargin=dp(index==0?0:8); panel.addView(row,rowParams);
            }
            Button item=new Button(activity); item.setText(labels[index]); item.setAllCaps(false);
            item.setTextSize(13); item.setMaxLines(2); item.setMinWidth(dp(48)); item.setMinimumWidth(dp(48));
            item.setMinHeight(dp(48)); item.setMinimumHeight(dp(48));
            item.setPadding(dp(4),dp(4),dp(4),dp(4)); item.setGravity(Gravity.CENTER);
            item.setContentDescription(descriptions[index]); item.setElevation(0);
            LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(0,dp(48),1);
            params.leftMargin=index%columns==0?0:dp(8); row.addView(item,params);
            Runnable task=tasks[index]; item.setOnClickListener(v->{if(active) task.run();});
            mark(item,false); items[index]=item;
        }
        return items;
    }
    private void mark(Button item,boolean selected) {
        if(item.getStateDescription()!=null && item.getBackground() instanceof RippleDrawable && item.isSelected()==selected) return;
        item.setSelected(selected); item.setStateDescription(selected?"Đã chọn":"Chưa chọn");
        item.setTextColor(new ColorStateList(new int[][]{{-android.R.attr.state_enabled},{}},
            new int[]{0xff9ba4b2,selected?ACCENT:FOREGROUND}));
        GradientDrawable fill=new GradientDrawable(); fill.setCornerRadius(dp(8));
        fill.setColor(selected?0xff203c33:SURFACE);
        item.setBackground(new RippleDrawable(ColorStateList.valueOf(0x3380e1bf),fill,null));
    }
    private boolean currentMenu(int revision) {
        return active && menuOpen && revision==menuRevision;
    }
    private void show() {
        if(!active) return;
        if(confirmation!=null) confirmation.dismiss();
        if(dialog!=null) dialog.dismiss();
        final int revision=++menuRevision;
        lights=null; ledReading=false; forceFlag=null;
        final int menuWidth=Math.min(dp(600),Math.max(dp(248),root.getWidth()-dp(32)));
        wideMenu=menuWidth>=dp(520);
        LinearLayout content=new LinearLayout(activity); content.setOrientation(LinearLayout.VERTICAL);
        GradientDrawable backdrop=new GradientDrawable(); backdrop.setColor(BACKGROUND); backdrop.setCornerRadius(dp(16));
        content.setBackground(backdrop); content.setClipToOutline(true);
        LinearLayout header=new LinearLayout(activity); header.setOrientation(LinearLayout.HORIZONTAL);
        header.setPadding(dp(16),dp(4),dp(8),0); content.addView(header,new LinearLayout.LayoutParams(-1,-2));
        TextView title=new TextView(activity); title.setText("Điều khiển"); title.setTextSize(18);
        title.setTextColor(FOREGROUND); title.setGravity(Gravity.CENTER_VERTICAL);
        header.addView(title,new LinearLayout.LayoutParams(0,dp(48),1));
        Button close=new Button(activity); close.setText("×"); close.setTextSize(24); close.setAllCaps(false);
        close.setPadding(0,0,0,0); close.setMinWidth(dp(48)); close.setMinimumWidth(dp(48));
        close.setMinHeight(dp(48)); close.setMinimumHeight(dp(48)); close.setElevation(0);
        close.setContentDescription("Đóng menu"); mark(close,false);
        close.setStateDescription(null);
        close.setOnClickListener(v->{if(dialog!=null)dialog.dismiss();});
        header.addView(close,new LinearLayout.LayoutParams(dp(48),dp(48)));
        LinearLayout panel=new LinearLayout(activity); panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(16),0,dp(16),dp(12));
        LinearLayout lightGroup=control(panel,"Đèn");
        ledActions=actions(lightGroup,new String[]{"Trước: …","Sau: …","Bật hết","Tắt hết"},
            new String[]{"LED trước: chưa xác định","LED sau: chưa xác định",
                "Bật LED trước và sau","Tắt toàn bộ LED trước và sau"},
            new Runnable[]{()->changeLed(0),()->changeLed(1),()->changeLed(2),()->changeLed(3)});
        ledStatus=status(lightGroup,ledBusy?"Đang đổi LED…":"Đang đọc LED…");
        LinearLayout hudGroup=control(panel,"HUD");
        CheckBox gesture=new CheckBox(activity); gesture.setText("Chạm 2 lần để ẩn / hiện"); gesture.setTextSize(14);
        gesture.setTextColor(FOREGROUND); gesture.setMinHeight(dp(48)); gesture.setMinimumHeight(dp(48));
        gesture.setButtonTintList(new ColorStateList(new int[][]{{android.R.attr.state_checked},{}},new int[]{ACCENT,MUTED}));
        gesture.setContentDescription("Chạm hai lần để ẩn hoặc hiện HUD trên màn hình bay");
        gesture.setChecked(options.getBoolean("double_tap",true));
        hudGroup.addView(gesture,new LinearLayout.LayoutParams(-1,dp(48)));
        gesture.setOnCheckedChangeListener((v,checked)->{
            if(currentMenu(revision)) options.edit().putBoolean("double_tap",checked).apply();
        });
        LinearLayout outputGroup=control(panel,"Xuất hình");
        outputActions=actions(outputGroup,new String[]{"Có HUD","Không HUD"},
            new String[]{"Xuất hình có HUD","Xuất hình không có HUD, giữ HUD trên tay cầm"},
            new Runnable[]{()->chooseOutput(true),()->chooseOutput(false)});
        outputStatus=status(outputGroup,output.statusText());
        LinearLayout radioGroup=control(panel,"Radio");
        radioActions=actions(radioGroup,new String[]{"FCC","Vùng gốc"},
            new String[]{"Yêu cầu cấu hình FCC","Khôi phục cấu hình radio ban đầu"},
            new Runnable[]{()->confirmRadio(true),()->confirmRadio(false)});
        radioStatus=status(radioGroup,"");
        ScrollView scroll=new ScrollView(activity); scroll.setFillViewport(false); scroll.addView(panel);
        content.addView(scroll,new LinearLayout.LayoutParams(-1,-2));
        AlertDialog opened=new AlertDialog.Builder(activity,AlertDialog.THEME_DEVICE_DEFAULT_DARK).create();
        opened.setView(content,0,0,0,0);
        dialog=opened;
        opened.setOnDismissListener(d->{
            if(dialog!=opened) return;
            menuOpen=false; ++menuRevision; dialog=null; ledStatus=null; radioStatus=null; outputStatus=null;
            ledActions=null; radioActions=null; outputActions=null; lights=null; ledReading=false;
            if(confirmation!=null) confirmation.dismiss();
        });
        opened.show();
        menuOpen=true;
        Window window=opened.getWindow();
        if(window!=null) { window.setBackgroundDrawable(new ColorDrawable(0x00000000)); window.setDimAmount(.72f); window.setLayout(menuWidth,-2); }
        refreshOutput(); refreshControls(); readLights(revision); inspectAirlink(revision);
    }
    private void chooseOutput(boolean withHud) {
        output.setWithHud(withHud); refreshOutput();
    }
    private void refreshOutput() {
        if(outputStatus==null || outputActions==null) return;
        boolean withHud=output.withHud();
        mark(outputActions[0],withHud); mark(outputActions[1],!withHud);
        outputStatus.setText(output.statusText());
    }
    private void refreshControls() {
        NativeRadio.Status value=radio.status();
        boolean grounded=aircraft.snapshot().allowed();
        if(ledActions!=null) {
            boolean known=lights!=null && !ledReading;
            boolean rear=known && (lights.rear || lights.status);
            boolean[] selected={known && lights.front,rear,false,false};
            String frontLabel=known?(lights.front?"Bật":"Tắt"):"…";
            String rearLabel=known?(lights.rear && lights.status?"Bật":rear?"Một phần":"Tắt"):"…";
            ledActions[0].setText("Trước: "+frontLabel); ledActions[1].setText("Sau: "+rearLabel);
            for(int index=0;index<ledActions.length;index++) {
                mark(ledActions[index],selected[index]);
                ledActions[index].setEnabled(grounded && known && !ledBusy && !value.busy && !value.locked);
            }
            String unavailable=ledReading?"Đang đọc":"Chưa xác định";
            ledActions[0].setStateDescription(known?frontLabel:unavailable);
            ledActions[1].setStateDescription(known?rearLabel:unavailable);
            ledActions[0].setContentDescription("LED trước: "+(known?frontLabel+". Bấm để "+(lights.front?"tắt":"bật"):unavailable));
            ledActions[1].setContentDescription("LED sau: "+(known?rearLabel+". Bấm để "+(rear?"tắt":"bật"):unavailable));
        }
        if(radioActions!=null) for(Button item:radioActions) item.setEnabled(grounded && !ledBusy && !value.busy && !value.locked);
        if(radioStatus!=null) radioStatus.setText(grounded || value.busy || value.locked
            ?radioSummary(value):"Chờ máy bay ở mặt đất, động cơ dừng");
    }
    private String radioSummary(NativeRadio.Status value) {
        if(value.busy) return "Đang xử lý…";
        if(value.locked) return "Đang chờ xác nhận lệnh trước";
        if(!value.message.isEmpty()) {
            String message=value.message;
            if(message.startsWith("Đã ghi và đọc lại Force FCC")) return "Đã đọc lại yêu cầu FCC; kiểm tra Truyền tín hiệu";
            if(message.startsWith("Đã khôi phục và đọc lại")) return "Đã khôi phục cấu hình ban đầu";
            if(message.contains("giá trị 2")) return "Đã đọc cờ FCC; chờ kiểm tra chế độ";
            if(message.contains("ban đầu đã được giữ")) return "Đã giữ cấu hình ban đầu";
            int end=message.indexOf('.');
            return (end<0?message:message.substring(0,end)).replace(" qua SDK","");
        }
        if(forceFlag!=null && forceFlag==2) return "Đã đọc cờ FCC; chờ kiểm tra chế độ";
        return "Chưa xác nhận vùng";
    }
    private void readLights(int revision) {
        if(!currentMenu(revision) || ledReading || ledBusy) return;
        ledReading=true; lights=null;
        ledStatus.setText("Đang đọc LED…"); refreshControls();
        led.inspect(new LedJob.Reply<LedJob.Lights>() {
            public boolean active() { return currentMenu(revision); }
            public void success(LedJob.Lights value) {
                android.util.Log.i("RC2Hud","led_read subIndex=0 front="+value.front+" status="+value.status+" rear="+value.rear+" navigation="+value.navigation);
                activity.runOnUiThread(()->{
                    if(!active()) return;
                    ledReading=false; lights=value;
                    ledStatus.setText(aircraft.snapshot().allowed()?"":"Chờ động cơ dừng");
                    refreshControls();
                });
            }
            public void failure(String message) {
                android.util.Log.i("RC2Hud","led_read_failed subIndex=0 "+message);
                activity.runOnUiThread(()->{
                    if(!active()) return;
                    ledReading=false; lights=null; ledStatus.setText("Chưa đọc được LED"); refreshControls();
                });
                forearm.inspect(new ForearmParamProbe.Reply() {
                    public boolean active() { return currentMenu(revision); }
                    public void finished(ForearmParamProbe.Result result) {
                        if(active()) android.util.Log.i("RC2Hud",result.metadata());
                    }
                });
            }
        });
    }
    private void changeLed(int selection) {
        GroundGate gate=aircraft.snapshot();
        if(!gate.allowed()) { Toast.makeText(activity,gate.explanation(),Toast.LENGTH_LONG).show(); return; }
        NativeRadio.Status radioState=radio.status();
        if(!currentMenu(menuRevision) || ledBusy || ledReading || lights==null || radioState.busy || radioState.locked)return;
        ledBusy=true; ledStatus.setText("Đang đổi LED…"); refreshControls();
        NativeLed.Result result=(ok,message)->activity.runOnUiThread(()->{
            if(!active)return;
            ledBusy=false;
            if(dialog!=null && dialog.isShowing()) { readLights(menuRevision);refreshControls(); }
            if(!ok)Toast.makeText(activity,message,Toast.LENGTH_LONG).show();
        });
        boolean submitted=selection==0?led.toggleFront(result):selection==1?led.toggleRear(result):led.requestAll(selection==2,result);
        if(!submitted && ledBusy) { ledBusy=false;readLights(menuRevision);refreshControls(); }
    }
    private void inspectAirlink(int revision) {
        Thread worker=new Thread(()->airlink.inspect(new AirlinkInspection.Reply() {
            public boolean active() { return currentMenu(revision); }
            public void finished(AirlinkInspection.Result result) {
                if(active()) android.util.Log.i("RC2Hud",result.metadata());
            }
        }),"RC2-AirlinkRead");
        worker.setDaemon(true); worker.start();
        Thread sdrWorker=new Thread(()->sdr.inspect(0xffff0048,new SdrRadioProbe.Reply() {
            public boolean active() { return currentMenu(revision); }
            public void finished(SdrRadioProbe.Result value) {
                if(!active()) return;
                android.util.Log.i("RC2Hud",value.metadata());
                activity.runOnUiThread(()->{
                    if(!active()) return;
                    forceFlag=value.status==SdrRadioProbe.Status.OK?value.value:null; refreshControls();
                });
                sdr.inspect(0xffff0063,new SdrRadioProbe.Reply() {
                    public boolean active() { return currentMenu(revision); }
                    public void finished(SdrRadioProbe.Result second) { if(active()) android.util.Log.i("RC2Hud",second.metadata()); }
                });
            }
        }),"RC2-SdrRead");
        sdrWorker.setDaemon(true); sdrWorker.start();
    }
    private void confirmRadio(boolean fcc) {
        if(!active) return;
        GroundGate latest=radio.state();
        if(!latest.allowed()) { Toast.makeText(activity,latest.explanation(),Toast.LENGTH_LONG).show(); return; }
        if(confirmation!=null) confirmation.dismiss();
        final int revision=menuRevision;
        String detail="Chỉ thực hiện khi máy bay đã hạ cánh và động cơ dừng. "+(fcc
            ?"Kiểm tra chế độ thực tế trong Truyền tín hiệu sau khi đổi."
            :"Khôi phục cấu hình ban đầu đã lưu trong phiên này.");
        confirmation=new AlertDialog.Builder(activity,AlertDialog.THEME_DEVICE_DEFAULT_DARK).setTitle(fcc?"Yêu cầu FCC":"Khôi phục vùng gốc")
            .setMessage(detail).setNegativeButton("Hủy",null).setPositiveButton("Tiếp tục",(d,n)->{
                if(currentMenu(revision)) radio.request(fcc,(ok,message)->activity.runOnUiThread(()->{
                    if(!active) return;
                    forceFlag=null; refreshControls();
                    Toast.makeText(activity,message,Toast.LENGTH_LONG).show();
                }));
            }).create(); confirmation.show();
    }
    void dispose() {
        active=false; menuOpen=false; ++menuRevision;
        if(ledWatch!=null)ledWatch.cancel();
        led.close(); forearm.close(); airlink.close(); sdr.close();
        if(radioWatch!=null) radioWatch.cancel();
        if(outputWatch!=null) outputWatch.cancel();
        radioStatus=null; ledStatus=null; outputStatus=null;
        ledActions=null; radioActions=null; outputActions=null; lights=null;
        if(root.getViewTreeObserver().isAlive()) root.getViewTreeObserver().removeOnGlobalLayoutListener(this);
        if(confirmation!=null) confirmation.dismiss();
        if(dialog!=null) dialog.dismiss(); root.removeView(button);
    }
}
