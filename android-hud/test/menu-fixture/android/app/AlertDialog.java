package android.app;
import android.content.DialogInterface; import android.view.View; import java.util.ArrayList; import java.util.List;
public class AlertDialog implements DialogInterface {
 public static final int THEME_DEVICE_DEFAULT_DARK=4; public static final List<AlertDialog> shown=new ArrayList<>();
 public View view,titleView; public CharSequence title,message; private boolean showing; private OnDismissListener dismissListener; private OnClickListener positive;
 public void setView(View value,int l,int t,int r,int b){view=value;} public void setView(View value){view=value;}
 public void setOnDismissListener(OnDismissListener value){dismissListener=value;}
 public void show(){showing=true;shown.add(this);} public boolean isShowing(){return showing;}
 public void dismiss(){if(!showing)return;showing=false;if(dismissListener!=null)dismissListener.onDismiss(this);}
 public android.view.Window getWindow(){return new android.view.Window();}
 public void clickPositive(){if(!showing)throw new AssertionError("confirmation is closed");if(positive!=null)positive.onClick(this,-1);dismiss();}
 public static AlertDialog latest(){return shown.get(shown.size()-1);}
 public static class Builder {
  private final AlertDialog dialog=new AlertDialog(); public Builder(Activity activity,int theme){}
  public Builder setCustomTitle(View view){dialog.titleView=view;return this;} public Builder setTitle(CharSequence value){dialog.title=value;return this;}
  public Builder setMessage(CharSequence value){dialog.message=value;return this;}
  public Builder setNegativeButton(CharSequence value,OnClickListener listener){return this;}
  public Builder setPositiveButton(CharSequence value,OnClickListener listener){dialog.positive=listener;return this;}
  public AlertDialog create(){return dialog;}
 }
}
