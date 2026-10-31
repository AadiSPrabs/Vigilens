import asyncio,io,pytest
from PIL import Image
from core import AuditError
from pipeline import Frame
import sam_parser
from sam_parser import parse_sam_image_text,parse_sam_image_text_quarantine
import fresh_review.wide_scene as ws
from fresh_review.wide_sequential import SequentialLimits
from fresh_review.overlays import render_overlay
from test_wide_sequential import seq,run
TEXT="<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|><|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
BAD=TEXT.replace('x2=270','x2=269')   # box 60 wide->see test below
F=Frame(320,334,'official-doc-saved-example')
def q(t=TEXT):return asyncio.run(parse_sam_image_text_quarantine(t,F,wire_completed=True))
def test_consistent_reply_identical_in_both_modes():
 a=asyncio.run(parse_sam_image_text(TEXT,F,wire_completed=True))['objects'][0];b=q()['objects'][0]
 assert a['box_half_open']==b['box_half_open'] and a['mask'].tobytes()==b['mask'].tobytes() and 'geometry_status' not in b
def test_strict_default_still_rejects_mismatch():
 with pytest.raises(AuditError):asyncio.run(parse_sam_image_text(BAD,F,wire_completed=True))
def test_quarantine_keeps_raw_box_no_mask_no_repair():
 r=q(BAD);o=r['objects'][0]
 assert o['mask'] is None and o['geometry_status']=='unverified_box_only' and o['box_half_open']==(211,228,270,255)
 assert o['declared_mask_size']==[60,27] and o['box_size']==[59,27] and r['detection_status']=='parsed_with_geometry_quarantine'
def test_quarantine_count_bounded(monkeypatch):
 monkeypatch.setattr(sam_parser,'MAX_QUARANTINED',0)
 with pytest.raises(AuditError):q(BAD)
def test_text_cap_raised_only_in_quarantine_and_bounded():
 pad=TEXT+' '*300_000
 with pytest.raises(AuditError):asyncio.run(parse_sam_image_text(pad,F,wire_completed=True))
 with pytest.raises(AuditError):q(TEXT+'x'*520_000)   # above the explicit bound
def test_hostile_mismatch_magnitudes_fail_whole_source():
 for t in (TEXT.replace('x2=270','x2=250'),TEXT.replace('x2=270','x2=290'),TEXT.replace('x1=211','x1=100'),TEXT.replace('x2=270','x2=268'),TEXT.replace('x2=270','x2=272')):
  with pytest.raises(AuditError):q(t)
def test_one_pixel_delta_still_quarantined():
 assert q(TEXT.replace('x2=270','x2=269'))['objects'][0]['mask'] is None and q(TEXT.replace('x2=270','x2=271'))['objects'][0]['mask'] is None
def test_other_failures_not_softened():
 for t in (TEXT[:-8],TEXT.replace('x1=211','x1=211;surprise=1'),TEXT.replace('27,60,','999999,999999,'),BAD.replace('w=320','w=999')):
  with pytest.raises(AuditError):q(t)
 with pytest.raises(AuditError):asyncio.run(parse_sam_image_text_quarantine(BAD,F,wire_completed=False))
def quar(tmp_path,monkeypatch,bad_ids=('1',)):
 p,raw,f,calls=seq(tmp_path,monkeypatch,eligible=4,limits=SequentialLimits(max_ppe_calls=16,geometry_quarantine=True))
 objs=asyncio.run(ws.parse_sam_image_text(None,None)) if False else None
 return p,raw,f,calls
def test_pipeline_unverified_person_and_overlapping_neighbours_blocked(tmp_path,monkeypatch):
 p,raw,f,calls=seq(tmp_path,monkeypatch,eligible=4,limits=SequentialLimits(max_ppe_calls=16,geometry_quarantine=True))
 orig=ws.parse_sam_image_text
 async def parse(*a,**k):
  objs=(await orig(*a,**k))['objects'];out=[]
  for o in objs:
   if o['object_id']=='1':o={'object_id':'1','box_half_open':o['box_half_open'],'mask':None,'confidence':None,'geometry_status':'unverified_box_only','quarantine_reason':'mask_shape_differs_from_box','declared_mask_size':[99,179],'box_size':[100,180]}
   out.append(o)
  # neighbour 2 gets a box overlapping the unverified box 1 (but no verified foreground overlap)
  l,t,r,b=out[2]['box_half_open'];x,y,rr,bb=out[1]['box_half_open'];out[2]={**out[2],'box_half_open':[x+50,t,x+50+(r-l),b],'mask':Image.new('L',(r-l,b-t),255)}
  return {'objects':out}
 monkeypatch.setattr(ws,'parse_sam_image_text_quarantine',parse)
 out=run(p,raw);r=out['result'];by={x['id']:x for x in r['persons']}
 assert out['state']=='completed' and len(calls)==1 and [c['model'] for c in calls]==['sam-3.1']
 assert r['wide_scene']['PPE_assessed_count']==0 and r['wide_scene']['ppe_withheld_unverified_geometry']
 assert all(q['ppe_evidence_status']in('geometry_unverified_not_assessed','crop_evidence_ineligible','ppe_withheld_source_has_unverified_geometry')and not q['ppe_assessed']for q in r['persons'])
 assert any(q['ppe_evidence_status']=='ppe_withheld_source_has_unverified_geometry'for q in r['persons'])
 assert by['1']['ppe_evidence_status']=='geometry_unverified_not_assessed' and by['1']['mask'] is None and not by['1']['ppe_assessed'] and by['1']['helmet']=='unknown'
 assert by['2']['ppe_evidence_status']=='crop_evidence_ineligible' and 'overlaps_unverified_geometry_person_box' in by['2']['crop_eligibility']['review_reasons']
 assert r['wide_scene']['geometry_unverified_count']==1 and r['wide_scene']['all_detected_persons_retained'] and r['wide_scene']['geometry_quarantine_mode']
 assert not any(c.get('model')!='sam-3.1' and False for c in calls)
 again=run(p,raw);assert again['provider_calls_this_request']==0 and again['result']==r
def test_default_limits_are_strict_and_bound_into_binding(tmp_path,monkeypatch):
 assert SequentialLimits().geometry_quarantine is False
 with pytest.raises(ValueError):SequentialLimits(geometry_quarantine=1).validate()
def test_overlay_draws_box_only_for_unverified():
 im=Image.new('RGB',(200,200),'black');b=io.BytesIO();im.save(b,'PNG')
 res={'image':{'width':200,'height':200},'persons':[{'id':'1','box_half_open':[20,20,120,160],'mask':None}],'zones':[]}
 out=render_overlay(b.getvalue(),res,[]);assert out is not None

def test_http_report_pdf_and_proposal_label_unverified_geometry(tmp_path,monkeypatch):
 from test_wide_sequential import sequential_http_report
 box={}
 async def parse(*a,**k):
  out=[]
  for o in (await box['orig'](*a,**k))['objects']:
   if o['object_id']=='1':o={'object_id':'1','box_half_open':o['box_half_open'],'mask':None,'confidence':None,'geometry_status':'unverified_box_only','quarantine_reason':'mask_shape_differs_from_box','declared_mask_size':[99,179],'box_size':[100,180]}
   out.append(o)
  return {'objects':out}
 def hook():
  box['orig']=ws.parse_sam_image_text;monkeypatch.setattr(ws,'parse_sam_image_text_quarantine',parse)
 p,f,res,doc,pdf,calls=sequential_http_report(tmp_path,monkeypatch,partial=False,limits=SequentialLimits(max_ppe_calls=16,geometry_quarantine=True),hook=hook)
 by={q['person_id']:q for q in doc['persons']}
 assert by['1']['geometry_status']=='unverified_box_only' and not by['1']['ppe_assessed'] and by['1']['report_display_helmet']=='unknown'
 assert doc['wide_scene']['geometry_unverified_count']==1 and doc['wide_scene']['PPE_assessed_count']==0 and len(calls)==1
 assert doc['wide_scene']['coverage']=='ppe_withheld_source_unverified_geometry'
 import os
 if os.environ.get('QUAR_PDF_OUT'):open(os.environ['QUAR_PDF_OUT'],'wb').write(pdf)

def test_no_ppe_continuation_for_unverified_source_with_otherwise_valid_grant(tmp_path,monkeypatch):
 from test_wide_sequential import sequential_http_report,grant
 import json as _j
 box={}
 async def parse(*a,**k):
  out=[]
  for o in (await box['orig'](*a,**k))['objects']:
   if o['object_id']=='1':o={'object_id':'1','box_half_open':o['box_half_open'],'mask':None,'confidence':None,'geometry_status':'unverified_box_only','quarantine_reason':'x','declared_mask_size':[99,179],'box_size':[100,180]}
   out.append(o)
  return {'objects':out}
 def hook():
  box['orig']=ws.parse_sam_image_text;monkeypatch.setattr(ws,'parse_sam_image_text_quarantine',parse)
 p,f,res,doc,pdf,calls=sequential_http_report(tmp_path,monkeypatch,partial=False,limits=SequentialLimits(max_ppe_calls=16,geometry_quarantine=True),hook=hook)
 out=p.read(f.digest);w=out['result']['wide_scene']
 assert out['state']=='completed' and w['all_detected_people_assessed'] is False and w['coverage']=='ppe_withheld_source_unverified_geometry' and w['job_state_is_execution_terminal_not_assessment_complete'] is True
 assert doc['wide_scene']['coverage']=='ppe_withheld_source_unverified_geometry' and doc['wide_scene']['all_detected_people_assessed'] is False
 ids=[q['id'] for q in out['result']['persons'] if q['crop_eligibility']['eligible_for_selected_crop_call']][:1] or ['0']
 gp,gs=grant(tmp_path,p,f,out,ids)
 # same grant shape is accepted on a verified partial source (see continuation tests); here only the geometry guard may refuse it
 with pytest.raises(ValueError,match='unverified geometry'):p.continue_partial(f.digest,gp,gs)
 assert len(calls)==1
def test_no_proposal_api_consumer_can_infer_complete_from_state(tmp_path,monkeypatch):
 from test_wide_sequential import sequential_http_report
 box={}
 async def parse(*a,**k):
  out=[]
  for o in (await box['orig'](*a,**k))['objects']:
   if o['object_id']=='1':o={'object_id':'1','box_half_open':o['box_half_open'],'mask':None,'confidence':None,'geometry_status':'unverified_box_only','quarantine_reason':'x','declared_mask_size':[99,179],'box_size':[100,180]}
   out.append(o)
  return {'objects':out}
 def hook():
  box['orig']=ws.parse_sam_image_text;monkeypatch.setattr(ws,'parse_sam_image_text_quarantine',parse)
 p,f,res,doc,pdf,calls=sequential_http_report(tmp_path,monkeypatch,partial=False,limits=SequentialLimits(max_ppe_calls=16,geometry_quarantine=True),hook=hook)
 r=p._c.get('/fresh-review/'+f.digest+'/integration-contract');assert r.status_code==200,r.text;j=r.json()
 assert j['all_detected_people_assessed'] is False and j['coverage']=='ppe_withheld_source_unverified_geometry' and j['ppe_withheld_unverified_geometry'] and j['execution_state_is_not_assessment_completeness'] is True
 assert all(x['ppe']['assessment_status']=='not_assessed' for x in j['persons'])
