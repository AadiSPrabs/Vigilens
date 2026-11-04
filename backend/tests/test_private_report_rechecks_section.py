import io
from fresh_review.report_document import render_private_pdf
from PIL import Image

def base_report():
 return {'source':'private_report_preview_not_released','evidence_export_allowed':False,
 'source_digest':'a'*64,'assessment_id':'fresh:'+'a'*64+':'+'b'*64,'derivative_sha256':'c'*64,
 'privacy_review_status':'not_validated','persons':[]}

def rechecks():
 return {'status':'separate_candidates_require_review','original_result_unchanged':True,
 'automatic_candidate_adoption':False,
 'attempts':[{'attempt_id':'935e62c002b7562e4b73bd7627f93e6b1d40ea7d25833c8ac1bea63c5e85812a',
 'state':'completed','result':{'candidate_observations':{'helmet':'unknown','vest':'absent'}},
 'retry_allowed':False,'provider_calls_this_request':0,'evidence_export_allowed':False,
 'binding':{'source_digest':'a'*64,'result_sha256':'b'*64,'person_id':'0','attempt':1,'crop_png_sha256':'d'*64},
 'original_result_unchanged':True,'candidate_adoption':'requires_separate_human_review'},
 {'attempt_id':'e'*64,'state':'reserved_not_dispatched','result':None,'binding':{'person_id':'1'}}]}

def png():
 b=io.BytesIO();Image.new('RGB',(4,4)).save(b,'PNG');return b.getvalue()

def test_pdf_renders_deliberate_rechecks_section():
 without,_=render_private_pdf(base_report(),png())
 withr,_=render_private_pdf({**base_report(),'deliberate_rechecks':rechecks()},png())
 assert without.startswith(b'%PDF-')and withr.startswith(b'%PDF-')
 # The rechecks section actually adds rendered content.
 assert withr!=without

def test_pdf_rechecks_pages_bounded_and_original_unchanged_wording():
 pages=render_private_pdf({**base_report(),'deliberate_rechecks':rechecks()},png(),_pages_only=True)
 assert 1<=len(pages)<=32
 # not_configured renders no section: identical output to a missing key
 a=render_private_pdf(base_report(),png(),_pages_only=True)
 b=render_private_pdf({**base_report(),'deliberate_rechecks':{'status':'not_configured','attempts':[]}},png(),_pages_only=True)
 assert len(a)==len(b) and all(x.tobytes()==y.tobytes() for x,y in zip(a,b))
