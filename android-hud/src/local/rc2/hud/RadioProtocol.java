// SPDX-License-Identifier: AGPL-3.0-only
// Profile attribution: doesthings/FreeFCC v1.5.5, https://github.com/doesthings/FreeFCC
// Upstream license: docs/FREEFCC_LICENSE.txt (AGPL version 3).
// The ordered profile constants are derived from upstream; CRC implementation is local.
package local.rc2.hud;

/**
 * Fixed FreeFCC v1.5.5 profiles, commit 597157bd52120dfeb9677f79a8ad46b6027ce8dc.
 * Source: app/src/main/assets/profiles/{fcc,ce_restore}.json, independently
 * inspected from the pinned source and tested against public assets/freefcc.apk.
 * No runtime assets or arbitrary
 * command/host input. DUML CRCs follow the pinned DumlBuilder.
 */
final class RadioProtocol {
    private RadioProtocol() { }
    static final class Profile {
        final int rounds,frameDelayMillis,roundDelayMillis,readMillis;
        private final byte[][] packets;
        private Profile(byte[][] packets,int rounds,int frameDelay,int roundDelay,int read) {
            this.packets=packets; this.rounds=rounds; frameDelayMillis=frameDelay;
            roundDelayMillis=roundDelay; readMillis=read;
        }
        int count() { return packets.length*rounds; }
        int roundSize() { return packets.length; }
        byte[] packet(int index) {
            if(index<0 || index>=count()) throw new IndexOutOfBoundsException("Fixed radio profile index");
            return packets[index%packets.length].clone();
        }
    }
    static Profile profile(boolean fcc,int sequence) {
        if(sequence<0 || sequence>65535) throw new IllegalArgumentException("DUML sequence out of range");
        if(!fcc) return new Profile(new byte[][]{frame(6,114,32,"00000000000100",6,sequence)},1,0,0,80);
        // Literal ordered commands, including the repeated WIFI and SVO toggles.
        // Build once per request and reuse the same sequences in round two,
        // exactly as Profiles.load + DumlTransport.sendFrames in the pinned source.
        byte[][] packets={
            frame(16,88,18,"030100",32,sequence++),
            frame(6,114,6,"00000000000100",32,sequence++),
            frame(3,249,3,"8a237103f401",32,sequence++),
            frame(0,0,31,"000001",32,sequence++),
            frame(0,50,111,"3131000000",32,sequence++),
            frame(3,175,3,"032400000000000000",32,sequence++),
            frame(7,48,9,"41550000415500000100",32,sequence++),
            frame(7,48,9,"41550000415500000100",32,sequence++),
            frame(9,39,9,"00024800ffff0200000000",32,sequence++),
            frame(9,39,9,"00026300ffff0300000000",32,sequence++),
            frame(7,24,7,"ff415500",32,sequence++),
            frame(7,25,9,"c0",32,sequence++),
            frame(3,249,146,"d04aeffb01",32,sequence++),
            frame(3,249,146,"d04aeffb00",32,sequence++),
            frame(0,229,111,"323201",32,sequence++),
            frame(3,249,3,"236b820101",32,sequence++),
            frame(3,249,3,"8773e68a01",32,sequence++),
            frame(6,140,9,"000300",32,sequence++),
            frame(6,140,9,"000100",32,sequence++),
            frame(6,114,6,"000000000001ff",32,sequence++),
            frame(16,88,18,"030100",32,sequence)
        };
        return new Profile(packets,2,30,100,50);
    }
    private static byte[] frame(int set,int command,int destination,String payload,int type,int sequence) {
        byte[] out=new byte[13+payload.length()/2];
        out[0]=0x55; out[1]=(byte)out.length; out[2]=4;
        out[3]=(byte)crc(out,3,0x77,0x8c);
        out[4]=(byte)130; out[5]=(byte)destination;
        out[6]=(byte)sequence; out[7]=(byte)(sequence>>8); out[8]=(byte)type;
        out[9]=(byte)set; out[10]=(byte)command;
        for(int i=0;i<payload.length()/2;i++) out[11+i]=(byte)Integer.parseInt(payload.substring(i*2,i*2+2),16);
        int tail=crc(out,out.length-2,0x3692,0x8408);
        out[out.length-2]=(byte)tail; out[out.length-1]=(byte)(tail>>8);
        return out;
    }
    /** Strict version-1 frame header. A length is usable only after CRC-8 validation. */
    static int length(byte[] header) {
        if(header==null || header.length<4 || header[0]!=0x55 || (header[2]&0xfc)!=4
                || (header[3]&255)!=crc(header,3,0x77,0x8c)) return -1;
        int size=(header[1]&255)|((header[2]&3)<<8);
        return size>=13 && size<=1023?size:-1;
    }
    static boolean valid(byte[] packet) {
        if(packet==null || length(packet)!=packet.length) return false;
        int tail=(packet[packet.length-2]&255)|((packet[packet.length-1]&255)<<8);
        return tail==crc(packet,packet.length-2,0x3692,0x8408);
    }
    static boolean matches(byte[] request,byte[] response) {
        return valid(request) && valid(response) && (response[8]&0x80)!=0
            && response[4]==request[5] && response[5]==request[4]
            && response[6]==request[6] && response[7]==request[7]
            && response[9]==request[9] && response[10]==request[10];
    }
    /** Pinned validateResponse checks the response bit, not an invented cmdType mask. */
    static RadioDiagnostics.Ack classify(byte[] request,byte[] response) {
        if(length(response)<0) return RadioDiagnostics.Ack.INVALID_HEADER;
        if(!valid(response)) return RadioDiagnostics.Ack.INVALID_CRC;
        if((response[8]&0x80)==0) return RadioDiagnostics.Ack.NOT_RESPONSE;
        if(response[4]!=request[5] || response[5]!=request[4]) return RadioDiagnostics.Ack.ROUTING_MISMATCH;
        if(response[6]!=request[6] || response[7]!=request[7]) return RadioDiagnostics.Ack.SEQUENCE_MISMATCH;
        if(response[9]!=request[9] || response[10]!=request[10]) return RadioDiagnostics.Ack.COMMAND_MISMATCH;
        // Routing can match an encrypted response, but its body is not a plaintext status.
        if((response[8]&7)!=0) return RadioDiagnostics.Ack.BODY_UNINTERPRETED;
        if(response.length==13) return RadioDiagnostics.Ack.EMPTY_BODY;
        if(response.length!=14) return RadioDiagnostics.Ack.BODY_UNINTERPRETED;
        return response[11]==0?RadioDiagnostics.Ack.ZERO_STATUS:RadioDiagnostics.Ack.NONZERO_STATUS;
    }
    private static int crc(byte[] bytes,int length,int seed,int polynomial) {
        int result=seed;
        for(int i=0;i<length;i++) {
            result^=bytes[i]&255;
            for(int bit=0;bit<8;bit++) result=(result>>>1)^((result&1)!=0?polynomial:0);
        }
        return result;
    }
}
