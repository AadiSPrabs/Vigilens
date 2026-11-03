"""Real HTTP API handlers, local canned transport only. No network/provider."""
import json,asyncio
import pytest
from test_fresh_upload_routes import prepare,acknowledge,report,OWNER
from test_fresh_zones import submit
from test_rule_report_integration import rules
from test_private_report_document import payload
from test_spatial_explanation import setup_explanation,response
from fresh_review.transport import MetaRequestTransport,CURRENT_VISITOR_KEY
from test_byok_visitor_key import FakeResponse

KEY='synthetic-request-key-not-real'

@pytest.fixture
def material(tmp_path,monkeypatch):
 from test_byok_visitor_key import _byok_pipeline,FakeOpener
 from fastapi.testclient import TestClient
 from app import create_app
 from test_seamless_demo import _img
 from fresh_review.api import _visitor_owner
 monkeypatch.setenv('VIGILENS_LIVE_DISPATCH','on')
 op=FakeOpener();p=_byok_pipeline(tmp_path,monkeypatch,op);raw,frame=_img()
 token=CURRENT_VISITOR_KEY.set(KEY)
 try:job=asyncio.run(p.run(raw,'image/png',[],owner=_visitor_owner(OWNER)))
 finally:CURRENT_VISITOR_KEY.reset(token)
 assert job['state']=='completed'
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 yield p,raw,frame,op.requests,c,job


def configured(material):
 p,raw,frame,calls,c,job=material
 x=prepare(c,raw,frame);acknowledge(c,x);submit(c,frame,job);rules(c,frame,job)
 e,plan,aid=setup_explanation(p,raw,job,c,x);p.explanation_executor=e
 class Opener:
  def __init__(self):self.requests=[]
  def open(self,request,timeout=None):
   assert CURRENT_VISITOR_KEY.get()==KEY
   self.requests.append(request)
   return FakeResponse(200,response(plan))
 op=Opener();p.transport=MetaRequestTransport(opener=op)
 return p,c,job,x,e,aid,op

def test_explanation_http_key_context_success_and_reset(material,monkeypatch):
 p,c,job,x,e,aid,op=configured(material);monkeypatch.setenv('VIGILENS_LIVE_DISPATCH','on')
 route='/fresh-private-report/'+x['session_id']+'/explanation/'+aid
 out=c.post(route,json=payload(x,job),headers={'X-Vigilens-Visitor-Key':KEY})
 assert out.status_code==200,out.text
 assert out.json()['state']=='completed'and len(op.requests)==1
 assert CURRENT_VISITOR_KEY.get()is None
 assert c.post(route,json=payload(x,job),headers={'X-Vigilens-Visitor-Key':KEY}).json()['provider_calls_this_request']==0
 assert len(op.requests)==1

@pytest.mark.parametrize('key,enabled',[('',True),('bad key',True),(KEY,False)])
def test_missing_invalid_key_or_flag_refuses_before_hold_and_dispatch(material,monkeypatch,key,enabled):
 p,c,job,x,e,aid,op=configured(material)
 monkeypatch.setenv('VIGILENS_LIVE_DISPATCH','on'if enabled else'off')
 before=e.read(aid)['state']
 for suffix in ['/explanation-reservation','/explanation/'+aid]:
  out=c.post('/fresh-private-report/'+x['session_id']+suffix,json=payload(x,job),headers={'X-Vigilens-Visitor-Key':key})
  assert out.status_code==503,out.text
 assert e.read(aid)['state']==before=='reserved_not_dispatched'
 assert not op.requests and CURRENT_VISITOR_KEY.get()is None

def test_wrong_account_cannot_use_attempt_and_context_resets_on_refusal(material,monkeypatch):
 p,c,job,x,e,aid,op=configured(material);monkeypatch.setenv('VIGILENS_LIVE_DISPATCH','on')
 out=c.post('/fresh-private-report/'+x['session_id']+'/explanation/'+aid,json=payload(x,job),headers={'X-Vigilens-Visitor-Key':KEY,'X-Vigilens-Display-Session':'cd'*32})
 assert out.status_code in(403,404,409)
 assert not op.requests and e.read(aid)['state']=='reserved_not_dispatched'
 assert CURRENT_VISITOR_KEY.get()is None

@pytest.mark.parametrize('suffix',['/recheck-reservation','/recheck/not-an-attempt','/bounded-review-loop','/ppe-segmentation/not-a-batch'])
def test_other_aux_http_paths_require_key_before_any_hold(material,monkeypatch,suffix):
 p,raw,frame,calls,c,job=material;p.transport=MetaRequestTransport();monkeypatch.setenv('VIGILENS_LIVE_DISPATCH','on')
 out=c.post('/fresh-review/'+frame.digest+suffix,json={})
 assert out.status_code==503
 assert CURRENT_VISITOR_KEY.get()is None
 db=p.connect()
 try:assert not db.execute("SELECT 1 FROM sqlite_master WHERE name IN ('recheck_attempts','explanation_attempts')").fetchall()
 finally:db.close()

@pytest.mark.parametrize('loop',[False,True])
def test_recheck_and_loop_http_propagate_key_without_retry(material,monkeypatch,loop):
 from test_recheck_execution import executor
 from fresh_review.pipeline import digest
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x)
 e,a=executor(p,frame,monkeypatch);p.recheck_executor=e
 route='/fresh-review/'+frame.digest+('/bounded-review-loop'if loop else'/recheck/'+a['attempt_id'])
 body={'source_digest':frame.digest,'result_sha256':digest(job['result'])}
 before=len(calls)
 out=c.post(route,json=body,headers={'X-Vigilens-Visitor-Key':KEY})
 assert out.status_code==200,out.text
 assert len(calls)==before+2
 assert CURRENT_VISITOR_KEY.get()is None
 assert c.post(route,json=body,headers={'X-Vigilens-Visitor-Key':KEY}).status_code==(409 if loop else 200)
 assert len(calls)==before+2
 assert p.read(frame.digest)['result']==job['result']


def test_explanation_reserve_missing_key_leaves_no_new_attempt(material,monkeypatch):
 p,c,job,x,e,aid,op=configured(material)
 # setup_explanation built a test fixture grant/hold; remove only that fixture row
 # to prove the actual HTTP reservation cannot create a new hold without a key.
 db=p.connect();db.execute('DELETE FROM explanation_attempts');db.commit();db.close()
 out=c.post('/fresh-private-report/'+x['session_id']+'/explanation-reservation',json=payload(x,job))
 assert out.status_code==503
 db=p.connect()
 try:assert db.execute('SELECT count(*) FROM explanation_attempts').fetchone()[0]==0
 finally:db.close()
 assert not op.requests
 out=c.post('/fresh-private-report/'+x['session_id']+'/explanation-reservation',json=payload(x,job),headers={'X-Vigilens-Visitor-Key':KEY})
 assert out.status_code==200,out.text
 assert out.json()['state']=='reserved_not_dispatched'and not op.requests
 assert CURRENT_VISITOR_KEY.get()is None


def test_key_context_restored_in_same_async_task_on_error(material):
 p,raw,frame,calls,c,job=material
 router=__import__('fresh_review.api',fromlist=['create_router']).create_router(p,c.app.state.fresh_display)
 route=next(r for r in router.routes if r.path.endswith('/explanation-reservation'))
 dependency=route.dependant.dependencies[0].call
 async def exercise():
  outer=CURRENT_VISITOR_KEY.set('outer-task-value')
  try:
   context=dependency(x_vigilens_visitor_key=KEY)
   await context.__anext__();assert CURRENT_VISITOR_KEY.get()==KEY
   try:await context.athrow(ValueError('synthetic failure'))
   except ValueError:pass
   assert CURRENT_VISITOR_KEY.get()=='outer-task-value'
  finally:CURRENT_VISITOR_KEY.reset(outer)
 asyncio.run(exercise());assert CURRENT_VISITOR_KEY.get()is None


def test_concurrent_aux_requests_do_not_share_keys(material):
 p,raw,frame,calls,c,job=material
 router=__import__('fresh_review.api',fromlist=['create_router']).create_router(p,c.app.state.fresh_display)
 dependency=next(r for r in router.routes if r.path.endswith('/explanation-reservation')).dependant.dependencies[0].call
 async def worker(key):
  context=dependency(x_vigilens_visitor_key=key);await context.__anext__()
  try:
   await asyncio.sleep(.01)
   assert CURRENT_VISITOR_KEY.get()==key
  finally:await context.aclose()
  assert CURRENT_VISITOR_KEY.get()is None
 async def run():await asyncio.gather(worker('synthetic-key-A'),worker('synthetic-key-B'))
 asyncio.run(run());assert CURRENT_VISITOR_KEY.get()is None
