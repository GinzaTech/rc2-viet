"""Host-only test of a two-address allowlisted SDR GET; no device access."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_sdr_read_only_contract(tmp_path):
    fixture = tmp_path / "DataOsdSetSdrAssitantRead.java"
    fixture.write_text('''package uav.midware.data.model.P3;
import uav.midware.interfaces.UAVDataCallBack;
public class DataOsdSetSdrAssitantRead {
 public enum SdrCpuType { CP_A7; public int value(){return 0;} }
 public enum SdrDataType { Byte_Data; public int value(){return 2;} }
 public enum SdrDeviceType { Sky; public int value(){return 0;} }
 public static DataOsdSetSdrAssitantRead last;
 public static int count;
 public UAVDataCallBack callback; public int address;
 public byte[] bytes=new byte[]{2,0,0,0};
 public DataOsdSetSdrAssitantRead(){last=this;}
 public DataOsdSetSdrAssitantRead setAddress(int a){address=a;return this;}
 public DataOsdSetSdrAssitantRead setSdrCpuType(SdrCpuType t){return this;}
 public DataOsdSetSdrAssitantRead setSdrDataType(SdrDataType t){return this;}
 public DataOsdSetSdrAssitantRead setSdrDeviceType(SdrDeviceType t){return this;}
 public byte[] getRecData(){return bytes;}
 public int getIntValue(){int n=0;for(int i=Math.min(4,bytes.length)-1;i>=0;i--)n=(n<<8)|(bytes[i]&255);return n;}
 public void start(UAVDataCallBack c){callback=c;count++;}
}''', encoding="utf-8")
    callback = tmp_path / "UAVDataCallBack.java"
    callback.write_text('''package uav.midware.interfaces;
import uav.midware.data.config.P3.Ccode;
public interface UAVDataCallBack { void onSuccess(Object o); void onFailure(Ccode c); }
''', encoding="utf-8")
    ccode = tmp_path / "Ccode.java"
    ccode.write_text('''package uav.midware.data.config.P3;
public class Ccode { public int c(){return 7;} }
''', encoding="utf-8")
    runner = tmp_path / "SdrRadioProbeTest.java"
    runner.write_text('''package local.rc2.hud;
import uav.midware.data.model.P3.DataOsdSetSdrAssitantRead;
import uav.midware.data.config.P3.Ccode;
public class SdrRadioProbeTest {
 static SdrRadioProbe.Result result; static int replies; static Runnable expiry;
 static class Reply implements SdrRadioProbe.Reply {
  boolean enabled=true; public boolean active(){return enabled;}
  public void finished(SdrRadioProbe.Result r){result=r;replies++;}
 }
 static void check(boolean b){if(!b)throw new AssertionError();}
 static SdrRadioProbe make(){return new SdrRadioProbe(SdrRadioProbeTest.class.getClassLoader(),
  (r,ms)->{expiry=r;return ()->{};});}
 public static void main(String[] args){
  SdrRadioProbe p=make(); Reply r=new Reply();
  check(p.inspect(0xffff0048,r));
  DataOsdSetSdrAssitantRead m=DataOsdSetSdrAssitantRead.last;
  check(m.address==0xffff0048); check(!p.inspect(0xffff0063,r));
  m.callback.onSuccess(m); check(result.status==SdrRadioProbe.Status.OK);
  check(result.value==2); check(result.metadata().contains("effective_mode=unknown"));
  int before=replies; m.callback.onSuccess(m); expiry.run(); check(replies==before);
  check(p.inspect(0xffff0063,r)); m=DataOsdSetSdrAssitantRead.last;
  m.bytes=new byte[]{3}; m.callback.onSuccess(m);
  check(result.status==SdrRadioProbe.Status.OK && result.firstByte==3 && result.value==3);
  check(p.inspect(0xffff0063,r)); m=DataOsdSetSdrAssitantRead.last;
  m.bytes=new byte[]{3,0}; m.callback.onSuccess(m);
  check(result.status==SdrRadioProbe.Status.RESPONSE_LENGTH);
  check(p.inspect(0xffff0048,r)); m=DataOsdSetSdrAssitantRead.last;
  m.callback.onSuccess(new Object()); check(result.status==SdrRadioProbe.Status.CALLBACK_MISMATCH);
  check(p.inspect(0xffff0048,r)); DataOsdSetSdrAssitantRead.last.callback.onFailure(new Ccode());
  check(result.status==SdrRadioProbe.Status.SDK_FAILURE && result.errorCode==7);
  check(p.inspect(0xffff0048,r)); expiry.run(); check(result.status==SdrRadioProbe.Status.TIMEOUT);
  check(p.inspect(0xffff0048,r)); m=DataOsdSetSdrAssitantRead.last;
  before=replies; p.close(); m.callback.onSuccess(m); check(replies==before);
  check(!p.inspect(0xffff0048,r));
  int count=DataOsdSetSdrAssitantRead.count;
  try {make().inspect(123,r);throw new AssertionError();}catch(IllegalArgumentException expected){}
  check(DataOsdSetSdrAssitantRead.count==count);
  p=make(); r=new Reply(); check(p.inspect(0xffff0048,r)); r.enabled=false;
  before=replies; DataOsdSetSdrAssitantRead.last.callback.onSuccess(DataOsdSetSdrAssitantRead.last);
  check(replies==before); p.close();
  System.out.println("sdr_read_only_contract_passed");
 }
}''', encoding="utf-8")
    source = ROOT / "android-hud/src/local/rc2/hud/SdrRadioProbe.java"
    compile_result = subprocess.run(
        ["javac", "-source", "8", "-target", "8", "-encoding", "UTF-8", "-d", str(tmp_path),
         str(source), str(fixture), str(callback), str(ccode), str(runner)],
        capture_output=True, text=True, timeout=30,
    )
    assert compile_result.returncode == 0, compile_result.stderr
    result = subprocess.run(["java", "-cp", str(tmp_path), "local.rc2.hud.SdrRadioProbeTest"],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "sdr_read_only_contract_passed" in result.stdout
