import json,io,asyncio,httpx,pytest
from PIL import Image
from app import create_app
from local_ui_proxy import create_proxy
from test_fresh_upload_routes import material
TOKEN='synthetic-local-test-token-12345678901234567890'
NONCE='n'*48
O={'Origin':'http://localhost:8000'}
def mk(p,ui=None):
 backend=httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(fresh_service=p)),base_url='http://backend')
 return create_proxy(backend,TOKEN,launch_nonce=NONCE,ui_dir=ui)
def run(p,raw,headers=O,ctype=True,key='k'*16,token=TOKEN,launch=True,nonce=NONCE):
 async def go():
  backend=httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(fresh_service=p)),base_url='http://backend')
  app=create_proxy(backend,token,launch_nonce=NONCE)
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost:8000') as c:
   if launch:
    await c.post('/launch',json={'n':nonce},headers=O)
   h={**headers}
   if key:h['Idempotency-Key']=key
   return await c.post('/audit',files={'image':('x.png',raw,'image/png')},data={'zones':'[]'},headers=h)
 return asyncio.run(go())
def test_stored_result_through_proxy_browser_sends_no_token(material):
 p,raw,frame,calls,c,job=material;n=len(calls)
 r=run(p,raw);assert r.status_code==200 and len(calls)==n
 x=r.json();assert x['provider_calls_this_request']==0 and x['evidence_image'] is None and x['zones_applied'] is False and '"mask"' not in json.dumps(x)
 assert TOKEN not in r.text and TOKEN not in json.dumps(dict(r.headers))
def test_origin_key_and_bad_token_refused_and_no_call(material):
 p,raw,frame,calls,c,job=material;n=len(calls)
 assert run(p,raw,headers={}).status_code==403
 assert run(p,raw,launch=False).status_code==401   # no cookie: not authorised
 assert run(p,raw,nonce='x'*48).status_code==401   # wrong nonce: no session
 assert run(p,raw,headers={'Origin':'http://evil.example'}).status_code==403
 assert run(p,raw,headers={**O,'Sec-Fetch-Site':'same-site'}).status_code==403
 assert run(p,raw,key='').status_code==400
 r=run(p,raw,token='W'*40);assert r.status_code==502 and r.json()['error']['code']=='BACKEND_AUTH_FAILED'
 with pytest.raises(ValueError):create_proxy(None,'short',launch_nonce=NONCE)
 assert len(calls)==n
def test_new_image_goes_through_governed_path_not_proxy_decision(material):
 # An unapproved new image is refused by the backend runtime (409 -> proxy 501 (a status the unchanged client shows verbatim)), and no extra provider call happens.
 p,raw,frame,calls,c,job=material;n=len(calls)
 buf=io.BytesIO();Image.new('RGB',(40,40),(9,8,7)).save(buf,'PNG')
 r=run(p,buf.getvalue());assert r.status_code==501 and 'never starts analysis' in r.json()['error']['message'] and len(calls)==n

def test_nonce_single_use_cookie_flags_static_gated_and_traversal(material,tmp_path):
 p,raw,frame,calls,c,job=material
 ui=tmp_path/'ui';ui.mkdir();(ui/'index.html').write_text('<html>ui</html>');(tmp_path/'secret.txt').write_text('SECRET')
 async def go():
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mk(p,ui)),base_url='http://localhost:8000') as a:
   assert (await a.get('/')).status_code==401 and (await a.get('/index.html')).status_code==401   # UI itself needs the session
   r=await a.post('/launch',json={'n':NONCE},headers=O);assert r.status_code==200
   sc=r.headers['set-cookie'].lower();assert 'httponly' in sc and 'samesite=strict' in sc and NONCE not in sc
   assert (await a.get('/')).status_code==200
   assert (await a.get('/../secret.txt')).text!='SECRET' and (await a.get('/%2e%2e/secret.txt')).text!='SECRET'
   async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mk(p,ui)),base_url='http://localhost:8000') as b:
    assert (await b.post('/launch',json={'n':NONCE},headers=O)).status_code==200
    assert (await b.post('/launch',json={'n':NONCE},headers=O)).status_code==403   # single use
 asyncio.run(go())
 with pytest.raises(ValueError):create_proxy(None,TOKEN,launch_nonce='short')

def _post_new(tmp_path,monkeypatch,governed,people=1):
 from test_fresh_upload_pipeline import setup
 p,raw,frame,calls=setup(tmp_path,monkeypatch,people=people)
 async def go():
  backend=httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(fresh_service=p)),base_url='http://backend')
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_proxy(backend,TOKEN,launch_nonce=NONCE,governed_new_image=governed)),base_url='http://localhost:8000') as c:
   await c.post('/launch',json={'n':NONCE},headers=O)
   return await c.post('/audit',files={'image':('x.png',raw,'image/png')},data={'zones':'[]'},headers={**O,'Idempotency-Key':'k'*16})
 return asyncio.run(go()),calls
def test_proxy_default_never_dispatches_new_image_and_governed_flag_only_selects_the_governed_handler(tmp_path,monkeypatch):
 (tmp_path/'a').mkdir();r,calls=_post_new(tmp_path/'a',monkeypatch,False)
 assert r.status_code==501 and not calls                                 # default: stored-only, even an approved image is not dispatched
 (tmp_path/'b').mkdir();r,calls=_post_new(tmp_path/'b',monkeypatch,True)
 assert r.status_code==200 and len(calls)==2                              # governed handler: synthetic stub transport only, approval present
 x=r.json();assert x['provider_calls_this_request'] is None and 'ledger' in x['provider_calls_note'] and TOKEN not in r.text
def test_no_existence_oracle_unbound_vs_unknown_digest(material):
 p,raw,frame,calls,c,job=material
 a=c.get('/fresh-review/'+frame.digest+'/frontend-audit',headers={'X-Vigilens-Display-Session':'Z'*40})
 b=c.get('/fresh-review/'+'1'*64+'/frontend-audit',headers={'X-Vigilens-Display-Session':'Z'*40})
 assert a.status_code==b.status_code==409 and a.json()==b.json()   # stored-but-unbound is indistinguishable from nonexistent

def test_governed_refusal_message_does_not_claim_no_call_was_made(tmp_path,monkeypatch):
 from test_fresh_upload_pipeline import setup
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 buf=io.BytesIO();Image.new('RGB',(40,40),(9,8,7)).save(buf,'PNG')
 r=run_gov(p,buf.getvalue());assert r.status_code==501 and r.json()['error']['code']=='ANALYSIS_REFUSED' and 'No call was made' not in r.text and not calls
def run_gov(p,raw):
 async def go():
  backend=httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(fresh_service=p)),base_url='http://backend')
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_proxy(backend,TOKEN,launch_nonce=NONCE,governed_new_image=True)),base_url='http://localhost:8000') as c:
   await c.post('/launch',json={'n':NONCE},headers=O);return await c.post('/audit',files={'image':('x.png',raw,'image/png')},data={'zones':'[]'},headers={**O,'Idempotency-Key':'k'*16})
 return asyncio.run(go())


def _client(p,ui=None,clock=None,**kw):
 backend=httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(fresh_service=p)),base_url='http://backend')
 extra={'clock':clock}if clock else{}
 return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_proxy(backend,TOKEN,launch_nonce=NONCE,ui_dir=ui,**extra,**kw)),base_url='http://localhost:8000')
def _post(c,raw,key='k'*16,headers=None,files=None):
 return c.post('/audit',files=files or {'image':('x.png',raw,'image/png')},data={'zones':'[]'},headers={**O,'Idempotency-Key':key,**(headers or{})})
def test_launch_page_has_no_nonce_expiry_idle_absolute_logout_and_launch_get_does_not_redeem(material):
 p,raw,frame,calls,c0,job=material;t=[1000.]
 async def go():
  async with _client(p,clock=lambda:t[0]) as c:
   page=await c.get('/launch',params={'n':NONCE});assert page.status_code==200 and NONCE not in page.text and 'location.hash' in page.text   # GET never redeems; nonce stays in the fragment
   assert (await c.post('/launch',json={'n':NONCE},headers=O)).status_code==200
   assert (await _post(c,raw)).status_code==200
   t[0]+=1801;assert (await _post(c,raw,key='j'*16)).status_code==401          # idle expiry
  async with _client(p,clock=lambda:t[0]) as c:
   t[0]+=301;assert (await c.post('/launch',json={'n':NONCE},headers=O)).status_code==403   # nonce expiry
  t[0]=1000.
  async with _client(p,clock=lambda:t[0]) as c:
   await c.post('/launch',json={'n':NONCE},headers=O)
   for i in range(9):t[0]+=1700;assert (await _post(c,raw,key='a%015d'%i)).status_code in(200,401)
   assert (await _post(c,raw,key='z'*16)).status_code==401                      # absolute lifetime (4 h) reached despite activity
  async with _client(p,clock=lambda:t[0]) as c:
   await c.post('/launch',json={'n':NONCE},headers=O)
   assert (await c.post('/logout',headers=O)).status_code==200
   assert (await _post(c,raw)).status_code==401                                   # revoked
 asyncio.run(go())
def test_idempotency_replay_conflict_and_scope(material):
 p,raw,frame,calls,c0,job=material;n=len(calls);seen=[]
 async def go():
  async with _client(p) as c:
   await c.post('/launch',json={'n':NONCE},headers=O)
   a=await _post(c,raw,key='idem-key-0001');b=await _post(c,raw,key='idem-key-0001')
   assert a.status_code==b.status_code==200 and b.headers.get('x-vigilens-idempotent-replay')=='true' and a.content==b.content
   buf=io.BytesIO();Image.new('RGB',(40,40),(1,2,3)).save(buf,'PNG')
   x=await _post(c,raw,key='idem-key-0001',files={'image':('y.png',buf.getvalue(),'image/png')});assert x.status_code==409 and x.json()['error']['code']=='IDEMPOTENCY_CONFLICT'
 asyncio.run(go());assert len(calls)==n
def test_malformed_content_length_sec_fetch_none_and_neutral_messages(material):
 p,raw,frame,calls,c0,job=material
 async def go():
  async with _client(p) as c:
   await c.post('/launch',json={'n':NONCE},headers=O)
   for bad in ('abc','-5','1e3'):
    r=await _post(c,raw,headers={'Content-Length':bad});assert r.status_code in(400,413,422) or r.status_code==400
   assert (await _post(c,raw,headers={'Sec-Fetch-Site':'none'})).status_code==403
   assert (await _post(c,raw,headers={'Sec-Fetch-Site':'same-origin'})).status_code==200
 asyncio.run(go())
def test_launcher_refuses_port_not_matching_bundle(tmp_path):
 import subprocess,sys,os
 ui=tmp_path/'ui';ui.mkdir();(ui/'index.html').write_text('x');(ui/'a.js').write_text('const b="http://localhost:8000"')
 tf=tmp_path/'tok';tf.write_text('t'*40);tf.chmod(0o600)
 r=subprocess.run([sys.executable,str(pathlib.Path(__file__).parent.parent/'run_ui_proxy.py'),'--token-file',str(tf),'--ui-dist',str(ui),'--port','9123','--no-open'],capture_output=True,text=True,timeout=20)
 assert r.returncode==2 and 'http://localhost:8000' in r.stderr and 'matching --port' in r.stderr
import pathlib


def test_governed_proxy_reports_uncertain_attempt_and_retry_makes_no_new_call(tmp_path,monkeypatch):
 from test_fresh_upload_pipeline import setup
 p,raw,frame,calls=setup(tmp_path,monkeypatch,people=2,timeout=2)
 r=run_gov(p,raw);n=len(calls)
 assert r.status_code==501 and r.json()['error']['code']=='ATTEMPT_UNCERTAIN' and 'no call' not in r.text.lower() and n==2
 r=run_gov(p,raw);assert r.json()['error']['code']=='ATTEMPT_UNCERTAIN' and len(calls)==n


def test_session_bridge_helper_is_default_off_strict_and_not_the_cookie_value():
 import local_ui_proxy as L
 z='/fresh-review/'+'a'*64+'/zone-review'
 assert L.bridge_allowed('GET',z) is False and L.BRIDGE_ALLOWLIST==()           # off by default
 on={('GET','zone-review')}
 assert L.bridge_allowed('GET',z,on) is True
 for m,p in(('POST',z),('GET',z+'/x'),('GET','/fresh-review/'+'a'*63+'/zone-review'),('GET','/fresh-review/'+'A'*64+'/zone-review'),('GET','/private-display/x/image'),('GET','/fresh-review/'+'a'*64+'/contact')):
  assert L.bridge_allowed(m,p,on) is False
 d1=L.display_session_for(b'k'*32,'sid1');d2=L.display_session_for(b'k'*32,'sid2')
 assert d1!=d2 and d1!='sid1' and 32<=len(d1)<=128 and d1==L.display_session_for(b'k'*32,'sid1') and d1!=L.display_session_for(b'j'*32,'sid1')
 import inspect;assert 'bridge_allowed' not in inspect.getsource(L.create_proxy)    # bridge_allowed is not used by any route (display_session_for is, by POST /audit)


def test_backend_receives_derived_display_value_never_the_cookie_value(tmp_path,monkeypatch):
 import local_ui_proxy as L
 seen=[]
 async def go():
  async def fake(request):
   seen.append(request.headers.get('x-vigilens-display-session'));return httpx.Response(409,json={'detail':'x'})
  backend=httpx.AsyncClient(transport=httpx.MockTransport(fake),base_url='http://backend')
  px=create_proxy(backend,TOKEN,launch_nonce=NONCE,display_secret=b's'*32)
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=px),base_url='http://localhost:8000') as c:
   await c.get('/launch')
   r=await c.post('/launch',json={'n':NONCE},headers={'Origin':'http://localhost:8000'});sid=r.cookies.get('vigilens_session')
   buf=io.BytesIO();Image.new('RGB',(8,8)).save(buf,'PNG')
   for k in('key-aaaaaaaa','key-bbbbbbbb'):
    await c.post('/audit',files={'image':('x.png',buf.getvalue(),'image/png')},data={'zones':'[]'},headers={'Origin':'http://localhost:8000','Sec-Fetch-Site':'same-origin','Idempotency-Key':k})
  return sid
 sid=asyncio.run(go())
 assert len(seen)==2 and seen[0]==seen[1]==L.display_session_for(b's'*32,sid) and seen[0]!=sid and 32<=len(seen[0])<=128
 with pytest.raises(ValueError):create_proxy(httpx.AsyncClient(),TOKEN,launch_nonce=NONCE,display_secret=b'short')
