import os
OUT=os.environ.get('REHEARSAL_OUT','.');os.makedirs(OUT,exist_ok=True)  # set REHEARSAL_UI_DIST to the built bundle (built with VITE_API_BASE_URL=http://localhost:8000)
"""OFFLINE compatibility rehearsal only. Synthetic blue 80x80 image, stub transport (no network, no provider). Backend :8001 behind the real gate,
proxy :8000. Not a runtime and not a demo mode: it exists to drive the real unchanged client against the real routes with synthetic data."""
import os,sys,threading,time,asyncio,tempfile,pathlib,secrets
sys.path[:0]=[str(pathlib.Path(__file__).parent.parent),str(pathlib.Path(__file__).parent.parent/'tests')]
TOKEN=secrets.token_urlsafe(40);os.environ['VIGILENS_LOCAL_ACCESS_TOKEN']=TOKEN
import httpx,uvicorn
from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient
from test_fresh_upload_pipeline import setup
from app import create_app
from local_ui_proxy import create_proxy
OWNER='fresh_rehearsal_owner_1234567890123456'
tmp=pathlib.Path(tempfile.mkdtemp());mp=MonkeyPatch()
p,raw,frame,calls=setup(tmp,mp,people=2)
seed=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER,'X-Vigilens-Local-Access':TOKEN})
GOV=os.environ.get('REHEARSAL_GOVERNED')=='1'   # governed: skip seeding, let the real governed handler run the SYNTHETIC stub transport for the approved image
r=None if GOV else seed.post('/fresh-review-upload',files={'image':('s.png',raw,'image/png')},data={'zones':'[]'});assert GOV or r.status_code==200,r.text
pathlib.Path(os.path.join(OUT,'synth-blue.png')).write_bytes(raw);n=len(calls)
import atexit;atexit.register(lambda:print('STUB_TRANSPORT_CALLS',len(calls),flush=True))
import PIL.Image as I;I.new('RGB',(80,80),(200,10,10)).save(os.path.join(OUT,'synth-unseen.png'))
def count_guard(body):raise AssertionError('transport must not be called after seeding')
p.transport=p.transport if GOV else count_guard
TRACE=[]
backend_app=create_app(fresh_service=p)
@backend_app.middleware('http')
async def trace(request,call_next):
    n0=len(calls);r=await call_next(request);TRACE.append('BACKEND %s %s -> %s (stub transport calls this request: %d)'%(request.method,request.url.path,r.status_code,len(calls)-n0));print(TRACE[-1],flush=True);return r
threading.Thread(target=lambda:uvicorn.run(backend_app,host='127.0.0.1',port=8001,log_level='warning'),daemon=True).start()
time.sleep(1.5)
NONCE='rehearsal-launch-nonce-'+'x'*30
uvicorn.run(create_proxy(httpx.AsyncClient(base_url='http://127.0.0.1:8001',timeout=30),TOKEN,launch_nonce=NONCE,ui_dir=os.environ['REHEARSAL_UI_DIST'],port=8000,governed_new_image=GOV),host='127.0.0.1',port=8000,log_level='warning')
