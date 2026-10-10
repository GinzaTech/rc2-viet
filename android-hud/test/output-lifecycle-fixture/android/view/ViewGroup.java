package android.view;
import android.content.Context;
import java.util.ArrayList;
import java.util.List;
public class ViewGroup extends View {
    public static class LayoutParams {public static final int MATCH_PARENT=-1;public LayoutParams(int w,int h){}}
    protected final List<View> children=new ArrayList<>();
    public ViewGroup(Context context){super(context);}
    public void addView(View view,LayoutParams params){children.add(view);}
    public void removeView(View view){children.remove(view);}
    public int getChildCount(){return children.size();}public View getChildAt(int index){return children.get(index);}
    public <T extends View>T findViewById(int id){T found=super.findViewById(id);if(found!=null)return found;for(View child:children){found=child.findViewById(id);if(found!=null)return found;}return null;}
    public void attach(int w,int h){super.attach(w,h);for(View child:children)child.attach(w,h);}
    public void detach(){for(View child:children)child.detach();}
}
