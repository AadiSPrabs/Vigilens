"""Review claim 7 (fixed): disabled transport is rejected before frame work, not reported as a partial."""
import asyncio,pytest
from test_clip_preparation import clip,LIMITS
from test_fresh_upload_pipeline import setup
from test_clip_audit import clip_parser,approve_frames
from test_fresh_upload_routes import material
from fresh_review.clip_audit import audit_clip
from fresh_review.pipeline import disabled_transport

def test_clip_disabled_transport_should_raise_so_route_returns_503(clip,tmp_path,monkeypatch):
 from adapters import LiveTransportDisabled
 service,_,_,calls=setup(tmp_path,monkeypatch);clip_parser(monkeypatch);approve_frames(service,clip)
 service.transport=disabled_transport
 with pytest.raises(LiveTransportDisabled):asyncio.run(audit_clip(clip,[0,.8],LIMITS,service))

def test_clip_route_returns_503_no_review_registered_when_transport_disabled(material,clip,monkeypatch):
 import json
 from fresh_review.pipeline import disabled_transport
 p,raw,frame,calls,c,job=material;clip_parser(monkeypatch)
 p.trusted_clip_limits=LIMITS;approve_frames(p,clip);n=len(calls);p.transport=disabled_transport
 import fresh_review.clip_review as cr
 registered=[];orig=cr.ClipReviewStore.register
 monkeypatch.setattr(cr.ClipReviewStore,'register',lambda self,*a,**k:(registered.append(1),orig(self,*a,**k))[1])
 out=c.post('/fresh-review-clip-upload',files={'clip':('g.mp4',clip,'video/mp4')},data={'offsets':json.dumps([0,.8])})
 assert out.status_code==503 and not registered and len(calls)==n

def test_clip_enabled_transport_unchanged_and_real_attempt_failure_stays_partial(clip,tmp_path,monkeypatch):
 service,_,_,calls=setup(tmp_path,monkeypatch);clip_parser(monkeypatch);approve_frames(service,clip)
 live=service.transport;n=[0]
 def fails_after_dispatch_started(body):
  n[0]+=1
  if n[0]>=2:raise TimeoutError()
  return live(body)
 service.transport=fails_after_dispatch_started
 out=asyncio.run(audit_clip(clip,[0,.8],LIMITS,service))   # must NOT raise: a genuine attempt keeps partial semantics
 assert out['status']=='partial_requires_operator_reconciliation'
 assert out['frames'][0]['image_job']['state']=='running_uncertain'
 service.transport=live;before=len(calls)
 again=asyncio.run(audit_clip(clip,[0,.8],LIMITS,service))
 assert again['provider_calls_this_request']==0 and len(calls)==before   # uncertain attempt preserved, never retried
