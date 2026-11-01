import asyncio
import concurrent.futures
import sqlite3
import pytest
from operations import LocalOperations
from ledger import Ledger,QueueFull
from test_limits import invoke

def test_rate_limit_before_body_and_recovery():
 now=[100.];seen=[]
 async def app(s,r,w):seen.append(1);await w({'type':'http.response.start','status':204,'headers':[]});await w({'type':'http.response.body','body':b''})
 o=LocalOperations(app,max_requests=2,period_seconds=10,clock=lambda:now[0])
 for _ in range(2):assert asyncio.run(invoke(o,[]))[0]['status']==204
 assert asyncio.run(invoke(o,[]))[0]['status']==429 and len(seen)==2
 now[0]=111.;assert asyncio.run(invoke(o,[]))[0]['status']==204
 assert o.snapshot()['counters']=={'admitted':3,'status_2xx':3,'rate_limited':1}

def test_safe_metrics_no_private_path_or_error():
 async def app(s,r,w):raise RuntimeError('SECRET_BODY_TOKEN')
 o=LocalOperations(app)
 with pytest.raises(RuntimeError):asyncio.run(invoke(o,[],[(b'authorization',b'SECRET_BODY_TOKEN')]))
 snapshot=o.snapshot();assert 'SECRET' not in str(snapshot)
 assert snapshot['counters']['unhandled_exception']==1 and len(o.counters)==3

def test_metric_snapshot_not_mutable_reference():
 o=LocalOperations(None);s=o.snapshot();s['counters']['secret']=1;assert 'secret' not in o.snapshot()['counters']

def test_journal_record_bound_keeps_tombstone_and_uncertain(tmp_path):
 l=Ledger(tmp_path/'j',max_records=1);j,_=l.register('s','k','d');t=l.claim(j);l.mark_external_started(j,t);l.fail(j,t,'UNKNOWN')
 with pytest.raises(QueueFull):l.register('s','new','d')
 assert l.get(j)['state']=='needs_review' and l.register('s','k','d')==(j,False)

def test_atomic_record_bound_across_connections(tmp_path):
 p=tmp_path/'j';Ledger(p,max_records=3)
 def reg(i):
  try:return Ledger(p,max_records=3).register('s',str(i),'d')[1]
  except QueueFull:return False
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:xs=list(ex.map(reg,range(20)))
 assert sum(xs)==3

def test_concurrent_legacy_schema_migration_is_serialized(tmp_path):
 p=tmp_path/'old';c=sqlite3.connect(p);c.execute('''CREATE TABLE jobs(scope TEXT,request_key TEXT,job_id TEXT UNIQUE,digest TEXT,state TEXT,created REAL,updated REAL,lease_until REAL,owner TEXT,external_started INTEGER DEFAULT 0,result TEXT,error_code TEXT,PRIMARY KEY(scope,request_key))''');c.commit();c.close();p.chmod(0o600)
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:xs=list(ex.map(lambda _:Ledger(p),range(12)))
 assert len(xs)==12
 c=sqlite3.connect(p);cols=[r[1] for r in c.execute('PRAGMA table_info(jobs)')];c.close()
 assert cols.count('cost_state')==cols.count('result_expired')==1

def test_entrypoint_rate_limit_before_buffering(tmp_path):
 from run_local import build
 async def scenario():
  app=build(str(tmp_path/'j'),local_rate_limit=1)
  # Spend the one admitted request with an empty ASGI body at an unknown route.
  async def receive():return {'type':'http.request','body':b''}
  async def send(m):pass
  scope={'type':'http','method':'GET','path':'/health','raw_path':b'/health','query_string':b'','headers':[],'http_version':'1.1','scheme':'http','server':('127.0.0.1',8000),'client':('127.0.0.1',123)}
  await app(scope,receive,send)
  async def must_not_read():raise AssertionError('Rate-rejected body must not be buffered')
  out=[]
  async def capture(m):out.append(m)
  await app(scope,must_not_read,capture)
  assert out[0]['status']==429
 asyncio.run(scenario())

def test_result_payload_bound_no_partial_completion(tmp_path):
 l=Ledger(tmp_path/'j',max_result_bytes=64);j,_=l.register('s','k','d');t=l.claim(j)
 with pytest.raises(ValueError):l.complete(j,t,{'source':'mock','data':'x'*100})
 assert l.get(j)['state']=='running' and l.get(j)['result'] is None

def test_reconciliation_payload_bound_preserves_uncertain(tmp_path):
 l=Ledger(tmp_path/'j',max_result_bytes=200);j,_=l.register('s','k','d');l.claim(j)
 l.clock=lambda:10**10;l.recover_expired()
 with pytest.raises(ValueError):l.reconcile_local_late_result(j,{'source':'mock','data':'x'*300},'local review')
 assert l.get(j)['state']=='needs_review'

def test_wal_setup_retries_only_bounded_local_busy():
 now=[0.];calls=[]
 class Cursor:
  def fetchone(self):return ('wal',)
 class Connection:
  def execute(self,sql):
   calls.append(sql)
   if len(calls)==1:
    error=sqlite3.OperationalError('database is locked');error.sqlite_errorcode=5;raise error
   return Cursor()
 Ledger._enable_wal(Connection(),timeout=.1,clock=lambda:now[0],pause=lambda n:now.__setitem__(0,now[0]+n))
 assert len(calls)==2 and now[0]>0

@pytest.mark.parametrize('code',[5,10])
def test_wal_setup_busy_deadline_or_other_error_propagates(code):
 now=[0.];calls=[]
 class Connection:
  def execute(self,sql):
   calls.append(sql);error=sqlite3.OperationalError('local setup failure');error.sqlite_errorcode=code;raise error
 with pytest.raises(sqlite3.OperationalError):Ledger._enable_wal(Connection(),timeout=.05,clock=lambda:now[0],pause=lambda n:now.__setitem__(0,now[0]+n))
 assert len(calls)==(3 if code==5 else 1)

def test_wal_setup_older_python_busy_message_is_bounded():
 now=[0.];calls=[]
 class Connection:
  def execute(self,sql):calls.append(sql);raise sqlite3.OperationalError('database is locked')
 with pytest.raises(sqlite3.OperationalError):Ledger._enable_wal(Connection(),timeout=.05,clock=lambda:now[0],pause=lambda n:now.__setitem__(0,now[0]+n))
 assert len(calls)==3
