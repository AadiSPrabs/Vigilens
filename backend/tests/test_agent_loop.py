import asyncio
import pytest
from test_fresh_upload_routes import material
from test_recheck_execution import executor
from fresh_review.agent_loop import run_review_loop

def test_configured_unknown_loop_executes_exact_preapproved_attempt_then_escalates(material,monkeypatch):
 p,raw,frame,calls,c,job=material;e,a=executor(p,frame,monkeypatch);p.recheck_executor=e
 out=asyncio.run(run_review_loop(p,frame.digest,attempt_ids=[a['attempt_id']]))
 assert out['status']=='human_review_required'and out['attempts'][0]['state']=='completed'and not out['automatic_candidate_adoption']
 assert p.read(frame.digest)['result']==job['result']and len(calls)==4
 asyncio.run(run_review_loop(p,frame.digest,attempt_ids=[a['attempt_id']]))
 assert len(calls)==4

def test_loop_without_grant_escalates_unknown_no_dispatch(material):
 p,raw,frame,calls,c,job=material
 out=asyncio.run(run_review_loop(p,frame.digest,attempt_ids=[]))
 assert out['unattempted_unknown_person_ids']==['0']and len(calls)==2
 with pytest.raises(ValueError):asyncio.run(run_review_loop(p,frame.digest,attempt_ids=['new']))
 assert len(calls)==2

def test_loop_http_server_owned_attempts_exact_preview_and_result(material,monkeypatch):
 from test_fresh_upload_routes import prepare,acknowledge
 from fresh_review.pipeline import digest
 p,raw,frame,calls,c,job=material;e,a=executor(p,frame,monkeypatch);p.recheck_executor=e
 route='/fresh-review/'+frame.digest+'/bounded-review-loop'
 body={'source_digest':frame.digest,'result_sha256':digest(job['result'])}
 assert c.post(route,json=body).status_code==409
 x=prepare(c,raw,frame);acknowledge(c,x)
 assert c.post(route,json=body).status_code==409
 p.review_loop_attempts={frame.digest:[a['attempt_id']]}
 assert c.post(route,json={**body,'attempts':[a['attempt_id']]}).status_code==409
 out=c.post(route,json=body);assert out.status_code==200 and out.json()['attempts'][0]['state']=='completed'
 assert c.post(route,json=body).status_code==200 and len(calls)==4

def test_unknown_loop_uncertain_hold_escalates_without_retry(material,monkeypatch):
 p,raw,frame,calls,c,job=material;e,a=executor(p,frame,monkeypatch);p.recheck_executor=e
 def timeout(body):calls.append(body);raise TimeoutError()
 p.transport=timeout
 out=asyncio.run(run_review_loop(p,frame.digest,attempt_ids=[a['attempt_id']]))
 assert out['attempts'][0]['state']=='attempted_uncertain'and out['status']=='human_review_required'and len(calls)==3
 asyncio.run(run_review_loop(p,frame.digest,attempt_ids=[a['attempt_id']]))
 assert len(calls)==3 and p.read(frame.digest)['result']==job['result']
