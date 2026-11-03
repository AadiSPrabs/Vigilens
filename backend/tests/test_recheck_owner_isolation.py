"""Owner-isolation regression for the private-report deliberate_rechecks listing.

Two visitor accounts (display sessions A and B) upload the same image bytes, so
both hold completed jobs under the same (source, result_sha256), each in its own
owner namespace. The operator then reserves a recheck attempt in A's namespace.
Invariant: B's private report and B's audit surface never list A's attempt.

The private-report route currently selects recheck_attempts by
(source, result_sha) with NO owner predicate, while every sibling listing on
that route (zones, rules, contacts, current ppe masks) is owner-scoped and the
recheck_attempts table's UNIQUE key includes owner. The Step 3 visitor audit
surface does filter by owner. Synthetic transport only; no grant execution, no
spend, no adoption."""
import json
from fastapi.testclient import TestClient
from app import create_app
from test_fresh_upload_pipeline import setup
from test_fresh_upload_routes import OWNER
from test_recheck_execution import executor
from fresh_review.pipeline import digest

B='cd'*32  # second visitor account: distinct 64-hex display session

def _scenario(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 a=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 out=a.post('/fresh-review-upload',files={'image':('synthetic.png',raw,'image/png')},data={'zones':'[]'})
 assert out.status_code==200 and out.json()['state']=='completed'
 job_a=out.json()
 e,attempt=executor(p,frame,monkeypatch)  # operator reserve while only A's job exists: inherits A's namespace
 p.recheck_executor=e
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':B})
 out=c.post('/fresh-review-upload',files={'image':('synthetic.png',raw,'image/png')},data={'zones':'[]'})
 assert out.status_code==200 and out.json()['state']=='completed'
 job_b=out.json()
 assert digest(job_b['result'])==digest(job_a['result'])  # same bytes, same stored result: the exposure precondition
 review={'source_digest':frame.digest,'frame_size':[80,80],'regions':[{'person_id':'0','box':[1,1,5,5]}],'reviewer_label':'synthetic review','redaction_method':'opaque'}
 r=c.post('/fresh-review/'+frame.digest+'/private-display',files={'image':('x.png',raw,'image/png')},data={'review':json.dumps(review)})
 assert r.status_code==200
 x=r.json()
 ack={**{k:x[k]for k in ['source_digest','output_sha256','regions_digest']},'frame_size':[80,80],**{k:True for k in ['foreground_checked','background_checked','reflections_checked','derivative_checked']}}
 assert c.post('/private-display/'+x['session_id']+'/review',json=ack).status_code==200
 return p,raw,frame,c,job_b,x

def _report(c,x,job):
 identity='fresh:'+x['source_digest']+':'+digest(job['result'])
 payload={'assessment_id':identity,'source_digest':x['source_digest'],'output_sha256':x['output_sha256'],'regions_digest':x['regions_digest'],'persons':{'0':{'exact_source_confirmed':True,'face_coverage_checked':True,'head_evidence_visible':True,'torso_evidence_visible':True}}}
 r=c.post('/fresh-private-report/'+x['session_id'],json=payload)
 assert r.status_code==200
 return r.json()

def test_private_report_recheck_listing_is_owner_isolated(tmp_path,monkeypatch):
 p,raw,frame,c,job_b,x=_scenario(tmp_path,monkeypatch)
 preview=_report(c,x,job_b)
 assert preview['deliberate_rechecks']['attempts']==[]  # B must never see A's attempt

# NOTE (review packaging): the visitor-audit contrast test from the development tree
# (test_visitor_audit_recheck_surface_is_owner_isolated) exercises the Step 3
# /fresh-review-audit rechecks surface, which is NOT part of this reviewed base.
# It ships with the Step 3 review slice instead.

def test_any_listed_attempt_view_carries_no_private_pixels_or_identity(tmp_path,monkeypatch):
 p,raw,frame,c,job_b,x=_scenario(tmp_path,monkeypatch)
 preview=_report(c,x,job_b)
 blob=json.dumps(preview['deliberate_rechecks'])
 for forbidden in ('data:image','owner_session','authority_reference','created','request_sha'):
  assert forbidden not in blob
