package local.rc2.hud;
public final class OutputGeometryTest {
    static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    public static void main(String[] args){
        int[] wide=OutputGeometry.fit(1920,1080,2560,1080);
        check(wide[0]==320 && wide[1]==0 && wide[2]==1920 && wide[3]==1080,"wide monitor letterbox");
        int[] portrait=OutputGeometry.fit(1920,1080,1080,1920);
        check(portrait[2]==1080 && portrait[3]==608 && portrait[0]==0,"portrait monitor fit");
        for(int width:new int[]{640,1280,1920,3840})for(int height:new int[]{480,720,1080,2160}){
            int[] fitted=OutputGeometry.fit(1920,1080,width,height);
            check(fitted[0]>=0 && fitted[1]>=0 && fitted[0]+fitted[2]<=width && fitted[1]+fitted[3]<=height,"never crop beyond target");
        }
        int[] copy=OutputGeometry.copySize(3840,2160);
        check(copy[0]==960 && copy[1]==540 && copy[0]*copy[1]<=518400,"bounded fallback RAM");
        for(int bad:new int[]{0,-1})try{OutputGeometry.fit(bad,1080,1920,1080);throw new AssertionError();}catch(IllegalArgumentException expected){}
        System.out.println("output_geometry_passed");
    }
}
