import io,json,hashlib
from pathlib import Path
import pytest
from fresh_review.transport import MetaTransport
from fresh_review.runtime import from_config
from fresh_review.pipeline import FreshPipeline
from test_fresh_upload_pipeline import setup

def private(path,raw):path.write_bytes(raw);path.chmod(0o600);return path
class Reply:
 status=200
 def __init__(self,raw):self.raw=raw
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def read(self,n):return self.raw[:n]
class Opener:
 def __init__(self,reply=None,error=None):self.calls=[];self.reply=reply or Reply(b'{}');self.error=error
 def open(self,request,timeout):
  self.calls.append((request,timeout))
  if self.error:raise self.error
  return self.reply

def test_transport_fixedendpoint_privatekey_once(tmp_path):
 key=private(tmp_path/'key',b'synthetic-key-not-real');op=Opener();t=MetaTransport(key,opener=op)
 assert t({'model':'muse-spark-1.3','store':False})==b'{}'
 assert len(op.calls)==1 and op.calls[0][0].full_url=='https://api.meta.ai/v1/responses'
 assert op.calls[0][0].get_header('Authorization')=='Bearer synthetic-key-not-real'
@pytest.mark.parametrize('failure',['timeout','oversize','status'])
def test_transport_no_retry_on_failure(tmp_path,failure):
 op=Opener(error=TimeoutError()if failure=='timeout'else None,reply=Reply(b'x'*256001)if failure=='oversize'else Reply(b'{}'))
 if failure=='status':op.reply.status=429
 t=MetaTransport(private(tmp_path/'key',b'synthetic'),opener=op)
 with pytest.raises((ValueError,TimeoutError)):t({'model':'muse-spark-1.3','store':False})
 assert len(op.calls)==1

def config(tmp_path,monkeypatch):
 p,raw,f,calls=setup(tmp_path,monkeypatch);tmp_path.chmod(0o700)
 token=private(tmp_path/'access',b'synthetic-local-runtime-token-123456789012345')
 key=private(tmp_path/'key',b'synthetic-not-real-key')
 c={'version':1,'journal':str(tmp_path/'runtime.sqlite'),'carry_path':str(p.carry_path),'carry_sha256':p.carry_sha,'approval_path':str(p.approval_store.path),'approval_sha256':p.approval_store.sha,'key_file':str(key),'access_token_file':str(token),'execution_scope':'private_provider_processing'}
 path=private(tmp_path/'runtime.json',json.dumps(c).encode());return path,c

def test_runtime_builds_actual_private_app_without_dispatch(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 path,c=config(tmp_path,monkeypatch);app=from_config(path)
 client=TestClient(app,headers={'X-Vigilens-Local-Access':'synthetic-local-runtime-token-123456789012345'})
 assert client.get('/fresh-review/'+'a'*64,headers={'X-Vigilens-Local-Access':'synthetic-local-runtime-token-123456789012345'}).status_code==409
 assert not Path(c['journal']).exists()
 assert isinstance(app.state.fresh_pipeline.transport,MetaTransport)
@pytest.mark.parametrize('field,value',[('execution_scope','synthetic_local_qualification'),('key_file','relative-key'),('carry_sha256','0'*64)])
def test_runtime_wrongconfig_fails_nojournal(tmp_path,monkeypatch,field,value):
 path,c=config(tmp_path,monkeypatch);c[field]=value;path.write_text(json.dumps(c))
 with pytest.raises((ValueError,OSError)):from_config(path)
 assert not Path(c['journal']).exists()

def test_completed_restart_and_unknown_failure_keep_same_dedup(tmp_path,monkeypatch):
 import asyncio
 p,raw,f,calls=setup(tmp_path,monkeypatch)
 assert asyncio.run(p.run(raw,'image/png',[]))['state']=='completed'
 restart=FreshPipeline(p.path,approval_store=p.approval_store,transport=lambda _:pytest.fail('restart redispatch'),execution_scope=p.execution_scope,carry_path=p.carry_path,carry_sha=p.carry_sha)
 assert asyncio.run(restart.run(raw,'image/png',[]))['provider_calls_this_request']==0
 assert len(calls)==2

def test_network_transport_timeout_integrated_hold_no_retry(tmp_path,monkeypatch):
 import asyncio
 p,raw,f,calls=setup(tmp_path,monkeypatch)
 op=Opener(error=TimeoutError());p.transport=MetaTransport(private(tmp_path/'key',b'synthetic-key'),opener=op)
 result=asyncio.run(p.run(raw,'image/png',[]))
 assert result['state']=='running_uncertain'and result['reservation_usd']=='2.627012'
 restart=FreshPipeline(p.path,approval_store=p.approval_store,transport=p.transport,execution_scope=p.execution_scope,carry_path=p.carry_path,carry_sha=p.carry_sha)
 assert asyncio.run(restart.run(raw,'image/png',[]))['provider_calls_this_request']==0 and len(op.calls)==1

@pytest.mark.parametrize('raw',[b'',b'   ',b'bad key',b'nonascii-\xc3\xa9'])
def test_runtime_bad_key_fails_before_journal(tmp_path,monkeypatch,raw):
 path,c=config(tmp_path,monkeypatch);Path(c['key_file']).write_bytes(raw)
 with pytest.raises(ValueError):from_config(path)
 assert not Path(c['journal']).exists()
