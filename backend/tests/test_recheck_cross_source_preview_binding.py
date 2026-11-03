"""Cross-source preview-binding regression for the recheck execute gate.
One visitor account uploads TWO different images (sources A and B) and completes
the private-display ceremony (prepare + exact acknowledgment) for source A only.
Invariant: the acknowledged preview bound to A must NOT satisfy the
current_preview gate for source B - executing B's reserved recheck attempt is
refused 409, while A's own attempt proceeds. This is the backend anchor for the
UI rule that an acknowledgment on one audit can never enable rechecks on another.
Synthetic transport only; no spend beyond the synthetic reservation, no adoption."""
import io,json
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app import create_app
from core import decode_image
from test_fresh_upload_pipeline import setup,add_approval
from test_fresh_upload_routes import OWNER
from test_recheck_execution import executor
def _frame_b():
 im=Image.new('RGB',(80,80),'blue');im.putpixel((0,0),(255,255,255))
 out=io.BytesIO();im.save(out,'PNG');raw=out.getvalue()
 return raw,decode_image(raw,'image/png')
def _ceremony(c,raw,frame):
 review={'source_digest':frame.digest,'frame_size':[80,80],'regions':[{'person_id':'0','box':[1,1,5,5]}],'reviewer_label':'synthetic review','redaction_method':'opaque'}
 r=c.post('/fresh-review/'+frame.digest+'/private-display',files={'image':('x.png',raw,'image/png')},data={'review':json.dumps(review)})
 assert r.status_code==200
 x=r.json()
 ack={**{k:x[k]for k in ['source_digest','output_sha256','regions_digest']},'frame_size':[80,80],**{k:True for k in ['foreground_checked','background_checked','reflections_checked','derivative_checked']}}
 assert c.post('/private-display/'+x['session_id']+'/review',json=ack).status_code==200
 return x
def test_acknowledged_preview_on_A_does_not_enable_recheck_on_B(tmp_path,monkeypatch):
 p,raw_a,frame_a,calls=setup(tmp_path,monkeypatch)
 raw_b,frame_b=_frame_b()
 add_approval(p,frame_b.digest,{'size':[80,80],'rights_reference':'synthetic-generated-test-only','provider_upload_approved':True})
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 out=c.post('/fresh-review-upload',files={'image':('a.png',raw_a,'image/png')},data={'zones':'[]'})
 assert out.status_code==200 and out.json()['state']=='completed';job_a=out.json()
 out=c.post('/fresh-review-upload',files={'image':('b.png',raw_b,'image/png')},data={'zones':'[]'})
 assert out.status_code==200 and out.json()['state']=='completed';job_b=out.json()
 # NOTE: executor() writes the shared synthetic grant file, so the A executor is
 # created AFTER the B attempt (re-pinning the grant to A's plan) to keep the
 # control's approval pin valid.
 e_b,attempt_b=executor(p,frame_b,monkeypatch)
 _ceremony(c,raw_a,frame_a)  # acknowledged preview bound to source A only
 # A acknowledged, B attempted: the preview gate must refuse before any executor run.
 p.recheck_executor=e_b
 r=c.post('/fresh-review/'+frame_b.digest+'/recheck/'+attempt_b['attempt_id'],json={'source_digest':frame_b.digest,'result_sha256':attempt_b['plan']['result_sha256']})
 assert r.status_code==409,r.text
 assert e_b.read(attempt_b['attempt_id'])['state']=='reserved_not_dispatched'
 # Control: A acknowledged, A attempted: the gate passes and the executor runs.
 e_a,attempt_a=executor(p,frame_a,monkeypatch)
 p.recheck_executor=e_a
 r=c.post('/fresh-review/'+frame_a.digest+'/recheck/'+attempt_a['attempt_id'],json={'source_digest':frame_a.digest,'result_sha256':attempt_a['plan']['result_sha256']})
 assert r.status_code==200,r.text
 assert r.json()['state']=='completed'
 assert r.json()['result']['original_overwrite_allowed'] is False
