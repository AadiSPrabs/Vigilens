"""Read-only mapping of a stored fresh-review job to the frontend's v0.2 audit shape.
No provider call, no new state. Compliance findings come ONLY from the deterministic draft matrix (rules.py, ruleset 'draft-unapproved') applied to
unvalidated provider readings plus mask-derived ground-contact estimates, and only when the operator posted zones for
this exact request: each matrix violation says so in its message, carries review_state 'auto' (a rule outcome, not a
verification), and never upgrades the readings. Without zones or without a recorded mask, membership stays unknown and
no zone check is claimed.
PPE values shown come ONLY from ppe_basis.effective_value: a present/absent reading is shown only for a record-proven clean_crop;
legacy, partial and ineligible bases show 'unknown'. Decisive provider readings (present/absent) are shown as 'observation'
findings (auto review state) so the actual reading stays readable, SEPARATE from the human-review escalation: every person still
carries the 'provider_reading_unvalidated' uncertainty finding (and genuinely undetermined readings stay uncertainty findings),
so the current client (which colours a person green only when findings are empty and helmet and vest are both present) can never
show 'fully equipped'.
Outline is the person's bounding box (display only, not a segmentation); invalid geometry refuses the whole view.
The full source/result digests are included and are stable, linkable identifiers; the 16-char image id is not anonymised."""
import math
from core import contains,memberships
from rules import assess as matrix_assess
from .masks import decode_mask
from .ppe_basis import basis_of,item_state,effective_value,counts,unresolved,person_resolved,ITEMS

def _num(v):return isinstance(v,int)and not isinstance(v,bool)
def _box_polygon(box,W,H):
    if not(isinstance(box,(list,tuple))and len(box)==4 and all(_num(v)for v in box)):raise ValueError('Integer person box required')
    l,t,r,b=box
    if not(0<=l<r<=W and 0<=t<b<=H):raise ValueError('Person box outside the image refused')
    pts=[{'x':round(l/W,5),'y':round(t/H,5)},{'x':round(r/W,5),'y':round(t/H,5)},{'x':round(r/W,5),'y':round(b/H,5)},{'x':round(l/W,5),'y':round(b/H,5)}]
    if not all(math.isfinite(q['x'])and math.isfinite(q['y'])for q in pts):raise ValueError('Finite polygon required')
    return pts


def _contact_estimate(p,W,H):
    """Ground-contact ESTIMATE from the stored SAM mask: bottom-most foreground row with >=3 foreground
    pixels, centre = median x of that row's foreground pixels (chosen statistic: less sensitive to one-leg
    or few-pixel outliers than a mean, but on a row split into disjoint leg clusters the median can land
    BETWEEN clusters - between the feet - rather than on a foot; a disclosed limitation, and semantic
    ground-contact validity remains UNVERIFIED regardless), normalised. This is never a verified contact. not_determinable (membership stays unknown) when: no row has
    3+ foreground pixels (noise-prone), or the mask has foreground on ANY frame edge it touches (bottom: the
    person is cropped and no contact is visible; sides/top: the visible shape is truncated, so the bottom row
    may be a crop boundary rather than a foot). Shadows, mask spill, ladders/platforms, occlusion and seated /
    legs-hidden postures are NOT detectable from a binary mask alone - a plausible_estimate still carries that
    standing caveat, which is why every downstream output remains a review candidate. Corrupt or
    frame-mismatched masks raise, refusing the whole view like any invalid geometry."""
    m=p.get('mask')
    if not isinstance(m,dict):return {'basis':'not_recorded','point':None,'validity':'not_determinable','reasons':['no_mask_recorded']}
    mask=decode_mask(m)
    ox,oy=m['origin_pixels'];fw,fh=m['source_frame_size']
    if fw!=W or fh!=H:raise ValueError('Mask frame does not match result image')
    w,h=mask.size;px=mask.load()
    edge=[]
    if oy==0 and any(px[x,0] for x in range(w)):edge.append('top')
    if oy+h==H and any(px[x,h-1] for x in range(w)):edge.append('bottom')
    if ox==0 and any(px[0,y] for y in range(h)):edge.append('left')
    if ox+w==W and any(px[w-1,y] for y in range(h)):edge.append('right')
    if edge:return {'basis':'mask_derived_estimate_unverified','point':None,'validity':'not_determinable','reasons':['mask_touches_frame_edge_'+e for e in edge]}
    for y in range(h-1,-1,-1):
        run=[x for x in range(w) if px[x,y]]
        if not run:continue
        if len(run)<3:return {'basis':'mask_derived_estimate_unverified','point':None,'validity':'not_determinable','reasons':['contact_row_sparse_lt_3px']}
        run.sort();mid=len(run)//2;med=float(run[mid]) if len(run)%2 else (run[mid-1]+run[mid])/2
        pt={'x':round((ox+med)/W,5),'y':round((oy+y)/H,5)}
        return {'basis':'mask_derived_estimate_unverified','point':pt,'validity':'plausible_estimate','reasons':['median_of_bottom_foreground_row','shadow_spill_occlusion_posture_not_detectable_from_mask']}
    return {'basis':'mask_derived_estimate_unverified','point':None,'validity':'not_determinable','reasons':['empty_mask']}


def _zone_ids_at(pt,zones):
    return sorted(z['id'] for z in zones if contains(pt,z['points']))


def _response_ids(node,out):
    if isinstance(node,dict):
        for k,v in node.items():
            if isinstance(k,str)and k.endswith('response_id')and isinstance(v,str)and v:out.append(v)
            else:_response_ids(v,out)
    elif isinstance(node,list):
        for v in node:_response_ids(v,out)

def _readings_origin(result):
    ids=[];_response_ids(result,ids)
    if not ids:return 'unknown'
    syn=sum(1 for i in ids if i.startswith('synthetic-'))
    if syn==len(ids):return 'synthetic'
    if syn==0:return 'live_provider'
    return 'unknown'

def to_frontend_audit(result,*,audit_id,job_state='completed',source_digest=None,zones=None):
    origin=_readings_origin(result)
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
        def add(rule,msg,zone=None,kind='uncertainty',review='needs_human_review',severity=None):
            nonlocal n;n+=1;findings.append({'id':f'f{n}','rule_id':rule,'kind':kind,'severity':severity,'zone_id':zone,'message':msg,'review_state':review})
        for k in ITEMS:
            if eff[k]=='unknown':add(f'{k}_reading',f'{k} not determined or not usable for this person (basis: {basis_of(p)}); needs human review')
            elif eff[k]=='absent':
                if origin=='synthetic':add(f'{k}_reading',f'Synthetic transport generated a {k}-absent reading (offline test data, not a provider observation)',kind='observation',review='auto')
                else:add(f'{k}_reading',f'Provider read {k} as absent (unvalidated reading, not a verified safety judgment)',kind='observation',review='auto')
        if job_state!='completed'or ws_partial:add('result_partial','PARTIAL RESULT (state: %s): not every person or item was resolved; absence of a finding here is not a clearance; needs human review'%job_state)
        contact=_contact_estimate(p,W,H)
        zone_id=None;zone_ids=[];zm_status='unknown';worst=None
        foot=contact['point']if contact['validity']=='plausible_estimate'else None
        boundary_flip=[]
        if zones and foot is not None:
            # Boundary rule (reviewer-required): membership must be stable under perturbation of the contact
            # estimate. Probe radius is scale-relative: max(2px, 0.5% of the frame dimension) per axis, so a
            # 4000px photo probes 20px. Center plus eight offsets (axis + diagonal) are tested; if ANY offset
            # changes the zone-id set, membership is boundary_uncertain - never a clean in/out - the matrix
            # is not run, and the differing zone sets are recorded in the finding, not silently dropped.
            # LIMITED CHECK, not a guarantee: thin slivers or notches narrower than the probe spacing can
            # still evade every probe, so even a stable result stays an unverified estimate.
            rpx,rpy=max(2,-(-W//200)),max(2,-(-H//200))
            rx,ry=rpx/W,rpy/H
            probes=((0,0),(rx,0),(-rx,0),(0,ry),(0,-ry),(rx,ry),(rx,-ry),(-rx,ry),(-rx,-ry))
            sets={tuple(_zone_ids_at({'x':min(max(foot['x']+dx,0.0),1.0),'y':min(max(foot['y']+dy,0.0),1.0)},zones))for dx,dy in probes}
            if len(sets)>1:
                zm_status='boundary_uncertain'
                boundary_flip=sorted({zid for s in sets for zid in s}|set(_zone_ids_at(foot,zones)))
                boundary_sets=sorted(list(s) for s in sets)
        if zones and foot is not None and zm_status!='boundary_uncertain':
            # core.memberships/rules.assess are polygon-based (they anchor membership at the polygon's
            # mid-x/bottom-y). The mask-derived contact estimate is a point, so it is evaluated as an
            # epsilon triangle whose bottom vertex is exactly that point: core's own containment and
            # hazard-first ranking apply unchanged, and the approximation drift is below 1e-6 of frame.
            _e=1e-6
            fx=min(max(foot['x'],_e),1-_e);fy=min(max(foot['y'],3*_e),1)
            fpoly=[{'x':fx-_e,'y':fy-3*_e},{'x':fx+_e,'y':fy-3*_e},{'x':fx,'y':fy}]
            mem=memberships(fpoly,zones,contact_known=True)
            zone_id=mem['display_zone_id'];zone_ids=mem['zone_ids'];zm_status='known'  # 'known' means: stable under the limited scale-relative probes for THIS unverified mask estimate - never a verified membership
            assessed=matrix_assess({'id':pid,'polygon':fpoly,'helmet':eff['helmet'],'vest':eff['vest'],'contact_known':True},zones)
            # Reviewer-required demotion: unverified inputs can never render as a confirmed violation or
            # severity. Every matrix output becomes an uncertainty finding needing human review; the
            # deterministic class survives only as message text. Inputs are stated plainly: unvalidated
            # provider PPE readings plus a mask-derived contact estimate from ONE still image - no dwell
            # time, no tracking, no verified contact.
            for f in assessed['findings']:
                if f['kind']!='violation':continue
                # Rule-specific inputs: location-only intrusion never consumes PPE readings,
                # so its candidate must not imply a PPE verdict; PPE rules state both inputs.
                if f['rule_id'].startswith('NO_'):
                    inputs='Inputs: unvalidated provider PPE readings and a mask-derived ground-contact estimate from a single still image; no duration or tracking is claimed.'
                else:
                    inputs='Inputs: zone geometry and a mask-derived ground-contact estimate from a single still image only; no PPE reading is used by this rule; no duration or tracking is claimed.'
                add(f['rule_id'],f'Draft matrix candidate (deterministic class {f["severity"]}, rule {f["rule_id"]}): {f["message"]} {inputs} Requires human confirmation; not a compliance determination.',zone=f['zone_id'])
        elif zones and zm_status=='boundary_uncertain':
            for zid in boundary_flip:
                zn=next((z for z in zones if z['id']==zid),None)
                add(f'zone_membership_boundary_{zid}'[:120],f'Zone "{(zn or {}).get("name",zid)}": the mask-derived contact estimate lies within the {rpx}x{rpy}px probe radius of this zone boundary, so membership flips under pixel noise; treated as NOT determined, not as inside or outside. Differing zone sets observed under the probes: {boundary_sets}. Needs human review',zone=zid)
        else:
            for z in zones:add(f'zone_membership_{z["id"]}'[:120],f'Zone "{z["name"]}": whether this person is inside it was NOT determined ({", ".join(contact["reasons"]) if contact["basis"]!="not_recorded" else "no recorded ground contact for this person"}); this is not a zone or safety check; needs human review',zone=z['id'])
        add('provider_reading_unvalidated','Provider readings are unvalidated observations, not a safety or compliance check; needs human review')
        persons.append({'id':pid,'polygon':_box_polygon(p['box_half_open'],W,H),'outline_basis':'bounding_box_display_only_not_segmentation',
            'geometry_status':p.get('geometry_status')if p.get('geometry_status')in('mask_verified','unverified_box_only')else 'unknown_not_recorded','spatial_rule_inputs':'unknown','helmet':eff['helmet'],'vest':eff['vest'],
            'ppe_basis':{'crop_basis':basis_of(p),'provider_observation_attempted':p.get('ppe_assessed')is True,
                'target_level_outcome_permitted':{k:bool(st[k]['target_level_outcome_permitted'])for k in ITEMS},'resolved':person_resolved(p)},
            'ground_contact':contact,
            'zone_id':zone_id,'zone_ids':zone_ids,'zone_membership_status':zm_status,
            'zone_membership_basis':'unverified_mask_estimate_limited_scale_relative_probes_only_not_a_guarantee' if zm_status=='known' else ('estimate_within_scale_relative_probe_radius_of_a_zone_boundary' if zm_status=='boundary_uncertain' else 'no_usable_contact_estimate'),
            'worst_severity':worst,'findings':findings})
    ws=result.get('wide_scene')or{}
    zones_applied=bool(zones)and all(q['zone_membership_status']=='known' for q in persons)
    return {'audit_id':audit_id,'schema_version':'0.2-local-draft','ruleset_version':'draft-unapproved' if zones_applied else 'none-compliance-not-evaluated','source':'backend','created_at':None,
        'image':{'id':img['pixel_digest'][:16],'pixel_digest':img['pixel_digest'],'width':W,'height':H},
        'source_digest':source_digest or img['pixel_digest'],'zones':zones,'evidence_image':None,'evidence_status':'unavailable','evidence_export_allowed':False,
        'persons':persons,'zones_applied':zones_applied,
        'zones_applied_meaning':'Membership resolved for every person and the draft matrix was evaluated as review candidates only: deterministic classes appear in message text, never as confirmed violations or severities; inputs are unvalidated readings plus a mask-derived contact estimate from a single still image, never compliance determinations' if zones_applied else ('Zones were posted but ground contact is not determinable for every person; no zone check claimed' if zones else 'No zones posted; no zone check claimed'),
        'review_mode':'private_review_draft_matrix_findings_are_not_compliance_determinations',
        'job_state':job_state,'partial_result':job_state!='completed','coverage':ws.get('coverage','not_wide_scene'),
        'ppe_withheld_unverified_geometry':bool(ws.get('ppe_withheld_unverified_geometry')),
        'all_detected_people_target_level_resolved':bool(result['persons'])and not any(unresolved(q)for q in result['persons']),
        'ppe_basis_counts':counts(result['persons']),'execution_state_is_not_assessment_completeness':True,
        'provider_calls_this_request':0,'readings_status':'unvalidated_provider_observations',
        # Origin of the readings, derived from this exact stored result's recorded provider response ids: the
        # synthetic transport labels every id 'synthetic-*'. All ids synthetic -> 'synthetic'; none synthetic ->
        # 'live_provider'; missing or mixed -> 'unknown' (never guessed). Live readings stay unvalidated either way.
        'readings_origin':origin,
        # Geometry honesty: in synthetic mode the person boxes/masks are generated deterministically from the
        # request bytes by the offline transport (hash-derived positions), not detected from scene content.
        'person_geometry_origin':'synthetic_generated_not_detected' if origin=='synthetic' else 'provider_returned_unvalidated',
        'compliance_status':'not_evaluated','privacy_review_status':'not_validated'}
