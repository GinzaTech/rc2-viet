// SPDX-License-Identifier: AGPL-3.0-only
package local.rc2.hud;

/** Immutable, bounded metadata. Never retains payloads, serials or exception text. */
final class RadioDiagnostics {
    private RadioDiagnostics() { }
    enum Stage { CONNECTING, CONNECT_FAILED, DISPATCHING, WRITE_FAILED, WRITTEN }
    enum Ack {
        NOT_READ, NOT_EXPECTED, EMPTY_BODY, ZERO_STATUS, NONZERO_STATUS, BODY_UNINTERPRETED,
        INVALID_HEADER, INVALID_CRC, NOT_RESPONSE, ROUTING_MISMATCH, SEQUENCE_MISMATCH,
        COMMAND_MISMATCH, TIMEOUT, EOF, TRUNCATED, EMPTY_READ, IO_ERROR, FRAME_LIMIT, CANCELLED;
        // Body shapes are observations. Upstream defines no acceptance/status decoder.
        boolean matched() {
            return this==EMPTY_BODY || this==ZERO_STATUS || this==NONZERO_STATUS || this==BODY_UNINTERPRETED;
        }
    }
    static final class Metadata {
        final int sequence,sender,destination,type,set,command,bodyLength;
        private Metadata(byte[] frame) {
            sequence=(frame[6]&255)|((frame[7]&255)<<8); sender=frame[4]&255;
            destination=frame[5]&255; type=frame[8]&255; set=frame[9]&255;
            command=frame[10]&255; bodyLength=frame.length-13;
        }
        static Metadata of(byte[] frame) { return RadioProtocol.valid(frame)?new Metadata(frame):null; }
        String summary() {
            return "seq="+sequence+" src="+sender+" dst="+destination+" type="+type
                +" set="+set+" cmd="+command+" bodyLen="+bodyLength;
        }
    }
    static final class Frame {
        final int index,total,round,position,status,received,observed;
        final Metadata request,response;
        final Stage stage;
        final Ack ack,lastMismatch;
        private Frame(int index,int total,int round,int position,Metadata request,Metadata response,
                Stage stage,Ack ack,Ack mismatch,int status,int received,int observed) {
            this.index=index; this.total=total; this.round=round; this.position=position;
            this.request=request; this.response=response; this.stage=stage; this.ack=ack;
            lastMismatch=mismatch; this.status=status; this.received=received; this.observed=observed;
        }
        static Frame begin(int index,RadioProtocol.Profile profile,byte[] packet) {
            return new Frame(index,profile.count(),index/profile.roundSize()+1,index%profile.roundSize()+1,
                Metadata.of(packet),null,Stage.CONNECTING,Ack.NOT_READ,Ack.NOT_READ,-1,0,0);
        }
        Frame stage(Stage value) {
            return new Frame(index,total,round,position,request,response,value,ack,lastMismatch,status,received,observed);
        }
        Frame ack(Ack value,Ack mismatch,Metadata response,int status,int received,int observed) {
            return new Frame(index,total,round,position,request,response,stage,value,mismatch,status,received,observed);
        }
        String summary() {
            return "frame="+index+" total="+total+" round="+round+" position="+position+" "+request.summary()
                +" stage="+stage+" ack="+ack+" status="+status+" received="+received+" observed="+observed
                +" lastMismatch="+lastMismatch+(response==null?"":" response={"+response.summary()+"}");
        }
    }
    static final class Report {
        final int total,attempted,written,matchedReplies,writeFailures;
        final boolean complete;
        final Frame last,firstIssue;
        private final Frame[] frames;
        private Report(Frame[] frames,boolean complete,Frame last) {
            this.frames=frames; this.complete=complete; this.last=last; total=frames.length;
            int attempted=0,written=0,matched=0,failures=0; Frame issue=null;
            for(Frame frame:frames) {
                if(frame==null) continue;
                attempted++;
                if(frame.stage==Stage.WRITTEN) written++;
                if(frame.ack.matched()) matched++;
                boolean failed=frame.stage==Stage.CONNECT_FAILED || frame.stage==Stage.WRITE_FAILED;
                if(failed) failures++;
                if(issue==null && (failed || (frame.stage==Stage.WRITTEN && frame.ack!=Ack.NOT_READ
                        && frame.ack!=Ack.NOT_EXPECTED && frame.ack!=Ack.EMPTY_BODY && frame.ack!=Ack.ZERO_STATUS))) issue=frame;
            }
            this.attempted=attempted; this.written=written; matchedReplies=matched;
            writeFailures=failures; firstIssue=issue;
        }
        static Report empty() { return start(0); }
        static Report start(int total) { return new Report(new Frame[total],false,null); }
        Report with(Frame frame) {
            Frame[] next=frames.clone(); next[frame.index]=frame; return new Report(next,complete,frame);
        }
        Report completed() { return new Report(frames,true,last); }
        String summary() {
            return "attempted="+attempted+"/"+total+" written="+written+" matchedReplies="+matchedReplies
                +" writeFailures="+writeFailures+" complete="+complete
                +(firstIssue==null?"":" firstIssue={"+firstIssue.summary()+"}")
                +(last==null?"":" last={"+last.summary()+"}");
        }
    }
}
