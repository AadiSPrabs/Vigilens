"""Cross-owner recheck execution must fail closed. Visitor B holding A's attempt_id
(byte-identical upload, B's own completed preview ceremony) must not execute or
mutate A's attempt. A's own execution must still complete. Synthetic transport only."""
import json
from fastapi.testclient import TestClient
from app import create_app
from test_fresh_upload_pipeline import setup
from test_fresh_upload_routes import OWNER
from test_recheck_execution import executor
from fresh_review.pipeline import digest

B='cd'*32

def _upload(client,raw):
    out=client.post('/fresh-review-upload',files={'image':('synthetic.png',raw,'image/png')},data={'zones':'[]'})
    assert out.status_code==200 and out.json()['state']=='completed'
    return out.json()

def _ceremony(client,frame,raw):
    review={'source_digest':frame.digest,'frame_size':[80,80],'regions':[{'person_id':'0','box':[1,1,5,5]}],'reviewer_label':'synthetic review','redaction_method':'opaque'}
    r=client.post('/fresh-review/'+frame.digest+'/private-display',files={'image':('x.png',raw,'image/png')},data={'review':json.dumps(review)})
    assert r.status_code==200
    x=r.json()
    ack={**{k:x[k]for k in ['source_digest','output_sha256','regions_digest']},'frame_size':[80,80],**{k:True for k in ['foreground_checked','background_checked','reflections_checked','derivative_checked']}}
    assert client.post('/private-display/'+x['session_id']+'/review',json=ack).status_code==200

def _pair(tmp_path,monkeypatch):
    p,raw,frame,calls=setup(tmp_path,monkeypatch)
    a=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
    job_a=_upload(a,raw)
    e,attempt=executor(p,frame,monkeypatch)
    p.recheck_executor=e
    b=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':B})
    job_b=_upload(b,raw)
    assert digest(job_b['result'])==digest(job_a['result'])
    body={'source_digest':frame.digest,'result_sha256':digest(job_b['result'])}
    return p,raw,frame,a,b,e,attempt,body

def test_cross_owner_execute_refused_and_attempt_unchanged(tmp_path,monkeypatch):
    p,raw,frame,a,b,e,attempt,body=_pair(tmp_path,monkeypatch)
    _ceremony(b,frame,raw)
    out=b.post('/fresh-review/'+frame.digest+'/recheck/'+attempt['attempt_id'],json=body)
    assert out.status_code==409
    current=e.read(attempt['attempt_id'])
    assert current['state']==attempt['state'] and current['result'] is None
    assert current['provider_calls_this_request']==0

def test_cross_owner_read_of_completed_attempt_refused(tmp_path,monkeypatch):
    p,raw,frame,a,b,e,attempt,body=_pair(tmp_path,monkeypatch)
    _ceremony(a,frame,raw)
    own=a.post('/fresh-review/'+frame.digest+'/recheck/'+attempt['attempt_id'],json=body)
    assert own.status_code==200 and own.json()['state']=='completed'
    out=b.post('/fresh-review/'+frame.digest+'/recheck/'+attempt['attempt_id'],json=body)
    assert out.status_code==409
    assert e.read(attempt['attempt_id'])['state']=='completed'

def test_own_owner_execute_still_completes_after_refusal(tmp_path,monkeypatch):
    p,raw,frame,a,b,e,attempt,body=_pair(tmp_path,monkeypatch)
    _ceremony(b,frame,raw)
    assert b.post('/fresh-review/'+frame.digest+'/recheck/'+attempt['attempt_id'],json=body).status_code==409
    _ceremony(a,frame,raw)
    out=a.post('/fresh-review/'+frame.digest+'/recheck/'+attempt['attempt_id'],json=body)
    assert out.status_code==200 and out.json()['state']=='completed'
    assert out.json()['evidence_export_allowed'] is False and out.json()['retry_allowed'] is False
