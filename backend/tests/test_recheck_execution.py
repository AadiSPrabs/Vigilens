import asyncio,json,hashlib,sqlite3
import pytest
from PIL import Image
from test_fresh_upload_routes import material
from fresh_review.recheck_journal import RecheckJournal,RECHECK_RESERVE,reservation_total
from fresh_review.recheck_execution import RecheckExecutor
from fresh_review.pipeline import digest

def executor(p,frame,monkeypatch,*,objects=1):
 import fresh_review.recheck_execution as module
 async def parse(*args,**kwargs):
  return {'objects':[{'object_id':str(i),'box_half_open':[0,0,20,60],'mask':Image.new('L',(20,60),255)}for i in range(objects)]}
 monkeypatch.setattr(module,'parse_sam_image_text',parse)
 attempt=RecheckJournal(p).reserve(frame.digest,'0',max_attempts=1,authority_reference='synthetic-exact-request-authority')
 plan=attempt['plan'];grant={'format':'vigilens.exact-recheck-approval.v1','execution_scope':p.execution_scope,'source_digest':frame.digest,'result_sha256':plan['result_sha256'],'person_id':'0','plan_sha256':digest(plan),'authority_reference':'synthetic-exact-request-authority','request_sha256':[s['request_sha256']for s in plan['steps']],'max_reserved_usd':str(RECHECK_RESERVE)}
 path=p.path.parent/'synthetic-recheck-grant.json';raw=json.dumps(grant).encode();path.write_bytes(raw);path.chmod(0o600)
 return RecheckExecutor(p,approval_path=path,approval_sha256=hashlib.sha256(raw).hexdigest()),attempt

def test_exact_recheck_execution_separate_immutable_result_cost_and_repeat(material,monkeypatch):
 p,raw,frame,calls,c,job=material;e,a=executor(p,frame,monkeypatch)
 result=asyncio.run(e.run(a['attempt_id']))
 assert result['state']=='completed'and len(calls)==4 and result['provider_calls_this_request']==2
 assert result['result']['original_overwrite_allowed']is False
 assert p.read(frame.digest)['result']==job['result']
 db=p.connect();assert reservation_total(db)<RECHECK_RESERVE;db.close()
 assert asyncio.run(e.run(a['attempt_id']))['provider_calls_this_request']==0 and len(calls)==4

def test_recheck_approval_pin_and_scope_before_calls(material,monkeypatch):
 p,raw,frame,calls,c,job=material;e,a=executor(p,frame,monkeypatch)
 e.approval_path.write_text('{}')
 with pytest.raises(ValueError):asyncio.run(e.run(a['attempt_id']))
 assert len(calls)==2 and e.read(a['attempt_id'])['state']=='reserved_not_dispatched'

def test_recheck_timeout_keeps_full_hold_no_retry(material,monkeypatch):
 p,raw,frame,calls,c,job=material;e,a=executor(p,frame,monkeypatch)
 def uncertain(body):calls.append(body);raise TimeoutError()
 p.transport=uncertain
 result=asyncio.run(e.run(a['attempt_id']))
 assert result['state']=='attempted_uncertain'and result['result']is None and result['provider_calls_this_request']is None
 assert len(calls)==3
 assert asyncio.run(e.run(a['attempt_id']))['provider_calls_this_request']==0 and len(calls)==3
 db=p.connect();assert reservation_total(db)==RECHECK_RESERVE;db.close()
 assert p.read(frame.digest)['result']==job['result']

@pytest.mark.parametrize('objects',[0,2])
def test_ambiguous_crop_stops_before_ppe(material,monkeypatch,objects):
 p,raw,frame,calls,c,job=material;e,a=executor(p,frame,monkeypatch,objects=objects)
 result=asyncio.run(e.run(a['attempt_id']))
 assert result['state']=='attempted_uncertain'and len(calls)==3
 assert result['result']is None

def test_recheck_response_and_result_tamper_fail_closed(material,monkeypatch):
 p,raw,frame,calls,c,job=material;e,a=executor(p,frame,monkeypatch)
 assert asyncio.run(e.run(a['attempt_id']))['state']=='completed'
 e.artifact(a['attempt_id'],1,'reply.bin').write_bytes(b'changed')
 with pytest.raises(ValueError):e.read(a['attempt_id'])
 assert len(calls)==4

def test_recheck_second_call_uncertain_preserves_hold_and_no_retry(material,monkeypatch):
 p,raw,frame,calls,c,job=material;e,a=executor(p,frame,monkeypatch);original=p.transport
 def timeout_ppe(body):
  if body['model']=='muse-spark-1.3':calls.append(body);raise TimeoutError()
  return original(body)
 p.transport=timeout_ppe
 out=asyncio.run(e.run(a['attempt_id']))
 assert out['state']=='attempted_uncertain'and out['result']is None and len(calls)==4
 assert asyncio.run(e.run(a['attempt_id']))['retry_allowed']is False and len(calls)==4
 db=p.connect();assert reservation_total(db)==RECHECK_RESERVE;db.close()

def test_recheck_contradiction_keeps_original_unknown_proposal(material,monkeypatch):
 from fresh_test_helpers import response
 p,raw,frame,calls,c,job=material;e,a=executor(p,frame,monkeypatch);original=p.transport
 def opposite(body):
  if body['model']=='muse-spark-1.3':calls.append(body);return response('present','present')
  return original(body)
 p.transport=opposite
 out=asyncio.run(e.run(a['attempt_id']))
 assert out['state']=='completed'and out['result']['contradictions']==['vest']
 assert out['result']['review_display_proposal']=={'helmet':'present','vest':'unknown'}
 assert p.read(frame.digest)['result']['persons'][0]['vest']=='absent'

def test_future_original_budget_claim_revalidates_recheck_artifacts(material,monkeypatch):
 from test_fresh_upload_pipeline import add_approval
 from core import decode_image
 import io
 p,raw,frame,calls,c,job=material;e,a=executor(p,frame,monkeypatch)
 assert asyncio.run(e.run(a['attempt_id']))['state']=='completed'
 e.artifact(a['attempt_id'],1,'reply.bin').write_bytes(b'changed')
 b=io.BytesIO();Image.new('RGB',(80,80),'green').save(b,'PNG');f=decode_image(b.getvalue(),'image/png')
 add_approval(p,f.digest,{'size':[80,80],'rights_reference':'synthetic','provider_upload_approved':True})
 _,_,_,binding=p.prepare(b.getvalue(),'image/png',[])
 with pytest.raises(ValueError):p.claim(binding)
 assert len(calls)==4

def test_http_recheck_opt_in_bound_to_current_preview_and_report(material,monkeypatch):
 from test_fresh_upload_routes import prepare,acknowledge,report
 p,raw,frame,calls,c,job=material;e,a=executor(p,frame,monkeypatch)
 path='/fresh-review/'+frame.digest+'/recheck/'+a['attempt_id']
 body={'source_digest':frame.digest,'result_sha256':digest(job['result'])}
 assert c.post(path,json=body).status_code==409
 x=prepare(c,raw,frame);acknowledge(c,x)
 assert c.post(path,json=body).status_code==409 # Never configured by caller JSON.
 p.recheck_executor=e
 assert c.post(path,json={**body,'result_sha256':'0'*64}).status_code==409
 out=c.post(path,json=body);assert out.status_code==200 and out.json()['state']=='completed'
 assert len(calls)==4 and 'data:image'not in out.text and 'plan'not in out.json()
 assert c.post(path,json=body).json()['provider_calls_this_request']==0
 preview=report(c,x,job).json()
 assert preview['persons'][0]['provider_helmet_observation']=='unknown'
 assert preview['deliberate_rechecks']['original_result_unchanged']
 assert len(preview['deliberate_rechecks']['attempts'])==1
 assert preview['deliberate_rechecks']['automatic_candidate_adoption']is False
 assert len(calls)==4
