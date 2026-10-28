"""Offline real-image region redaction probe. No routes, storage service or release."""
from PIL import Image,ImageDraw
from core import decode_image,pixel_only_png
import io,hashlib,math

def probe(data,mime,*,source_digest,frame_size,regions,reviewer_label):
 frame=decode_image(data,mime)
 if (frame.digest,(frame.width,frame.height))!=(source_digest,tuple(frame_size)):raise ValueError('Review belongs to a different source/frame')
 if not reviewer_label.strip() or len(reviewer_label)>80:raise ValueError('Local reviewer label required, not authenticated identity')
 if not isinstance(regions,list) or not 1<=len(regions)<=64:raise ValueError('Zero regions cannot establish no faces')
 im=Image.open(io.BytesIO(pixel_only_png(data,mime))).convert('RGB');out=im.copy();draw=ImageDraw.Draw(out)
 ids=set()
 for region in regions:
  if set(region)!={'person_id','box'} or not isinstance(region['person_id'],str) or not region['person_id'].strip() or region['person_id'] in ids:raise ValueError('Unique local person label required')
  ids.add(region['person_id']);b=region['box']
  if not isinstance(b,list) or len(b)!=4 or any(type(v)is not int for v in b):raise ValueError('Integer source pixel bounds required')
  l,t,r,bottom=b
  if not 0<=l<r<=frame.width or not 0<=t<bottom<=frame.height:raise ValueError('Out of frame privacy region')
  draw.rectangle((l,t,r-1,bottom-1),fill='black')
 # Pixels-only re-encode, never preserve source EXIF/name/embedded thumbnail.
 clean=Image.frombytes('RGB',out.size,out.tobytes());buf=io.BytesIO();clean.save(buf,'PNG');png=buf.getvalue()
 return png,{'source':'offline_manual_regions_real_image_probe','source_digest':frame.digest,'width':frame.width,'height':frame.height,'regions':regions,'reviewer_label':reviewer_label.strip(),'output_sha256':hashlib.sha256(png).hexdigest(),'coverage':'not_verified','privacy_review_status':'not_validated','evidence_export_allowed':False,'warning':'Manual opaque regions only, not a face detector or anonymity guarantee. Body, tattoos, clothes and location can identify people. Not model input or safe evidence.'}
