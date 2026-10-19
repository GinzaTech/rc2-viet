package local.rc2.hud;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

/** Original menu -> utilities -> exactly one selected page. */
public final class AdvancedSectionMenu {
    private static final String TAG="RC2FeaturePort";
    private static final int BACKGROUND=0xff101820,SURFACE=0xff192630;
    private static final int FOREGROUND=0xfff4f6f9,MUTED=0xffb0b9c8,ACCENT=0xff80e1bf;
    private AdvancedSectionMenu() { }
    private static int dp(Context c,int size) {return Math.round(size*c.getResources().getDisplayMetrics().density);}
    private static GradientDrawable fill(Context c,int color,int radius) {
        GradientDrawable shape=new GradientDrawable();shape.setColor(color);shape.setCornerRadius(dp(c,radius));
        shape.setStroke(dp(c,1),0xff30424f);return shape;
    }
    private static TextView label(Activity a,String text,int size,int color) {
        TextView view=new TextView(a);view.setText(text);view.setTextSize(size);view.setTextColor(color);return view;
    }
    private static LinearLayout column(Activity a) {
        LinearLayout view=new LinearLayout(a);view.setOrientation(LinearLayout.VERTICAL);return view;
    }
    private static void interactive(Activity a,View view) {
        view.setBackground(new RippleDrawable(ColorStateList.valueOf(0x3380e1bf),fill(a,SURFACE,12),null));
        view.setClickable(true);view.setFocusable(true);
    }
    private static LinearLayout card(Activity a,String title,String description,boolean compact) {
        LinearLayout row=new LinearLayout(a);row.setOrientation(LinearLayout.HORIZONTAL);row.setGravity(Gravity.CENTER_VERTICAL);
        int vertical=dp(a,8);
        row.setPadding(dp(a,12),vertical,dp(a,12),vertical);row.setMinimumHeight(dp(a,compact?56:80));
        interactive(a,row);row.setContentDescription(title);
        LinearLayout copy=column(a);row.addView(copy,new LinearLayout.LayoutParams(0,-2,1));
        TextView eyebrow=label(a,compact?"CÁ NHÂN HÓA":"THIẾT LẬP",10,ACCENT);copy.addView(eyebrow);
        TextView heading=label(a,title,compact?14:16,FOREGROUND);heading.setMaxLines(2);
        LinearLayout.LayoutParams hp=new LinearLayout.LayoutParams(-1,-2);hp.topMargin=dp(a,3);copy.addView(heading,hp);
        TextView note=label(a,description,11,MUTED);note.setMaxLines(2);
        LinearLayout.LayoutParams noteParams=new LinearLayout.LayoutParams(-1,-2);noteParams.topMargin=dp(a,4);copy.addView(note,noteParams);
        TextView arrow=label(a,"›",24,ACCENT);arrow.setGravity(Gravity.CENTER);
        row.addView(arrow,new LinearLayout.LayoutParams(dp(a,28),dp(a,40)));return row;
    }
    static void addEntry(Activity a,LinearLayout panel) {
        LinearLayout entry=card(a,"Tiện ích nâng cao","Nâng cao và Hiệu chỉnh gimbal",true);entry.setOnClickListener(v->showSelector(a));
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.topMargin=dp(a,12);panel.addView(entry,params);
    }
    private static Button icon(Activity a,String glyph,String description) {
        Button button=new Button(a);button.setText(glyph);button.setAllCaps(false);button.setTextSize(22);button.setTextColor(MUTED);
        button.setContentDescription(description);button.setPadding(0,0,0,0);button.setMinWidth(0);button.setMinimumWidth(0);
        button.setMinHeight(0);button.setMinimumHeight(0);button.setElevation(0);interactive(a,button);return button;
    }
    private static LinearLayout shell(Activity a,AlertDialog dialog,String title,boolean child) {
        LinearLayout panel=column(a);panel.setBackground(fill(a,BACKGROUND,16));panel.setClipToOutline(true);
        LinearLayout header=new LinearLayout(a);header.setOrientation(LinearLayout.HORIZONTAL);header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(dp(a,12),dp(a,6),dp(a,12),dp(a,6));
        if(child) {
            Button back=icon(a,"‹","Quay lại Tiện ích nâng cao");back.setOnClickListener(v->{dialog.dismiss();showSelector(a);});
            LinearLayout.LayoutParams bp=new LinearLayout.LayoutParams(dp(a,44),dp(a,44));bp.rightMargin=dp(a,12);header.addView(back,bp);
        }
        LinearLayout copy=column(a);header.addView(copy,new LinearLayout.LayoutParams(0,-2,1));copy.addView(label(a,title,16,FOREGROUND));
        TextView subtitle=label(a,child?"Tiện ích nâng cao":"RC 2  /  Tùy chỉnh theo cách của bạn",11,MUTED);
        LinearLayout.LayoutParams sp=new LinearLayout.LayoutParams(-1,-2);sp.topMargin=dp(a,3);copy.addView(subtitle,sp);
        Button close=icon(a,"×","Đóng "+title);close.setOnClickListener(v->dialog.dismiss());
        header.addView(close,new LinearLayout.LayoutParams(dp(a,44),dp(a,44)));panel.addView(header,new LinearLayout.LayoutParams(-1,-2));
        View line=new View(a);line.setBackgroundColor(SURFACE);panel.addView(line,new LinearLayout.LayoutParams(-1,dp(a,1)));return panel;
    }
    private static AlertDialog dialog(Activity a) {return new AlertDialog.Builder(a,AlertDialog.THEME_DEVICE_DEFAULT_DARK).create();}
    private static void display(Activity a,AlertDialog dialog,View panel,int width,int height) {
        dialog.setView(panel,0,0,0,0);dialog.show();Window window=dialog.getWindow();
        if(window!=null) {
            window.setBackgroundDrawable(new ColorDrawable(0));window.setDimAmount(.6f);
            window.setLayout(Math.min(dp(a,width),a.getResources().getDisplayMetrics().widthPixels-dp(a,32)),height);
        }
    }
    public static void showSelector(Context context) {
        if(!(context instanceof Activity)) {Log.w(TAG,"selected_menu_requires_activity");return;}
        Activity a=(Activity)context;a.runOnUiThread(()->{
            if(a.isFinishing()||a.isDestroyed())return;
            AlertDialog dialog=dialog(a);LinearLayout panel=shell(a,dialog,"Tiện ích nâng cao",false);
            LinearLayout choices=column(a);boolean wide=a.getResources().getDisplayMetrics().widthPixels>=dp(a,560);
            choices.setPadding(dp(a,12),dp(a,8),dp(a,12),dp(a,8));
            int columns=wide?2:1;LinearLayout row=null;
            for(int i=0;i<AdvancedSectionPolicy.count();i++) {
                if(i%columns==0) {
                    row=new LinearLayout(a);row.setOrientation(LinearLayout.HORIZONTAL);
                    LinearLayout.LayoutParams rp=new LinearLayout.LayoutParams(-1,-2);
                    if(i>0)rp.topMargin=dp(a,8);choices.addView(row,rp);
                }
                final int selected=i;LinearLayout option=card(a,AdvancedSectionPolicy.title(i),AdvancedSectionPolicy.description(i),false);
                option.setOnClickListener(v->{dialog.dismiss();show(a,selected);});
                LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,-2,1);
                if(i%columns>0)p.leftMargin=dp(a,12);row.addView(option,p);
            }
            ScrollView scroll=new ScrollView(a);scroll.setFillViewport(false);scroll.addView(choices);
            panel.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
            int height=Math.min(dp(a,480),a.getResources().getDisplayMetrics().heightPixels-dp(a,32));
            display(a,dialog,panel,760,height);
        });
    }
    public static void show(Context context,int section) {
        if(!(context instanceof Activity)) {Log.w(TAG,"selected_menu_requires_activity");return;}
        final String title,factory;
        try {title=AdvancedSectionPolicy.title(section);factory=AdvancedSectionPolicy.factory(section);}
        catch(IllegalArgumentException error) {Log.w(TAG,"unselected_menu_rejected");return;}
        Activity a=(Activity)context;a.runOnUiThread(()->open(a,title,factory));
    }
    static void stylePage(View view) {
        Context c=view.getContext();
        view.setPadding(Math.round(view.getPaddingLeft()*.75f),Math.round(view.getPaddingTop()*.65f),
            Math.round(view.getPaddingRight()*.75f),Math.round(view.getPaddingBottom()*.65f));
        ViewGroup.LayoutParams params=view.getLayoutParams();
        if(params!=null&&params.height>=dp(c,40)) {
            params.height=Math.max(dp(c,40),Math.round(params.height*.8f));view.setLayoutParams(params);
        }
        if(view.getMinimumHeight()>dp(c,40))view.setMinimumHeight(Math.max(dp(c,40),Math.round(view.getMinimumHeight()*.8f)));
        if(view instanceof LinearLayout&&view.getBackground() instanceof ColorDrawable) {
            int color=((ColorDrawable)view.getBackground()).getColor(),r=(color>>16)&255,g=(color>>8)&255,b=color&255;
            if((color>>>24)==255&&Math.max(r,Math.max(g,b))-Math.min(r,Math.min(g,b))<=4&&r>=32&&r<=64)
                view.setBackground(fill(c,SURFACE,12));
        }
        if(view instanceof TextView) {
            TextView text=(TextView)view;float size=text.getTextSize()/c.getResources().getDisplayMetrics().scaledDensity;
            int limit=view instanceof Button?12:13;
            if(size>limit)text.setTextSize(limit);
            if(text.getMinHeight()>dp(c,40))text.setMinHeight(Math.max(dp(c,40),Math.round(text.getMinHeight()*.8f)));
        }
        if(view instanceof Switch) {
            Switch toggle=(Switch)view;int[][] states={{android.R.attr.state_checked},{}};
            toggle.setThumbTintList(new ColorStateList(states,new int[]{FOREGROUND,MUTED}));
            toggle.setTrackTintList(new ColorStateList(states,new int[]{ACCENT,0xff536070}));
        }
        if(view instanceof ViewGroup) {ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++)stylePage(group.getChildAt(i));}
    }
    private static View page(Activity a,String factory,int height) throws ReflectiveOperationException {
        Class<?> settings=Class.forName("flysettings.S",true,a.getClassLoader());Field ctx=settings.getDeclaredField("sCtx");ctx.setAccessible(true);
        if(ctx.get(null)==null)ctx.set(null,a.getApplicationContext());
        Method create=settings.getDeclaredMethod(factory,Context.class);create.setAccessible(true);Object value=create.invoke(null,a);
        if(!(value instanceof View))throw new IllegalStateException("Selected page returned no view");
        View page=(View)value;if(page.getParent()!=null)throw new IllegalStateException("Selected page already has a parent");
        page.getClass().getMethod("setAvailHeight",int.class).invoke(page,Math.max(0,height));stylePage(page);return page;
    }
    private static void open(Activity a,String title,String factory) {
        if(a.isFinishing()||a.isDestroyed())return;
        try {
            int height=a.getResources().getDisplayMetrics().heightPixels-dp(a,24),bodyHeight=Math.max(dp(a,100),height-dp(a,57));
            AlertDialog dialog=dialog(a);LinearLayout panel=shell(a,dialog,title,true),body=column(a);
            if("tabBasic".equals(factory))panel.setMinimumHeight(Math.min(dp(a,280),height));
            body.setPadding(dp(a,10),dp(a,6),dp(a,10),dp(a,8));
            // Columns measures its entire content, but does not implement scrolling.
            // Give it wrap-content height inside one bounded vertical viewport.
            ScrollView scroll=new ScrollView(a);scroll.setFillViewport(false);
            scroll.setContentDescription("Nội dung "+title);
            scroll.addView(page(a,factory,bodyHeight-dp(a,14)),new ScrollView.LayoutParams(-1,-2));
            body.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
            if("tabAdvanced".equals(factory)) {
                Button features=new Button(a);features.setText("Trạng thái tính năng Air 3S");features.setAllCaps(false);
                features.setTextSize(12);features.setContentDescription("Đọc Cruise, Dynamic Home, bám địa hình, gimbal và HDMI");
                features.setOnClickListener(v->Air3sFeaturePanel.open(a));
                LinearLayout.LayoutParams fp=new LinearLayout.LayoutParams(-1,dp(a,44));fp.topMargin=dp(a,6);body.addView(features,fp);
            }
            panel.addView(body,new LinearLayout.LayoutParams(-1,0,1));display(a,dialog,panel,720,height);
            Log.i(TAG,"selected_menu_open:"+factory);
        } catch(ReflectiveOperationException|RuntimeException|LinkageError error) {
            Log.e(TAG,"selected_menu_failed:"+factory,error);
            Toast.makeText(a,"Chưa mở được mục "+title+". Xem log RC2FeaturePort.",Toast.LENGTH_LONG).show();
        }
    }
}
