package android.view;
import java.util.ArrayList; import java.util.List;
public class ViewGroup extends View {
 public static class LayoutParams {public static final int MATCH_PARENT=-1,WRAP_CONTENT=-2; public int width,height; public LayoutParams(int w,int h){width=w;height=h;}}
 protected final List<View> children=new ArrayList<>(); public ViewGroup(android.content.Context context){super(context);}
 public void addView(View view){addView(view,new LayoutParams(-2,-2));} public void addView(View view,LayoutParams params){children.add(view);view.setLayoutParams(params);}
 public void removeView(View view){children.remove(view);} public int getChildCount(){return children.size();} public View getChildAt(int index){return children.get(index);}
 public <T extends View>T findViewById(int id){T found=super.findViewById(id);if(found!=null)return found;for(View child:children){found=child.findViewById(id);if(found!=null)return found;}return null;}
}
