import io
from PIL import Image
from fresh_review.report_document import render_private_pdf

def report():
 return {'source':'private_report_preview_not_released','evidence_export_allowed':False,'source_digest':'a'*64,'assessment_id':'a','derivative_sha256':'b'*64,'privacy_review_status':'not_validated','person_display':{'0':{'text':'Person 1 (backend id 0)'}},'persons':[{'person_id':'0','provider_helmet_observation':'absent','provider_vest_observation':'absent','report_display_helmet':'unknown','report_display_vest':'unknown','status':'needs_human_review','evidence_review':{'display_finding_allowed':False},'vest_evidence_review':{'display_finding_allowed':False}}]}

def test_pdf_distinguishes_preserved_provider_from_review_display(monkeypatch):
 import fresh_review.report_document as module
 lines=[];original=module.ImageDraw.ImageDraw.text
 def record(self,xy,text,*args,**kw):
  lines.append(text);return original(self,xy,text,*args,**kw)
 monkeypatch.setattr(module.ImageDraw.ImageDraw,'text',record)
 b=io.BytesIO();Image.new('RGB',(80,80),'blue').save(b,'PNG')
 pages=render_private_pdf(report(),b.getvalue(),_pages_only=True)
 text=' '.join(lines)
 assert 'Report-display hardhat: unknown' in text
 assert 'Preserved provider readings' in text and 'hardhat absent' in text
 assert 'unknown here does not overwrite' in text and 'evidence insufficient or withheld' in text
 pages[0].save('/downloads/local-pdf-layer-proof.png')
 lines.clear();r=report();r['image_withheld']={'meaning':'withheld','election':{}}
 render_private_pdf(r,b.getvalue(),_pages_only=True)
 assert 'Preserved provider readings' not in ' '.join(lines)
