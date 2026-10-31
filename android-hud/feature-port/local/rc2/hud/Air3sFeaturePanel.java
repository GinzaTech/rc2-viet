package local.rc2.hud;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Read-only Air 3S capability panel. No SDK SET/action entry point exists here. */
final class Air3sFeaturePanel {
    private static final String[][] ROWS={
        {"Kết nối máy bay","FlightController.Connection"},
        {"Đang bay","FlightController.IsFlying"},
        {"Động cơ đang chạy","FlightController.AreMotorsOn"},
        {"Air 3S hỗ trợ Cruise","FlightAssistant.IsFixedSpeedSupport"},
        {"Sẵn sàng vào Cruise","FlightAssistant.NavigationCanEnterFixedSpeed"},
        {"Hợp đồng Cruise mới","FlightAssistant.IsFixedSpeedNavigationSupport"},
        {"RC có Dynamic Home","RemoteController.RcDynamicHomePointExisted"},
        {"FC có Dynamic Home","FlightController.RcDynamicHomePointExisted"},
        {"RC hỗ trợ Dynamic Home","RemoteController.IsSupportDynamicHome"},
        {"Dynamic Home đang bật","FlightController.DynamicHomePointEnabled"},
        {"Trạng thái Dynamic Home","FlightController.DynamicHomePointState"},
        {"Loại Home Point","FlightController.HomeLocationType"},
        {"Đã đặt Home Point","FlightController.IsHomeLocationSet"},
        {"Bám địa hình đang bật","FlightController.TerrainFollowModeEnabled"},
        {"Chế độ bám địa hình","FlightController.TerrainFollowingMode"},
        {"Virtual Stick","FlightController.VirtualStickControlModeEnabled"},
        {"Navigation","FlightController.NavigationModeEnabled"},
        {"Gimbal pitch mở rộng","Gimbal.PitchRangeExtensionEnabled"},
        {"Gimbal quay dọc chuẩn","Gimbal.IsVerticalShotStandardSupport"},
        {"RC hỗ trợ HDMI","RemoteController.IsHdmiPresentationSupported"},
        {"Trạng thái HDMI camera","Camera.CameraHDMIOutputState"},
        {"Camera zoom quang","Camera.CameraOpticalZoomSupported"},
        {"Camera hỗ trợ khẩu độ","Camera.ApertureIsSupport"}
    };
    private Air3sFeaturePanel() { }
    private static int dp(Activity activity,int value) {
        return Math.round(value*activity.getResources().getDisplayMetrics().density);
    }
    private static TextView text(Activity activity,String value,int size,int color) {
        TextView view=new TextView(activity);view.setText(value);view.setTextSize(size);view.setTextColor(color);return view;
    }
    private static String display(String value) {
        if(value==null)return "Đang đọc…";
        if("VALUE:true".equals(value))return "Có";
        if("VALUE:false".equals(value))return "Không";
        if(value.startsWith("VALUE:"))return value.substring(6);
        if("TIMEOUT".equals(value))return "Chưa phản hồi";
        if(value.startsWith("SDK_ERROR:"))return "SDK từ chối ("+value.substring(10)+")";
        if(value.startsWith("UNAVAILABLE:"))return "Không có hợp đồng SDK";
        return "Chưa xác định";
    }
    static void open(Activity activity) {
        if(activity.isFinishing()||activity.isDestroyed())return;
        Handler main=new Handler(Looper.getMainLooper());
        LinearLayout content=new LinearLayout(activity);content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(activity,16),dp(activity,10),dp(activity,16),dp(activity,10));
        content.setBackgroundColor(0xff101820);
        TextView title=text(activity,"Tính năng Air 3S",17,Color.WHITE);content.addView(title);
        TextView note=text(activity,
            "Chỉ đọc trạng thái thật từ RC và máy bay. Lỗi hoặc hết thời gian không được coi là hỗ trợ.",11,0xffb0b9c8);
        note.setPadding(0,dp(activity,4),0,dp(activity,8));content.addView(note);
        TextView guide=text(activity,
            "Cruise: gán Cruise Control cho C1/C2 trong Điều khiển; khi đang bay và dòng ",
            11,0xff80e1bf);
        guide.append("Sẵn sàng vào Cruise");guide.append(" báo Có thì bấm nút đã gán. Waypoint dùng mục Điểm bay gốc của DJI Fly.");
        guide.setPadding(0,0,0,dp(activity,8));content.addView(guide);
        LinearLayout rows=new LinearLayout(activity);rows.setOrientation(LinearLayout.VERTICAL);
        TextView[] values=new TextView[ROWS.length];
        for(int index=0;index<ROWS.length;index++) {
            LinearLayout row=new LinearLayout(activity);row.setGravity(Gravity.CENTER_VERTICAL);
            row.setPadding(dp(activity,8),dp(activity,4),dp(activity,8),dp(activity,4));
            row.addView(text(activity,ROWS[index][0],12,Color.WHITE),new LinearLayout.LayoutParams(0,dp(activity,38),1));
            values[index]=text(activity,"Đang đọc…",11,0xffb0b9c8);values[index].setGravity(Gravity.END|Gravity.CENTER_VERTICAL);
            row.addView(values[index],new LinearLayout.LayoutParams(dp(activity,190),dp(activity,38)));rows.addView(row);
        }
        ScrollView scroll=new ScrollView(activity);scroll.addView(rows);
        content.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        Button refresh=new Button(activity);refresh.setText("Đọc lại trạng thái");refresh.setAllCaps(false);
        content.addView(refresh,new LinearLayout.LayoutParams(-1,dp(activity,46)));
        AlertDialog dialog=new AlertDialog.Builder(activity,AlertDialog.THEME_DEVICE_DEFAULT_DARK)
            .setView(content).setNegativeButton("Đóng",null).create();
        final boolean[] alive={true};final Runnable[] poll={null};
        Runnable start=()->{
            if(!alive[0])return;
            refresh.setEnabled(false);CapabilityAudit.call(activity,true);
            poll[0]=new Runnable(){
                public void run(){
                    if(!alive[0])return;
                    Bundle snapshot=CapabilityAudit.call(activity,false);
                    for(int index=0;index<ROWS.length;index++)values[index].setText(display(snapshot.getString(ROWS[index][1])));
                    boolean busy=snapshot.getBoolean("busy");refresh.setEnabled(!busy);
                    if(busy)main.postDelayed(this,500);
                }
            };
            main.post(poll[0]);
        };
        refresh.setOnClickListener(view->start.run());
        dialog.setOnDismissListener(value->{alive[0]=false;if(poll[0]!=null)main.removeCallbacks(poll[0]);});
        dialog.show();
        if(dialog.getWindow()!=null)dialog.getWindow().setLayout(
            Math.min(dp(activity,680),activity.getResources().getDisplayMetrics().widthPixels-dp(activity,24)),
            Math.min(dp(activity,600),activity.getResources().getDisplayMetrics().heightPixels-dp(activity,24)));
        start.run();
    }
}
