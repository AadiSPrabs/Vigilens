import pytest
from test_fresh_upload_routes import material
from fresh_review.rechecks import plan_recheck,compare_candidate

def test_recheck_plan_binding_bounds_no_dispatch(material):
 p,raw,frame,calls,c,job=material;r=job['result']
 plan=plan_recheck(raw,r,'0',attempts_so_far=0,max_attempts=1)
 assert plan['unknown_items']==['helmet']and plan['status']=='planned_not_authorised_or_dispatched'
 assert len(plan['steps'])==2 and plan['provider_calls']==0 and plan['source_geometry_update_allowed']is False
 assert plan_recheck(raw,r,'0',attempts_so_far=1,max_attempts=1)['status']=='escalate_human_review'
 assert len(calls)==2
 with pytest.raises(ValueError):plan_recheck(raw,r,'wrong',attempts_so_far=0,max_attempts=1)
 with pytest.raises(ValueError):plan_recheck(raw,r,'0',attempts_so_far=0,max_attempts=True)

def test_recheck_wrong_source_or_crop_refused(material):
 import copy,io
 from PIL import Image
 p,raw,frame,calls,c,job=material;r=copy.deepcopy(job['result'])
 r['persons'][0]['crop_png_sha256']='wrong'
 with pytest.raises(ValueError):plan_recheck(raw,r,'0',attempts_so_far=0,max_attempts=1)
 r=copy.deepcopy(job['result']);r['image']['pixel_digest']='0'*64
 with pytest.raises(ValueError):plan_recheck(raw,r,'0',attempts_so_far=0,max_attempts=1)

def test_recheck_candidate_preserves_original_and_contradiction():
 before={'helmet':'present','vest':'unknown'};after={'helmet':'absent','vest':'present'}
 out=compare_candidate(before,after)
 assert out['review_display_proposal']=={'helmet':'unknown','vest':'present'}and out['contradictions']==['helmet']
 assert before=={'helmet':'present','vest':'unknown'}and out['original_overwrite_allowed']is False
 assert out['status']=='needs_human_review'
 with pytest.raises(ValueError):compare_candidate(before,{'helmet':'safe','vest':'present'})
