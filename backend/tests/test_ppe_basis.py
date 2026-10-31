import pytest
from fresh_review.ppe_basis import basis_of,item_state,effective_value,counts
from fresh_review.reports import build_private_report
from fresh_review.policy import evaluate_configured_rules
from test_site_policy import policy
D='a'*64
def person(i,h,v,basis=None,elig=True,assessed=True):
    p={'id':i,'helmet':h,'vest':v,'ppe_assessed':assessed,'provider_observation':{'observation':{}}if assessed else None,'crop_eligibility':{'eligible_for_selected_crop_call':elig}}
    if basis:p['crop_basis']=basis
    return p
def report_for(persons):
    assessment={'source':'fresh_upload_provider_review','ground_assessment_id':'g','image':{'pixel_digest':D,'width':10,'height':10},'persons':persons,'wide_scene':None}
    der={'source_digest':D,'width':10,'height':10,'privacy_review_status':'not_validated','evidence_export_allowed':False,'output_sha256':'b'*64,'regions_digest':'c'*64}
    ok={'exact_source_confirmed':True,'face_coverage_checked':True,'head_evidence_visible':True,'torso_evidence_visible':True}
    review={'assessment_id':'g','source_digest':D,'output_sha256':'b'*64,'regions_digest':'c'*64,'persons':{p['id']:dict(ok)for p in persons}}
    ff={'source_digest':D,'output_sha256':'b'*64,'regions_digest':'c'*64,'frame_size':[10,10],'foreground_checked':True,'background_checked':True,'reflections_checked':True,'derivative_checked':True}
    return build_private_report(assessment,der,review,full_frame_review=ff)

def test_clean_crop_keeps_existing_outcomes_not_certified():
    p=person('c','absent','present');assert basis_of(p)=='clean_crop'
    s=item_state(p,'helmet');assert s['resolved_state']=='provider_observed_absent' and s['target_level_outcome_permitted'] and s['target_attribution']=='crop_rule_retained_not_verified'
    r=report_for([p])['persons'][0];assert r['report_display_helmet']=='absent' and r['report_display_vest']=='present'
@pytest.mark.parametrize('basis',['overlapped_crop','isolated_crop'])
@pytest.mark.parametrize('h,v',[('absent','absent'),('present','present'),('absent','present'),('unknown','absent')])
def test_partial_basis_cannot_emit_present_or_absent_outcome(basis,h,v):
    p=person('x',h,v,basis);
    for k,raw in(('helmet',h),('vest',v)):
        s=item_state(p,k);assert not s['target_level_outcome_permitted'] and effective_value(p,k)=='unknown' and s['provider_observation']==raw
        if raw!='unknown':assert s['resolved_state']==raw+'_attribution_unresolved' and s['target_attribution']=='unresolved_partial_evidence'
    r=report_for([p])['persons'][0]
    assert r['report_display_helmet']=='unknown' and r['report_display_vest']=='unknown' and r['status']=='needs_human_review'
    assert r['provider_helmet_observation']==h and r['provider_vest_observation']==v  # raw reading preserved, labelled

def test_rule_review_inputs_for_partial_never_violation_or_clear():
    r=report_for([person('x','absent','absent','overlapped_crop')])['persons'][0]
    out=evaluate_configured_rules(policy(),[{'id':'x','helmet':r['report_display_helmet'],'vest':r['report_display_vest']}],{'x':{'work':'inside'}},camera_id='synthetic-camera',policy_sha256=__import__('fresh_review.policy',fromlist=['x']).validate_policy(policy())[1])
    rows=[e for p in out['persons']for e in p['evaluations']if e['rule_id']=='vest']
    assert rows and all(e['status']=='needs_review' for e in rows)
def test_ineligible_crop_with_observation_never_treated_clean():
    assert basis_of(person('i','absent','absent',elig=False))=='crop_rule_ineligible' and effective_value(person('i','absent','absent',elig=False),'helmet')=='unknown'
def test_legacy_without_record_withheld_and_forged_refused():
    p={'id':'l','helmet':'absent','vest':'unknown'};assert basis_of(p)=='not_recorded_legacy' and effective_value(p,'helmet')=='unknown'
    assert item_state(p,'helmet')['provider_observation']=='absent'
    for bad in ('clean','CLEAN_CROP','',None,'isolated'):
        with pytest.raises(ValueError):basis_of({**p,'crop_basis':bad})
def test_unassessed_never_outcome():
    p=person('u','unknown','unknown',assessed=False);assert item_state(p,'vest')['resolved_state']=='not_assessed' and not item_state(p,'vest')['target_level_outcome_permitted']
def test_counts_separate_attempt_from_permitted_outcomes():
    c=counts([person('1','present','absent'),person('2','absent','absent','overlapped_crop'),person('3','present','present','isolated_crop'),person('4','unknown','unknown',assessed=False),person('5','unknown','unknown')])
    assert c['detected_count']==5 and c['provider_observation_attempted_count']==4
    assert c['target_level_outcome_permitted_count']==1 and c['attribution_unresolved_partial_count']==2
    assert c['attempted_is_not_resolved_assessment'] and c['counts_are_not_the_10_plus_qualification']
def test_report_carries_counts_and_basis():
    r=report_for([person('1','present','absent'),person('2','absent','absent','isolated_crop')])
    assert r['ppe_basis_counts']['attribution_unresolved_partial_count']==1 and r['persons'][1]['ppe_basis']['crop_basis']=='isolated_crop'

def test_contract_ppe_partial_has_no_outcome_and_labels():
    from fresh_review.ppe_basis import contract_ppe
    p=person('x','absent','present','overlapped_crop');p['provider_observation']={'observation':{'helmet_evidence':'e1','vest_evidence':'e2'}}
    c=contract_ppe(p);assert c['crop_basis']=='overlapped_crop' and c['helmet']['status']=='unknown' and c['vest']['status']=='unknown'
    assert c['helmet']['provider_observation']=='absent' and c['vest']['resolved_state']=='present_attribution_unresolved' and not c['vest']['target_level_outcome_permitted']
    q=person('c','absent','present');q['provider_observation']=p['provider_observation'];d=contract_ppe(q)
    assert d['helmet']['status']=='absent' and d['vest']['status']=='present' and d['helmet']['target_attribution']=='crop_rule_retained_not_verified'

def test_legacy_not_claimed_clean_and_explicit_clean_needs_record():
    p={'id':'l','helmet':'absent','vest':'present'}
    s=item_state(p,'helmet');assert s['target_attribution']=='legacy_basis_not_recorded_unverified' and s['basis_evidence']=='none' and not s['target_level_outcome_permitted'] and not s['item_resolved'] and s['resolved_state']=='legacy_absent_basis_not_recorded'
    assert basis_of(p)!='clean_crop' and counts([p])['legacy_basis_not_recorded_count']==1
    with pytest.raises(ValueError):basis_of({**p,'crop_basis':'clean_crop'})
    with pytest.raises(ValueError):basis_of({**p,'crop_basis':'clean_crop','crop_eligibility':{'eligible_for_selected_crop_call':False}})
    c=person('c','absent','present');assert item_state(c,'helmet')['basis_evidence']=='stored_eligibility_record'
def test_counts_document_legacy_field_names():
    c=counts([person('1','present','present')]);assert 'PPE_assessed_count' in c['legacy_field_semantics'] and 'attempted' in c['legacy_field_semantics']
def test_clip_unresolved_vs_unassessed_fields():
    from fresh_review.clip_audit import unresolved_people,unassessed,summary
    j=lambda ps:{'state':'completed','result':{'wide_scene':None,'persons':ps}}
    part=j([person('2','absent','absent','overlapped_crop')]);clean=j([person('1','present','present')])
    assert not unassessed(part) and unresolved_people(part) and not unresolved_people(clean)
    assert unresolved_people(j([person('3','unknown','unknown',assessed=False)]))
    clip={'source_clip_sha256':D,'duration_seconds':1,'frames':[]}
    out=summary(clip,[{'sample_index':0,'image_job':part},{'sample_index':1,'image_job':clean}],None,'x')
    assert out['frames_with_unresolved_people']==[0] and out['frames_with_unassessed_people']==[] and out['attempted_is_not_resolved_assessment']

def leg(i,h='present',v='absent'):return {'id':i,'helmet':h,'vest':v}
def test_all_legacy_known_never_emits_clear_or_violation_nor_resolved():
    ps=[leg('a'),leg('b','absent','present')];c=counts(ps)
    assert c['outcome_emitted_count']==0 and c['legacy_outcome_withheld_count']==2 and c['fully_resolved_person_count']==0 and c['resolved_item_count']==0 and c['legacy_basis_not_recorded_count']==2
    from fresh_review.ppe_basis import unresolved
    assert all(unresolved(p)for p in ps)
    r=report_for([leg('a','absent','present')]);q=r['persons'][0]
    assert q['report_display_helmet']=='unknown' and q['report_display_vest']=='unknown' and q['status']=='needs_human_review' and q['provider_helmet_observation']=='absent' and q['provider_vest_observation']=='present'
def test_legacy_inputs_to_rules_are_needs_review_only():
    q=report_for([leg('a','absent','absent')])['persons'][0]
    out=evaluate_configured_rules(policy(),[{'id':'a','helmet':q['report_display_helmet'],'vest':q['report_display_vest']}],{'a':{'work':'inside'}},camera_id='synthetic-camera',policy_sha256=__import__('fresh_review.policy',fromlist=['x']).validate_policy(policy())[1])
    rows=[e for p in out['persons']for e in p['evaluations']if e['rule_id']=='vest']
    assert rows and all(e['status']=='needs_review' for e in rows)
def test_clean_unknown_not_resolved_and_clean_known_resolved():
    c=counts([person('u','unknown','unknown'),person('h','present','unknown'),person('k','present','absent')])
    assert c['attempted_clean_rule_both_items_unknown_count']==1 and c['outcome_emitted_count']==2
    assert c['resolved_item_count']==3 and c['fully_resolved_person_count']==1
    from fresh_review.ppe_basis import person_resolved,item_state
    assert not person_resolved(person('h','present','unknown')) and person_resolved(person('k','present','absent'))
    assert item_state(person('h','present','unknown'),'helmet')['item_resolved'] and not item_state(person('h','present','unknown'),'vest')['item_resolved']
def test_mixed_partial_clean_legacy_unassessed_headline_arithmetic():
    ps=[person('1','present','absent'),person('2','absent','absent','overlapped_crop'),person('3','present','present','isolated_crop'),leg('4'),person('5','unknown','unknown',assessed=False),person('6','unknown','unknown')]
    c=counts(ps)
    assert (c['detected_count'],c['provider_observation_attempted_count'],c['outcome_emitted_count'])==(6,5,1)
    assert c['outcome_emitted_clean_rule_count']==1 and c['legacy_outcome_withheld_count']==1
    assert c['attribution_unresolved_partial_count']==2 and c['fully_resolved_person_count']==1 and c['resolved_item_count']==2
    assert c['emitted_is_not_resolved']
