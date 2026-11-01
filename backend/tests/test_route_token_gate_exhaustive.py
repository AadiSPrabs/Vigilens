"""Every route the app mounts (enumerated from app.routes, not a hand-picked list) must refuse a missing or wrong
local access token before any handler runs. Allowed exceptions must be listed explicitly and are asserted."""
import pytest
from fastapi.testclient import TestClient
from app import create_app
from test_fresh_upload_routes import material
import re
TOKEN='synthetic-local-test-token-12345678901234567890'
EXEMPT={('GET','/health'),('POST','/audit')}   # install.OPEN_PATHS: health probe and fixture skeleton only; asserted below

def routes(app):
 # OpenAPI enumerates every mounted route incl. include_router ones (app.routes is lazy in this FastAPI).
 return sorted((m.upper(),path) for path,ops in app.openapi()['paths'].items() for m in ops if m.upper() not in('HEAD','OPTIONS'))

def concrete(path):return re.sub(r'\{[^}]+\}','x'*8,path)

@pytest.mark.parametrize('mode',['empty','wrong'])
def test_every_mounted_route_requires_local_access_token(material,mode):
 p,raw,frame,calls,c,job=material
 app=create_app(fresh_service=p);client=TestClient(app,raise_server_exceptions=False)
 rs=routes(app);assert len(rs)>25,rs
 bad=[]
 for m,path in rs:
  if (m,path) in EXEMPT:continue
  r=client.request(m,concrete(path),headers={'X-Vigilens-Local-Access':'' if mode=='empty' else 'wrong-token'})
  if r.status_code!=403:bad.append((m,path,r.status_code))
 assert not bad,bad
 assert len(calls)==2   # nothing dispatched beyond the original fixture upload

def test_gate_is_not_a_blanket_deny_valid_token_reaches_handler(material):
 p,raw,frame,calls,c,job=material
 app=create_app(fresh_service=p);client=TestClient(app,raise_server_exceptions=False)
 codes={client.request(m,concrete(path),headers={'X-Vigilens-Local-Access':TOKEN}).status_code for m,path in routes(app)}
 assert codes-{403}

def test_no_mounted_route_is_hidden_from_openapi_enumeration(material):
 p,raw,frame,calls,c,job=material
 from fresh_review.api import create_router
 app=create_app(fresh_service=p);seen={path for _,path in routes(app)}
 hidden=[r.path for r in create_router(p,app.state.fresh_display).routes+app.state.fresh_display.router.routes if r.path not in seen]
 assert not hidden,hidden

def test_exempt_routes_are_exactly_the_documented_open_paths():
 from fresh_review.install import OPEN_PATHS
 assert {path for _,path in EXEMPT}==set(OPEN_PATHS)
