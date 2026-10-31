"""Evidence basis for stored PPE provider observations. Derived at read time; nothing stored changes.

A provider present/absent/unknown is only an unvalidated reading of one image crop. This module
records which kind of crop produced it and whether the reading may be used for a target-level
outcome (a displayed present/absent, or a rule finding). Strict eligibility is unchanged: crops
admitted by the existing no-other-person-foreground rule keep today's behavior, which is retained
and not certified: predicted masks and boxes may be wrong, so correct person association is not proven.

Partial bases (overlapped_crop, isolated_crop, crop_rule_ineligible) have unresolved target attribution. Neighbour gear can
cause a false present; a clipped mask or hidden body can cause a false absent. Both are therefore
incapable of producing a target-level outcome, and downstream consumers get 'unknown'.
No builder produces partial bases today; this is the contract any future one must meet.
"""
CLEAN='clean_crop';PARTIAL=('overlapped_crop','isolated_crop','crop_rule_ineligible');LEGACY='not_recorded_legacy'
ITEMS=('helmet','vest');VALUES=('present','absent','unknown')

def basis_of(person):
    """Explicit crop_basis wins (forged values refused). Else derive from the stored eligibility record."""
    if 'crop_basis' in person:
        if person['crop_basis']not in (CLEAN,)+PARTIAL:raise ValueError('Unknown crop_basis refused')
        if person['crop_basis']==CLEAN and (person.get('crop_eligibility')or{}).get('eligible_for_selected_crop_call')is not True:raise ValueError('clean_crop needs the stored eligibility record that proves it')
        return person['crop_basis']
    gate=person.get('crop_eligibility')
    if gate is None:return LEGACY  # older single-crop paths with no eligibility record: raw reading kept, but no target-level outcome (not shown to be a clean crop)
    if gate.get('eligible_for_selected_crop_call')is True:return CLEAN
    # An observation on a crop the rule did not admit is never treated as clean. The label stays truthful:
    # genuine overlap reasons keep 'overlapped_crop'; any other recorded reason (e.g. too small) is the generic
    # 'crop_rule_ineligible'. The exact reasons are always exposed as crop_rule_reasons.
    if any(r in('other_person_foreground_in_crop','overlaps_unverified_geometry_person_box')for r in gate.get('review_reasons',[])):return 'overlapped_crop'
    return 'crop_rule_ineligible'

def assessed(person):return person.get('ppe_assessed',True)is True and person.get('provider_observation',True)is not None

def _item_state(person,item):
    if item not in ITEMS:raise ValueError('helmet or vest')
    raw=person.get(item,'unknown')
    if raw not in VALUES:raise ValueError('Observation enum required')
    basis=basis_of(person)
    if not assessed(person):
        return {'provider_observation':'unknown','resolved_state':'not_assessed','target_attribution':'not_applicable','target_level_outcome_permitted':False}
    if basis in PARTIAL:
        state={'present':'present_attribution_unresolved','absent':'absent_attribution_unresolved','unknown':'unknown'}[raw]
        return {'provider_observation':raw,'resolved_state':state,'target_attribution':'unresolved_partial_evidence','target_level_outcome_permitted':False}
    state={'present':'provider_observed_present','absent':'provider_observed_absent','unknown':'unknown'}[raw]
    if basis==LEGACY:
        lst={'present':'legacy_present_basis_not_recorded','absent':'legacy_absent_basis_not_recorded','unknown':'unknown'}[raw]
        return {'provider_observation':raw,'resolved_state':lst,'target_attribution':'legacy_basis_not_recorded_unverified','basis_evidence':'none','target_level_outcome_permitted':False}
    return {'provider_observation':raw,'resolved_state':state,'target_attribution':'crop_rule_retained_not_verified','basis_evidence':'stored_eligibility_record','target_level_outcome_permitted':raw!='unknown'}

def item_state(person,item):
    """Permission to emit is not resolution: resolved needs a known value AND a supported (clean, record-proven) basis. Legacy missing-basis is never resolved."""
    st=_item_state(person,item)
    st['item_resolved']=bool(st['target_level_outcome_permitted'])and st['provider_observation']in('present','absent')and basis_of(person)==CLEAN and assessed(person)
    return st

def person_resolved(person):return all(item_state(person,k)['item_resolved']for k in ITEMS)

def effective_value(person,item):
    """The only value downstream display, policy or rule code may use."""
    s=item_state(person,item)
    return s['provider_observation']if s['target_level_outcome_permitted']else'unknown'

def person_summary(person):
    return {'crop_basis':basis_of(person),'crop_rule_reasons':list((person.get('crop_eligibility')or{}).get('review_reasons',[])),'items':{k:item_state(person,k)for k in ITEMS}}

def counts(persons):
    """Attempted, emitted-outcome and resolved are three different things; never merge them."""
    A=[p for p in persons if assessed(p)]
    emitted=[p for p in A if any(item_state(p,k)['target_level_outcome_permitted']for k in ITEMS)]
    return {'detected_count':len(persons),
            'provider_observation_attempted_count':len(A),
            'outcome_emitted_count':len(emitted),
            'legacy_outcome_withheld_count':sum(1 for p in A if basis_of(p)==LEGACY and any(item_state(p,k)['provider_observation']!='unknown'for k in ITEMS)),
            'outcome_emitted_clean_rule_count':sum(1 for p in emitted if basis_of(p)==CLEAN),
            'legacy_basis_not_recorded_count':sum(1 for p in A if basis_of(p)==LEGACY),
            'attribution_unresolved_partial_count':sum(1 for p in A if basis_of(p)in PARTIAL),
            'attempted_clean_rule_both_items_unknown_count':sum(1 for p in A if basis_of(p)==CLEAN and all(item_state(p,k)['provider_observation']=='unknown'for k in ITEMS)),
            'resolved_item_count':sum(item_state(p,k)['item_resolved']for p in persons for k in ITEMS),
            'fully_resolved_person_count':sum(1 for p in persons if person_resolved(p)),
            'legacy_field_semantics':'PPE_assessed_count, all_detected_people_assessed and ppe_assessed (older names, kept unchanged for compatibility) mean provider observation attempted, not a resolved assessment',
            'target_level_outcome_permitted_count':len(emitted),
            'attempted_is_not_resolved_assessment':True,'emitted_is_not_resolved':True,'counts_are_not_the_10_plus_qualification':True,
            'resolved_means':'both helmet and vest known (present or absent) on a clean_crop proven by the stored eligibility record; still an unvalidated provider reading, not safe or compliant'}

def contract_ppe(p):
    """Integration-contract PPE block for an assessed person."""
    pb=person_summary(p);observation=p['provider_observation']['observation']
    return {'assessment_status':'provider_observation_unvalidated','crop_basis':pb['crop_basis'],'crop_rule_reasons':pb['crop_rule_reasons'],**{k:{'status':p[k]if pb['items'][k]['target_level_outcome_permitted']else'unknown','provider_observation':p[k],'resolved_state':pb['items'][k]['resolved_state'],'target_attribution':pb['items'][k]['target_attribution'],'target_level_outcome_permitted':pb['items'][k]['target_level_outcome_permitted'],'reason':'provider_observation_not_safety_clearance','visible_evidence':observation[k+'_evidence']}for k in ITEMS}}

def unresolved(person):
    """Anything short of both items resolved: not attempted, partial, legacy missing-basis, or any unknown item."""
    return not person_resolved(person)
