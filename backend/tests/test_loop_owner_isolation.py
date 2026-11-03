"""Cross-owner bounded-review-loop must fail closed. Visitor B with byte-identical
upload and B's own completed ceremony must not trigger operator-configured attempts
reserved for A, nor read back A's candidate results. Synthetic transport only."""
import asyncio,json,hashlib,pytest
from fastapi.testclient import TestClient
from app import create_app
from test_fresh_upload_routes import material,OWNER
from test_recheck_execution import executor
from fresh_review.agent_loop import run_review_loop
from fresh_review.pipeline import digest

B='cd'*32
_A=hashlib.sha256(OWNER.encode()).hexdigest()
_BH=hashlib.sha256(B.encode()).hexdigest()

def _ceremony(client,frame,raw):
    review={'source_digest':frame.digest,'frame_size':[80,80],'regions':[{'person_id':'0','box':[1,1,5,5]}],'reviewer_label':'synthetic review','redaction_method':'opaque'}
    r=client.post('/fresh-review/'+frame.digest+'/private-display',files={'image':('x.png',raw,'image/png')},data={'review':json.dumps(review)})
    assert r.status_code==200
    x=r.json()
    ack={**{k:x[k]for k in ['source_digest','output_sha256','regions_digest']},'frame_size':[80,80],**{k:True for k in ['foreground_checked','background_checked','reflections_checked','derivative_checked']}}
    assert client.post('/private-display/'+x['session_id']+'/review',json=ack).status_code==200

def _setup(material,monkeypatch):
    p,raw,frame,calls,c,job=material;e,a=executor(p,frame,monkeypatch)
    p.recheck_executor=e
    p.review_loop_attempts={frame.digest:[a['attempt_id']]}
    b=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':B})
    out=b.post('/fresh-review-upload',files={'image':('synthetic.png',raw,'image/png')},data={'zones':'[]'})
    assert out.status_code==200 and out.json()['state']=='completed'
    body={'source_digest':frame.digest,'result_sha256':digest(out.json()['result'])}
    _ceremony(b,frame,raw)
    return p,raw,frame,calls,c,job,e,a,b,body

def test_cross_owner_loop_route_refused_and_attempt_unchanged(material,monkeypatch):
    p,raw,frame,calls,c,job,e,a,b,body=_setup(material,monkeypatch)
    before=len(calls)
    out=b.post('/fresh-review/'+frame.digest+'/bounded-review-loop',json=body)
    assert out.status_code==409
    assert e.read(a['attempt_id'])['state']==a['state'] and len(calls)==before

def test_cross_owner_loop_function_refused(material,monkeypatch):
    p,raw,frame,calls,c,job,e,a,b,body=_setup(material,monkeypatch)
    with pytest.raises(ValueError):asyncio.run(run_review_loop(p,frame.digest,attempt_ids=[a['attempt_id']],owner=_BH))
    assert e.read(a['attempt_id'])['state']==a['state']

def test_own_owner_loop_still_completes_after_refusal(material,monkeypatch):
    p,raw,frame,calls,c,job,e,a,b,body=_setup(material,monkeypatch)
    assert b.post('/fresh-review/'+frame.digest+'/bounded-review-loop',json=body).status_code==409
    _ceremony(c,frame,raw)
    own=c.post('/fresh-review/'+frame.digest+'/bounded-review-loop',json={'source_digest':frame.digest,'result_sha256':digest(job['result'])})
    assert own.status_code==200 and own.json()['attempts'][0]['state']=='completed'
    assert own.json()['automatic_candidate_adoption'] is False and own.json()['evidence_export_allowed'] is False
