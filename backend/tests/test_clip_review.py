import json
from test_clip_preparation import clip,LIMITS
from test_clip_audit import clip_parser,approve_frames
from test_fresh_upload_routes import material,OWNER
from fresh_review.pipeline import digest

def reviewed_clip(material,clip,monkeypatch):
 p,raw,frame,calls,c,job=material;clip_parser(monkeypatch);frames=approve_frames(p,clip);p.trusted_clip_limits=LIMITS
 out=c.post('/fresh-review-clip-upload',files={'clip':('generated.mp4',clip,'video/mp4')},data={'offsets':'[0,0.8]'})
 assert out.status_code==200
 summary=out.json();frame=frames[0];source=frame['pixel_digest']
 region={'source_digest':source,'frame_size':[64,48],'regions':[{'person_id':'0','box':[1,1,5,5]}],'reviewer_label':'generated clip operator'}
 prepared=c.post('/fresh-review/'+source+'/private-display',files={'image':('sample.png',frame['png'],'image/png')},data={'review':json.dumps(region)})
 assert prepared.status_code==200;x=prepared.json()
 ack={k:x[k]for k in ('source_digest','output_sha256','regions_digest')};ack.update(frame_size=[64,48],foreground_checked=True,background_checked=True,reflections_checked=True,derivative_checked=True)
 assert c.post('/private-display/'+x['session_id']+'/review',json=ack).status_code==200
 result=p.read(source)['result'];review={'assessment_id':'fresh:'+source+':'+digest(result),'source_digest':source,'output_sha256':x['output_sha256'],'regions_digest':x['regions_digest'],'persons':{'0':{'exact_source_confirmed':True,'face_coverage_checked':True,'head_evidence_visible':True,'torso_evidence_visible':True}}}
 payload={'frames':[{'sample_index':i,'session_id':x['session_id'],'review':review}for i in (0,1)]}
 return p,c,calls,summary,payload,x

def test_reviewed_clip_combined_json_pdf_keeps_samples_no_tracking(material,clip,monkeypatch,tmp_path):
 p,c,calls,summary,payload,x=reviewed_clip(material,clip,monkeypatch)
 path='/fresh-private-clip-report/'+summary['private_clip_review_id']
 out=c.post(path,json=payload);assert out.status_code==200
 doc=out.json();assert doc['sample_count']==2 and [f['sample']['requested_offset_seconds']for f in doc['frames']]==[0,.8]
 assert doc['cross_frame_person_identity']=='not_inferred'and doc['sampled_frames_are_not_complete_clip_coverage']and not doc['evidence_export_allowed']
 pdf=c.post(path+'/pdf-preview',json=payload);assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-')and pdf.headers['x-vigilens-export-allowed']=='false'
 assert len(calls)==4 and c.post(path,json=payload).json()['provider_calls_this_request']==0
 assert c.post(path,json=payload,headers={'X-Vigilens-Display-Session':'other_browser_nonce_1234567890123456789'}).status_code==409
 assert c.post(path,json={'frames':payload['frames'][:1]}).status_code==409
 changed=json.loads(json.dumps(payload));changed['frames'][1]['sample_index']=0
 assert c.post(path,json=changed).status_code==409
 c.app.state.fresh_display.SESSIONS[x['session_id']].reviewed=False
 assert c.post(path,json=payload).status_code==409 and len(calls)==4

def test_distinct_sample_previews_coexist_and_changed_result_manifest_rejected(material,clip,monkeypatch):
 from test_fresh_upload_pipeline import add_approval
 from core import decode_image
 from fresh_review.clip_review import ClipReviewStore
 import io,asyncio,sqlite3
 from PIL import Image
 p,raw,frame,calls,c,job=material;clip_parser(monkeypatch)
 frames=[];reviews=[]
 for index,color in enumerate(('green','red')):
  buf=io.BytesIO();Image.new('RGB',(64,48),color).save(buf,'PNG');image=buf.getvalue();f=decode_image(image,'image/png')
  add_approval(p,f.digest,{'size':[64,48],'rights_reference':'generated-frame','provider_upload_approved':True})
  j=asyncio.run(p.run(image,'image/png',[]))
  frames.append({'sample_index':index,'requested_offset_seconds':index*.8,'timestamp_basis':'requested_decode_offset_not_exact_presentation_timestamp','pixel_digest':f.digest,'width':64,'height':48,'image_job':j})
  r={'source_digest':f.digest,'frame_size':[64,48],'regions':[{'person_id':'0','box':[1,1,5,5]}],'reviewer_label':'generated operator'}
  x=c.post('/fresh-review/'+f.digest+'/private-display',files={'image':('frame.png',image,'image/png')},data={'review':json.dumps(r)}).json()
  ack={k:x[k]for k in ('source_digest','output_sha256','regions_digest')};ack.update(frame_size=[64,48],foreground_checked=True,background_checked=True,reflections_checked=True,derivative_checked=True)
  assert c.post('/private-display/'+x['session_id']+'/review',json=ack).status_code==200
  review={'assessment_id':'fresh:'+f.digest+':'+digest(j['result']),'source_digest':f.digest,'output_sha256':x['output_sha256'],'regions_digest':x['regions_digest'],'persons':{'0':{'exact_source_confirmed':True,'face_coverage_checked':True,'head_evidence_visible':True,'torso_evidence_visible':True}}}
  reviews.append({'sample_index':index,'session_id':x['session_id'],'review':review})
 manifest={'source_clip_sha256':'a'*64,'duration_seconds':2,'status':'sampled_image_jobs_completed_not_clip_safety_clearance','frames':frames}
 identity=ClipReviewStore(p).register(manifest,OWNER)
 path='/fresh-private-clip-report/'+identity
 out=c.post(path,json={'frames':reviews});assert out.status_code==200 and len(calls)==6
 assert c.post(path+'/pdf-preview',json={'frames':reviews}).status_code==200
 db=p.connect();db.execute("UPDATE jobs SET result_sha='changed' WHERE source=?",(frames[1]['pixel_digest'],));db.commit();db.close()
 assert c.post(path,json={'frames':reviews}).status_code==409 and len(calls)==6


def test_clip_report_routes_require_local_access_token(material):
 # Regression: the clip report routes were outside the private gate prefixes.
 p,raw,frame,calls,c,job=material
 for path in ['/fresh-private-clip-report/x','/fresh-private-clip-report/x/pdf-preview','/fresh-private-clip-report/x/private-download']:
  assert c.post(path,json={'frames':[]},headers={'X-Vigilens-Local-Access':''}).status_code==403
  assert c.post(path,json={'frames':[]},headers={'X-Vigilens-Local-Access':'wrong'}).status_code==403
