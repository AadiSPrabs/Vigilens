"""Clip request-key context with generated MP4 and fake opener. Zero provider traffic."""
import json
import pytest
from fastapi.testclient import TestClient
from app import create_app
from test_clip_preparation import clip,LIMITS
from test_clip_audit import clip_parser
from test_byok_visitor_key import _byok_pipeline,FakeOpener,_job_count
from test_fresh_upload_routes import OWNER
from fresh_review.transport import CURRENT_VISITOR_KEY
KEY='synthetic-clip-key-not-real'

@pytest.mark.parametrize('key,on', [('',True),('bad key',True),(KEY,False)])
def test_clip_key_or_switch_refused_before_decoder_and_journal(tmp_path,monkeypatch,clip,key,on):
 op=FakeOpener();p=_byok_pipeline(tmp_path,monkeypatch,op);p.trusted_clip_limits=LIMITS
 monkeypatch.setenv('VIGILENS_LIVE_DISPATCH','on' if on else 'off')
 def refused(*a,**k):pytest.fail('Decoder must not run before request gate')
 monkeypatch.setattr('fresh_review.clips.extract_clip_frames',refused)
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 out=c.post('/fresh-review-clip-upload',files={'clip':('generated.mp4',clip,'video/mp4')},data={'offsets':'[0,0.8]'},headers={'X-Vigilens-Visitor-Key':key})
 assert out.status_code==503,out.text
 assert not op.requests and _job_count(p.path)==0 and CURRENT_VISITOR_KEY.get() is None

def test_clip_http_key_context_dispatches_fake_opener_and_resets(tmp_path,monkeypatch,clip):
 class Opener(FakeOpener):
  def open(self,request,timeout=None):
   assert CURRENT_VISITOR_KEY.get()==KEY
   assert request.get_header('Authorization')=='Bearer '+KEY
   return super().open(request,timeout)
 op=Opener();p=_byok_pipeline(tmp_path,monkeypatch,op);p.trusted_clip_limits=LIMITS
 clip_parser(monkeypatch);monkeypatch.setenv('VIGILENS_LIVE_DISPATCH','on')
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 def post():return c.post('/fresh-review-clip-upload',files={'clip':('generated.mp4',clip,'video/mp4')},data={'offsets':'[0,0.8]'},headers={'X-Vigilens-Visitor-Key':KEY})
 out=post();assert out.status_code==200,out.text
 assert out.json()['completed_sample_count']==2 and out.json()['provider_calls_this_request']==2 and len(op.requests)==2
 assert CURRENT_VISITOR_KEY.get() is None
 assert post().json()['provider_calls_this_request']==0 and len(op.requests)==2
 assert CURRENT_VISITOR_KEY.get() is None

def test_clip_key_context_resets_after_decoder_refusal(tmp_path,monkeypatch):
 op=FakeOpener();p=_byok_pipeline(tmp_path,monkeypatch,op);p.trusted_clip_limits=LIMITS
 monkeypatch.setenv('VIGILENS_LIVE_DISPATCH','on')
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 out=c.post('/fresh-review-clip-upload',files={'clip':('bad.mp4',b'not an mp4','video/mp4')},data={'offsets':'[0]'},headers={'X-Vigilens-Visitor-Key':KEY})
 assert out.status_code==409 and not op.requests and CURRENT_VISITOR_KEY.get() is None
