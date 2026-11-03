import json
from test_fresh_upload_routes import material, prepare, acknowledge, report, OWNER  # noqa: F401
from fresh_review.pipeline import FreshPipeline
from fresh_review.api import _visitor_owner

H={'X-Vigilens-Display-Session':OWNER}
OTHER='cd'*32

def review(frame):
 return {'source_digest':frame.digest,'frame_size':[80,80],'regions':[{'person_id':'0','box':[1,1,5,5]}],'reviewer_label':'synthetic review','redaction_method':'opaque'}

def reopen(c,frame,owner=OWNER,source=None):
 return c.post('/fresh-review/'+(source or frame.digest)+'/private-display/reopen',data={'review':json.dumps(review(frame))},headers={'X-Vigilens-Display-Session':owner})

def test_reopen_matches_upload_needs_fresh_ack_and_no_provider_call(material):
 p,raw,frame,calls,c,job=material;before=len(calls)
 up=prepare(c,raw,frame)
 r=reopen(c,frame);assert r.status_code==200;x=r.json()
 assert x['output_sha256']==up['output_sha256'] and x['regions_digest']==up['regions_digest']
 assert report(c,x,job).status_code==409          # reopen alone never acknowledges
 acknowledge(c,x);assert report(c,x,job).status_code==200
 contact={'person_id':'0','point':[.1,.5],'exact_source_confirmed':True,'boots_ground_visible':True,'reviewer_label':'synthetic operator'}
 assert c.post('/fresh-review/'+frame.digest+'/contact',json=contact).status_code==200
 assert len(calls)==before

def test_reopen_other_account_and_wrong_source_refused(material):
 p,raw,frame,calls,c,job=material
 assert reopen(c,frame,owner=OTHER).status_code==409
 assert reopen(c,frame,source='0'*64).status_code==409
 assert reopen(c,frame,source='zz').status_code in (409,422)
 assert reopen(c,frame,owner='').status_code==403
 assert not c.app.state.fresh_display.SESSIONS

def test_reopen_refused_when_preserved_source_missing_or_changed(material):
 p,raw,frame,calls,c,job=material
 f=p.path.parent/FreshPipeline._art(_visitor_owner(OWNER),frame.digest,'source.png')
 assert f.is_file();data=f.read_bytes()
 f.write_bytes(data[:-1]+bytes([data[-1]^1]))
 assert reopen(c,frame).status_code==409
 f.unlink();assert reopen(c,frame).status_code==409
 assert not c.app.state.fresh_display.SESSIONS

def test_reopen_does_not_carry_old_ack_or_add_listing(material):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x)
 y=reopen(c,frame).json()
 assert report(c,y,job).status_code==409
 for path in ('/fresh-review','/fresh-review/'+frame.digest+'/private-display/reopen'):
  assert c.get(path,headers=H).status_code in (404,405)
