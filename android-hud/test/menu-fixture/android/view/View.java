package android.view;
import android.content.Context; import android.graphics.Rect; import android.graphics.drawable.Drawable;
public class View {
 public static final int VISIBLE=0,INVISIBLE=4,GONE=8; protected final Context context;
 private int width=640,height=360,id,visibility=VISIBLE; private boolean selected,enabled=true; private CharSequence description,stateDescription;
 private OnClickListener click; private Drawable background; private ViewGroup.LayoutParams layout; public int mutations;
 private final ViewTreeObserver observer=new ViewTreeObserver();
 public interface OnClickListener {void onClick(View view);} public View(Context context){this.context=context;}
 public Context getContext(){return context;} public int getWidth(){return width;} public int getHeight(){return height;}
 public void setSize(int w,int h){width=w;height=h;} public int getId(){return id;} public void setId(int value){id=value;}
 @SuppressWarnings("unchecked") public <T extends View>T findViewById(int value){return id==value?(T)this:null;}
 public ViewTreeObserver getViewTreeObserver(){return observer;}
 public void setVisibility(int value){visibility=value;mutations++;} public int getVisibility(){return visibility;} public boolean isShown(){return visibility==VISIBLE;}
 public boolean getGlobalVisibleRect(Rect bounds){bounds.set(0,0,width,height);return isShown();} public void getLocationOnScreen(int[] location){location[0]=0;location[1]=0;}
 public void setOnClickListener(OnClickListener listener){click=listener;} public boolean performClick(){if(click==null)return false;click.onClick(this);return true;}
 public void userClick(){if(enabled&&isShown())performClick();}
 public void setContentDescription(CharSequence value){description=value;mutations++;} public CharSequence getContentDescription(){return description;}
 public void setStateDescription(CharSequence value){stateDescription=value;mutations++;} public CharSequence getStateDescription(){return stateDescription;}
 public void setSelected(boolean value){selected=value;mutations++;} public boolean isSelected(){return selected;}
 public void setEnabled(boolean value){enabled=value;mutations++;} public boolean isEnabled(){return enabled;}
 public void setBackground(Drawable value){background=value;mutations++;} public Drawable getBackground(){return background;}
 public void setBackgroundColor(int value){mutations++;} public void setPadding(int l,int t,int r,int b){} public void setElevation(float value){}
 public void setClickable(boolean value){} public void setFocusable(boolean value){} public void setMinHeight(int value){} public void setMinimumHeight(int value){} public void setMinimumWidth(int value){}
 public void setClipToOutline(boolean value){}
 public void setLayoutParams(ViewGroup.LayoutParams value){layout=value;} public ViewGroup.LayoutParams getLayoutParams(){return layout;}
 protected void onDraw(android.graphics.Canvas canvas){}
}
