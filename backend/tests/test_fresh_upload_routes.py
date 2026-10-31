import asyncio,json,sqlite3
import pytest
from fastapi.testclient import TestClient
from app import create_app
from test_fresh_upload_pipeline import setup
import fresh_review.api as routes
from fresh_review.pipeline import digest
OWNER='fresh_local_test_owner_123456789012345'
@pytest.fixture
def material(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER});out=c.post('/fresh-review-upload',files={'image':('synthetic.png',raw,'image/png')},data={'zones':'[]'})
 assert out.status_code==200 and out.json()['state']=='completed'
 yield p,raw,frame,calls,c,out.json()


def prepare(c,raw,frame):
 review={'source_digest':frame.digest,'frame_size':[80,80],'regions':[{'person_id':'0','box':[1,1,5,5]}],'reviewer_label':'synthetic review','redaction_method':'opaque'}
 #source allblue, opaque changes pixels. Synthetic privacy coverage not claimed.
 r=c.post('/fresh-review/'+frame.digest+'/private-display',files={'image':('x.png',raw,'image/png')},data={'review':json.dumps(review)},headers={'X-Vigilens-Display-Session':OWNER});assert r.status_code==200
 return r.json()

def acknowledge(c,x):
 ack={**{k:x[k]for k in ['source_digest','output_sha256','regions_digest']},'frame_size':[80,80],**{k:True for k in ['foreground_checked','background_checked','reflections_checked','derivative_checked']}}
 assert c.post('/private-display/'+x['session_id']+'/review',json=ack,headers={'X-Vigilens-Display-Session':OWNER}).status_code==200

def report(c,x,job):
 identity='fresh:'+x['source_digest']+':'+digest(job['result'])
 payload={'assessment_id':identity,'source_digest':x['source_digest'],'output_sha256':x['output_sha256'],'regions_digest':x['regions_digest'],'persons':{'0':{'exact_source_confirmed':True,'face_coverage_checked':True,'head_evidence_visible':True,'torso_evidence_visible':True}}}
 return c.post('/fresh-private-report/'+x['session_id'],json=payload,headers={'X-Vigilens-Display-Session':OWNER})

def test_fresh_upload_manual_private_report_unknown_and_repeat(material):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame)
 assert report(c,x,job).status_code==409
 acknowledge(c,x);out=report(c,x,job);assert out.status_code==200;out=out.json()
 assert out['persons'][0]['provider_helmet_observation']=='unknown'and out['persons'][0]['report_display_helmet']=='unknown'
 assert out['persons'][0]['report_display_vest']=='unknown'and out['persons'][0]['provider_vest_observation']=='absent'and out['persons'][0]['ppe_basis']['crop_basis']=='crop_rule_ineligible'and out['persons'][0]['status']=='needs_human_review'and not out['evidence_export_allowed']and not out['compliance_decision']
 assert out['contact_review_status']=='needs_manual_contact_review'
 contact={'person_id':'0','point':[.1,.5],'exact_source_confirmed':True,'boots_ground_visible':True,'reviewer_label':'synthetic operator'}
 r=c.post('/fresh-review/'+frame.digest+'/contact',json=contact);assert r.status_code==200
 again=c.post('/fresh-review/'+frame.digest+'/contact',json=contact);assert again.json()==r.json()
 assert report(c,x,job).json()['contact_review_status']=='operator_claims_only'
 repeated=c.post('/fresh-review-upload',files={'image':('same.png',raw,'image/png')},data={'zones':'[]'});assert repeated.json()['provider_calls_this_request']==0 and len(calls)==2

def test_changed_stored_result_invalidates_preview(material):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x)
 db=sqlite3.connect(p.path);db.execute('UPDATE jobs SET result_sha=?',('changed',));db.commit();db.close()
 assert c.get(x['preview_url'],headers={'X-Vigilens-Display-Session':OWNER}).status_code==409
 assert x['session_id']not in c.app.state.fresh_display.SESSIONS

def test_wrong_contact_person_numeric_approval_and_source_rejected(material):
 p,raw,frame,calls,c,job=material;prepare(c,raw,frame)
 for patch in [{'person_id':'wrong'},{'boots_ground_visible':1},{'point':[.8,.8]}]:
  contact={'person_id':'0','point':[.1,.5],'exact_source_confirmed':True,'boots_ground_visible':True,'reviewer_label':'operator',**patch}
  assert c.post('/fresh-review/'+frame.digest+'/contact',json=contact).status_code==409
 assert len(calls)==2

def test_expired_manual_claim_not_in_report(material,monkeypatch):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x)
 payload={'person_id':'0','point':[.1,.5],'exact_source_confirmed':True,'boots_ground_visible':True,'reviewer_label':'operator'}
 assert c.post('/fresh-review/'+frame.digest+'/contact',json=payload).status_code==200
 db=sqlite3.connect(p.path);db.execute('UPDATE contact_events SET at=0');db.commit();db.close()
 assert report(c,x,job).json()['contact_review_status']=='needs_manual_contact_review'

def test_route_default_not_general_live_enabled(tmp_path,monkeypatch):
 from fresh_review.pipeline import FreshPipeline
 p=FreshPipeline(tmp_path/'disabled.sqlite')
 c=TestClient(create_app(fresh_service=p));assert c.post('/fresh-review-upload',files={'image':('x.png',b'invalid','image/png')},data={'zones':'[]'}).status_code==409
 assert not p.path.exists()

def test_lossless_frontend_proposal_explicit_states_and_no_original_fallback(material):
 p,raw,frame,calls,c,job=material
 r=c.get('/fresh-review/'+frame.digest+'/integration-contract');assert r.status_code==200;x=r.json()
 assert x['contract_status']=='local_proposal_not_agreed_with_frontend'and x['compliance']['status']=='not_evaluated'and x['evidence_image']is None
 assert x['ppe_basis_counts']['attempted_is_not_resolved_assessment']and x['all_detected_people_assessed_meaning'].startswith('provider_observation_attempted')and isinstance(x['all_detected_people_target_level_resolved'],bool)
 assert x['persons'][0]['ppe']['helmet']['status']=='unknown'and x['persons'][0]['findings']is None and x['persons'][0]['zone_membership']['zone_ids']is None
 from fresh_review.masks import decode_mask
 assert decode_mask(x['persons'][0]['mask']).size==(20,60)
 assert len(calls)==2

def test_contact_owner_history_and_restart(material):
 from fresh_review.contacts import ContactStore
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x)
 payload={'person_id':'0','point':[.1,.5],'exact_source_confirmed':True,'boots_ground_visible':True,'reviewer_label':'operator'}
 path='/fresh-review/'+frame.digest+'/contact'
 first=c.post(path,json=payload).json()['manual_contact']
 changed=c.post(path,json={**payload,'point':[.15,.55]}).json()['manual_contact']
 assert changed['event_id']!=first['event_id']
 db=sqlite3.connect(p.path);assert db.execute('SELECT count(*) FROM contact_events').fetchone()[0]==2;db.close()
 assert ContactStore(p).latest(frame.digest,digest(job['result']),OWNER)['0']==changed
 assert ContactStore(p).latest(frame.digest,digest(job['result']),'different_browser_owner_123456789012345')=={}
 assert c.post(path,json=payload,headers={'X-Vigilens-Display-Session':'different_browser_owner_123456789012345'}).status_code==409
 assert c.post(path,json=payload,headers={'X-Vigilens-Display-Session':''}).status_code==403
 assert report(c,x,job).json()['manual_contact_review']['0']==changed

@pytest.mark.parametrize('gate',['unset','wrong','missing'])
def test_outer_app_token_gate_covers_all_fresh_routes(material,monkeypatch,gate):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x)
 expected='synthetic-local-test-token-12345678901234567890'
 if gate=='unset':c=TestClient(create_app(fresh_service=p,fresh_token=''),headers={'X-Vigilens-Display-Session':OWNER})
 if gate=='unset':monkeypatch.delenv('VIGILENS_LOCAL_ACCESS_TOKEN',raising=False)
 else:monkeypatch.setenv('VIGILENS_LOCAL_ACCESS_TOKEN',expected)
 # Autouse test helper supplies a default header,so explicit empty overrides it.
 headers={'X-Vigilens-Local-Access':'wrong-token'if gate=='wrong'else'','X-Vigilens-Display-Session':OWNER}
 path='/fresh-review/'+frame.digest
 responses=[
  c.post('/fresh-review-upload',files={'image':('generated.png',raw,'image/png')},data={'zones':'[]'},headers=headers),
  c.get(path,headers=headers),c.get(path+'/integration-contract',headers=headers),
  c.post(path+'/private-display',files={'image':('generated.png',raw,'image/png')},data={'review':'{}'},headers=headers),
  c.post(path+'/contact',json={'person_id':'0'},headers=headers),
  c.post('/fresh-private-report/'+x['session_id'],json={},headers=headers),
  c.get(x['preview_url'],headers=headers)]
 assert all(r.status_code==403 and r.json()['detail']=='Private local access required'for r in responses)
 assert len(calls)==2
 db=sqlite3.connect(p.path);assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='contact_events'").fetchone()[0]==0;db.close()

def test_two_actual_backend_apps_do_not_share_pipeline(material,tmp_path):
 from fresh_review.pipeline import FreshPipeline
 p,raw,frame,calls,c,job=material
 other=FreshPipeline(tmp_path/'other.sqlite')
 other_client=TestClient(create_app(fresh_service=other))
 assert other_client.get('/fresh-review/'+frame.digest).status_code==409
 assert c.get('/fresh-review/'+frame.digest).json()['state']=='completed'
 assert not other.path.exists()and len(calls)==2

def test_default_actual_factory_does_not_enable_real_upload(tmp_path,monkeypatch):
 monkeypatch.setenv('VIGILENS_PRIVATE_DATA_DIR',str(tmp_path/'not-created'))
 default=create_app();client=TestClient(default)
 assert not hasattr(default.state,'fresh_pipeline')
 assert client.post('/fresh-review-upload',files={'image':('generated.png',b'generated','image/png')},data={'zones':'[]'}).status_code==404
 assert not (tmp_path/'not-created').exists()

def test_display_nonce_does_not_cross_actual_apps(material):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame)
 other=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 assert other.get(x['preview_url']).status_code==404
 assert c.get(x['preview_url']).status_code==200
 assert other.app.state.fresh_display is not c.app.state.fresh_display


def test_browser_origin_preflight_and_request(material):
 p,raw,frame,calls,c,job=material
 headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type,x-vigilens-local-access,x-vigilens-display-session'}
 for path in ['/fresh-review-upload','/fresh-review/'+frame.digest+'/contact','/fresh-private-report/example']:
  r=c.options(path,headers=headers);assert r.status_code==200
  assert r.headers['access-control-allow-origin']=='http://localhost:5173'
  assert 'x-vigilens-display-session'in r.headers['access-control-allow-headers'].lower()
 r=c.post('/fresh-review-upload',files={'image':('generated.png',raw,'image/png')},data={'zones':'[]'},headers={'Origin':'http://localhost:5173','X-Vigilens-Display-Session':OWNER})
 assert r.status_code==200 and r.headers['access-control-allow-origin']=='http://localhost:5173'and len(calls)==2
 assert c.options('/fresh-review-upload',headers={**headers,'Origin':'https://unapproved.invalid'}).status_code==400

def test_per_app_tokens_captured_not_env_global(material,monkeypatch):
 p,raw,frame,calls,c,job=material
 other=TestClient(create_app(fresh_service=p,fresh_token='different-app-token-12345678901234567890'))
 assert other.get('/fresh-review/'+frame.digest).status_code==403
 monkeypatch.setenv('VIGILENS_LOCAL_ACCESS_TOKEN','changed-environment-token-123456789012345')
 assert c.get('/fresh-review/'+frame.digest).status_code==200

def test_persisted_derivative_guard_across_app_restart(material):
 from fresh_review.pipeline import FreshPipeline
 from test_fresh_upload_pipeline import add_approval
 from core import decode_image
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);png=c.get(x['preview_url']).content
 f=decode_image(png,'image/png');add_approval(p,f.digest,{'size':[80,80],'rights_reference':'synthetic-intentionally-approved-derivative-test','provider_upload_approved':True})
 other=FreshPipeline(p.path,approval_store=p.approval_store,transport=p.transport,execution_scope=p.execution_scope,carry_path=p.carry_path,carry_sha=p.carry_sha)
 client=TestClient(create_app(fresh_service=other))
 assert client.post('/fresh-review-upload',files={'image':('generated-derivative.png',png,'image/png')},data={'zones':'[]'}).status_code==409
 assert len(calls)==2


def test_health_reports_mounted_routes_not_live_readiness(tmp_path):
 from fresh_review.pipeline import FreshPipeline
 default=TestClient(create_app()).get('/health').json()
 assert default['mode']=='fixture_only'and default['real_analysis_enabled']is False
 assert default['capabilities']['fresh_review_routes_mounted']is False and default['capabilities']['evidence_export']is False
 disabled=FreshPipeline(tmp_path/'disabled-health.sqlite')
 mounted=TestClient(create_app(fresh_service=disabled)).get('/health').json()
 assert mounted['mode']=='private_review_configured'and mounted['real_analysis_enabled']is False
 assert mounted['capabilities']['fresh_review_routes_mounted']is True and mounted['capabilities']['max_people_per_image']==2
 assert not disabled.path.exists() # health does not initialize/dispatch a pipeline


def test_cross_origin_delete_preflight_and_authenticated_cleanup(material):
 p,raw,frame,calls,c,job=material
 token='synthetic-local-test-token-12345678901234567890'
 client=TestClient(create_app(fresh_service=p,fresh_token=token),headers={
  'X-Vigilens-Local-Access':token,'X-Vigilens-Display-Session':OWNER})
 x=prepare(client,raw,frame)
 path='/private-display/'+x['session_id']
 for origin in ['http://localhost:5173','http://127.0.0.1:5173']:
  preflight={'Origin':origin,'Access-Control-Request-Method':'DELETE',
   'Access-Control-Request-Headers':'x-vigilens-local-access,x-vigilens-display-session'}
  response=client.options(path,headers=preflight)
  assert response.status_code==200
  assert response.headers['access-control-allow-origin']==origin
  assert 'DELETE'in response.headers['access-control-allow-methods']
  assert client.options(path,headers={**preflight,'Origin':'https://unapproved.invalid'}).status_code==400
 assert client.delete(path,headers={'X-Vigilens-Local-Access':'wrong'}).status_code==403
 assert client.delete(path,headers={'X-Vigilens-Display-Session':'different_browser_nonce_123456789012345'}).status_code==404
 assert client.get(x['preview_url']).status_code==200
 deleted=client.delete(path,headers={'Origin':'http://localhost:5173'})
 assert deleted.status_code==200
 assert deleted.headers['access-control-allow-origin']=='http://localhost:5173'
 assert client.get(x['preview_url']).status_code==404
 assert len(calls)==2 # synthetic setup only; cleanup made no model calls
 # Default fixture-only app does not advertise DELETE.
 assert TestClient(create_app()).options(path,headers=preflight).status_code==400
