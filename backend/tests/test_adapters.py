import pytest
from adapters import build_sam_image_request,DisabledSamAdapter,LiveTransportDisabled,SamStreamBoundary
from core import AuditError
from explanations import explanation_for,verify_claims
from test_backend import png,person,Z
from rules import assess

def test_documented_request_offline_only():
 x=build_sam_image_request(png(),'image/png','person')
 assert x['model']=='sam-3.1' and x['stream'] is True
 assert x['input'][0]['content'][1]['image_url'].startswith('data:image/png;base64,')
 with pytest.raises(LiveTransportDisabled):DisabledSamAdapter().send(x)
def test_multiple_concepts_rejected():
 with pytest.raises(AuditError):build_sam_image_request(png(),'image/png','person,helmet')
def test_empty_completed_not_clearance():
 s=SamStreamBoundary();s.feed({'type':'response.completed'});x=s.finish()
 assert x['detection_status']=='none_detected' and not x['geometry_available'] and not x['evidence_export_allowed']
def test_incomplete_never_partial_geometry():
 s=SamStreamBoundary();s.feed({'type':'response.output_text.delta','delta':'<0f>truncated'})
 with pytest.raises(AuditError):s.finish()
def test_raw_text_requires_official_parser():
 s=SamStreamBoundary();s.feed({'type':'response.output_text.delta','delta':'<0f>MOCK_NOT_REAL_MASK'});s.feed({'type':'response.completed'})
 assert s.finish()['detection_status']=='requires_official_parser' and not s.finish()['geometry_available']
@pytest.mark.parametrize('kind',['error','response.failed','response.incomplete'])
def test_stream_failed(kind):
 s=SamStreamBoundary()
 with pytest.raises(AuditError):s.feed({'type':kind,'error':'private contents'})
 with pytest.raises(AuditError):s.finish()
def test_stream_limits():
 s=SamStreamBoundary(max_text_bytes=2)
 with pytest.raises(AuditError):s.feed({'type':'response.output_text.delta','delta':'abc'})
def test_terminal_event_blocks_late_delta():
 s=SamStreamBoundary();s.feed({'type':'response.completed'})
 with pytest.raises(AuditError):s.feed({'type':'response.output_text.delta','delta':'late'})
def claims(p):
 x=explanation_for(p);return {k:([{a:f[a] for a in ('finding_id','rule_id','severity')} for f in x[k]] if k=='findings' else x[k]) for k in ('person_id','assessment_status','worst_severity','findings')}
def test_explanation_deterministic():
 p=assess(person(helmet='absent'),Z);assert verify_claims(p,claims(p))['source']=='deterministic_draft_rules'
def test_favourable_explanation_contradiction_rejects():
 p=assess(person(helmet='absent'),Z);c=claims(p);c['worst_severity']=None
 with pytest.raises(AuditError):verify_claims(p,c)
def test_missing_finding_rejects():
 p=assess(person(helmet='absent'),Z);c=claims(p);c['findings']=[]
 with pytest.raises(AuditError):verify_claims(p,c)
def test_arbitrary_prose_not_approved_by_schema():
 p=assess(person(helmet='absent'),Z);c=claims(p);c['text']='safe'
 with pytest.raises(AuditError):verify_claims(p,c)
