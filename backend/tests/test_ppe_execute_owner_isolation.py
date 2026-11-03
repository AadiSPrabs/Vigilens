"""Cross-owner PPE batch execution must fail closed. Visitor B holding A's batch id
(byte-identical upload, B's OWN completed preview ceremony) must not run A's batch.
Synthetic transport only; no live dispatch."""
import json
from fastapi.testclient import TestClient
from app import create_app
from test_fresh_upload_routes import material,OWNER
from test_ppe_segmentation import helper
from fresh_review.pipeline import digest

B='cd'*32

def _ceremony(client,frame,raw):
    review={'source_digest':frame.digest,'frame_size':[80,80],'regions':[{'person_id':'0','box':[1,1,5,5]}],'reviewer_label':'synthetic review','redaction_method':'opaque'}
    r=client.post('/fresh-review/'+frame.digest+'/private-display',files={'image':('x.png',raw,'image/png')},data={'review':json.dumps(review)})
    assert r.status_code==200
    x=r.json()
    ack={**{k:x[k]for k in ['source_digest','output_sha256','regions_digest']},'frame_size':[80,80],**{k:True for k in ['foreground_checked','background_checked','reflections_checked','derivative_checked']}}
    assert client.post('/private-display/'+x['session_id']+'/review',json=ack).status_code==200

def _visitor_b(p,raw,frame):
    b=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':B})
    out=b.post('/fresh-review-upload',files={'image':('synthetic.png',raw,'image/png')},data={'zones':'[]'})
    assert out.status_code==200 and out.json()['state']=='completed'
    job_b=out.json()
    _ceremony(b,frame,raw)
    return b,{'source_digest':frame.digest,'result_sha256':digest(job_b['result'])}

def test_cross_owner_ppe_execute_refused_and_batch_unchanged(material,monkeypatch):
    p,raw,frame,calls,c,job=material;h,identity=helper(p,frame,monkeypatch)
    b,body=_visitor_b(p,raw,frame)
    p.ppe_segmentation=h
    before=len(calls)
    out=b.post('/fresh-review/'+frame.digest+'/ppe-segmentation/'+identity,json=body)
    assert out.status_code==409
    assert h.read(identity)['state']=='reserved_not_dispatched' and len(calls)==before

def test_own_owner_ppe_execute_completes_after_cross_owner_refusal(material,monkeypatch):
    p,raw,frame,calls,c,job=material;h,identity=helper(p,frame,monkeypatch)
    b,body=_visitor_b(p,raw,frame)
    p.ppe_segmentation=h
    assert b.post('/fresh-review/'+frame.digest+'/ppe-segmentation/'+identity,json=body).status_code==409
    _ceremony(c,frame,raw)
    own=c.post('/fresh-review/'+frame.digest+'/ppe-segmentation/'+identity,json={'source_digest':frame.digest,'result_sha256':digest(job['result'])})
    assert own.status_code==200 and own.json()['state']=='completed'
    assert own.json()['evidence_export_allowed'] is False and own.json()['retry_allowed'] is False
