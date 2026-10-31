"""Runtime delta seq18 proposal: new single-person-path uploads record the ACTUAL crop eligibility checks
(same function and default limits as the wide-scene gate). Never blanket clean. Older stored results untouched."""
import asyncio
import pytest
from PIL import Image
import fresh_review.pipeline as m
import test_fresh_upload_pipeline as base
from fresh_test_helpers import response as real_response
from fresh_review.ppe_basis import basis_of,effective_value,item_state,person_resolved,person_summary

def run(tmp_path,monkeypatch,boxes,helmet='present',vest='absent'):
 p,raw,frame,calls=base.setup(tmp_path,monkeypatch,people=1)
 async def parse(*a,**k):return {'objects':[{'object_id':str(i),'box_half_open':list(b),'mask':Image.new('L',(b[2]-b[0],b[3]-b[1]),255)}for i,b in enumerate(boxes)]}
 monkeypatch.setattr(m,'parse_sam_image_text',parse)
 monkeypatch.setattr(base,'response',lambda h='absent',v='unknown':real_response(helmet,vest))
 out=asyncio.run(p.run(raw,'image/png',[]));assert out['state']=='completed'
 return p,raw,calls,out['result']['persons']

def test_new_eligible_crop_records_real_checks_and_is_clean(tmp_path,monkeypatch):
 p,raw,calls,persons=run(tmp_path,monkeypatch,[(0,0,40,80)])
 g=persons[0]['crop_eligibility'];assert g['eligible_for_selected_crop_call']is True and g['review_reasons']==[]
 assert g['recorded_by']=='single_upload_same_eligibility_function'and g['limits_applied']['min_crop_height']==64
 assert g['identity_or_visibility_validated']is False
 assert basis_of(persons[0])=='clean_crop'and effective_value(persons[0],'helmet')=='present'and effective_value(persons[0],'vest')=='absent' and person_resolved(persons[0])
 n=len(calls);assert asyncio.run(p.run(raw,'image/png',[]))['state']=='completed'and len(calls)==n  # repeat: stored, 0 calls

def test_new_ineligible_small_crop_is_recorded_ineligible_and_unknown(tmp_path,monkeypatch):
 p,raw,calls,persons=run(tmp_path,monkeypatch,[(0,0,20,60)])
 g=persons[0]['crop_eligibility'];assert g['eligible_for_selected_crop_call']is False and 'crop_too_small_for_configured_evidence_threshold'in g['review_reasons']
 assert basis_of(persons[0])=='crop_rule_ineligible'  # truthful: size, not overlap
 assert person_summary(persons[0])['crop_rule_reasons']==['crop_too_small_for_configured_evidence_threshold']
 assert len(calls)==2  # recording evidence did not change dispatch: the PPE call was still made
 assert persons[0]['helmet']=='present'and persons[0]['vest']=='absent'  # raw preserved
 assert effective_value(persons[0],'helmet')=='unknown'and effective_value(persons[0],'vest')=='unknown'and not person_resolved(persons[0])
 assert item_state(persons[0],'vest')['target_level_outcome_permitted']is False

def test_new_unknown_reading_on_eligible_crop_stays_unknown_and_unresolved(tmp_path,monkeypatch):
 p,raw,calls,persons=run(tmp_path,monkeypatch,[(0,0,40,80)],helmet='unknown',vest='unknown')
 assert basis_of(persons[0])=='clean_crop'and effective_value(persons[0],'helmet')=='unknown'and not person_resolved(persons[0])

def test_two_people_get_separate_records_not_blanket_clean(tmp_path,monkeypatch):
 p,raw,calls,persons=run(tmp_path,monkeypatch,[(0,0,40,80),(50,0,70,40)])
 assert [x['crop_eligibility']['eligible_for_selected_crop_call']for x in persons]==[True,False]
 assert [basis_of(x)for x in persons]==['clean_crop','crop_rule_ineligible']

def test_old_stored_result_without_record_is_still_legacy_unknown():
 old={'id':'0','helmet':'present','vest':'absent','ppe_assessed':True,'provider_observation':{}}
 assert basis_of(old)=='not_recorded_legacy'and effective_value(old,'helmet')=='unknown'

def test_cross_person_foreground_still_blocks_every_call(tmp_path,monkeypatch):
 p,raw,frame,calls=base.setup(tmp_path,monkeypatch,people=2)
 async def overlap(*a,**k):return {'objects':[{'object_id':str(i),'box_half_open':[i*10,0,i*10+40,80],'mask':Image.new('L',(40,80),255)}for i in range(2)]}
 monkeypatch.setattr(m,'parse_sam_image_text',overlap)
 out=asyncio.run(p.run(raw,'image/png',[]));assert out['state']!='completed'and len(calls)==1  # SAM only, no PPE call

def test_genuine_overlap_record_keeps_overlapped_label_and_reasons():
 g={'eligible_for_selected_crop_call':False,'review_reasons':['other_person_foreground_in_crop']}
 p={'id':'0','helmet':'present','vest':'absent','ppe_assessed':True,'provider_observation':{},'crop_eligibility':g}
 assert basis_of(p)=='overlapped_crop' and person_summary(p)['crop_rule_reasons']==['other_person_foreground_in_crop'] and effective_value(p,'helmet')=='unknown'

def test_report_text_names_the_real_reason_for_size_ineligible(tmp_path,monkeypatch):
 from fresh_review.ppe_basis import contract_ppe
 p,raw,calls,persons=run(tmp_path,monkeypatch,[(0,0,20,60)])
 persons[0]['provider_observation']['observation']={'helmet':'present','vest':'absent','helmet_evidence':'x','vest_evidence':'y'}
 k=contract_ppe(persons[0]);assert k['crop_basis']=='crop_rule_ineligible' and k['crop_rule_reasons']==['crop_too_small_for_configured_evidence_threshold'] and k['helmet']['status']=='unknown'

@pytest.mark.parametrize('h',['present','absent','unknown'])
@pytest.mark.parametrize('v',['present','absent','unknown'])
def test_label_correction_changes_no_semantics_counts_or_rule_inputs(h,v):
 """crop_rule_ineligible and overlapped_crop must be semantically identical: only the label and reasons differ."""
 from fresh_review.ppe_basis import counts,contract_ppe
 def mk(reasons):return {'id':'0','helmet':h,'vest':v,'ppe_assessed':True,'provider_observation':{'observation':{'helmet':h,'vest':v,'helmet_evidence':'x','vest_evidence':'y'}},'crop_eligibility':{'eligible_for_selected_crop_call':False,'review_reasons':reasons}}
 a=mk(['other_person_foreground_in_crop']);b=mk(['crop_too_small_for_configured_evidence_threshold'])
 assert basis_of(a)=='overlapped_crop' and basis_of(b)=='crop_rule_ineligible'
 strip=lambda d:{k:val for k,val in d.items() if k!='target_attribution' or True}
 for k in('helmet','vest'):
  assert item_state(a,k)==item_state(b,k) and effective_value(a,k)==effective_value(b,k)=='unknown'
 assert person_resolved(a)==person_resolved(b)==False and counts([a])==counts([b])
 ca,cb=contract_ppe(a),contract_ppe(b)
 for k in('helmet','vest'):assert ca[k]==cb[k]
