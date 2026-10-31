"""Deterministic explanations; optional external text never changes assessments.
Validate structured claims, not natural-language truth. Unstructured model prose
is deliberately not accepted as a released explanation.
"""
from core import fail

def explanation_for(person):
    return {'person_id':person['id'],'assessment_status':person['assessment_status'],
            'worst_severity':person['worst_severity'],
            'findings':[{'finding_id':f['id'],'rule_id':f['rule_id'],'severity':f['severity'],'text':f['message']} for f in person['findings']],
            'source':'deterministic_draft_rules','notice':'Draft rules, not a safety clearance.'}

def verify_claims(person,claim):
    if not isinstance(claim,dict) or set(claim)!={'person_id','assessment_status','worst_severity','findings'}:fail('INVALID_EXPLANATION','Use structured rule-linked claims only.',422)
    expected=explanation_for(person)
    if any(claim.get(k)!=expected[k] for k in ('person_id','assessment_status','worst_severity')):fail('EXPLANATION_CONTRADICTION','Explanation conflicts with deterministic assessment.',422)
    fs=claim['findings']
    if not isinstance(fs,list) or any(not isinstance(f,dict) or set(f)!={'finding_id','rule_id','severity'} for f in fs):fail('INVALID_EXPLANATION','Unsupported explanation claims.',422)
    target=[{k:f[k] for k in ('finding_id','rule_id','severity')} for f in expected['findings']]
    if sorted(fs,key=lambda f:str(f['finding_id']))!=sorted(target,key=lambda f:str(f['finding_id'])):fail('EXPLANATION_CONTRADICTION','Missing, duplicate or conflicting finding claims.',422)
    return expected
