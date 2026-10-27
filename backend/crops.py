"""Source-bound crop preparation, never a detection or PPE correctness claim."""
import io
from PIL import Image
from dataclasses import dataclass
from core import fail,pixel_only_png,decode_image
from pipeline import Frame

@dataclass(frozen=True)
class PreparedRaster:
    png:bytes
    frame:Frame

def prepare_raster(data,mime):
    png=pixel_only_png(data,mime);decoded=decode_image(png,'image/png')
    return PreparedRaster(png,Frame(decoded.width,decoded.height,decoded.digest))

def crop_for_selected_object(raster,parsed,object_id):
    """Use the exact parsed frame and half-open source box, no wrong-frame fallback.
The crop contains the object rectangle, NOT a proven isolated person or private crop.
"""
    if not isinstance(raster,PreparedRaster):fail('INVALID_PREPARED_RASTER','Use validated pixel-only input.')
    actual=decode_image(raster.png,'image/png')
    if (actual.digest,actual.width,actual.height)!=(raster.frame.identity,raster.frame.width,raster.frame.height):fail('CROP_SOURCE_MISMATCH','Prepared raster identity mismatch.',422)
    if not isinstance(parsed,dict) or parsed.get('source')!='offline_saved_sam_text' or parsed.get('frame_identity')!=raster.frame.identity:fail('CROP_SOURCE_MISMATCH','Parsed output belongs to a different source frame.',422)
    objects=parsed.get('objects')
    if not isinstance(objects,list) or len(objects)>64:fail('INVALID_PARSED_OBJECTS','Bounded parsed objects required.')
    matches=[o for o in objects if isinstance(o,dict) and o.get('object_id')==object_id]
    if len(matches)!=1:fail('CROP_OBJECT_AMBIGUOUS','Select one exact parsed object.',422)
    o=matches[0];b=o.get('box_half_open');mask=o.get('mask')
    if not isinstance(b,(tuple,list)) or len(b)!=4 or any(type(v) is not int for v in b):fail('INVALID_CROP_BOX','Explicit integer half-open source box required.')
    x1,y1,x2,y2=b
    if not 0<=x1<x2<=raster.frame.width or not 0<=y1<y2<=raster.frame.height:fail('INVALID_CROP_BOX','Crop outside source raster.')
    if not isinstance(mask,Image.Image) or mask.size!=(x2-x1,y2-y1):fail('CROP_MASK_MISMATCH','Mask dimensions do not match selected source box.')
    with Image.open(io.BytesIO(raster.png)) as im:
        cropped=im.crop(tuple(b));out=io.BytesIO();cropped.save(out,'PNG')
    return {'png':out.getvalue(),'source_frame_identity':raster.frame.identity,'object_id':object_id,
            'box_half_open':tuple(b),'width':x2-x1,'height':y2-y1,'source':'offline_selected_object_crop',
            'person_identity_verified':False,'privacy_review_status':'not_validated','evidence_export_allowed':False}
