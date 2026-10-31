"""Read-only mapping of a stored fresh-review job to the frontend's v0.2 audit shape.
No provider call, no new state. Never emits a 'violation': compliance rules are not evaluated and provider readings are unvalidated.
PPE values shown come ONLY from ppe_basis.effective_value: a present/absent reading is shown only for a record-proven clean_crop;
legacy, partial and ineligible bases show 'unknown'. Every person also carries one uncertainty finding, so the current client
(which colours a person green only when findings are empty and helmet and vest are both present) can never show 'fully equipped'.
Outline is the person's bounding box (display only, not a segmentation); invalid geometry refuses the whole view.
The full source/result digests are included and are stable, linkable identifiers; the 16-char image id is not anonymised."""
import math
from .ppe_basis import basis_of,item_state,effective_value,counts,unresolved,person_resolved,ITEMS

def _num(v):return isinstance(v,int)and not isinstance(v,bool)
def _box_polygon(box,W,H):
    if not(isinstance(box,(list,tuple))and len(box)==4 and all(_num(v)for v in box)):raise ValueError('Integer person box required')
    l,t,r,b=box
    if not(0<=l<r<=W and 0<=t<b<=H):raise ValueError('Person box outside the image refused')
    pts=[{'x':round(l/W,5),'y':round(t/H,5)},{'x':round(r/W,5),'y':round(t/H,5)},{'x':round(r/W,5),'y':round(b/H,5)},{'x':round(l/W,5),'y':round(b/H,5)}]
    if not all(math.isfinite(q['x'])and math.isfinite(q['y'])for q in pts):raise ValueError('Finite polygon required')
    return pts

def to_frontend_audit(result,*,audit_id,job_state='completed',source_digest=None,zones=None):
    img=result['image'];W,H=img['width'],img['height']
    if not(_num(W)and _num(H)and W>0 and H>0):raise ValueError('Image size required')
    if not isinstance(result.get('persons'),list)or not result['persons']:raise ValueError('Zero detected people: an empty person list could be misread as a clearance, so no view is produced')
    zones=[dict(id=z['id'],name=z['name'],hazard=z['hazard'],points=[dict(x=q['x'],y=q['y'])for q in z['points']])for z in(zones or[])]
    persons=[];n=0;ids=set();ws0=result.get('wide_scene')or{};ws_partial=bool(ws0.get('ppe_withheld_unverified_geometry'))or ws0.get('coverage','not_wide_scene')not in('not_wide_scene','complete')
    for p in result['persons']:
        pid=str(p['id'])
        if pid in ids:raise ValueError('Duplicate person id refused')
        ids.add(pid)
        eff={k:effective_value(p,k)for k in ITEMS};st={k:item_state(p,k)for k in ITEMS}
        findings=[]
        def add(rule,msg,zone=None):
            nonlocal n;n+=1;findings.append({'id':f'f{n}','rule_id':rule,'kind':'uncertainty','severity':None,'zone_id':zone,'message':msg,'review_state':'needs_human_review'})
        for k in ITEMS:
            if eff[k]=='unknown':add(f'{k}_reading',f'{k} not determined or not usable for this person (basis: {basis_of(p)}); needs human review')
            elif eff[k]=='absent':add(f'{k}_reading',f'Provider read {k} as absent (unvalidated reading); needs human review')
        if job_state!='completed'or ws_partial:add('result_partial','PARTIAL RESULT (state: %s): not every person or item was resolved; absence of a finding here is not a clearance; needs human review'%job_state)
        for z in zones:add(f'zone_membership_{z["id"]}'[:120],f'Zone "{z["name"]}": whether this person is inside it was NOT determined (no ground-contact review was made); this is not a zone or safety check; needs human review',zone=z['id'])
        add('provider_reading_unvalidated','Provider readings are unvalidated observations, not a safety or compliance check; needs human review')
        persons.append({'id':pid,'polygon':_box_polygon(p['box_half_open'],W,H),'outline_basis':'bounding_box_display_only_not_segmentation',
            'geometry_status':p.get('geometry_status')if p.get('geometry_status')in('mask_verified','unverified_box_only')else 'unknown_not_recorded','spatial_rule_inputs':'unknown','helmet':eff['helmet'],'vest':eff['vest'],
            'ppe_basis':{'crop_basis':basis_of(p),'provider_observation_attempted':p.get('ppe_assessed')is True,
                'target_level_outcome_permitted':{k:bool(st[k]['target_level_outcome_permitted'])for k in ITEMS},'resolved':person_resolved(p)},
            'zone_id':None,'zone_ids':[],'zone_membership_status':'unknown','worst_severity':None,'findings':findings})
    ws=result.get('wide_scene')or{}
    return {'audit_id':audit_id,'schema_version':'0.2-local-draft','ruleset_version':'none-compliance-not-evaluated','source':'backend','created_at':None,
        'image':{'id':img['pixel_digest'][:16],'pixel_digest':img['pixel_digest'],'width':W,'height':H},
        'source_digest':source_digest or img['pixel_digest'],'zones':zones,'evidence_image':None,'evidence_status':'unavailable','evidence_export_allowed':False,
        'persons':persons,'review_mode':'private_review_uncertainty_only_findings_are_not_violations',
        'job_state':job_state,'partial_result':job_state!='completed','coverage':ws.get('coverage','not_wide_scene'),
        'ppe_withheld_unverified_geometry':bool(ws.get('ppe_withheld_unverified_geometry')),
        'all_detected_people_target_level_resolved':bool(result['persons'])and not any(unresolved(q)for q in result['persons']),
        'ppe_basis_counts':counts(result['persons']),'execution_state_is_not_assessment_completeness':True,
        'provider_calls_this_request':0,'readings_status':'unvalidated_provider_observations','compliance_status':'not_evaluated','privacy_review_status':'not_validated'}
