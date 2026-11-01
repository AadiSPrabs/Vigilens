import asyncio
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from access import LocalBearerGate
from schemas import LocalJob
from job_api import create_job_app
from run_local import build
from test_backend import manifest
from test_job_api import submit

TOKEN='synthetic-test-token-not-real-'+'0'*32

def test_response_schema_and_openapi(tmp_path):
 app=create_job_app(tmp_path/'j',manifest())
 with TestClient(app) as c:
  x=submit(c).json()['job'];assert LocalJob.model_validate(x).state=='completed'
  schema=c.get('/openapi.json').json();assert 'LocalJob' in schema['components']['schemas']
  assert schema['paths']['/local/jobs/{job_id}']['get']['responses']['200']['content']['application/json']['schema']['$ref'].endswith('JobResponse')
@pytest.mark.parametrize('change',[{'result_available':False},{'result_expired':True},{'retryable_with_same_key':True},{'state':'needs_review'},{'cancellation_kind':'before_local_execution'}])
def test_response_invariants_fail_closed(tmp_path,change):
 with TestClient(create_job_app(tmp_path/'j',manifest())) as c:x=submit(c).json()['job']
 with pytest.raises(ValidationError):LocalJob.model_validate(dict(x,**change))

def test_bearer_gate_before_body_read():
 async def scenario():
  calls=[];output=[]
  async def app(s,r,w):calls.append(1)
  async def receive():raise AssertionError('Unauthorized body must not be consumed')
  async def send(m):output.append(m)
  gate=LocalBearerGate(app,TOKEN)
  await gate({'type':'http','headers':[]},receive,send)
  assert output[0]['status']==401 and not calls
  await gate({'type':'http','headers':[(b'authorization',b'Bearer '+TOKEN.encode())]},receive,send)
  assert calls==[1]
 asyncio.run(scenario())

def test_duplicate_auth_header_denied():
 async def scenario():
  output=[]
  async def app(s,r,w):raise AssertionError()
  async def recv():raise AssertionError()
  async def send(m):output.append(m)
  auth=(b'authorization',b'Bearer '+TOKEN.encode())
  await LocalBearerGate(app,TOKEN)({'type':'http','headers':[auth,auth]},recv,send)
  assert output[0]['status']==401
 asyncio.run(scenario())

def test_optional_gate_local_server(tmp_path):
 with TestClient(build(str(tmp_path/'j'),local_token=TOKEN)) as c:
  assert c.get('/health').status_code==401
  assert c.get('/health',headers={'Authorization':'Bearer '+TOKEN}).status_code==200
  assert c.get('/health',headers={'Authorization':'Bearer wrong'}).status_code==401

def test_small_token_refused():
 with pytest.raises(ValueError):LocalBearerGate(None,'short')
