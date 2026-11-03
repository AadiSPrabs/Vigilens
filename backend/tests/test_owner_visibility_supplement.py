"""REVIEWER supplement (not carrier code): post-patch own-visibility check.
The carrier isolation tests assert B sees nothing; this probe asserts the patch
did not over-narrow: A's own private report still lists A's own recheck attempt
and A's own completed PPE mask batch. Synthetic only; no provider calls."""
import asyncio,json
from fastapi.testclient import TestClient
from app import create_app
from test_fresh_upload_pipeline import setup
from test_fresh_upload_routes import OWNER,report
from test_recheck_execution import executor
from test_ppe_segmentation import helper
from fresh_review.pipeline import digest

def _a_upload_and_ack(p,raw,frame):
 a=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 out=a.post('/fresh-review-upload',files={'image':('synthetic.png',raw,'image/png')},data={'zones':'[]'})
 assert out.status_code==200 and out.json()['state']=='completed'
 job=out.json()
 review={'source_digest':frame.digest,'frame_size':[80,80],'regions':[{'person_id':'0','box':[1,1,5,5]}],'reviewer_label':'synthetic review','redaction_method':'opaque'}
 r=a.post('/fresh-review/'+frame.digest+'/private-display',files={'image':('x.png',raw,'image/png')},data={'review':json.dumps(review)})
 assert r.status_code==200
 x=r.json()
 ack={**{k:x[k]for k in ['source_digest','output_sha256','regions_digest']},'frame_size':[80,80],**{k:True for k in ['foreground_checked','background_checked','reflections_checked','derivative_checked']}}
 assert a.post('/private-display/'+x['session_id']+'/review',json=ack).status_code==200
 return a,job,x

def test_owner_still_sees_own_recheck_attempt(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 a,job,x=_a_upload_and_ack(p,raw,frame)
 e,attempt=executor(p,frame,monkeypatch)
 p.recheck_executor=e
 doc=report(a,x,job).json()
 assert len(doc['deliberate_rechecks']['attempts'])==1,doc['deliberate_rechecks']
 assert doc['deliberate_rechecks']['attempts'][0]['attempt_id']==attempt['attempt_id']

def test_owner_still_sees_own_ppe_batch(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 a,job,x=_a_upload_and_ack(p,raw,frame)
 h,identity=helper(p,frame,monkeypatch)
 assert asyncio.run(h.run(identity))['state']=='completed'
 p.ppe_segmentation=h
 doc=report(a,x,job).json()
 assert len(doc['ppe_segmentation']['batches'])==1,doc['ppe_segmentation']
 assert doc['ppe_segmentation']['batches'][0]['state']=='completed'
