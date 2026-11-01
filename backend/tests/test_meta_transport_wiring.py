"""MetaTransport wiring with an injected fake opener: exact request shape, fail-closed replies, no network."""
import io,json
import pytest
from PIL import Image
from fresh_review.ppe import canonical_body
from fresh_review.transport import MetaTransport

class FakeResponse:
 def __init__(self,status=200,payload=b'{"ok":true}',read_size=None):
  self.status=status;self.payload=payload;self.read_size=read_size
 def __enter__(self):return self
 def __exit__(self,*a):return False
 def read(self,n):return self.payload if self.read_size is None else self.payload*(self.read_size)

class FakeOpener:
 def __init__(self,response):self.response=response;self.calls=[]
 def open(self,request,timeout=None):
  self.calls.append((request,timeout))
  return self.response

def key_file(tmp_path):
 path=tmp_path/'developer-key.txt';path.write_bytes(b'developer-owned-test-key-not-real-0123456789');path.chmod(0o600)
 return path

def test_exact_request_shape_and_success(tmp_path):
 opener=FakeOpener(FakeResponse(200,b'{"status":"completed"}'))
 transport=MetaTransport(key_file(tmp_path),opener=opener)
 body=canonical_body(b'fake-crop-bytes')
 result=transport(body)
 assert result==b'{"status":"completed"}' and len(opener.calls)==1
 request,timeout=opener.calls[0]
 assert request.full_url=='https://api.meta.ai/v1/responses' and request.get_method()=='POST' and timeout==90
 assert request.get_header('Authorization')=='Bearer developer-owned-test-key-not-real-0123456789'
 assert request.get_header('Content-type')=='application/json'
 assert json.loads(request.data)==body

def test_non_success_refused_without_retry(tmp_path):
 opener=FakeOpener(FakeResponse(500,b'{"error":"x"}'))
 transport=MetaTransport(key_file(tmp_path),opener=opener)
 with pytest.raises(ValueError):transport(canonical_body(b'fake-crop-bytes'))
 assert len(opener.calls)==1

def test_oversize_ppe_reply_refused(tmp_path):
 opener=FakeOpener(FakeResponse(200,b'x',read_size=256001))
 transport=MetaTransport(key_file(tmp_path),opener=opener)
 with pytest.raises(ValueError):transport(canonical_body(b'fake-crop-bytes'))

def test_sam_reply_bound_larger_than_ppe(tmp_path):
 from fresh_review.ppe import image_input
 opener=FakeOpener(FakeResponse(200,b'x',read_size=4000001))
 transport=MetaTransport(key_file(tmp_path),opener=opener)
 sam={'model':'sam-3.1','input':image_input(b'fake-image','prompt'),'store':False}
 with pytest.raises(ValueError):transport(sam)
 opener2=FakeOpener(FakeResponse(200,b'x',read_size=256001))
 transport2=MetaTransport(key_file(tmp_path),opener=opener2)
 assert transport2(sam)==b'x'*256001

def test_bad_body_refused_before_network(tmp_path):
 opener=FakeOpener(FakeResponse(200))
 transport=MetaTransport(key_file(tmp_path),opener=opener)
 for bad in [{'model':'gpt-4','store':False},{'model':'muse-spark-1.3','store':True},{'model':'muse-spark-1.3','store':False,'tools':[{'type':'web_search'}]}]:
  with pytest.raises(ValueError):transport(bad)
 assert opener.calls==[]

def test_key_permissions_enforced_at_init(tmp_path):
 path=tmp_path/'open-key.txt';path.write_bytes(b'k'*40);path.chmod(0o644)
 with pytest.raises(ValueError):MetaTransport(path,opener=FakeOpener(FakeResponse(200)))

def test_dev_install_transport_selection(tmp_path):
 from dev_install import create_state, load_service
 from fresh_review.synthetic_transport import SyntheticTransport
 config=create_state(tmp_path/'state')
 config_path=str(tmp_path/'state'/'dev-config.json')
 service,token,origins=load_service(config_path)
 assert isinstance(service.transport,SyntheticTransport)
 assert service.execution_scope=='synthetic_local_qualification'
 service2,_,_=load_service(config_path,transport='meta',key_file=str(key_file(tmp_path)))
 assert isinstance(service2.transport,MetaTransport)
 assert service2.execution_scope=='private_provider_processing'
 with pytest.raises(ValueError):load_service(config_path,transport='meta')

def test_constructor_refuses_meta_transport_under_synthetic_scope(tmp_path):
 from fresh_review.pipeline import FreshPipeline
 from test_fresh_upload_pipeline import approval_store, carry
 with pytest.raises(ValueError):
  FreshPipeline(tmp_path/'fresh.sqlite',**carry(tmp_path),execution_scope='synthetic_local_qualification',
                approval_store=approval_store(tmp_path,{}),
                transport=MetaTransport(key_file(tmp_path),opener=FakeOpener(FakeResponse(200,b'{}'))))

def test_wide_constructor_refuses_meta_transport_under_synthetic_scope(tmp_path):
 from fresh_review.wide_scene import WideScenePipeline,WideLimits
 from test_fresh_upload_pipeline import approval_store, carry
 with pytest.raises(ValueError):
  WideScenePipeline(tmp_path/'wide.sqlite',**carry(tmp_path),execution_scope='synthetic_local_qualification',
                    approval_store=approval_store(tmp_path,{}),
                    transport=MetaTransport(key_file(tmp_path),opener=FakeOpener(FakeResponse(200,b'{}'))),
                    wide_limits=WideLimits())

def test_post_construction_transport_mutation_refused_before_dispatch(tmp_path):
 # Muse Q1(a): transport/execution_scope are mutable attributes; the pairing invariant is
 # re-checked on every checkpoint read, so swapping in a live transport after construction
 # fails closed at the first booking-path read, before any provider request.
 from dev_install import create_state, load_service
 import io
 from PIL import Image
 im=Image.new('RGB',(64,64),'navy');buf=io.BytesIO();im.save(buf,'PNG');raw=buf.getvalue()
 (tmp_path/'seed.png').write_bytes(raw)
 config=create_state(tmp_path/'state',images=[tmp_path/'seed.png'])
 service,token,origins=load_service(str(tmp_path/'state'/'dev-config.json'))
 opener=FakeOpener(FakeResponse(200,b'{}'))
 service.transport=MetaTransport(key_file(tmp_path),opener=opener)
 import asyncio
 with pytest.raises(ValueError):asyncio.run(service.run(raw,'image/png',[]))
 assert opener.calls==[]

def test_subclass_of_meta_transport_also_refused_under_synthetic_scope(tmp_path):
 # Zero-network stub: subclass retains the live __call__ but uses the injected fake opener.
 class SubMeta(MetaTransport):
  pass
 from fresh_review.pipeline import FreshPipeline
 from test_fresh_upload_pipeline import approval_store, carry
 opener=FakeOpener(FakeResponse(200,b'{}'))
 with pytest.raises(ValueError):
  FreshPipeline(tmp_path/'fresh.sqlite',**carry(tmp_path),execution_scope='synthetic_local_qualification',
                approval_store=approval_store(tmp_path,{}),
                transport=SubMeta(key_file(tmp_path),opener=opener))
 # Legitimate live pairing with a subclass is allowed.
 service=FreshPipeline(tmp_path/'live.sqlite',**carry(tmp_path),execution_scope='private_provider_processing',
                       approval_store=approval_store(tmp_path,{}),
                       transport=SubMeta(key_file(tmp_path),opener=opener))
 assert service.execution_scope=='private_provider_processing'

def test_post_construction_subclass_mutation_refused_before_dispatch(tmp_path):
 class SubMeta(MetaTransport):
  pass
 from dev_install import create_state, load_service
 import io
 from PIL import Image
 im=Image.new('RGB',(64,64),'navy');buf=io.BytesIO();im.save(buf,'PNG');raw=buf.getvalue()
 (tmp_path/'seed.png').write_bytes(raw)
 config=create_state(tmp_path/'state',images=[tmp_path/'seed.png'])
 service,token,origins=load_service(str(tmp_path/'state'/'dev-config.json'))
 opener=FakeOpener(FakeResponse(200,b'{}'))
 service.transport=SubMeta(key_file(tmp_path),opener=opener)
 import asyncio
 with pytest.raises(ValueError):asyncio.run(service.run(raw,'image/png',[]))
 assert opener.calls==[]
