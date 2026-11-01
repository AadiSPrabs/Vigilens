"""Offline official meta-sam-parser 0.0.6 integration. No model transport.
Use complete saved/test text only. Conservative preflight quotas before official
parser's mask decoding, which otherwise has no quota ceiling.
"""
import re,threading
from collections import OrderedDict
from PIL import Image
from core import fail
from pipeline import Frame

# Content-addressed successful pure parse memo only. Every caller still rereads and
# verifies current private source/request/reply/ledger artifacts. No cached job or
# authority decision. Exact text+frame key; copied rasters; bounded to four entries.
_PARSE_MEMO=OrderedDict()
_PARSE_LOCK=threading.Lock()

def _copy_parse(result):
    return {**result,'objects':[{**obj,'mask':obj['mask'].copy()}for obj in result['objects']]}

async def parse_sam_image_text(text,frame,*,wire_completed):
    frame.validate()
    if wire_completed is not True or not isinstance(text,str)or len(text.encode('utf-8'))>256_000:
        return await _parse_sam_image_text(text,frame,wire_completed=wire_completed)
    key=(text,frame.width,frame.height,frame.identity)
    with _PARSE_LOCK:
        cached=_PARSE_MEMO.get(key)
        if cached is not None:
            _PARSE_MEMO.move_to_end(key)
            return _copy_parse(cached)
    parsed=await _parse_sam_image_text(text,frame,wire_completed=wire_completed)
    with _PARSE_LOCK:
        _PARSE_MEMO[key]=_copy_parse(parsed)
        _PARSE_MEMO.move_to_end(key)
        while len(_PARSE_MEMO)>4:_PARSE_MEMO.popitem(last=False)
    return parsed

MAX_QUARANTINED=8
MAX_QUARANTINE_DELTA=1  # observed-case bound only, not a proved containment margin

async def parse_sam_image_text_quarantine(text,frame,*,wire_completed):
    """Explicit opt-in: larger bounded saved text/mask quotas; objects whose official-parser mask
    shape differs from the named box are kept as raw box-only unverified records (mask None).
    Never pads, crops, drops or repairs a mask. No memo. Strict parse remains the default."""
    return await _parse_sam_image_text(text,frame,wire_completed=wire_completed,quarantine=True)

async def _parse_sam_image_text(text,frame,*,wire_completed,quarantine=False):
    frame.validate()
    if wire_completed is not True:fail('SEGMENTATION_INCOMPLETE','Require confirmed completed saved output; no partial decode.',422)
    text_cap=512_000 if quarantine else 256_000;area_cap=4_000_000 if quarantine else 2_000_000
    if not isinstance(text,str) or len(text.encode('utf-8'))>text_cap:fail('SAM_TEXT_LIMIT','Saved SAM text exceeds offline limit.',422)
    # Live SAM output may terminate its single image record with one line ending.
    # Remove only that terminator, never internal whitespace or additional frames.
    if text.endswith('\r\n'):text=text[:-2]
    elif text.endswith('\n'):text=text[:-1]
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
            if not 0<w<=frame.width or not 0<h<=frame.height or w*h>1_000_000 or area>area_cap:fail('SAM_MASK_LIMIT','Decoded mask quota exceeded before parser.',422)
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
        objects=[];held=0
        for key,b in boxes.items():
            m=masks[key];bounds=m.bounds
            if (bounds.left,bounds.top,bounds.right,bounds.bottom)!=(b.left,b.top,b.right,b.bottom) or not 0<=b.left<b.right<=frame.width or not 0<=b.top<b.bottom<=frame.height:fail('SAM_BOUNDS_MISMATCH','Parsed geometry outside source frame.',422)
            if (m.mask.width,m.mask.height)!=(b.right-b.left,b.bottom-b.top):
                if not quarantine:fail('SAM_BOUNDS_MISMATCH','Mask shape differs from source box.',422)
                if abs(m.mask.width-(b.right-b.left))>MAX_QUARANTINE_DELTA or abs(m.mask.height-(b.bottom-b.top))>MAX_QUARANTINE_DELTA:fail('SAM_BOUNDS_MISMATCH','Mask/box mismatch beyond the bounded quarantine delta; whole source stopped.',422)
                held+=1
                if held>MAX_QUARANTINED:fail('SAM_QUARANTINE_LIMIT','Too many inconsistent masks; whole source stopped.',422)
                # Raw box kept for conservative blocking only; the declared mask is never used.
                objects.append({'object_id':key,'box_half_open':(b.left,b.top,b.right,b.bottom),'mask':None,'confidence':b.confidence,
                                'geometry_status':'unverified_box_only','quarantine_reason':'mask_shape_differs_from_box',
                                'declared_mask_size':[m.mask.width,m.mask.height],'box_size':[b.right-b.left,b.bottom-b.top]})
                continue
            raster=decode_mask_to_raster(m.mask)
            if len(raster)!=m.mask.width*m.mask.height or not set(raster)<={0,1}:fail('SAM_MASK_INVALID','Invalid decoded binary raster.',422)
            objects.append({'object_id':key,'box_half_open':(b.left,b.top,b.right,b.bottom),
                            'mask':Image.frombytes('L',(m.mask.width,m.mask.height),bytes(v*255 for v in raster)),
                            'confidence':b.confidence})
        return {'objects':objects,'source':'offline_saved_sam_text','frame_identity':frame.identity,
                'evidence_export_allowed':False,'privacy_review_status':'not_validated',
                'detection_status':'none_detected' if not objects else ('parsed_with_geometry_quarantine' if held else 'parsed_not_assessed')}
    except Exception as e:
        from core import AuditError
        if isinstance(e,AuditError):raise
        fail('SAM_PARSE_FAILED','Official offline parser failed; no partial output released.',422)
