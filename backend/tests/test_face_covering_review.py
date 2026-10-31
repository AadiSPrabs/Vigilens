import json,asyncio
from test_fresh_upload_routes import material,acknowledge,report
from fresh_review.pipeline import digest

def review(frame,**patch):
 return {'source_digest':frame.digest,'frame_size':[80,80],'regions':[],'reviewer_label':'synthetic operator claim only','face_coverings':[{'person_id':'0','basis':'opaque_worn_face_shield','face_fully_hidden':True,'no_visible_face_pixels':True,'exact_source_confirmed':True}],**patch}

def prepare_cover(c,raw,frame,r):
 return c.post('/fresh-review/'+frame.digest+'/private-display',files={'image':('original.png',raw,'image/png')},data={'review':json.dumps(r)})

def test_explicit_covered_face_preserves_pixels_and_original_unknown(material):
 p,raw,frame,calls,c,job=material
 out=prepare_cover(c,raw,frame,review(frame));assert out.status_code==200
 x=out.json();assert x['display_pixels_unchanged']and x['face_coverings'][0]['basis']=='opaque_worn_face_shield'
 assert x['privacy_review_status']=='not_validated'and not x['evidence_export_allowed']
 assert c.get(x['preview_url']).content==raw
 acknowledge(c,x)
 r=report(c,x,job);assert r.status_code==200
 assert r.json()['persons'][0]['report_display_helmet']=='unknown' # actual provider unknown stays unknown
 assert r.json()['face_covering_review']and not r.json()['evidence_export_allowed']
 assert asyncio.run(p.run(raw,'image/png',[]))['provider_calls_this_request']==0 and len(calls)==2
 again=c.post('/fresh-review-upload',files={'image':('original.png',raw,'image/png')},data={'zones':'[]'})
 assert again.status_code==200 and again.json()['provider_calls_this_request']==0 and len(calls)==2

def test_detector_miss_or_incomplete_or_unbound_claim_never_skips_treatment(material):
 p,raw,frame,calls,c,job=material
 for patch in ({'face_coverings':[]},{'face_coverings':[{'person_id':'0','basis':'no_face_detected','face_fully_hidden':True,'no_visible_face_pixels':True,'exact_source_confirmed':True}]},{'face_coverings':[{'person_id':'other','basis':'opaque_worn_face_shield','face_fully_hidden':True,'no_visible_face_pixels':True,'exact_source_confirmed':True}]}):
  assert prepare_cover(c,raw,frame,review(frame,**patch)).status_code in (409,422)
 for key in ('face_fully_hidden','no_visible_face_pixels','exact_source_confirmed'):
  for bad in (False,1):
   r=review(frame);r['face_coverings'][0][key]=bad
   assert prepare_cover(c,raw,frame,r).status_code==422
 assert len(calls)==2
