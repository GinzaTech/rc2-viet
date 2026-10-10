// SPDX-License-Identifier: AGPL-3.0-only
// Golden profile fixture derived from doesthings/FreeFCC v1.5.5, commit
// 597157bd52120dfeb9677f79a8ad46b6027ce8dc; CRC/response fixtures constructed locally.
package local.rc2.hud;

import java.util.Arrays;

/** Independent raw response fixtures; no SDK, Android or network. */
public final class RadioProtocolTest {
    static void check(boolean value,String label) { if(!value) throw new AssertionError(label); }
    static byte[] ack(byte[] request,byte[] payload) {
        byte[] out=new byte[13+payload.length];
        out[0]=0x55; out[1]=(byte)out.length; out[2]=4;
        out[4]=request[5]; out[5]=request[4]; out[6]=request[6]; out[7]=request[7];
        out[8]=(byte)0x80; out[9]=request[9]; out[10]=request[10];
        System.arraycopy(payload,0,out,11,payload.length); repair(out); return out;
    }
    static void repair(byte[] out) {
        out[3]=(byte)crc(out,3,0x77,0x8c);
        int tail=crc(out,out.length-2,0x3692,0x8408);
        out[out.length-2]=(byte)tail; out[out.length-1]=(byte)(tail>>8);
    }
    static int crc(byte[] data,int length,int seed,int poly) {
        int value=seed;
        for(int i=0;i<length;i++) {
            value^=data[i]&255;
            for(int j=0;j<8;j++) value=(value>>>1)^((value&1)==1?poly:0);
        }
        return value;
    }
    static String hex(byte[] data) {
        StringBuilder result=new StringBuilder();
        for(byte b:data) result.append(String.format("%02x",b&255));
        return result.toString();
    }
    public static void main(String[] args) {
        if(args.length>0) {
            for(boolean fcc:new boolean[]{true,false}) {
                RadioProtocol.Profile p=RadioProtocol.profile(fcc,0xfff8);
                for(int i=0;i<p.count();i++) System.out.println(fcc+":"+hex(p.packet(i)));
                System.out.println("timing-"+fcc+":"+p.rounds+":"+p.frameDelayMillis+":"+p.roundDelayMillis+":"+p.readMillis);
            }
            return;
        }
        RadioProtocol.Profile profile=RadioProtocol.profile(true,0xfff8);
        check(profile.count()==42,"exact two rounds");
        byte[] request=profile.packet(0);
        check(hex(request).equals("551004568212f8ff2010580301003fd8"),"independent golden request");
        check(Arrays.equals(profile.packet(0),profile.packet(21)),"pinned builder reuses round frames");
        check((profile.packet(8)[6]&255)==0 && (profile.packet(8)[7]&255)==0,"16-bit sequence wrap");
        request[4]=0; request=profile.packet(0);
        check((request[4]&255)==130,"defensive packet copy");
        check(RadioProtocol.matches(request,ack(request,new byte[]{0})),"matched ACK");
        check(RadioProtocol.classify(request,ack(request,new byte[0]))==RadioDiagnostics.Ack.EMPTY_BODY,"empty correlated reply");
        check(RadioProtocol.classify(request,ack(request,new byte[]{0}))==RadioDiagnostics.Ack.ZERO_STATUS,"single zero byte; no acceptance decoder");
        check(RadioProtocol.classify(request,ack(request,new byte[]{1}))==RadioDiagnostics.Ack.NONZERO_STATUS,"single nonzero byte; no NACK decoder");
        check(RadioProtocol.classify(request,ack(request,new byte[]{0,1}))==RadioDiagnostics.Ack.BODY_UNINTERPRETED,"opaque correlated reply");
        // Upstream validateResponse accepts response flags, requiring bit 7.
        for(int type:new int[]{0x80,0xa0,0xc0}) {
            byte[] flags=ack(request,new byte[]{0}); flags[8]=(byte)type; repair(flags);
            check(RadioProtocol.matches(request,flags),"response flags match pinned source");
        }
        byte[] notResponse=ack(request,new byte[]{0}); notResponse[8]=0; repair(notResponse);
        check(!RadioProtocol.matches(request,notResponse),"response bit required");
        byte[] encrypted=ack(request,new byte[]{0}); encrypted[8]=(byte)0x81; repair(encrypted);
        check(RadioProtocol.matches(request,encrypted),"routing matches encrypted response");
        check(RadioProtocol.classify(request,encrypted)==RadioDiagnostics.Ack.BODY_UNINTERPRETED,"encrypted body not interpreted as plaintext status");
        for(int offset:new int[]{0,1,2,3,4,5,6,7,9,10,12}) {
            byte[] bad=ack(request,new byte[]{0}); bad[offset]^=1;
            if(offset!=3 && offset!=12) repair(bad);
            check(!RadioProtocol.matches(request,bad),"reject malformed field "+offset);
        }
        byte[] response=ack(request,new byte[]{0});
        check(!RadioProtocol.matches(request,Arrays.copyOf(response,response.length-1)),"truncation");
        check(!RadioProtocol.matches(request,Arrays.copyOf(response,response.length+1)),"appended data");
        check(!RadioProtocol.matches(null,response) && !RadioProtocol.matches(request,null),"null");
        for(int invalid:new int[]{-1,65536}) {
            try { RadioProtocol.profile(true,invalid); throw new AssertionError("sequence range"); }
            catch(IllegalArgumentException expected) { }
        }
        try { profile.packet(42); throw new AssertionError("frame bounds"); }
        catch(IndexOutOfBoundsException expected) { }
        check(RadioProtocol.profile(false,1).count()==1,"single factory restore");
        System.out.println("RadioProtocolTest_passed");
    }
}
