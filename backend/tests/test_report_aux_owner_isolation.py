"""Owner-isolation regression for the private-report auxiliary-artifact listings.

Same pattern as the deliberate_rechecks exposure: the private-report route lists
ppe_mask_batches by (source, result_sha) and explanation_attempts by
(source, context_sha) with NO owner predicate, while both tables carry owner
columns with owner-scoped UNIQUE keys and every other listing on the route is
owner-scoped. Two visitors (A and B, distinct display sessions) upload the same
image bytes; the operator reserves the auxiliary artifact in A's namespace;
B's private report must not list it. Synthetic fixtures/transport only; no real
records, no provider calls, no adoption."""
import asyncio,json
from fastapi.testclient import TestClient
from app import create_app
from test_fresh_upload_pipeline import setup
from test_fresh_upload_routes import OWNER,report
from test_fresh_zones import submit,contact
from test_rule_report_integration import rules
from test_ppe_segmentation import helper
from test_spatial_explanation import setup_explanation,response
from test_private_report_document import payload
from fresh_review.pipeline import digest
from fresh_review.spatial_explanation import build_spatial_request

B='cd'*32  # second visitor account

def _a_material(p,raw):
 a=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 out=a.post('/fresh-review-upload',files={'image':('synthetic.png',raw,'image/png')},data={'zones':'[]'})
 assert out.status_code==200 and out.json()['state']=='completed'
 return a,out.json()

def _b_material(p,raw,frame):
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':B})
 out=c.post('/fresh-review-upload',files={'image':('synthetic.png',raw,'image/png')},data={'zones':'[]'})
 assert out.status_code==200 and out.json()['state']=='completed'
 review={'source_digest':frame.digest,'frame_size':[80,80],'regions':[{'person_id':'0','box':[1,1,5,5]}],'reviewer_label':'synthetic review','redaction_method':'opaque'}
 r=c.post('/fresh-review/'+frame.digest+'/private-display',files={'image':('x.png',raw,'image/png')},data={'review':json.dumps(review)})
 assert r.status_code==200
 x=r.json()
 ack={**{k:x[k]for k in ['source_digest','output_sha256','regions_digest']},'frame_size':[80,80],**{k:True for k in ['foreground_checked','background_checked','reflections_checked','derivative_checked']}}
 assert c.post('/private-display/'+x['session_id']+'/review',json=ack).status_code==200
 return c,out.json(),x

def _b_report(c,x,job):
 identity='fresh:'+x['source_digest']+':'+digest(job['result'])
 body={'assessment_id':identity,'source_digest':x['source_digest'],'output_sha256':x['output_sha256'],'regions_digest':x['regions_digest'],'persons':{'0':{'exact_source_confirmed':True,'face_coverage_checked':True,'head_evidence_visible':True,'torso_evidence_visible':True}}}
 r=c.post('/fresh-private-report/'+x['session_id'],json=body)
 assert r.status_code==200
 return r.json()

def _a_prep_ack(a,raw,frame):
 review={'source_digest':frame.digest,'frame_size':[80,80],'regions':[{'person_id':'0','box':[1,1,5,5]}],'reviewer_label':'synthetic review','redaction_method':'opaque'}
 r=a.post('/fresh-review/'+frame.digest+'/private-display',files={'image':('x.png',raw,'image/png')},data={'review':json.dumps(review)})
 assert r.status_code==200
 x=r.json()
 ack={**{k:x[k]for k in ['source_digest','output_sha256','regions_digest']},'frame_size':[80,80],**{k:True for k in ['foreground_checked','background_checked','reflections_checked','derivative_checked']}}
 assert a.post('/private-display/'+x['session_id']+'/review',json=ack).status_code==200
 return x

def test_ppe_mask_batch_listing_is_owner_isolated(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 a,job_a=_a_material(p,raw)
 h,identity=helper(p,frame,monkeypatch)  # operator reserve in A's namespace (only A's job exists)
 assert asyncio.run(h.run(identity))['state']=='completed'  # synthetic transport; no provider calls
 p.ppe_segmentation=h
 c,job_b,x=_b_material(p,raw,frame)
 assert digest(job_b['result'])==digest(job_a['result'])  # exposure precondition
 preview=_b_report(c,x,job_b)
 assert preview['ppe_segmentation']['batches']==[]  # B must never see A's batch

def test_spatial_explanation_listing_owner_hardening(tmp_path,monkeypatch):
 # HARDENING regression (not a confirmed leak): the listing key (source,
 # context_sha) is already bound to the visitor's own submission events by
 # construction - context_sha digests zone_geometry (snapshot event_id/at),
 # per-owner contact events and configuration_event_id, so B's key can never
 # equal A's. The AND owner=? predicate is defense-in-depth; executor.read
 # remains the operator/global path and is unchanged.
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 a,job_a=_a_material(p,raw)
 x=_a_prep_ack(a,raw,frame)
 submit(a,frame,job_a);contact(a,frame);rules(a,frame,job_a)
 e,plan_a,identity=setup_explanation(p,raw,job_a,a,x)  # reserve while only A's job exists: A's namespace
 p.explanation_executor=e
 c,job_b,xb=_b_material(p,raw,frame)  # B uploads before the transport stub: synthetic pipeline completes
 def transport(body):calls.append(body);return response(plan_a)
 p.transport=transport
 out=a.post('/fresh-private-report/'+x['session_id']+'/explanation/'+identity,json=payload(x,job_a))
 assert out.status_code==200 and out.json()['state']=='completed'  # synthetic transport only
 submit(c,frame,job_b);contact(c,frame);rules(c,frame,job_b)
 doc=_b_report(c,xb,job_b)
 plan_b=build_spatial_request(raw,job_b['result'],doc['zone_review'],doc['configured_rule_review'],[])
 assert plan_b['context_sha256']!=plan_a['context_sha256']  # owner-bound by construction: no shared listing key
 assert doc['spatial_explanations']['attempts']==[]  # B never sees A's attempt
 doc_a=report(a,x,job_a).json()
 assert len(doc_a['spatial_explanations']['attempts'])==1  # A still sees own attempt
