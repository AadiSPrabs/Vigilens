"""REVIEWER probe (not carrier code): bounded-review-loop cross-owner execution.
Operator pins A's reserved attempt for source S; visitor B (byte-identical
upload, B's OWN inline ceremony) posts the loop route without knowing any id.
Pre-fix expectation: loop dispatches A's attempt and returns candidate to B.
Synthetic transport only."""
import json
from fastapi.testclient import TestClient
from app import create_app
from test_fresh_upload_routes import material,OWNER
from test_recheck_execution import executor
from fresh_review.pipeline import digest

B='cd'*32

def _visitor_b(p,raw,frame):
    b=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':B})
    out=b.post('/fresh-review-upload',files={'image':('synthetic.png',raw,'image/png')},data={'zones':'[]'})
    assert out.status_code==200 and out.json()['state']=='completed'
    job_b=out.json()
    review={'source_digest':frame.digest,'frame_size':[80,80],'regions':[{'person_id':'0','box':[1,1,5,5]}],'reviewer_label':'synthetic review','redaction_method':'opaque'}
    r=b.post('/fresh-review/'+frame.digest+'/private-display',files={'image':('x.png',raw,'image/png')},data={'review':json.dumps(review)})
    assert r.status_code==200
    x=r.json()
    ack={**{k:x[k]for k in ['source_digest','output_sha256','regions_digest']},'frame_size':[80,80],**{k:True for k in ['foreground_checked','background_checked','reflections_checked','derivative_checked']}}
    assert b.post('/private-display/'+x['session_id']+'/review',json=ack).status_code==200
    return b,{'source_digest':frame.digest,'result_sha256':digest(job_b['result'])}

def test_probe_loop_cross_owner_execute(material,monkeypatch):
    p,raw,frame,calls,c,job=material;e,a=executor(p,frame,monkeypatch)
    p.recheck_executor=e
    p.review_loop_attempts={frame.digest:[a['attempt_id']]}  # operator pins A's attempt for this source
    b,body=_visitor_b(p,raw,frame)
    before=len(calls)
    out=b.post('/fresh-review/'+frame.digest+'/bounded-review-loop',json=body)
    print('PROBE-LOOP-STATUS',out.status_code)
    print('PROBE-LOOP-CALLS-DELTA',len(calls)-before)
    print('PROBE-LOOP-ATTEMPT-STATE',e.read(a['attempt_id'])['state'])
    print('PROBE-LOOP-BODY',json.dumps(out.json())[:400])
