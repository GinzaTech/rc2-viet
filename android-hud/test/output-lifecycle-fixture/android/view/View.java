package android.view;
import android.content.Context;
public class View {
    public static final int VISIBLE=0,INVISIBLE=4,GONE=8;
    protected final Context context;protected int width=640,height=360,visibility=VISIBLE;
    private int id;
    private final ViewTreeObserver observer=new ViewTreeObserver();
    public View(Context context){this.context=context;}
    public int getWidth(){return width;}public int getHeight(){return height;}
    public Context getContext(){return context;}
    public void setSize(int w,int h){width=w;height=h;}
    public void setId(int value){id=value;}
    public int getId(){return id;}
    public ViewTreeObserver getViewTreeObserver(){return observer;}
    @SuppressWarnings("unchecked") public <T extends View>T findViewById(int value){return id==value?(T)this:null;}
    public void setVisibility(int value){visibility=value;}
    public void attach(int w,int h){setSize(w,h);}
    public void detach(){}
}
