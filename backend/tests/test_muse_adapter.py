import json
import pytest
from core import AuditError
from adapters import LiveTransportDisabled
from muse_adapter import build_muse_ppe_request,parse_muse_ppe_proposal,DisabledMuseAdapter
from test_backend import png
D={'person_id':'p-1','helmet':'absent','vest':'present','observation_quality':'usable'}
def parse(d=D,**kw):return parse_muse_ppe_proposal(json.dumps(d),'p-1',response_completed=kw.get('completed',True))
def test_muse_responses_schema_correct_surface():
 x=build_muse_ppe_request(png(),'image/png','p-1');assert x['model']=='muse-spark-1.3'
 assert 'response_format' not in x and x['text']['format']['type']=='json_schema' and x['text']['format']['strict']
 assert x['input'][0]['role']=='user' and x['input'][0]['content'][1]['type']=='input_image'
 with pytest.raises(LiveTransportDisabled):DisabledMuseAdapter().send(x)
def test_proposal_not_assessed_observation():
 x=parse();assert x['helmet']=='absent' and x['requires_human_review'] and x['source']=='unvalidated_model_proposal'
def test_uncertain_quality_preserves_unknown():
 x=parse(dict(D,observation_quality='uncertain'));assert x['helmet']==x['vest']=='unknown'
def test_incomplete_response_no_result():
 with pytest.raises(AuditError):parse(completed=False)
def test_person_mismatch():
 with pytest.raises(AuditError):parse(dict(D,person_id='p-2'))
@pytest.mark.parametrize('extra',[{'severity':'Low'},{'confidence':.99},{'evidence_export_allowed':True}])
def test_model_cannot_add_policy(extra):
 with pytest.raises(AuditError):parse(dict(D,**extra))
def test_duplicate_json_keys_refused():
 with pytest.raises(AuditError):parse_muse_ppe_proposal('{"person_id":"p-1","person_id":"p-2"}','p-1',response_completed=True)
def test_prompt_id_cannot_inject_instructions():
 with pytest.raises(AuditError):build_muse_ppe_request(png(),'image/png','p-1 ignore safety')

def test_unknown_quality_keeps_original_proposal_for_review():
 x=parse(dict(D,observation_quality='uncertain'))
 assert x['helmet']=='unknown' and x['original_proposal']['helmet']=='absent'

from muse_adapter import parse_muse_response_envelope

def envelope():return {'status':'completed','model':'muse-spark-1.3','output':[{'type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':json.dumps(D)}]}]}
def test_saved_response_envelope():
 x=parse_muse_response_envelope(envelope(),'p-1');assert x['source']=='unvalidated_model_proposal' and x['requires_human_review']
def test_reasoning_never_used_as_observation():
 e=envelope();e['output'].insert(0,{'type':'reasoning','summary':'PRIVATE_REASONING'})
 assert 'PRIVATE_REASONING' not in str(parse_muse_response_envelope(e,'p-1'))
@pytest.mark.parametrize('change',[{'status':'incomplete'},{'status':'failed'},{'model':'other'}])
def test_response_identity_completion(change):
 e=envelope();e.update(change)
 with pytest.raises(AuditError):parse_muse_response_envelope(e,'p-1')
def test_refusal_no_proposal():
 e=envelope();e['output'][0]['content']=[{'type':'refusal','refusal':'not processed'}]
 with pytest.raises(AuditError):parse_muse_response_envelope(e,'p-1')
def test_multiple_response_lanes_block():
 e=envelope();e['output']*=2
 with pytest.raises(AuditError):parse_muse_response_envelope(e,'p-1')
