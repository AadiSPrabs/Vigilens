from test_clip_preparation import clip
from test_fresh_upload_routes import material,prepare,acknowledge
from test_private_report_document import payload

def test_operator_private_download_disabled_by_default_and_same_guard_when_enabled(material):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame)
 route='/fresh-private-report/'+x['session_id']+'/private-download';body=payload(x,job)
 assert c.post(route,json=body).status_code==409
 # Synthetic server option is not actual user approval.
 p.operator_private_download_enabled=True
 assert c.post(route,json=body).status_code==409
 acknowledge(c,x);r=c.post(route,json=body)
 assert r.status_code==200 and r.content.startswith(b'%PDF-')
 assert r.headers['content-disposition'].startswith('attachment;')and r.headers['cache-control']=='no-store'
 assert r.headers['x-vigilens-export-allowed']=='false'and 'not-certified-safe-to-share'in r.headers['x-vigilens-use-restriction']
 changed={**body,'output_sha256':'0'*64};assert c.post(route,json=changed).status_code==409
 assert c.post(route,json=body,headers={'X-Vigilens-Display-Session':'other_browser_nonce_1234567890123456789'}).status_code==404
 assert len(calls)==2

def test_clip_private_download_keeps_per_sample_review_and_disabled_scope(material,clip,monkeypatch):
 from test_clip_review import reviewed_clip
 p,c,calls,summary,body,x=reviewed_clip(material,clip,monkeypatch)
 path='/fresh-private-clip-report/'+summary['private_clip_review_id']+'/private-download'
 assert c.post(path,json=body).status_code==409
 p.operator_private_download_enabled=True
 out=c.post(path,json=body);assert out.status_code==200 and out.headers['content-disposition'].startswith('attachment;')
 assert out.headers['x-vigilens-export-allowed']=='false'and len(calls)==4
 c.app.state.fresh_display.SESSIONS[x['session_id']].reviewed=False
 assert c.post(path,json=body).status_code==409 and len(calls)==4
