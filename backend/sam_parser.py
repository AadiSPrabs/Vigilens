"""Offline official meta-sam-parser 0.0.6 integration. No model transport.
Use complete saved/test text only. Conservative preflight quotas before official
parser's mask decoding, which otherwise has no quota ceiling.
"""
import re
from PIL import Image
from core import fail
from pipeline import Frame

async def parse_sam_image_text(text,frame,*,wire_completed):
    frame.validate()
    if wire_completed is not True:fail('SEGMENTATION_INCOMPLETE','Require confirmed completed saved output; no partial decode.',422)
    if not isinstance(text,str) or len(text.encode('utf-8'))>256_000:fail('SAM_TEXT_LIMIT','Saved SAM text exceeds offline limit.',422)
    # Quota/identity preflight ONLY, not a replacement for official grammar parsing.
    if text:
        if '\n' in text or '\r' in text or not text.startswith('<0f>'):fail('SAM_IMAGE_FRAME_INVALID','Only a single image frame is accepted.',422)
        boxes=re.findall(r'<\|box;([^|]*)\|>',text)
        masks=re.findall(r'<\|mask;([^|]*)\|>',text)
        if not 1<=len(boxes)==len(masks)<=64:fail('SAM_RECORD_LIMIT','Require bounded paired image boxes/masks.',422)
        for box in boxes:
            dimensions={k:int(v) for k,v in re.findall(r'(?:^|;)(w|h)=([0-9]+)(?=;|$)',box)}
            if dimensions!={'w':frame.width,'h':frame.height}:fail('SAM_SOURCE_FRAME_MISMATCH','SAM source dimensions differ from the named raster.',422)
        area=0
        for mask in masks:
            match=re.search(r'(?:^|;)data=([0-9]+),([0-9]+),[!~]',mask)
            if not match:fail('SAM_MASK_INVALID','Missing explicit mask dimensions.',422)
            h,w=map(int,match.groups());area+=w*h
            if not 0<w<=frame.width or not 0<h<=frame.height or w*h>1_000_000 or area>2_000_000:fail('SAM_MASK_LIMIT','Decoded mask quota exceeded before parser.',422)
    try:
        from meta_sam_parser import parse_responses_stream,image_segmentation_format,decode_mask_to_raster
    except ImportError:fail('OFFICIAL_PARSER_MISSING','Install pinned meta-sam-parser before offline decoding.',503)
    async def events():
        lane={'item_id':'offline-saved-text','output_index':0,'content_index':0}
        if text:yield dict(lane,type='response.output_text.delta',delta=text)
        yield dict(lane,type='response.output_text.done',text=text)
        yield {'type':'response.completed','response':{'status':'completed'}}
    try:
        result=await parse_responses_stream(events(),image_segmentation_format()).final_result()
        if result.outcome.status!='completed' or result.diagnostics:fail('SAM_PARSE_REVIEW','Official parser diagnostics or incomplete output; hold result.',422)
        boxes={};masks={}
        for record in result.records:
            if record.kind=='box':
                if record.object_id in boxes:fail('SAM_DUPLICATE_ID','Duplicate object ID.',422)
                boxes[record.object_id]=record
            elif record.kind=='mask':
                if record.object_id in masks:fail('SAM_DUPLICATE_ID','Duplicate object ID.',422)
                masks[record.object_id]=record
            else:fail('SAM_UNEXPECTED_RECORD','Nongeometry record requires review.',422)
        if set(boxes)!=set(masks):fail('SAM_UNPAIRED_RECORD','Box and mask IDs do not match.',422)
        objects=[]
        for key,b in boxes.items():
            m=masks[key];bounds=m.bounds
            if (bounds.left,bounds.top,bounds.right,bounds.bottom)!=(b.left,b.top,b.right,b.bottom) or not 0<=b.left<b.right<=frame.width or not 0<=b.top<b.bottom<=frame.height:fail('SAM_BOUNDS_MISMATCH','Parsed geometry outside source frame.',422)
            if (m.mask.width,m.mask.height)!=(b.right-b.left,b.bottom-b.top):fail('SAM_BOUNDS_MISMATCH','Mask shape differs from source box.',422)
            raster=decode_mask_to_raster(m.mask)
            if len(raster)!=m.mask.width*m.mask.height or not set(raster)<={0,1}:fail('SAM_MASK_INVALID','Invalid decoded binary raster.',422)
            objects.append({'object_id':key,'box_half_open':(b.left,b.top,b.right,b.bottom),
                            'mask':Image.frombytes('L',(m.mask.width,m.mask.height),bytes(v*255 for v in raster)),
                            'confidence':b.confidence})
        return {'objects':objects,'source':'offline_saved_sam_text','frame_identity':frame.identity,
                'evidence_export_allowed':False,'privacy_review_status':'not_validated',
                'detection_status':'none_detected' if not objects else 'parsed_not_assessed'}
    except Exception as e:
        from core import AuditError
        if isinstance(e,AuditError):raise
        fail('SAM_PARSE_FAILED','Official offline parser failed; no partial output released.',422)
