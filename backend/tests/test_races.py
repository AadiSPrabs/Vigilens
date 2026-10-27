"""Bounded local concurrency regression, not production load certification."""
import concurrent.futures
import multiprocessing
from ledger import Ledger,QueueFull
from usage import UsageLedger,BudgetExceeded
from evidence import SyntheticEvidenceStore
from pipeline import Frame
from PIL import Image

def _reserve_job(args):
 path,i=args
 try:return Ledger(path,max_active=4).register('s',str(i),'d')[1]
 except QueueFull:return False

def test_atomic_queue_cap_across_processes(tmp_path):
 path=str(tmp_path/'j');Ledger(path,max_active=4)
 with multiprocessing.get_context('fork').Pool(4) as p:out=p.map(_reserve_job,[(path,i) for i in range(24)])
 assert sum(out)==4

def _reserve_units(args):
 path,i=args
 try:return UsageLedger(path).reserve('s',str(i),30,100)[1]
 except BudgetExceeded:return False

def test_atomic_usage_cap_across_processes(tmp_path):
 path=str(tmp_path/'u');UsageLedger(path)
 with multiprocessing.get_context('fork').Pool(4) as p:out=p.map(_reserve_units,[(path,i) for i in range(24)])
 assert sum(out)==3

def test_cancel_claim_race_never_runs_cancelled_job(tmp_path):
 l=Ledger(tmp_path/'j');j,_=l.register('s','k','d')
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
  cancel=ex.submit(l.cancel,j);claim=ex.submit(l.claim,j)
  cancelled,token=cancel.result(),claim.result()
 assert (cancelled and token is None and l.get(j)['state']=='cancelled') or (not cancelled and token and l.get(j)['state']=='running')

def test_synthetic_delete_read_race_no_resurrection(tmp_path):
 s=SyntheticEvidenceStore(tmp_path/'e');f=Frame(8,8,'f');x=s.put('s','a',f,Image.new('RGB',(8,8)),source='synthetic');aid=x['asset_id']
 def read():
  try:return s.read_for_local_test(aid,'s')
  except KeyError:return None
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
  r=ex.submit(read);d=ex.submit(s.delete,aid,'s');read_result=r.result();assert d.result()
 assert read_result is None or isinstance(read_result,bytes)
 # A read begun before delete may already have returned a copy. Deletion cannot recall it.
 assert s.metadata(aid,'s')['state']=='deleted'
 assert s.put('s','a',f,Image.new('RGB',(8,8)),source='synthetic')['state']=='deleted'
