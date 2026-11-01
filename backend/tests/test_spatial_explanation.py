import json,hashlib,asyncio
import pytest
from test_fresh_upload_routes import material,prepare,acknowledge,report
from test_fresh_zones import submit,contact
from test_rule_report_integration import rules
from test_private_report_document import payload
from fresh_review.spatial_explanation import build_spatial_request,parse_spatial_reply
from fresh_review.explanation_execution import ExplanationExecutor
from fresh_review.pipeline import digest
from fresh_review.ppe import MAX_COST

def setup_explanation(p,raw,job,c,x):
 doc=report(c,x,job).json()
 plan=build_spatial_request(raw,job['result'],doc['zone_review'],doc['configured_rule_review'],[])
 grant={'format':'vigilens.exact-explanation-grant.v1','execution_scope':p.execution_scope,'plan_sha256':digest(plan),'maximum_reserved_usd':str(MAX_COST),'authority_reference':'synthetic-only'}
 path=p.path.parent/'synthetic-explanation-grant.json';encoded=json.dumps(grant).encode();path.write_bytes(encoded);path.chmod(0o600)
 e=ExplanationExecutor(p,approval_path=path,approval_sha256=hashlib.sha256(encoded).hexdigest())
 return e,plan,e.reserve(plan)
def response(plan):
 return json.dumps({'model':'muse-spark-1.3','id':'synthetic-explanation','status':'completed','usage':{'input_tokens':100,'output_tokens':100},'output':[{'type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':json.dumps({'explanations':[{'finding_key':r['finding_key'],'explanation':'Synthetic commentary: '+r['reason']}for r in plan['expected_evaluations']]})}]}]}).encode()

def test_spatial_explanation_http_deterministic_fields_unchanged_current_context(material):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x);submit(c,frame,job);contact(c,frame);rules(c,frame,job)
 e,plan,identity=setup_explanation(p,raw,job,c,x)
 def transport(body):calls.append(body);return response(plan)
 p.transport=transport
 route='/fresh-private-report/'+x['session_id']+'/explanation/'+identity
 assert c.post(route,json=payload(x,job)).status_code==409
 p.explanation_executor=e
 out=c.post(route,json=payload(x,job));assert out.status_code==200 and out.json()['state']=='completed'and len(calls)==3
 assert out.json()['result']['explanations'][0]['priority']is None
 assert c.post(route,json=payload(x,job)).json()['provider_calls_this_request']==0 and len(calls)==3
 doc=report(c,x,job).json()
 assert len(doc['spatial_explanations']['attempts'])==1 and doc['spatial_explanations']['deterministic_fields_unchanged']
 assert 'not supplied, not evidence' in doc['spatial_explanations']['input_basis_notice']
 assert doc['configured_rule_review']['persons'][0]['highest_configured_priority']is None
 assert 'data:image'not in json.dumps(doc)
 submit(c,frame,job,[])
 assert c.post(route,json=payload(x,job)).status_code==409 and len(calls)==3

def test_explanation_timeout_no_retry_and_tamper(material):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x);submit(c,frame,job);rules(c,frame,job)
 e,plan,identity=setup_explanation(p,raw,job,c,x)
 def timeout(body):calls.append(body);raise TimeoutError()
 p.transport=timeout
 out=e.run(identity,plan);assert out['state']=='attempted_uncertain'and out['provider_calls_this_request']is None
 assert e.run(identity,plan)['provider_calls_this_request']==0 and len(calls)==3

def test_explanation_refuses_extra_keys_missing_ids_overrides(material):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x);submit(c,frame,job);rules(c,frame,job)
 e,plan,identity=setup_explanation(p,raw,job,c,x)
 valid=json.loads(response(plan));content=valid['output'][0]['content'][0]
 doc=json.loads(content['text']);doc['explanations'][0]['priority']='Critical';content['text']=json.dumps(doc)
 with pytest.raises(ValueError):parse_spatial_reply(json.dumps(valid).encode(),plan)
 valid=json.loads(response(plan));valid['output'][0]['content'][0]['text']='{"explanations":[]}'
 with pytest.raises(ValueError):parse_spatial_reply(json.dumps(valid).encode(),plan)
 assert len(calls)==2

def test_explanation_response_tamper_blocks_later_original_budget_claim(material):
 from test_fresh_upload_pipeline import add_approval
 from core import decode_image
 from PIL import Image
 import io
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x);submit(c,frame,job);rules(c,frame,job)
 e,plan,identity=setup_explanation(p,raw,job,c,x)
 p.transport=lambda body:response(plan)
 assert e.run(identity,plan)['state']=='completed'
 e.artifact(identity,'reply.bin').write_bytes(b'changed')
 out=io.BytesIO();Image.new('RGB',(80,80),'green').save(out,'PNG');f=decode_image(out.getvalue(),'image/png')
 add_approval(p,f.digest,{'size':[80,80],'rights_reference':'synthetic','provider_upload_approved':True})
 _,_,_,binding=p.prepare(out.getvalue(),'image/png',[])
 with pytest.raises(ValueError):p.claim(binding)

def test_changed_visibility_invalidates_explanation_context(material,monkeypatch):
 # Downstream-mechanism test: treat the stored legacy person as clean-basis so this still exercises the display/rule path. Real legacy behavior (withheld) is covered in test_ppe_basis and test_fresh_upload_routes.
 monkeypatch.setattr('fresh_review.ppe_basis.basis_of',lambda person:'clean_crop')
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x);submit(c,frame,job);rules(c,frame,job)
 e,plan,identity=setup_explanation(p,raw,job,c,x);p.explanation_executor=e
 body=payload(x,job);body['persons']['0']['torso_evidence_visible']=False
 route='/fresh-private-report/'+x['session_id']+'/explanation/'+identity
 assert c.post(route,json=body).status_code==409 and len(calls)==2


def test_commentary_missing_mask_reference_flagged_not_laundered():
 from fresh_review.spatial_explanation import commentary_review
 text='No helmet segmentation means absent.'
 attempt={'result':{'explanations':[{'finding_key':'exact-key','model_commentary':text}]}}
 review=commentary_review(attempt,ppe_masks=[])
 assert review['accepted']is False and review['auxiliary_PPE_masks']=='not_supplied'
 assert review['flagged_finding_keys']==['exact-key']
 assert attempt['result']['explanations'][0]['model_commentary']==text
 assert commentary_review(attempt,ppe_masks=[{'state':'completed'}])['flagged_finding_keys']==[]
 assert commentary_review(attempt,ppe_masks=[{'state':'completed'}])['accepted']is False
