"""Synthetic whole-clip stop semantics on the sequential wide path. Candidate behaviour, not an adopted policy,
no real clip, no spend. Frames are prepared dicts, so no decoder is involved."""
import asyncio,io,json,hashlib
from decimal import Decimal
from PIL import Image
from core import decode_image
from test_fresh_upload_pipeline import carry,approval_store
import fresh_review.wide_scene as ws
from fresh_review.wide_sequential import SequentialWidePipeline,SequentialLimits
from fresh_review.clip_audit import audit_prepared_clip
from test_wide_sequential import big,force_cost

def build(tmp_path,monkeypatch,shades,*,booked=None,fail_at=None,eligible=4):
 objects=[]
 for i in range(eligible):
  x=10+i*120;objects.append({'object_id':str(i),'box_half_open':[x,20,x+100,200],'mask':Image.new('L',(100,180),255)})
 async def parse(*a,**k):return {'objects':objects}
 monkeypatch.setattr(ws,'parse_sam_image_text',parse)
 frames=[];spec={}
 for n,shade in enumerate(shades):
  im=Image.new('RGB',(600,260),shade);b=io.BytesIO();im.save(b,'PNG');png=b.getvalue();f=decode_image(png,'image/png')
  frames.append({'sample_index':n,'requested_offset_seconds':n*.5,'timestamp_basis':'requested_decode_offset','source_clip_sha256':'c'*64,'pixel_digest':f.digest,'width':600,'height':260,'png':png})
  spec[f.digest]={'size':[600,260],'rights_reference':'generated','provider_upload_approved':True,'wide_scene':{'assess':'all_eligible','authority_reference':'synthetic-only'}}
 calls=[]
 def transport(body):
  calls.append(body)
  if fail_at is not None and len(calls)==fail_at:raise TimeoutError()
  if body['model']=='sam-3.1':return b'data: {"type":"response.completed","response":{"model":"sam-3.1","id":"synthetic-clip-SAM","status":"completed","usage":{"images_processed":1},"output":[]}}\n\n'
  return big(100)
 c=carry(tmp_path)
 if booked is not None:
  d=json.loads(c['carry_path'].read_text());d['conservative_booked_usd']=str(booked);c['carry_path'].write_text(json.dumps(d));c['carry_sha']=hashlib.sha256(c['carry_path'].read_bytes()).hexdigest()
 p=SequentialWidePipeline(tmp_path/'clip.sqlite',**c,execution_scope='synthetic_local_qualification',approval_store=approval_store(tmp_path,spec),transport=transport,wide_limits=SequentialLimits(max_ppe_calls=16))
 clip={'source_clip_sha256':'c'*64,'duration_seconds':2,'frames':frames}
 return p,clip,calls
def go(p,clip):return asyncio.run(audit_prepared_clip(clip,p))

def test_multi_person_clip_completes_per_frame_sequentially_and_shares_identical_pixels(tmp_path,monkeypatch):
 p,clip,calls=build(tmp_path,monkeypatch,['#223344','#334455','#223344'])
 out=go(p,clip)
 assert out['status']=='sampled_image_jobs_completed_not_clip_safety_clearance' and len(calls)==2*(1+4)
 assert out['frames'][2]['provider_calls_this_sample']==0 and out['provider_calls_this_request']==10
 assert out['frames_with_unassessed_people']==[] and out['cross_frame_person_identity']=='not_inferred'
 assert go(p,clip)['provider_calls_this_request']==0 and len(calls)==10

def test_budget_stop_on_a_frame_stops_whole_clip_and_later_frames_never_dispatch(tmp_path,monkeypatch):
 force_cost(monkeypatch,Decimal('.5'))
 # frame 0 completes; the shared aggregate (other jobs' reservations count) stops frame 1 part way
 p,clip,calls=build(tmp_path,monkeypatch,['#223344','#334455','#445566'],booked='1.0')
 out=go(p,clip)
 assert out['status']=='partial_requires_operator_reconciliation' and len(out['frames'])==2 and out['frames'][0]['image_job']['state']=='completed'
 states=[f['image_job']['state'] for f in out['frames']]
 assert states[-1]=='partial_completed' and out['frames'][-1]['image_job']['result']['wide_scene']['budget_deferred_never_attempted']
 stopped=out['frames'][-1]['pixel_digest']
 assert all(f['pixel_digest']!=clip['frames'][2]['pixel_digest'] for f in out['frames'])
 n=len(calls);again=go(p,clip);assert len(calls)==n  # no silent resume or retry
 assert out['frames_with_unassessed_people']==[out['frames'][-1]['sample_index']]
 assert out['sampled_frames_are_not_complete_clip_coverage'] is True

def test_uncertain_call_in_one_frame_stops_clip_without_retry_or_later_dispatch(tmp_path,monkeypatch):
 p,clip,calls=build(tmp_path,monkeypatch,['#223344','#334455','#445566'],fail_at=8)  # frame 1 completes (5 calls), 3rd call of frame 2 fails
 out=go(p,clip)
 assert out['status']=='partial_requires_operator_reconciliation' and len(out['frames'])==2 and len(calls)==8
 assert out['frames'][1]['image_job']['state']=='running_uncertain'
 again=go(p,clip);assert len(calls)==8 and again['status']=='partial_requires_operator_reconciliation'

def test_parser_stop_after_completed_sam_call_never_reports_zero_calls(tmp_path,monkeypatch):
 """Regression: a SAM call completed and was journaled, then the strict parser raised inside run().
 The returned job and clip summary must count that call (they reported 0). This does NOT change
 requires_operator_reconciliation: that field means an uncertain/in-flight provider call or unsettled cost,
 and here the single call is completed and fully costed, so it stays False by design. The clip status
 is partial_requires_operator_reconciliation because the clip stopped, which is a separate field."""
 from core import AuditError
 p,clip,calls=build(tmp_path,monkeypatch,['#223344','#334455'])
 async def refuse(*a,**k):raise AuditError('SAM_BOUNDS_MISMATCH','Mask shape differs from source box.',422)
 monkeypatch.setattr(ws,'parse_sam_image_text',refuse)
 out=go(p,clip);job=out['frames'][0]['image_job']
 assert len(calls)==1 and out['status']=='partial_requires_operator_reconciliation' and len(out['frames'])==1
 assert job['state']=='running_uncertain' and job['known_listed_usd']=='0.0025' and job['requires_operator_reconciliation'] is False
 assert out['provider_calls_this_request']==1 and out['frames'][0]['provider_calls_this_sample']==1
 again=go(p,clip)  # repeated run: reads the same stopped job, no second SAM call, and reports 0 NEW calls
 assert len(calls)==1 and again['status']=='partial_requires_operator_reconciliation'
 assert again['provider_calls_this_request']==0 and p.attempted_count(clip['frames'][0]['pixel_digest'])==1

def test_pre_dispatch_failure_after_claim_reports_zero_calls(tmp_path,monkeypatch):
 """A failure before any provider request leaves a claimed job with no call rows: 0 calls is then true."""
 p,clip,calls=build(tmp_path,monkeypatch,['#223344','#334455'])
 def boom(*a,**k):raise OSError('pre-dispatch failure')
 monkeypatch.setattr(p,'save_private',boom)
 out=go(p,clip)
 assert calls==[] and out['provider_calls_this_request']==0 and out['status']=='partial_requires_operator_reconciliation'
 assert out['frames'][0]['image_job']['requires_operator_reconciliation'] is True and len(out['frames'])==1
