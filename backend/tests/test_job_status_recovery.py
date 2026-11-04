"""Read-only recovery, no claims/approval mint/provider and no raw source leak."""
from test_fresh_upload_routes import material

def test_completed_status_readonly_sanitized_owner_only(material,monkeypatch):
 p,raw,frame,calls,c,job=material;n=len(calls)
 def refuse(*a,**k):raise AssertionError('Status must never prepare/run')
 monkeypatch.setattr(p,'prepare',refuse);monkeypatch.setattr(p,'run',refuse)
 def post(headers=None):return c.post('/fresh-review-job-status',files={'image':('x.png',raw,'image/png')},data={'zones':'[]'},headers=headers or {})
 r=post();assert r.status_code==200,r.text;d=r.json()
 assert d['status']=='completed' and d['provider_calls_this_request']==0 and not d['retry_allowed']
 assert d['audit']['image']['pixel_digest']==frame.digest and d['actual_debit']=='unchecked'
 assert not any(x in r.text for x in ('data:image','source.png','request_sha256','source_approval_snapshot'))
 assert post({'X-Vigilens-Display-Session':'cd'*32}).json()['status']=='not_found_or_not_visible'
 assert post({'X-Vigilens-Display-Session':''}).status_code==403
 assert len(calls)==n

def test_uncertain_status_no_partial_audit_or_retry(material):
 p,raw,frame,calls,c,job=material
 db=p.connect();db.execute("UPDATE jobs SET state='running_uncertain',result=NULL,result_sha=NULL");db.commit();db.close()
 r=c.post('/fresh-review-job-status',files={'image':('x.png',raw,'image/png')},data={'zones':'[]'})
 assert r.status_code==200,r.text
 assert r.json()['status']=='pending_or_uncertain' and 'audit' not in r.json() and not r.json()['retry_allowed']
 assert len(calls)==2
