import concurrent.futures
import pytest
from usage import UsageLedger,BudgetExceeded,UsageConflict

def test_uncertain_holds_budget_across_restart(tmp_path):
 p=tmp_path/'u';l=UsageLedger(p);r,_=l.reserve('s','one',80,100);l.uncertain(r,'s')
 with pytest.raises(BudgetExceeded):UsageLedger(p).reserve('s','two',30,100)
 with pytest.raises(UsageConflict):l.release_before_dispatch(r,'s')
 assert l.get(r,'s')['state']=='uncertain'
def test_exact_key_retrieval_not_new_spend(tmp_path):
 l=UsageLedger(tmp_path/'u');r,_=l.reserve('s','k',100,100)
 assert l.reserve('s','k',100,0)==(r,False)
 with pytest.raises(UsageConflict):l.reserve('s','k',99,100)
def test_pre_dispatch_release(tmp_path):
 l=UsageLedger(tmp_path/'u');r,_=l.reserve('s','k',100,100);l.release_before_dispatch(r,'s')
 assert l.reserve('s','k',100,100)==(r,False)
 assert l.reserve('s','new',100,100)[1]
def test_reconcile_actual_not_status_code_guess(tmp_path):
 l=UsageLedger(tmp_path/'u');r,_=l.reserve('s','k',100,100);l.uncertain(r,'s');l.reconcile(r,'s',25,'mock verified invoice')
 assert l.get(r,'s')['charged_units']==25
 assert l.reserve('s','new',75,100)[1]
def test_cap_not_silently_exceeded(tmp_path):
 l=UsageLedger(tmp_path/'u');r,_=l.reserve('s','k',10,100)
 with pytest.raises(UsageConflict):l.reconcile(r,'s',11,'overage mock')
 assert l.get(r,'s')['state']=='reserved'
def test_scoped_reservation_read_and_mutate(tmp_path):
 l=UsageLedger(tmp_path/'u');r,_=l.reserve('s','k',100,100)
 with pytest.raises(KeyError):l.get(r,'other')
 with pytest.raises(KeyError):l.reconcile(r,'other',0,'fake')
 assert l.reserve('other','k',100,100)[1]
def test_atomic_concurrent_budget(tmp_path):
 l=UsageLedger(tmp_path/'u')
 def reserve(i):
  try:return l.reserve('s',str(i),60,100)[1]
  except BudgetExceeded:return False
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:out=list(ex.map(reserve,range(8)))
 assert sum(out)==1
@pytest.mark.parametrize('bad',[True,-1,1.5,float('nan'),'100'])
def test_integer_units_only(tmp_path,bad):
 with pytest.raises(ValueError):UsageLedger(tmp_path/'u').reserve('s','k',bad,100)

def test_usage_transition_log_safe_and_scoped(tmp_path):
 l=UsageLedger(tmp_path/'u');r,_=l.reserve('s','k',100,100);l.uncertain(r,'s');l.reconcile(r,'s',25,'sensitive test account detail')
 assert [x['state'] for x in l.events(r,'s')]==['reserved','uncertain','settled']
 assert 'sensitive' not in str(l.events(r,'s'))
 with pytest.raises(KeyError):l.events(r,'other')

def test_reconciliation_idempotent_no_double_release(tmp_path):
 l=UsageLedger(tmp_path/'u');r,_=l.reserve('s','k',100,100);l.uncertain(r,'s')
 assert l.reconcile(r,'s',40,'local evidence reviewed') is True
 before=l.events(r,'s');assert l.reconcile(r,'s',40,'same local evidence reviewed') is False
 assert l.events(r,'s')==before
 with pytest.raises(UsageConflict):l.reconcile(r,'s',0,'changed claim')
 assert l.get(r,'s')['charged_units']==40
 l.reserve('s','new',60,100)
 with pytest.raises(BudgetExceeded):l.reserve('s','over',1,100)

def test_cap_never_evicts_uncertain_reservations(tmp_path):
 p=tmp_path/'u';l=UsageLedger(p);r,_=l.reserve('s','k',100,100);l.uncertain(r,'s')
 for _ in range(3):
  with pytest.raises(BudgetExceeded):UsageLedger(p).reserve('s','new',1,100)
 assert l.get(r,'s')['state']=='uncertain' and l.get(r,'s')['charged_units'] is None

def test_empty_review_reason_cannot_reconcile(tmp_path):
 l=UsageLedger(tmp_path/'u');r,_=l.reserve('s','k',100,100)
 with pytest.raises(ValueError):l.reconcile(r,'s',0,'')
 assert l.get(r,'s')['state']=='reserved'
