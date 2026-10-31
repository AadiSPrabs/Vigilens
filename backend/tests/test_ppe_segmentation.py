import asyncio,json,hashlib,sqlite3
import pytest
from PIL import Image
from test_fresh_upload_routes import material,prepare,acknowledge,report
from fresh_review.ppe_segmentation import PpeSegmentation,BATCH_RESERVE,total
from fresh_review.pipeline import digest

def helper(p,frame,monkeypatch,*,empty=False):
 import fresh_review.ppe_segmentation as module
 async def parse(*args,**kwargs):return {'objects':[]if empty else[{'object_id':'0','box_half_open':[0,0,10,10],'mask':Image.new('L',(10,10),255)}]}
 monkeypatch.setattr(module,'parse_sam_image_text',parse)
 h=PpeSegmentation(p);plan=h.plan(frame.digest)
 grant={'format':'vigilens.exact-ppe-mask-grant.v1','execution_scope':p.execution_scope,'source_digest':frame.digest,'result_sha256':plan['result_sha256'],'plan_sha256':digest(plan),'max_reserved_usd':str(BATCH_RESERVE),'authority_reference':'synthetic-only-not-owner-grant'}
 path=p.path.parent/'synthetic-mask-grant.json';raw=json.dumps(grant).encode();path.write_bytes(raw);path.chmod(0o600)
 h=PpeSegmentation(p,approval_path=path,approval_sha256=hashlib.sha256(raw).hexdigest())
 identity=h.reserve(frame.digest)
 return h,identity

def test_auxiliary_masks_http_report_original_immutable_and_dedup(material,monkeypatch):
 p,raw,frame,calls,c,job=material;h,identity=helper(p,frame,monkeypatch)
 x=prepare(c,raw,frame);acknowledge(c,x);body={'source_digest':frame.digest,'result_sha256':digest(job['result'])}
 path='/fresh-review/'+frame.digest+'/ppe-segmentation/'+identity
 assert c.post(path,json=body).status_code==409 and len(calls)==2
 p.ppe_segmentation=h
 out=c.post(path,json=body);assert out.status_code==200 and out.json()['state']=='completed'
 assert [s['concept']for s in out.json()['segmentations']]==['helmet','vest']
 assert len(calls)==4 and [b['input'][0]['content'][0]['text']for b in calls[-2:]]==['helmet','vest']
 assert c.post(path,json=body).json()['provider_calls_this_request']==0 and len(calls)==4
 assert p.read(frame.digest)['result']==job['result']
 r=report(c,x,job).json();assert len(r['ppe_segmentation']['batches'])==1
 assert 'data:image'not in json.dumps(r)
 assert h.reserve(frame.digest)==identity

def test_empty_segmentation_not_absence_and_timeout_no_retry(material,monkeypatch):
 p,raw,frame,calls,c,job=material;h,identity=helper(p,frame,monkeypatch,empty=True)
 out=asyncio.run(h.run(identity));assert out['state']=='completed'
 assert all(s['objects']==[]and s['empty_detection']=='not_proof_of_absence'for s in out['segmentations'])
 assert len(calls)==4

def test_mask_timeout_preserves_shared_hold(material,monkeypatch):
 p,raw,frame,calls,c,job=material;h,identity=helper(p,frame,monkeypatch)
 def timeout(body):calls.append(body);raise TimeoutError()
 p.transport=timeout
 out=asyncio.run(h.run(identity));assert out['state']=='attempted_uncertain'and out['segmentations']is None and out['provider_calls_this_request']is None
 assert len(calls)==3
 assert asyncio.run(h.run(identity))['provider_calls_this_request']==0 and len(calls)==3
 db=p.connect();assert total(db)==BATCH_RESERVE;db.close()

def test_mask_grant_tamper_and_reply_tamper(material,monkeypatch):
 p,raw,frame,calls,c,job=material;h,identity=helper(p,frame,monkeypatch)
 original=h.approval_path.read_bytes();h.approval_path.write_text('{}')
 with pytest.raises(ValueError):asyncio.run(h.run(identity))
 assert len(calls)==2
 h.approval_path.write_bytes(original);assert asyncio.run(h.run(identity))['state']=='completed'
 h.artifact(identity,1,'reply.bin').write_bytes(b'changed')
 with pytest.raises(ValueError):h.read(identity)

def test_aux_masks_render_on_treated_only_and_restore_privacy(material,monkeypatch):
 import io
 p,raw,frame,calls,c,job=material;h,identity=helper(p,frame,monkeypatch);p.ppe_segmentation=h
 assert asyncio.run(h.run(identity))['state']=='completed'
 x=prepare(c,raw,frame);acknowledge(c,x)
 r=c.get('/fresh-private-report/'+x['session_id']+'/overlay');assert r.status_code==200
 im=Image.open(io.BytesIO(r.content)).convert('RGB')
 assert im.getpixel((0,0))==(40,100,210) # last vest mask boundary, not invented box
 assert im.getpixel((2,2))==(0,0,0) # privacy treatment restored after all linework
 assert len(calls)==4

def test_cross_stage_signal_uses_only_report_visible_observations(tmp_path,monkeypatch):
 # Downstream-mechanism test: treat the stored legacy person as clean-basis so this still exercises the display/rule path. Real legacy behavior (withheld) is covered in test_ppe_basis and test_fresh_upload_routes.
 monkeypatch.setattr('fresh_review.ppe_basis.basis_of',lambda person:'clean_crop')
 from test_fresh_upload_pipeline import setup
 from fresh_test_helpers import response
 from fastapi.testclient import TestClient
 from app import create_app
 from test_fresh_upload_routes import OWNER
 p,raw,frame,calls=setup(tmp_path,monkeypatch);original=p.transport
 def transport(body):
  if body['model']=='muse-spark-1.3':calls.append(body);return response('present','present')
  return original(body)
 p.transport=transport
 job=asyncio.run(p.run(raw,'image/png',[]))
 h,identity=helper(p,frame,monkeypatch,empty=True);p.ppe_segmentation=h
 assert asyncio.run(h.run(identity))['state']=='completed'
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 x=prepare(c,raw,frame);acknowledge(c,x)
 visible=report(c,x,job).json()
 assert {row['item']for row in visible['ppe_cross_stage_review']['signals']}=={'helmet','vest'}
 identity='fresh:'+frame.digest+':'+digest(job['result'])
 payload={'assessment_id':identity,'source_digest':frame.digest,'output_sha256':x['output_sha256'],'regions_digest':x['regions_digest'],'persons':{'0':{'exact_source_confirmed':True,'face_coverage_checked':True,'head_evidence_visible':False,'torso_evidence_visible':False}}}
 hidden=c.post('/fresh-private-report/'+x['session_id'],json=payload)
 assert hidden.status_code==200 and hidden.json()['ppe_cross_stage_review']['signals']==[]
 assert p.read(frame.digest)['result']['persons'][0]['helmet']=='present'and len(calls)==4
