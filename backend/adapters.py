"""Offline request builder + stream boundary. NO network send implementation.
Wire grounding: https://dev.meta.ai/docs/sam/segmenting and
https://dev.meta.ai/docs/sam/reading-segmentation (read 2026-10-27).
Mask decoding intentionally requires the official parser; raw lane is not geometry.
"""
import base64
from core import decode_image,fail,pixel_only_png

class LiveTransportDisabled(RuntimeError):pass

def build_sam_image_request(image,mime,concept):
    decoded=decode_image(image,mime)
    if decoded.orientation!=1:fail('IMAGE_ORIENTATION_UNSUPPORTED','Use an explicitly upright image.',422)
    # Fixed application concepts prevent accidental multi-concept or reasoning prompts.
    if concept not in ('person','helmet','vest','face'):fail('INVALID_CONCEPT','Use one supported local test concept.')
    clean_image=pixel_only_png(image,mime)
    return {'model':'sam-3.1','input':[{'type':'message','role':'user','content':[
        {'type':'input_text','text':concept},
        {'type':'input_image','image_url':'data:image/png;base64,'+base64.b64encode(clean_image).decode('ascii')}]}],'stream':True}

class DisabledSamAdapter:
    def send(self,*args,**kwargs):raise LiveTransportDisabled('No live transport exists; account authority, budget, parser and privacy validation still required.')

class SamStreamBoundary:
    """SDK event envelope checks, not an SSE protocol or SAM token parser.
Completed empty output is normal detection output, NEVER face-free/safety clearance.
"""
    def __init__(self,max_text_bytes=2_000_000,max_events=4096):
        if type(max_text_bytes) is not int or max_text_bytes<=0 or type(max_events) is not int or max_events<=0:raise ValueError('Positive stream limits required')
        self.limit=max_text_bytes;self.max_events=max_events;self.parts=[];self.size=0;self.count=0;self.completed=False;self.failed=False
    def feed(self,event):
        if self.completed or self.failed:fail('STREAM_ALREADY_TERMINAL','No events accepted after terminal state.',422)
        self.count+=1
        if self.count>self.max_events:self.failed=True;fail('STREAM_LIMIT_EXCEEDED','Stream event bound exceeded.',422)
        if not isinstance(event,dict) or not isinstance(event.get('type'),str):self.failed=True;fail('INVALID_STREAM_EVENT','Invalid event envelope.',422)
        kind=event['type']
        if kind in ('error','response.failed','response.incomplete'):
            self.failed=True;self.parts=[];fail('MODEL_STREAM_FAILED','Stream failed or incomplete; hold result.',422)
        if kind=='response.output_text.delta':
            delta=event.get('delta')
            if not isinstance(delta,str):self.failed=True;fail('INVALID_STREAM_EVENT','Expected text delta.',422)
            self.size+=len(delta.encode('utf-8'))
            if self.size>self.limit:self.failed=True;self.parts=[];fail('STREAM_LIMIT_EXCEEDED','Stream text bound exceeded.',422)
            self.parts.append(delta)
        elif kind=='response.completed':self.completed=True
        # Other SDK lifecycle events carry no geometry and are ignored within limits.
    def finish(self):
        if not self.completed or self.failed:fail('SEGMENTATION_INCOMPLETE','Missing successful completion; no partial result.',422)
        text=''.join(self.parts)
        return {'raw_output_text':text,'wire_completed':True,'detection_status':'none_detected' if not text else 'requires_official_parser',
                'geometry_available':False,'evidence_export_allowed':False}
