import asyncio,hashlib,json
import pytest
from test_clip_preparation import clip,LIMITS
from test_fresh_upload_pipeline import setup,add_approval
from test_fresh_upload_routes import material
from fresh_review.clips import extract_clip_frames
from fresh_review.clip_audit import audit_clip
from core import decode_image

def clip_parser(monkeypatch):
 from PIL import Image
 import fresh_review.pipeline as module
 async def parse(*a,**kw):
  height=60 if a[1].height==80 else 40
  return {'objects':[{'object_id':'0','box_half_open':[0,0,20,height],'mask':Image.new('L',(20,height),255)}]}
 monkeypatch.setattr(module,'parse_sam_image_text',parse)

def approve_frames(service,clip):
 frames=extract_clip_frames(clip,[0,.8],LIMITS)['frames']
 for f in frames:
  add_approval(service,f['pixel_digest'],{'size':[f['width'],f['height']],'rights_reference':'synthetic-clip-frame','provider_upload_approved':True})
 return frames

def test_clip_actual_existing_image_pipeline_shared_pixels_dedup(clip,tmp_path,monkeypatch):
 service,_,_,calls=setup(tmp_path,monkeypatch);clip_parser(monkeypatch);approve_frames(service,clip)
 result=asyncio.run(audit_clip(clip,[0,.8],LIMITS,service))
 assert result['status']=='sampled_image_jobs_completed_not_clip_safety_clearance'
 assert result['completed_sample_count']==2 and len(calls)==2
 assert result['provider_calls_this_request']==2
 assert result['frames'][1]['provider_calls_this_sample']==0
 assert result['frames'][0]['image_job']['result']['persons'][0]['vest']=='absent'
 assert result['frames'][0]['requested_offset_seconds']==0 and result['frames'][1]['requested_offset_seconds']==.8
 assert not result['evidence_export_allowed']and result['cross_frame_person_identity']=='not_inferred'
 again=asyncio.run(audit_clip(clip,[0,.8],LIMITS,service))
 assert again['provider_calls_this_request']==0 and len(calls)==2

def test_clip_preflight_approval_before_any_call(clip,tmp_path,monkeypatch):
 service,_,_,calls=setup(tmp_path,monkeypatch)
 with pytest.raises(ValueError):asyncio.run(audit_clip(clip,[0,.8],LIMITS,service))
 assert not calls and not service.path.exists()

def test_clip_uncertain_stops_without_implicit_retry(clip,tmp_path,monkeypatch):
 service,_,_,calls=setup(tmp_path,monkeypatch,timeout=1);approve_frames(service,clip)
 result=asyncio.run(audit_clip(clip,[0,.8],LIMITS,service))
 assert result['status']=='partial_requires_operator_reconciliation'and result['completed_sample_count']==0
 assert result['provider_calls_this_request']is None
 assert len(result['frames'])==1 and len(calls)==1 and result['frames'][0]['image_job']['state']=='running_uncertain'
 again=asyncio.run(audit_clip(clip,[0,.8],LIMITS,service))
 assert again['provider_calls_this_request']==0 and len(calls)==1

def test_private_clip_http_explicit_enable_exact_frame_grants(material,clip,monkeypatch):
 import json
 from test_fresh_upload_routes import OWNER
 p,raw,frame,calls,c,job=material;clip_parser(monkeypatch)
 route='/fresh-review-clip-upload'
 files={'clip':('generated.mp4',clip,'video/mp4')};data={'offsets':json.dumps([0,.8])}
 assert c.post(route,files=files,data=data).status_code==409 and len(calls)==2
 p.trusted_clip_limits=LIMITS
 assert c.post(route,files=files,data=data).status_code==409 and len(calls)==2
 approve_frames(p,clip)
 out=c.post(route,files=files,data=data)
 assert out.status_code==200 and out.json()['completed_sample_count']==2 and len(calls)==4
 assert c.post(route,files=files,data=data).json()['provider_calls_this_request']==0 and len(calls)==4
 assert c.post(route,files=files,data=data,headers={'X-Vigilens-Local-Access':''}).status_code==403
 assert c.post(route,files=files,data=data,headers={'X-Vigilens-Display-Session':''}).status_code==403
