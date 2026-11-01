import asyncio
import pytest
from fastapi.testclient import TestClient
from limits import LocalAdmissionLimits
from app import create_app
from ledger import Ledger,QueueFull
from run_local import build

async def invoke(app,messages,headers=()):
 output=[];queue=list(messages)
 async def receive():return queue.pop(0) if queue else {'type':'http.disconnect'}
 async def send(m):output.append(m)
 await app({'type':'http','method':'POST','path':'/','headers':headers},receive,send)
 return output

def test_body_chunks_block_before_downstream():
 calls=[]
 async def downstream(s,r,w):calls.append(1)
 out=asyncio.run(invoke(LocalAdmissionLimits(downstream,4),[{'type':'http.request','body':b'abc','more_body':True},{'type':'http.request','body':b'de'}]))
 assert out[0]['status']==413 and not calls

def test_declared_size_rejected_before_read():
 async def downstream(s,r,w):raise AssertionError()
 out=asyncio.run(invoke(LocalAdmissionLimits(downstream,4),[],[(b'content-length',b'5')]))
 assert out[0]['status']==413

@pytest.mark.parametrize('headers', [[(b'content-length',b'-1')],[(b'content-length',b'x')],[(b'content-length',b'0')]*2])
def test_bad_length(headers):
 async def downstream(s,r,w):raise AssertionError()
 assert asyncio.run(invoke(LocalAdmissionLimits(downstream,4),[],headers))[0]['status']==400

def test_mismatched_length():
 async def downstream(s,r,w):raise AssertionError()
 assert asyncio.run(invoke(LocalAdmissionLimits(downstream,4),[{'type':'http.request','body':b'ab'}],[(b'content-length',b'1')]))[0]['status']==400

def test_exact_bound_and_replay():
 seen=[]
 async def downstream(s,r,w):seen.append(await r())
 asyncio.run(invoke(LocalAdmissionLimits(downstream,4),[{'type':'http.request','body':b'abcd'}]))
 assert seen==[{'type':'http.request','body':b'abcd','more_body':False}]

def test_concurrent_admission_and_slot_release():
 async def scenario():
  entered=asyncio.Event();release=asyncio.Event();out=[]
  async def downstream(s,r,w):entered.set();await release.wait()
  limited=LocalAdmissionLimits(downstream,4,1)
  first=asyncio.create_task(invoke(limited,[{'type':'http.request','body':b''}]))
  await entered.wait()
  second=await invoke(limited,[{'type':'http.request','body':b''}]);assert second[0]['status']==503
  release.set();await first
  await invoke(limited,[{'type':'http.request','body':b''}])
 asyncio.run(scenario())

def test_error_releases_slot():
 n=[]
 async def downstream(s,r,w):n.append(1);raise RuntimeError('test')
 limited=LocalAdmissionLimits(downstream,4,1)
 for _ in range(2):
  with pytest.raises(RuntimeError):asyncio.run(invoke(limited,[{'type':'http.request','body':b''}]))
 assert len(n)==2

def test_queue_limit_preserves_same_key(tmp_path):
 l=Ledger(tmp_path/'j',max_active=1);j,_=l.register('s','one','d')
 assert l.register('s','one','d')==(j,False)
 with pytest.raises(QueueFull):l.register('s','two','d')
 l.cancel(j);assert l.register('s','two','d')[1]

def test_loopback_entrypoint_health(tmp_path):
 with TestClient(build(str(tmp_path/'j'))) as c:
  x=c.get('/health');assert x.status_code==200 and not x.json()['real_analysis_enabled']

def test_stalled_body_times_out_and_slot_recovers():
 async def scenario():
  called=[];sent=[]
  async def downstream(s,r,w):called.append(1)
  async def stalled():await asyncio.sleep(1)
  async def send(m):sent.append(m)
  limited=LocalAdmissionLimits(downstream,4,1,body_timeout_seconds=.01)
  await limited({'type':'http','headers':[]},stalled,send)
  assert sent[0]['status']==408 and not called
  await invoke(limited,[{'type':'http.request','body':b''}]);assert len(called)==1
 asyncio.run(scenario())
