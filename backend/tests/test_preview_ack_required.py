"""Ack-required regression for preview-gated execute/review surfaces.

The private-display PREPARE binds the session to (source, result_sha256). The
acknowledgment (POST /private-display/{sid}/review) is what marks the exact
derivative reviewed. Every preview-gated surface must require BOTH: a prepared
but unacknowledged session must refuse with 409, zero dispatch, unchanged state.
Synthetic transport only; no spend, no adoption."""
import json
from fastapi.testclient import TestClient
from app import create_app
from test_fresh_upload_pipeline import setup
from test_fresh_upload_routes import OWNER
from test_recheck_execution import executor

def _prepare_only(c,raw,frame):
 review={'source_digest':frame.digest,'frame_size':[80,80],'regions':[{'person_id':'0','box':[1,1,5,5]}],'reviewer_label':'synthetic review','redaction_method':'opaque'}
 r=c.post('/fresh-review/'+frame.digest+'/private-display',files={'image':('x.png',raw,'image/png')},data={'review':json.dumps(review)})
 assert r.status_code==200
 return r.json()

def test_recheck_execute_requires_acknowledgment_not_just_preparation(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 out=c.post('/fresh-review-upload',files={'image':('a.png',raw,'image/png')},data={'zones':'[]'})
 assert out.status_code==200 and out.json()['state']=='completed'
 e,attempt=executor(p,frame,monkeypatch)
 p.recheck_executor=e
 _prepare_only(c,raw,frame)  # prepared, deliberately NOT acknowledged
 calls_before=len(calls)
 r=c.post('/fresh-review/'+frame.digest+'/recheck/'+attempt['attempt_id'],json={'source_digest':frame.digest,'result_sha256':attempt['plan']['result_sha256']})
 assert r.status_code==409,r.text
 assert e.read(attempt['attempt_id'])['state']=='reserved_not_dispatched'
 assert len(calls)==calls_before  # zero dispatch

def test_manual_contact_requires_acknowledgment_not_just_preparation(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 out=c.post('/fresh-review-upload',files={'image':('a.png',raw,'image/png')},data={'zones':'[]'})
 assert out.status_code==200 and out.json()['state']=='completed'
 _prepare_only(c,raw,frame)
 claim={'person_id':'0','point':[0.1,0.5],'exact_source_confirmed':True,'boots_ground_visible':True,'reviewer_label':'synthetic contact'}
 r=c.post('/fresh-review/'+frame.digest+'/contact',json=claim)
 assert r.status_code==409,r.text

def test_zone_review_submit_requires_acknowledgment_not_just_preparation(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 out=c.post('/fresh-review-upload',files={'image':('a.png',raw,'image/png')},data={'zones':'[]'})
 assert out.status_code==200 and out.json()['state']=='completed'
 _prepare_only(c,raw,frame)  # prepared, deliberately NOT acknowledged
 from test_fresh_zones import ZONE
 job=out.json();calls_before=len(calls)
 r=c.post('/fresh-review/'+frame.digest+'/zone-review',json={'source_digest':frame.digest,'result_sha256':__import__('fresh_review.pipeline',fromlist=['digest']).digest(job['result']),'zones':[ZONE],'reviewer_label':'synthetic reviewer'})
 assert r.status_code==409,r.text
 assert len(calls)==calls_before  # zero dispatch

def test_camera_zones_save_requires_acknowledgment_not_just_preparation(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 out=c.post('/fresh-review-upload',files={'image':('a.png',raw,'image/png')},data={'zones':'[]'})
 assert out.status_code==200 and out.json()['state']=='completed'
 _prepare_only(c,raw,frame)
 job=out.json();calls_before=len(calls)
 body={'source_digest':frame.digest,'result_sha256':__import__('fresh_review.pipeline',fromlist=['digest']).digest(job['result']),'camera_binding':{'camera_id':'synthetic-fixed-camera','scene_revision':'scene1','width':80,'height':80,'coordinate_space':'normalized_upright_source_v1','transform':'identity'},'reviewer_label':'synthetic operator','fixed_scene_confirmed':True}
 r=c.post('/fresh-review/'+frame.digest+'/camera-zones/save',json=body)
 assert r.status_code==409,r.text
 assert len(calls)==calls_before  # zero dispatch
