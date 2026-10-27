import sys,concurrent.futures
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from ledger import Ledger,Conflict,InvalidTransition,LeaseLost,fingerprint

@pytest.fixture
def ledger(tmp_path):return Ledger(tmp_path/'jobs.sqlite')
def new(l,key='one'):return l.register('local-user',key,'digest-v1')[0]
def test_repeat_key(ledger):
 j=new(ledger);assert ledger.register('local-user','one','digest-v1')==(j,False)
def test_conflicting_key(ledger):
 new(ledger)
 with pytest.raises(Conflict):ledger.register('local-user','one','other')
def test_separate_scopes(ledger):assert new(ledger)!=ledger.register('other-user','one','digest-v1')[0]
def test_restart_preserves_result(tmp_path):
 p=tmp_path/'jobs.sqlite';l=Ledger(p);j=new(l);t=l.claim(j);l.complete(j,t,{'source':'mock','value':1})
 assert Ledger(p).get(j)['result']=={'source':'mock','value':1}
 assert Ledger(p).claim(j) is None

def test_one_claim_across_connections(tmp_path):
 p=tmp_path/'jobs.sqlite';j=new(Ledger(p))
 with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:xs=list(ex.map(lambda _:Ledger(p).claim(j),range(24)))
 assert sum(x is not None for x in xs)==1

def test_one_registration_across_connections(tmp_path):
 p=tmp_path/'jobs.sqlite';Ledger(p)
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:xs=list(ex.map(lambda _:Ledger(p).register('scope','key','same'),range(16)))
 assert len({x[0] for x in xs})==1 and sum(x[1] for x in xs)==1

def test_preexternal_failure_explicit_retry(ledger):
 j=new(ledger);t=ledger.claim(j);ledger.fail(j,t)
 assert ledger.get(j)['state']=='failed';assert ledger.claim(j) is None
 ledger.retry_pre_external(j);assert ledger.claim(j) is not None

def test_postexternal_failure_needs_review(ledger):
 j=new(ledger);t=ledger.claim(j);ledger.mark_external_started(j,t);ledger.fail(j,t,'UPSTREAM_TIMEOUT')
 assert ledger.get(j)['state']=='needs_review'
 with pytest.raises(InvalidTransition):ledger.retry_pre_external(j)
 assert ledger.claim(j) is None

def test_expiry_no_retry_even_without_marker(tmp_path):
 now=[100];l=Ledger(tmp_path/'j',clock=lambda:now[0]);j=new(l);t=l.claim(j,10);now[0]=111
 assert l.recover_expired()==1;assert l.get(j)['state']=='needs_review';assert l.claim(j) is None
 with pytest.raises(LeaseLost):l.complete(j,t,{})

def test_owner_fencing(ledger):
 j=new(ledger);ledger.claim(j)
 with pytest.raises(LeaseLost):ledger.mark_external_started(j,'not-owner')
 with pytest.raises(LeaseLost):ledger.complete(j,'not-owner',{})

def test_heartbeat(tmp_path):
 now=[100];l=Ledger(tmp_path/'j',clock=lambda:now[0]);j=new(l);t=l.claim(j,10);now[0]=105;l.heartbeat(j,t,20);now[0]=115
 assert l.recover_expired()==0;l.complete(j,t,{'source':'mock'})

def test_cancel_queued_only(ledger):
 j=new(ledger);assert ledger.cancel(j);assert ledger.claim(j) is None
 k=new(ledger,'two');ledger.claim(k);assert not ledger.cancel(k);assert ledger.get(k)['state']=='running'

def test_completed_not_overwritten(ledger):
 j=new(ledger);t=ledger.claim(j);ledger.complete(j,t,{'source':'mock'})
 with pytest.raises(LeaseLost):ledger.fail(j,t)

def test_journal(ledger):
 j=new(ledger);t=ledger.claim(j);ledger.complete(j,t,{'source':'mock'})
 assert [e['new_state'] for e in ledger.events(j)]==['queued','running','completed']

def test_identity_binds_versions_and_order():
 a=fingerprint('sha',[{'id':'a'},{'id':'b'}],'draft','r1')
 assert a!=fingerprint('sha',[{'id':'b'},{'id':'a'}],'draft','r1')
 assert a!=fingerprint('sha',[{'id':'a'},{'id':'b'}],'draft','r2')

def test_no_nonfinite_result(ledger):
 j=new(ledger);t=ledger.claim(j)
 with pytest.raises(ValueError):ledger.complete(j,t,{'x':float('nan')})
 assert ledger.get(j)['state']=='running'

def test_safe_error_codes_only(ledger):
 j=new(ledger);t=ledger.claim(j)
 with pytest.raises(ValueError):ledger.fail(j,t,'secret text goes here')
from runner import LocalRunner

def test_runner_mock_result_persists(ledger):
 j=new(ledger);r=LocalRunner(ledger).run(j,lambda:{'source':'mock','persons':[]})
 assert r['state']=='completed' and r['result']['source']=='mock'

def test_runner_cannot_relabel_live_or_ambiguous_result(ledger):
 j=new(ledger);r=LocalRunner(ledger).run(j,lambda:{'source':'backend','persons':[]})
 assert r['state']=='failed' and r['error_code']=='UNAPPROVED_RESULT_SOURCE'

def test_runner_duplicate_has_no_second_execution(ledger):
 j=new(ledger);count=[];runner=LocalRunner(ledger)
 def work():count.append(1);return {'source':'fixture'}
 runner.run(j,work);runner.run(j,work);assert len(count)==1

def test_runner_failure_no_exception_secrets_stored(ledger):
 j=new(ledger)
 def work():raise RuntimeError('private details must not reach journal')
 r=LocalRunner(ledger).run(j,work)
 assert r['state']=='failed' and r['error_code']=='LOCAL_EXECUTION_FAILED'
 assert 'private details' not in str(ledger.events(j))

def test_runner_long_work_cannot_write_after_expired_lease(tmp_path):
 now=[100];l=Ledger(tmp_path/'j',clock=lambda:now[0]);j=new(l)
 def work():now[0]=200;return {'source':'mock'}
 r=LocalRunner(l).run(j,work,10)
 assert r['state']=='needs_review' and r['result'] is None

def _claim_process(args):
 path,job_id=args
 return Ledger(path).claim(job_id)

def test_one_claim_across_processes(tmp_path):
 import multiprocessing
 p=str(tmp_path/'jobs.sqlite');j=new(Ledger(p))
 with multiprocessing.get_context('fork').Pool(4) as pool:
  values=pool.map(_claim_process,[(p,j)]*12)
 assert sum(v is not None for v in values)==1

def test_ambiguous_cost_defaults_unknown(ledger):
 j=new(ledger);t=ledger.claim(j);ledger.mark_external_started(j,t);ledger.fail(j,t,'HTTP_401')
 assert ledger.get(j)['state']=='needs_review' and ledger.get(j)['cost_state']=='unknown'

def test_late_mock_result_explicit_reconciliation_no_new_send(tmp_path):
 now=[100];l=Ledger(tmp_path/'j',clock=lambda:now[0]);j=new(l);l.claim(j,10);now[0]=111;l.recover_expired()
 l.reconcile_local_late_result(j,{'source':'mock','value':2},'verified captured local mock result')
 assert l.get(j)['state']=='completed' and l.get(j)['cost_state']=='zero_local_only' and l.claim(j) is None
 assert [e['new_state'] for e in l.events(j)]==['queued','running','needs_review','completed']

def test_external_late_reconciliation_not_claimed(ledger):
 j=new(ledger);t=ledger.claim(j);ledger.mark_external_started(j,t);ledger.fail(j,t,'UPSTREAM_TIMEOUT')
 with pytest.raises(InvalidTransition):ledger.reconcile_local_late_result(j,{'source':'mock'},'not a provider verification')

def test_live_result_reconciliation_disabled(ledger):
 j=new(ledger)
 with pytest.raises(ValueError):ledger.reconcile_local_late_result(j,{'source':'backend'},'unverified')

def test_existing_ledger_adds_unknown_cost_column(tmp_path):
 import sqlite3
 p=tmp_path/'old.sqlite';c=sqlite3.connect(p)
 c.execute('''CREATE TABLE jobs(scope TEXT,request_key TEXT,job_id TEXT UNIQUE,digest TEXT,state TEXT,created REAL,updated REAL,lease_until REAL,owner TEXT,external_started INTEGER DEFAULT 0,result TEXT,error_code TEXT,PRIMARY KEY(scope,request_key))''')
 c.execute("INSERT INTO jobs(scope,request_key,job_id,digest,state,created,updated) VALUES('s','k','old','d','completed',1,1)");c.commit();c.close();p.chmod(0o600)
 assert Ledger(p).get('old')['cost_state']=='unknown'

def test_retention_does_not_touch_uncertain_or_running(ledger):
 j=new(ledger);t=ledger.claim(j);ledger.mark_external_started(j,t);ledger.fail(j,t,'UPSTREAM_TIMEOUT')
 k=new(ledger,'running');ledger.claim(k)
 assert ledger.expire_completed_results(10**20)==0
 assert ledger.get(j)['state']=='needs_review' and ledger.get(k)['state']=='running'

def test_retention_keeps_key_history_and_never_resends(ledger):
 j=new(ledger);t=ledger.claim(j);ledger.complete(j,t,{'source':'mock','private_test':'remove'})
 assert ledger.expire_completed_results(10**20)==1 and ledger.expire_completed_results(10**20)==0
 x=ledger.get(j);assert x['result'] is None and x['result_expired']==1
 assert ledger.register('local-user','one','digest-v1')==(j,False) and ledger.claim(j) is None
 assert ledger.events(j)[-1]['reason']=='result payload expired; dedup tombstone retained'

def test_scope_cancel_checks_in_same_transaction(ledger):
 j=new(ledger)
 with pytest.raises(KeyError):ledger.scoped_cancel(j,'wrong')
 assert ledger.get(j)['state']=='queued'
 assert ledger.scoped_cancel(j,'local-user')

def test_unknown_cost_completed_is_not_expired(ledger):
 j=new(ledger);t=ledger.claim(j);ledger.mark_external_started(j,t);ledger.complete(j,t,{'source':'unverified','x':1})
 assert ledger.get(j)['cost_state']=='unknown'
 assert ledger.expire_completed_results(10**20)==0 and ledger.get(j)['result'] is not None

def test_local_expiry_preserves_cost(ledger):
 j=new(ledger);t=ledger.claim(j);ledger.complete(j,t,{'source':'mock'})
 before=ledger.get(j)['cost_state'];ledger.expire_completed_results(10**20)
 assert before==ledger.get(j)['cost_state']=='zero_local_only'

def test_local_completion_cannot_claim_privacy_release(ledger):
 j=new(ledger);t=ledger.claim(j);ledger.complete(j,t,{'source':'mock','evidence_export_allowed':True,'evidence_status':'masked','evidence_image':'raw.png','privacy_review_status':'approved'})
 x=ledger.get(j)['result'];assert x['evidence_image'] is None and not x['evidence_export_allowed'] and x['privacy_review_status']=='not_validated'
