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

def test_runtime_optional_trusted_clip_limits_explicit_no_dispatch(tmp_path,monkeypatch):
 path,c=config(tmp_path,monkeypatch);c['trusted_clip_limits']={'max_bytes':1000000,'max_seconds':3,'max_frames':3,'max_side':640,'max_pixels':409600,'subprocess_seconds':5};path.write_text(json.dumps(c))
 app=from_config(path);assert app.state.fresh_pipeline.trusted_clip_limits.max_frames==3 and not Path(c['journal']).exists()
 c['review_loop_attempts']={'a'*64:['b'*64]};path.write_text(json.dumps(c))
 with pytest.raises(ValueError):from_config(path)
 assert not Path(c['journal']).exists()


def test_private_download_explicit_runtime_boolean_only(tmp_path,monkeypatch):
 path,c=config(tmp_path,monkeypatch);c['operator_private_download_enabled']=True;path.write_text(json.dumps(c))
 app=from_config(path);assert app.state.fresh_pipeline.operator_private_download_enabled is True
 assert not Path(c['journal']).exists()
 c['operator_private_download_enabled']=1;path.write_text(json.dumps(c))
 with pytest.raises(ValueError):from_config(path)

def test_optional_wide_runtime_explicit_limits_no_startup_dispatch(tmp_path,monkeypatch):
 from fresh_review.wide_scene import WideScenePipeline
 path,c=config(tmp_path,monkeypatch);c['wide_scene_limits']={'max_people':16,'max_ppe_calls':2,'min_crop_width':32,'min_crop_height':64};path.write_text(json.dumps(c));app=from_config(path)
 assert isinstance(app.state.fresh_pipeline,WideScenePipeline)and not Path(c['journal']).exists()
 c['wide_scene_limits']['max_ppe_calls']=10;path.write_text(json.dumps(c))
 with pytest.raises(ValueError):from_config(path)

def test_runtime_wires_pinned_chain_manifest_into_sequential_pipeline(tmp_path,monkeypatch):
 import hashlib
 from fresh_review import carry_chain as cc
 path,c=config(tmp_path,monkeypatch)
 PRES='b'*64;proof=tmp_path/'proof';proof.mkdir();(proof/'qualification.sqlite').write_bytes(b'proof')
 carry={'kind':'supplemental_accounting_carry_not_recovered_original_journal','provider_calls_total':19,'combined_listed_usd':'0.03969310','conservative_booked_usd':'0.05457125','aggregate_cap_usd':'5','blocked_source_digests':[PRES],'historical_unresolved_reservations':[],'new_unresolved_reservations':[]}
 cp=private(tmp_path/'settled.json',json.dumps(carry).encode());csha=hashlib.sha256(cp.read_bytes()).hexdigest()
 m={'format':cc.FORMAT,'carry_sha256':csha,'carry_kind':carry['kind'],'provider_calls_total':19,'combined_listed_usd':'0.03969310','conservative_booked_usd':'0.05457125','history_chain':['1'*64],'preserved':[{'source_digest':PRES,'files':{'qualification.sqlite':hashlib.sha256(b'proof').hexdigest()},'listed_usd':'0.0025','counted_in_carry':True}]}
 mp=private(tmp_path/'manifest.json',json.dumps(m).encode())
 c.update(carry_path=str(cp),carry_sha256=csha,wide_scene_limits={'sequential':True,'max_people':64,'max_ppe_calls':16},chain_manifest_path=str(mp),chain_manifest_sha256=hashlib.sha256(mp.read_bytes()).hexdigest(),chain_proof_dir=str(proof))
 good=private(tmp_path/'good.json',json.dumps(c).encode());app=from_config(good)
 assert app.state.fresh_pipeline.chain_manifest is not None and not Path(c['journal']).exists()
 (proof/'qualification.sqlite').write_bytes(b'tampered')
 with pytest.raises(ValueError):from_config(good)
 (proof/'qualification.sqlite').write_bytes(b'proof')
 bad=dict(c,chain_manifest_sha256='0'*64);private(tmp_path/'bad.json',json.dumps(bad).encode())
 with pytest.raises(ValueError):from_config(tmp_path/'bad.json')
 nochain=dict(c);[nochain.pop(k)for k in('chain_manifest_sha256',)]
 with pytest.raises(ValueError):from_config(private(tmp_path/'part.json',json.dumps(nochain).encode()))
