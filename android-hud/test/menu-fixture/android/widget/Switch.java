package android.widget;
public class Switch extends TextView {
 private boolean checked;public int checkedWrites;
 public Switch(android.content.Context context){super(context);}
 public void setChecked(boolean value){checked=value;checkedWrites++;}public boolean isChecked(){return checked;}
 public void setThumbTintList(android.content.res.ColorStateList tint){}
 public void setTrackTintList(android.content.res.ColorStateList tint){}
}
