import threading
import pytest
from ledger import Ledger
from worker import LocalWorker,WorkerBusy

def setup(tmp_path):
 now=[100.];l=Ledger(tmp_path/'j',clock=lambda:now[0]);j,_=l.register('s','k','d');return now,l,j

def test_worker_completion_and_no_duplicate(tmp_path):
 now,l,j=setup(tmp_path);w=LocalWorker(l);calls=[]
 def work(check):calls.append(1);check();return {'source':'mock'}
 assert w.run(j,work)['state']=='completed';w.run(j,work);assert len(calls)==1

def test_timeout_needs_review(tmp_path):
 now,l,j=setup(tmp_path);w=LocalWorker(l,timeout_seconds=5)
 def work(check):now[0]+=6;check();return {'source':'mock'}
 assert w.run(j,work)['state']=='needs_review' and l.claim(j) is None

def test_shutdown_before_claim_leaves_queued(tmp_path):
 now,l,j=setup(tmp_path);w=LocalWorker(l);w.shutdown();assert w.run(j,lambda c:{'source':'mock'})['state']=='queued'

def test_shutdown_inflight_needs_review(tmp_path):
 now,l,j=setup(tmp_path);w=LocalWorker(l)
 def work(check):w.shutdown();check()
 assert w.run(j,work)['state']=='needs_review'

def test_heartbeat_preserves_lease(tmp_path):
 now,l,j=setup(tmp_path);w=LocalWorker(l,lease_seconds=5,timeout_seconds=30)
 def work(check):
  for _ in range(3):now[0]+=4;check()
  return {'source':'mock'}
 assert w.run(j,work)['state']=='completed'

def test_worker_concurrency_bound(tmp_path):
 now,l,j=setup(tmp_path);w=LocalWorker(l);entered=threading.Event();release=threading.Event()
 def work(check):entered.set();release.wait(2);return {'source':'mock'}
 t=threading.Thread(target=lambda:w.run(j,work));t.start();assert entered.wait(2)
 try:
  with pytest.raises(WorkerBusy):w.run(j,work)
 finally:release.set();t.join(2)
 assert not t.is_alive()

def test_explicit_local_reconciliation_never_releases_evidence(tmp_path):
 now,l,j=setup(tmp_path);t=l.claim(j);now[0]+=100;l.recover_expired()
 l.reconcile_local_late_result(j,{'source':'mock','evidence_export_allowed':True,'evidence_image':'bad','evidence_status':'masked'},'local operator review')
 x=l.get(j)
 assert x['state']=='completed' and not x['result']['evidence_export_allowed']
 assert x['result']['evidence_image'] is None and x['result']['evidence_status']=='unavailable'

def test_job_reconciled_does_not_clear_privacy_review(tmp_path):
 now,l,j=setup(tmp_path);l.claim(j);now[0]+=100;l.recover_expired()
 l.reconcile_local_late_result(j,{'source':'mock','privacy_review_status':'approved'},'explicit test-only review')
 assert l.get(j)['state']=='completed' and l.get(j)['result']['privacy_review_status']=='not_validated'

def test_late_worker_cannot_overwrite_concurrently_reconciled_result(tmp_path):
 now,l,j=setup(tmp_path);w=LocalWorker(l,lease_seconds=5,timeout_seconds=30)
 def work(check):
  now[0]+=6;l.recover_expired()
  l.reconcile_local_late_result(j,{'source':'mock','value':'reviewed'},'operator local test review')
  return {'source':'mock','value':'stale callback'}
 x=w.run(j,work)
 assert x['state']=='completed' and x['result']['value']=='reviewed' and not x['result']['evidence_export_allowed']

def test_stop_does_not_overwrite_concurrent_operator_settlement(tmp_path):
 now,l,j=setup(tmp_path);w=LocalWorker(l,lease_seconds=5,timeout_seconds=30)
 def work(check):
  now[0]+=6;l.recover_expired()
  l.reconcile_local_late_result(j,{'source':'mock','value':'reviewed'},'operator local test review')
  w.shutdown();check()
 x=w.run(j,work)
 assert x['state']=='completed' and x['result']['value']=='reviewed'
