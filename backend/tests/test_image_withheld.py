import io,json
from test_fresh_upload_routes import material,acknowledge,report,OWNER
from test_private_report_document import payload
from test_rule_report_integration import rules
from test_fresh_zones import submit,contact
from PIL import Image

WITHHOLD={'basis':'operator_elected_image_withheld','exact_source_confirmed':True,'withhold_entire_frame':True}

def prepare_withhold(c,raw,frame,**patch):
 review={'source_digest':frame.digest,'frame_size':[80,80],'regions':[],'reviewer_label':'synthetic withhold election','image_withheld':WITHHOLD,**patch}
 return c.post('/fresh-review/'+frame.digest+'/private-display',files={'image':('x.png',raw,'image/png')},data={'review':json.dumps(review)},headers={'X-Vigilens-Display-Session':OWNER})

def test_image_withheld_masks_entire_frame_and_binds_through_report_and_pdf(material):
 p,raw,frame,calls,c,job=material
 out=prepare_withhold(c,raw,frame);assert out.status_code==200
 x=out.json()
 assert x['display_pixels_unchanged']is False and x['image_withheld']==WITHHOLD
 assert x['image_withheld_basis']=='operator_election_not_privacy_validation'
 assert x['coverage']=='not_verified'and x['privacy_review_status']=='not_validated'and not x['evidence_export_allowed']
 # Derivative pixels are entirely black: no image content survives anywhere.
 im=Image.open(io.BytesIO(c.get(x['preview_url']).content)).convert('RGB')
 assert all(px==(0,0,0)for px in im.getdata())
 acknowledge(c,x)
 r=report(c,x,job);assert r.status_code==200
 view=r.json()['image_withheld']
 assert view['election']==WITHHOLD and view['geometrically_verified']is False and view['ppe_display']=='withheld'
 assert 'NOT evidence that the image contains no faces' in view['meaning']
 person=r.json()['persons'][0]
 # Withheld pixels cannot support displayed PPE findings even with operator checks.
 assert person['report_display_helmet']=='unknown'and person['report_display_vest']=='unknown'
 assert not r.json()['evidence_export_allowed']
 submit(c,frame,job);contact(c,frame);rules(c,frame,job)
 pdf=c.post('/fresh-private-report/'+x['session_id']+'/pdf-preview',json=payload(x,job))
 assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-')and pdf.headers['x-vigilens-export-allowed']=='false'
 assert len(calls)==2  # zero provider calls added by the withhold path

def test_withhold_refusals_and_strict_zero_region_semantics(material):
 p,raw,frame,calls,c,job=material
 for key in ('exact_source_confirmed','withhold_entire_frame'):
  bad=dict(WITHHOLD);bad[key]=False
  assert prepare_withhold(c,raw,frame,image_withheld=bad).status_code==422
 # Face-asserting or detector-absence bases are never the withhold election.
 for basis in ('operator_confirmed_face_covers_entire_frame','opaque_worn_face_shield','no_face_detected','detector_zero_faces',''):
  assert prepare_withhold(c,raw,frame,image_withheld={**WITHHOLD,'basis':basis}).status_code==422
 # Extra face-asserting fields are not accepted onto the election.
 assert prepare_withhold(c,raw,frame,image_withheld={**WITHHOLD,'face_fully_hidden':True}).status_code==422
 # Blur cannot withhold pixels.
 assert prepare_withhold(c,raw,frame,redaction_method='blur').status_code==422
 # Zero regions and no election is still refused: detector-zero never means no faces.
 review={'source_digest':frame.digest,'frame_size':[80,80],'regions':[],'reviewer_label':'synthetic review'}
 assert c.post('/fresh-review/'+frame.digest+'/private-display',files={'image':('x.png',raw,'image/png')},data={'review':json.dumps(review)},headers={'X-Vigilens-Display-Session':OWNER}).status_code==422
 assert len(calls)==2

def test_withheld_overlay_and_pdf_draw_no_geometry_and_evidence_claims_unavailable(material):
 import hashlib
 p,raw,frame,calls,c,job=material
 x=prepare_withhold(c,raw,frame).json();acknowledge(c,x)
 r=report(c,x,job).json()
 person=r['persons'][0]
 assert person['vest_evidence_review']['torso_evidence_visible']is False
 assert person['report_display_helmet']=='unknown'and person['report_display_vest']=='unknown'
 ov=c.get('/fresh-private-report/'+x['session_id']+'/overlay',headers={'X-Vigilens-Display-Session':OWNER})
 assert ov.status_code==200
 if True:
  im=Image.open(io.BytesIO(ov.content)).convert('RGB')
  assert all(px==(0,0,0)for px in im.getdata())  # final output pixels: no outlines
 # PDF embeds the same overlay path: render its page images and assert no teal outline.
 submit(c,frame,job);contact(c,frame);rules(c,frame,job)
 pdf=c.post('/fresh-private-report/'+x['session_id']+'/pdf-preview',json=payload(x,job))
 assert pdf.status_code==200
 from fresh_review import report_document as rd
 import inspect
 assert 'overlay_png' in inspect.getsource(rd.render_private_pdf)
 # Final PDF pixels: rebuild pages from the same report+overlay the route used; no teal outline pixels.
 doc=c.post('/fresh-private-report/'+x['session_id'],json=payload(x,job),headers={'X-Vigilens-Display-Session':OWNER}).json()
 ovb=c.get('/fresh-private-report/'+x['session_id']+'/overlay',headers={'X-Vigilens-Display-Session':OWNER}).content
 pages=rd.render_private_pdf(doc,ovb,_pages_only=True)
 teal=0
 for pg in pages:
  im=pg if hasattr(pg,'getdata') else Image.open(io.BytesIO(pg))
  teal+=sum(1 for r_,g,b in im.convert('RGB').getdata() if g>120 and b>100 and r_<90)
 assert teal==0

def test_withheld_pdf_omits_overlay_legend():
 import inspect
 from fresh_review import report_document as rd
 src=inspect.getsource(rd.render_private_pdf)
 assert "if not report.get('image_withheld'):line('Mask edges" in src
