import time
import threading
from fastapi.testclient import TestClient
from core import decode_image,validate_zones
from ledger import fingerprint
from job_api import create_job_app
from test_backend import manifest,png,Z
from test_job_api import submit

def test_opt_in_worker_http_completion(tmp_path):
 app=create_job_app(tmp_path/'j',manifest(),cooperative_worker=True)
 with TestClient(app) as c:
  x=submit(c).json()['job'];assert x['state']=='completed' and x['result']['source']=='fixture'
  assert not x['result']['evidence_export_allowed'] and not app.state.local_worker.stopping
 assert app.state.local_worker.stopping

def test_startup_expired_recovery_no_rerun(tmp_path):
 app=create_job_app(tmp_path/'j',manifest(),cooperative_worker=True);l=app.state.ledger
 digest=fingerprint(decode_image(png(),'image/png').digest,validate_zones(Z),'0.2-local-draft','draft-unapproved')
 j,_=l.register('local-fixture-review','key',digest);l.clock=lambda:1.;l.claim(j,1);l.clock=time.time
 with TestClient(app) as c:
  x=submit(c).json()['job'];assert x['job_id']==j and x['state']=='needs_review' and x['result'] is None

def test_busy_http_job_stays_queued_then_same_key_runs_once(tmp_path):
 app=create_job_app(tmp_path/'j',manifest(),cooperative_worker=True);w=app.state.local_worker
 with TestClient(app) as c:
  w.lock.acquire()
  try:x=submit(c).json()['job'];assert x['state']=='queued' and not x['result_available']
  finally:w.lock.release()
  y=submit(c).json()['job'];assert y['job_id']==x['job_id'] and y['state']=='completed'
  z=submit(c).json()['job'];assert z['result']==y['result']

def test_shutdown_before_claim_does_not_execute(tmp_path):
 app=create_job_app(tmp_path/'j',manifest(),cooperative_worker=True)
 with TestClient(app) as c:
  app.state.local_worker.shutdown()
  assert submit(c).json()['job']['state']=='queued'

def test_original_factory_keeps_explicit_old_runner(tmp_path):
 app=create_job_app(tmp_path/'j',manifest());assert app.state.local_worker is None
 with TestClient(app) as c:assert submit(c).json()['job']['state']=='completed'

def test_actual_http_concurrent_worker_busy_and_cancel_queue(tmp_path):
 app=create_job_app(tmp_path/'j',manifest(),cooperative_worker=True)
 entered=threading.Event();release=threading.Event();original=app.state.service.audit
 def slow(*args):entered.set();release.wait(3);return original(*args)
 app.state.service.audit=slow
 with TestClient(app) as c:
  first=[]
  t=threading.Thread(target=lambda:first.append(submit(c,key='first')));t.start();assert entered.wait(2)
  try:
   busy=submit(c,key='second').json()['job'];assert busy['state']=='queued'
   cancelled=c.post('/local/jobs/'+busy['job_id']+'/cancel').json();assert cancelled['cancelled_before_execution']
  finally:release.set();t.join(3)
  assert not t.is_alive() and first[0].json()['job']['state']=='completed'
  repeat=submit(c,key='second').json()['job'];assert repeat['state']=='cancelled' and repeat['result'] is None

def test_queued_caller_behavior_not_retrying_uncertain_work(tmp_path):
 app=create_job_app(tmp_path/'j',manifest(),cooperative_worker=True)
 with TestClient(app) as c:
  w=app.state.local_worker;w.lock.acquire()
  try:x=submit(c).json()['job']
  finally:w.lock.release()
  assert x['same_key_behavior']=='may_start_queued_local_work' and not x['retryable_with_same_key']
  y=submit(c).json()['job'];assert y['same_key_behavior']=='retrieve_only_no_new_execution'
