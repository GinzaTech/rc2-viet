package local.rc2.hud;
import android.app.Activity;
import android.app.AlertDialog;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.view.View;
import android.view.ViewGroup;

public final class AdvancedSectionHierarchyTest {
    private static void require(boolean value,String message){if(!value)throw new AssertionError(message);}
    private static View find(View view,String description){
        if(view.getContentDescription()!=null&&description.contentEquals(view.getContentDescription()))return view;
        if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=find(group.getChildAt(i),description);if(found!=null)return found;}}
        return null;
    }
    private static int choices(View view){
        int count=0;for(int i=0;i<AdvancedSectionPolicy.count();i++)if(AdvancedSectionPolicy.title(i).equals(view.getContentDescription()))count++;
        if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++)count+=choices(group.getChildAt(i));}return count;
    }
    public static void main(String[] args){
        Activity activity=new Activity();LinearLayout parent=new LinearLayout(activity);
        Button oldLed=new Button(activity),oldHud=new Button(activity);
        int[] oldClicks={0};oldLed.setOnClickListener(v->oldClicks[0]++);
        parent.addView(oldLed);parent.addView(oldHud);
        AdvancedSectionMenu.addEntry(activity,parent);
        require(parent.getChildCount()==3,"Original menu must get exactly one additional entry");
        require(parent.getChildAt(0)==oldLed&&parent.getChildAt(1)==oldHud,"Original controls must remain in place");
        View entry=parent.getChildAt(2);
        require("Tiện ích nâng cao".contentEquals(entry.getContentDescription()),"Wrong parent entry");
        require(flysettings.S.advancedCalls==0&&flysettings.S.gimbalCalls==0,"Adding entry must not create a feature page");
        entry.performClick();AlertDialog submenu=AlertDialog.latest();
        require(choices(submenu.view)==2,"Submenu must have exactly two choices");
        find(submenu.view,"Nâng cao").performClick();
        require(!submenu.isShowing(),"Selecting a page must dismiss the chooser");
        require(find(AlertDialog.latest().view,"Đóng Nâng cao")!=null,"Advanced choice opens wrong page");
        require(flysettings.S.advancedCalls==1&&flysettings.S.gimbalCalls==0,"Wrong advanced factory");
        find(AlertDialog.latest().view,"Quay lại Tiện ích nâng cao").performClick();
        require(choices(AlertDialog.latest().view)==2,"Back must return to both choices");
        find(AlertDialog.latest().view,"Hiệu chỉnh gimbal").performClick();
        require(find(AlertDialog.latest().view,"Đóng Hiệu chỉnh gimbal")!=null,"Gimbal choice opens wrong page");
        require(flysettings.S.advancedCalls==1&&flysettings.S.gimbalCalls==1,"Wrong gimbal factory");
        for(int i=0;i<AdvancedSectionPolicy.count();i++) {
            AdvancedSectionMenu.show(activity,i);
            View viewport=find(AlertDialog.latest().view,"Nội dung "+AdvancedSectionPolicy.title(i));
            require(viewport instanceof android.widget.ScrollView,"Page must have a scroll viewport");
            View contents=((ViewGroup)viewport).getChildAt(0);
            require(contents instanceof flysettings.S.Columns,"Scroll must wrap the original page");
            require(contents.getLayoutParams().height==-2,"Long content must retain its natural height");
            require(viewport.getLayoutParams().height==0,"Viewport must use the bounded weighted dialog body");
        }
        require(flysettings.S.basicCalls==0&&flysettings.S.controlCalls==0&&flysettings.S.safetyCalls==0,"Hidden page factories must remain unused");
        activity.getResources().getDisplayMetrics().widthPixels=320;
        find(AlertDialog.latest().view,"Quay lại Tiện ích nâng cao").performClick();
        require(choices(AlertDialog.latest().view)==2,"Narrow menu must retain both pages");
        find(AlertDialog.latest().view,"Hiệu chỉnh gimbal").performClick();
        require(flysettings.S.gimbalCalls==3,"Last narrow-screen item is not reachable");
        require(android.widget.Toast.shows==0,"Page reflection failed");
        LinearLayout card=new LinearLayout(activity);card.setBackground(new android.graphics.drawable.ColorDrawable(0xff2e3031));
        TextView copy=new TextView(activity);copy.setText("Giữ nguyên nội dung");copy.setTextSize(18);card.addView(copy);
        android.widget.Switch toggle=new android.widget.Switch(activity);toggle.setChecked(true);card.addView(toggle);
        copy.setPadding(16,20,16,20);
        copy.setLayoutParams(new ViewGroup.LayoutParams(-1,60));
        copy.setMinHeight(60);
        AdvancedSectionMenu.stylePage(card);
        require(copy.getPaddingTop()==13&&copy.getLayoutParams().height==48&&copy.getMinHeight()==48,"Compact spacing must affect real layout");
        require(toggle.isChecked()&&toggle.checkedWrites==1,"Styling must not change settings");
        require(copy.getTextSize()==13&&"Giữ nguyên nội dung".contentEquals(copy.getText()),"Styling must retain content and fit typography");
        require(card.getBackground() instanceof android.graphics.drawable.GradientDrawable,"Cards should share rounded surfaces");
        oldLed.performClick();require(oldClicks[0]==1,"Original menu control stopped working");
        int shown=AlertDialog.shown.size();activity.finishing=true;
        AdvancedSectionMenu.showSelector(activity);
        AdvancedSectionMenu.showSelector(new android.content.Context());
        AdvancedSectionMenu.show(activity,5);
        require(AlertDialog.shown.size()==shown,"Invalid activity/page must not open a dialog");
        System.out.println("original_menu_preserved_with_nested_two_item_utilities");
    }
}
