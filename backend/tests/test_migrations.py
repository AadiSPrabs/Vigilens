import sqlite3
import pytest
from ledger import Ledger
from worker import LocalWorker

def test_original_schema_upgrade_preserves_pending_cost(tmp_path):
 p=tmp_path/'old.sqlite';c=sqlite3.connect(p)
 c.execute('''CREATE TABLE jobs(scope TEXT NOT NULL,request_key TEXT NOT NULL,job_id TEXT NOT NULL UNIQUE,digest TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,lease_until REAL,owner TEXT,external_started INTEGER NOT NULL DEFAULT 0,result TEXT,error_code TEXT,PRIMARY KEY(scope,request_key))''')
 c.execute("INSERT INTO jobs VALUES('s','k','old','d','completed',1,1,NULL,NULL,1,'{}',NULL)")
 c.commit();c.close();p.chmod(0o600)
 l=Ledger(p);x=l.get('old');assert x['cost_state']=='unknown' and x['result_expired']==0
 assert l.expire_completed_results(10)==0 and l.register('s','k','d')==('old',False)
 Ledger(p);assert l.get('old')['result']=={}
 c=sqlite3.connect(p);assert c.execute('PRAGMA user_version').fetchone()[0]==1;c.close()

def test_future_schema_rejected_without_rewrite(tmp_path):
 p=tmp_path/'future';c=sqlite3.connect(p);c.execute('PRAGMA user_version=2');c.close();p.chmod(0o600)
 with pytest.raises(ValueError):Ledger(p)
 c=sqlite3.connect(p);assert c.execute('PRAGMA user_version').fetchone()[0]==2;c.close()

def test_restart_recovers_expired_not_rerun(tmp_path):
 p=tmp_path/'j';clock=[1.];l=Ledger(p,clock=lambda:clock[0]);j,_=l.register('s','k','d');l.claim(j,5)
 clock[0]=7.;restart=Ledger(p,clock=lambda:clock[0]);assert restart.recover_expired()==1
 assert restart.get(j)['state']=='needs_review' and restart.claim(j) is None
 assert restart.register('s','k','d')==(j,False)

@pytest.mark.parametrize('bad',[True,float('nan'),float('inf'),-1,0,'30'])
def test_strict_worker_limits(tmp_path,bad):
 l=Ledger(tmp_path/'j')
 with pytest.raises(ValueError):LocalWorker(l,lease_seconds=bad)
@pytest.mark.parametrize('bad',[True,float('nan'),float('inf'),-1,0,'30'])
def test_strict_journal_lease(tmp_path,bad):
 l=Ledger(tmp_path/'j');j,_=l.register('s','k','d')
 with pytest.raises(ValueError):l.claim(j,bad)
 assert l.get(j)['state']=='queued'

def test_pipeline_to_worker_to_scoped_result(tmp_path):
 from pipeline import OfflinePipeline,Frame,Observation,SegmentationBatch
 from test_backend import PERSON,Z
 l=Ledger(tmp_path/'j');j,_=l.register('local-test','pipeline','digest')
 b=SegmentationBatch(Frame(128,72,'synthetic'),(Observation('p',tuple(PERSON),'absent','unknown'),),True)
 def work(check):check();return OfflinePipeline().run(b,Z)
 r=LocalWorker(l).run(j,work)
 assert r['state']=='completed' and r['cost_state']=='zero_local_only'
 result=l.scoped_get(j,'local-test')['result'];assert not result['evidence_export_allowed']
 person=result['persons'][0];assert person['explanation']['worst_severity']==person['worst_severity']
 assert person['original_observations']['vest']=='unknown'
 with pytest.raises(KeyError):l.scoped_get(j,'other')
