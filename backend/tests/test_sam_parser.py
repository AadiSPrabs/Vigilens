import asyncio
import pytest
from core import AuditError
from pipeline import Frame
from sam_parser import parse_sam_image_text
# Complete official documentation example, not model execution or a labelled person.
TEXT="<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|><|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
F=Frame(320,334,'official-doc-saved-example')
def parse(t=TEXT,f=F):return asyncio.run(parse_sam_image_text(t,f,wire_completed=True))
def test_official_parser_complete_example():
 x=parse();o=x['objects'][0]
 assert o['box_half_open']==(211,228,271,255) and o['mask'].size==(60,27)
 assert o['confidence'] is None and not x['evidence_export_allowed']
def test_empty_parse_is_not_privacy_clearance():
 x=parse('');assert x['detection_status']=='none_detected' and x['privacy_review_status']=='not_validated'
def test_parser_source_dimension_mismatch():
 with pytest.raises(AuditError):parse(f=Frame(334,320,'wrong'))
def test_parser_truncated_mask_no_partial_output():
 with pytest.raises(AuditError):parse(TEXT[:-8])
def test_parser_quota_before_decode():
 with pytest.raises(AuditError):parse(TEXT.replace('27,60,','999999,999999,'))
def test_parser_diagnostics_hold_even_completed():
 with pytest.raises(AuditError):parse(TEXT.replace('x1=211','x1=211;surprise=1'))
def test_parser_multiple_frames_rejected():
 with pytest.raises(AuditError):parse(TEXT+'\n'+TEXT.replace('<0f>','<1f>'))
def test_parser_unexpected_raw_text_rejected():
 with pytest.raises(AuditError):parse('arbitrary prose')

def test_incomplete_source_not_relabelled_complete():
 with pytest.raises(AuditError):asyncio.run(parse_sam_image_text(TEXT,F,wire_completed=False))
