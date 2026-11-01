import io
import pytest
from test_fresh_upload_routes import material,prepare,acknowledge,report
from test_rule_report_integration import rules
from test_fresh_zones import submit,contact
from fresh_review.report_document import render_private_pdf
from PIL import Image

def payload(x,job):
 from fresh_review.pipeline import digest
 return {'assessment_id':'fresh:'+x['source_digest']+':'+digest(job['result']),'source_digest':x['source_digest'],'output_sha256':x['output_sha256'],'regions_digest':x['regions_digest'],'persons':{'0':{'exact_source_confirmed':True,'face_coverage_checked':True,'head_evidence_visible':True,'torso_evidence_visible':True}}}
def test_private_pdf_route_binding_ack_and_no_provider_calls(material):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame)
 path='/fresh-private-report/'+x['session_id']+'/pdf-preview';body=payload(x,job)
 assert c.post(path,json=body).status_code==409
 acknowledge(c,x);submit(c,frame,job);contact(c,frame);rules(c,frame,job)
 out=c.post(path,json=body)
 assert out.status_code==200 and out.content.startswith(b'%PDF-')
 assert out.headers['content-type']=='application/pdf'and out.headers['cache-control']=='no-store'
 assert out.headers['x-vigilens-export-allowed']=='false'
 assert len(out.headers['x-vigilens-pdf-sha256'])==64
 assert c.post(path,json={**body,'source_digest':'0'*64}).status_code==409
 c.app.state.fresh_display.SESSIONS.clear()
 assert c.post(path,json=body).status_code==404
 assert len(calls)==2

def test_pdf_refuses_released_or_missing_report():
 b=io.BytesIO();Image.new('RGB',(2,2)).save(b,'PNG')
 for value in ({},{'source':'private_report_preview_not_released','evidence_export_allowed':True}):
  with pytest.raises(ValueError):render_private_pdf(value,b.getvalue())
