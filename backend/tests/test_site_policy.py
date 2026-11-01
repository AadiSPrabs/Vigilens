import copy,pytest
from fresh_review.policy import validate_policy,describe_policy,FORMAT

def policy():
 return {'format':FORMAT,'policy_id':'synthetic-demo','version':'test-1','scope':'illustrative_demo','camera_id':'synthetic-camera','approval_reference':'synthetic-no-owner-approval',
 'priorities':['review-priority'],'zones':[{'id':'work','name':'Generated work area','points':[{'x':.1,'y':.1},{'x':.9,'y':.1},{'x':.9,'y':.9},{'x':.1,'y':.9}],
 'access_mode':'authorised_only','rules':[{'id':'vest','check':'vest_worn','priority':None},{'id':'entry','check':'access','priority':'review-priority'}]}],'outside_rules':[]}

def test_policy_explicit_structure_not_approval():
 p=policy();out,sha=validate_policy(p)
 assert out==p and len(sha)==64
 desc=describe_policy(p);assert desc['runtime_application']=='not_enabled'and desc['regulatory_compliance_claim']is False
 assert desc['configuration_status']=='validated_structure_only_not_approval'
 assert not desc['evidence_export_allowed']
 for field in ('camera_id','version','scope'):
  other=copy.deepcopy(p);other[field]='other'if field!='scope'else'site_owner_policy'
  assert validate_policy(other)[1]!=sha
@pytest.mark.parametrize('mutation',[lambda p:p.update(scope='universal_safety'),lambda p:p.update(approved=True),lambda p:p.update(approval_reference=''),lambda p:p['zones'][0].update(access_mode='hazard_false'),lambda p:p['zones'][0]['rules'][0].update(priority='Critical'),lambda p:p['zones'][0]['rules'][0].update(check='goggles'),lambda p:p.update(outside_rules=[{'id':'outside','check':'access','priority':None}])])
def test_invalid_implicit_policy_rejected(mutation):
 p=policy();mutation(p)
 with pytest.raises(ValueError):validate_policy(p)

def test_no_entry_and_ppe_independent_and_no_hidden_defaults():
 p=policy();p['zones'][0]['access_mode']='no_entry_all';p['priorities']=[]
 for r in p['zones'][0]['rules']:r['priority']=None
 checked,_=validate_policy(p)
 assert checked['priorities']==[]and checked['outside_rules']==[]
 assert checked['zones'][0]['rules'][0]['check']=='vest_worn'

def evaluate(p,person=None,pos=None,permissions=None):
 from fresh_review.policy import evaluate_configured_rules
 _,sha=validate_policy(p)
 return evaluate_configured_rules(p,[person or{'id':'p','helmet':'present','vest':'absent'}],{'p':pos or{'work':'inside'}},camera_id=p['camera_id'],policy_sha256=sha,permissions=permissions)['persons'][0]

def test_explicit_policy_evaluation_keeps_uncertainty_and_unrated_findings():
 p=policy();x=evaluate(p)
 assert len(x['findings'])==2 and x['needs_review']is True and x['safe']is None
 assert x['findings'][0]['rating_status']=='not_configured_needs_review'
 assert x['findings'][1]['reason']=='permission_unresolved_not_inferred'
 p['zones'][0]['rules'][0]['priority']='review-priority'
 x=evaluate(p,permissions={'p':{'work':'authorised'}})
 assert len(x['findings'])==1 and x['highest_configured_priority']=='review-priority'and not x['needs_review']
 assert x['compliant']is None

def test_outside_is_not_automatic_safe_or_violation():
 p=policy();x=evaluate(p,pos={'work':'outside'})
 assert x['findings']==[]and x['safe']is None
 p['outside_rules']=[{'id':'site-vest','check':'vest_worn','priority':None}]
 assert evaluate(p,pos={'work':'outside'})['findings'][0]['rule_id']=='site-vest'
 assert evaluate(p,pos={'work':'boundary'})['needs_review']

def test_no_entry_all_independent_of_ppe_and_highest_does_not_hide_unknown():
 p=policy();p['zones'][0]['access_mode']='no_entry_all'
 x=evaluate(p,person={'id':'p','helmet':'present','vest':'unknown'},permissions={'p':{'work':'authorised'}})
 assert x['highest_configured_priority']=='review-priority'and x['needs_review']
 assert {f['status']for f in x['findings']}=={'observed_violation','needs_review'}

def test_policy_camera_and_hash_rejected():
 from fresh_review.policy import evaluate_configured_rules
 p=policy()
 with pytest.raises(ValueError):evaluate_configured_rules(p,[],{},camera_id='wrong',policy_sha256='0'*64)


def test_no_applicable_rules_not_reported_as_evaluated_clearance():
 p=policy();x=evaluate(p,pos={'work':'outside'})
 assert x['summary']=='no_applicable_rules_evaluated'and x['safe']is None
 from fresh_review.policy import evaluate_configured_rules
 _,sha=validate_policy(p)
 person={'id':'same','helmet':'present','vest':'present'}
 with pytest.raises(ValueError):evaluate_configured_rules(p,[person,person],{},camera_id=p['camera_id'],policy_sha256=sha)
