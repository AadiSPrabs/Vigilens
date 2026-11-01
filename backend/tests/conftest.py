import pytest
from fastapi.testclient import TestClient
@pytest.fixture(autouse=True)
def private_test_token(monkeypatch):
 token='synthetic-local-test-token-12345678901234567890'
 monkeypatch.setenv('VIGILENS_LOCAL_ACCESS_TOKEN',token)
 original=TestClient.request
 def request(self,*a,**kw):
  kw['headers']=kw.get('headers')or {};kw['headers'].setdefault('X-Vigilens-Local-Access',token);return original(self,*a,**kw)
 monkeypatch.setattr(TestClient,'request',request)
