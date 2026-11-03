"""REVIEWER probe (not carrier code): can visitor B execute visitor A's reserved
recheck attempt if B somehow knows the attempt_id? B uploads byte-identical image
(same source+result_sha) and completes B's own private-display ceremony. The execute
route binds attempt.plan source/result to the CALLER's job but never compares
attempt.owner to the caller. Synthetic transport only; no live dispatch."""
import json
from fastapi.testclient import TestClient
from app import create_app
from test_fresh_upload_pipeline import setup
from test_fresh_upload_routes import OWNER
from test_recheck_execution import executor
from fresh_review.pipeline import digest

B='cd'*32

def test_execute_route_attempt_owner_probe(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 a=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 out=a.post('/fresh-review-upload',files={'image':('synthetic.png',raw,'image/png')},data={'zones':'[]'})
 assert out.status_code==200 and out.json()['state']=='completed'
 job_a=out.json()
 e,attempt=executor(p,frame,monkeypatch)
 p.recheck_executor=e
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':B})
 out=c.post('/fresh-review-upload',files={'image':('synthetic.png',raw,'image/png')},data={'zones':'[]'})
 assert out.status_code==200
 job_b=out.json()
 assert digest(job_b['result'])==digest(job_a['result'])
 review={'source_digest':frame.digest,'frame_size':[80,80],'regions':[{'person_id':'0','box':[1,1,5,5]}],'reviewer_label':'synthetic review','redaction_method':'opaque'}
 r=c.post('/fresh-review/'+frame.digest+'/private-display',files={'image':('x.png',raw,'image/png')},data={'review':json.dumps(review)})
 assert r.status_code==200
 x=r.json()
 ack={**{k:x[k]for k in ['source_digest','output_sha256','regions_digest']},'frame_size':[80,80],**{k:True for k in ['foreground_checked','background_checked','reflections_checked','derivative_checked']}}
 assert c.post('/private-display/'+x['session_id']+'/review',json=ack).status_code==200
 body={'source_digest':frame.digest,'result_sha256':digest(job_b['result'])}
 out=c.post('/fresh-review/'+frame.digest+'/recheck/'+attempt['attempt_id'],json=body)
 print('PROBE-STATUS',out.status_code)
 print('PROBE-BODY',json.dumps(out.json())[:400])
