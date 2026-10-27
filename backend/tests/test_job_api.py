import json
from fastapi.testclient import TestClient
from test_backend import png,manifest,Z
from job_api import create_job_app

def submit(c,key='key'):
 return c.post('/local/jobs',files={'image':('fixture.png',png(),'image/png')},data={'zones':json.dumps(Z)},headers={'Idempotency-Key':key})

def test_durable_http_result_survives_new_app(tmp_path):
 p=tmp_path/'jobs.sqlite';c=TestClient(create_job_app(p,manifest()));r=submit(c)
 assert r.status_code==201 and r.json()['job']['state']=='completed'
 j=r.json()['job']['job_id'];old=r.json()['job']['result']
 c2=TestClient(create_job_app(p,manifest()));r2=submit(c2)
 assert r2.status_code==200 and r2.json()['job']['job_id']==j and r2.json()['job']['result']==old
 assert c2.get('/local/jobs/'+j).json()['job']['result']==old
 assert old['source']=='fixture' and old['evidence_image'] is None

def test_job_identity_not_leaked(tmp_path):
 c=TestClient(create_job_app(tmp_path/'j',manifest()));x=submit(c).json()['job']
 assert not {'request_key','digest','scope','owner'} & x.keys()

def test_missing_fixture_cannot_create_success(tmp_path):
 c=TestClient(create_job_app(tmp_path/'j'));assert submit(c).status_code==503

def test_unknown_job(tmp_path):
 c=TestClient(create_job_app(tmp_path/'j'));r=c.get('/local/jobs/not-real');assert r.status_code==404 and 'error' in r.json()

def test_cancel_completed_not_claimed_success(tmp_path):
 c=TestClient(create_job_app(tmp_path/'j',manifest()));j=submit(c).json()['job']['job_id']
 r=c.post('/local/jobs/'+j+'/cancel');assert not r.json()['cancelled_before_execution']
 assert r.json()['job']['state']=='completed'

def test_key_conflict_returns409(tmp_path):
 from ledger import fingerprint
 from core import decode_image
 c=TestClient(create_job_app(tmp_path/'j',manifest()))
 c.app.state.ledger.register('local-fixture-review','key','different-policy')
 assert submit(c).status_code==409

def test_interrupted_job_is_not_reexecuted(tmp_path):
 from core import decode_image
 from ledger import fingerprint
 c=TestClient(create_job_app(tmp_path/'j',manifest()));l=c.app.state.ledger
 digest=fingerprint(decode_image(png(),'image/png').digest,Z,'0.2-local-draft','draft-unapproved')
 # normalized zones are equivalent for canonical numeric values in this test.
 from core import validate_zones
 digest=fingerprint(decode_image(png(),'image/png').digest,validate_zones(Z),'0.2-local-draft','draft-unapproved')
 j,_=l.register('local-fixture-review','key',digest);token=l.claim(j)
 l.mark_external_started(j,token);l.fail(j,token,'UNCERTAIN_OUTCOME')
 r=submit(c);assert r.json()['job']['state']=='needs_review' and r.json()['job']['result'] is None

def test_other_scope_cannot_read_or_cancel_job(tmp_path):
 p=tmp_path/'jobs.sqlite';a=TestClient(create_job_app(p,manifest(),local_scope='local-fixture-review'))
 j=submit(a).json()['job']['job_id']
 b=TestClient(create_job_app(p,manifest(),local_scope='another-local-scope'))
 assert b.get('/local/jobs/'+j).status_code==404
 assert b.post('/local/jobs/'+j+'/cancel').status_code==404
 assert a.get('/local/jobs/'+j).status_code==200

def test_caller_cannot_choose_scope_via_header(tmp_path):
 p=tmp_path/'jobs.sqlite';a=TestClient(create_job_app(p,manifest(),local_scope='local-fixture-review'));j=submit(a).json()['job']['job_id']
 b=TestClient(create_job_app(p,manifest(),local_scope='other'))
 assert b.get('/local/jobs/'+j,headers={'X-Scope':'local-fixture-review'}).status_code==404

def test_expired_result_does_not_reexecute_http(tmp_path):
 c=TestClient(create_job_app(tmp_path/'j',manifest()));r=submit(c);j=r.json()['job']['job_id'];l=c.app.state.ledger
 assert l.expire_completed_results(10**20)==1
 r2=submit(c);assert r2.json()['job']['job_id']==j and r2.json()['job']['state']=='completed'
 assert r2.json()['job']['result'] is None and r2.json()['job']['result_expired']==1

def test_completed_and_expired_caller_shape(tmp_path):
 c=TestClient(create_job_app(tmp_path/'j',manifest()));x=submit(c).json()['job']
 assert x['result_available'] and not x['retryable_with_same_key'] and x['cost_state']=='zero_local_only'
 c.app.state.ledger.expire_completed_results(10**20)
 x=submit(c).json()['job'];assert x['state']=='completed' and x['result_expired'] is True
 assert not x['result_available'] and x['status_reason']=='result_expired' and not x['retryable_with_same_key']
 assert x['result_expires_at'] is None and x['dedup_expires_at'] is None

def test_cancelled_caller_shape_and_running_rejection(tmp_path):
 c=TestClient(create_job_app(tmp_path/'j',manifest()));l=c.app.state.ledger
 j,_=l.register('local-fixture-review','queued-key','d');x=c.post('/local/jobs/'+j+'/cancel').json()
 assert x['cancelled_before_execution'] and x['job']['cancellation_kind']=='before_local_execution'
 assert not x['job']['retryable_with_same_key'] and x['job']['cost_state']=='unknown'
 k,_=l.register('local-fixture-review','running-key','e');l.claim(k)
 x=c.post('/local/jobs/'+k+'/cancel').json();assert not x['cancelled_before_execution'] and x['job']['state']=='running'
