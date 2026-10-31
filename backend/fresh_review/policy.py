"""Versioned policy configuration validation. No universal safety defaults.
Not mounted as an approval endpoint; a validated object is not owner approval.
"""
import hashlib,json,math
from core import polygon

FORMAT='vigilens.site-policy.proposal.v1'
def validate_policy(doc):
    required={'format','policy_id','version','scope','camera_id','approval_reference','priorities','zones','outside_rules'}
    if not isinstance(doc,dict)or set(doc)!=required or doc['format']!=FORMAT:raise ValueError('Exact versioned policy configuration required')
    for k in ('policy_id','version','camera_id','approval_reference'):
        if not isinstance(doc[k],str)or not 1<=len(doc[k].strip())<=200:raise ValueError('Explicit bounded policy identity/scope references required')
    if doc['scope']not in ('illustrative_demo','site_owner_policy'):raise ValueError('Explicit demo/site scope required')
    priorities=doc['priorities']
    if not isinstance(priorities,list)or len(priorities)>16:raise ValueError('Bounded explicit priority order required')
    if any(not isinstance(p,str)or not 1<=len(p)<=80 for p in priorities)or len(set(priorities))!=len(priorities):raise ValueError('Unique configured priority labels required')
    def rules(items):
        if not isinstance(items,list)or len(items)>16:raise ValueError('Explicit bounded rule list required')
        ids=set();out=[]
        for rule in items:
            if not isinstance(rule,dict)or set(rule)!={'id','check','priority'}:raise ValueError('Explicit rule id/check/priority required')
            if not isinstance(rule['id'],str)or not 1<=len(rule['id'])<=128 or rule['id']in ids:raise ValueError('Unique rule id required')
            ids.add(rule['id'])
            if rule['check']not in ('helmet_worn','vest_worn','access'):raise ValueError('Unsupported check; do not invent PPE requirements')
            if rule['priority']is not None and rule['priority']not in priorities:raise ValueError('Priority must be explicitly configured or unrated')
            out.append(dict(rule))
        return out
    zones=doc['zones']
    if not isinstance(zones,list)or len(zones)>20:raise ValueError('Bounded zone list required')
    seen=set();normalized=[]
    for zone in zones:
        if not isinstance(zone,dict)or set(zone)!={'id','name','points','access_mode','rules'}:raise ValueError('Independent access mode and PPE rules required')
        if not isinstance(zone['id'],str)or not 1<=len(zone['id'])<=128 or zone['id']in seen:raise ValueError('Unique zone ID required')
        seen.add(zone['id'])
        if not isinstance(zone['name'],str)or not 1<=len(zone['name'])<=200:raise ValueError('Zone name required')
        if zone['access_mode']not in ('allowed','authorised_only','no_entry_all'):raise ValueError('Explicit access semantics required')
        checked=rules(zone['rules'])
        if any(r['check']=='access'for r in checked)and zone['access_mode']=='allowed':raise ValueError('Access rule conflicts with allowed entry')
        normalized.append({**zone,'points':polygon(zone['points']),'rules':checked})
    outside=rules(doc['outside_rules'])
    if any(r['check']=='access'for r in outside):raise ValueError('No implied outside access prohibition')
    out={**doc,'zones':normalized,'outside_rules':outside,'priorities':list(priorities)}
    raw=json.dumps(out,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return out,hashlib.sha256(raw).hexdigest()

def describe_policy(doc):
    policy,sha=validate_policy(doc)
    return {'policy_id':policy['policy_id'],'version':policy['version'],'policy_sha256':sha,
            'camera_id':policy['camera_id'],'scope':policy['scope'],
            'configuration_status':'validated_structure_only_not_approval',
            'approval_reference':policy['approval_reference'],
            'runtime_application':'not_enabled','regulatory_compliance_claim':False,
            'missing_priority_behavior':'needs_review_not_default_rating',
            'outside_behavior':'only_explicit_outside_rules_no_automatic_safe_or_violation',
            'identity_permission_behavior':'not_inferred_from_appearance',
            'presence_is_not_crossing':True,'evidence_export_allowed':False}

def evaluate_configured_rules(doc,persons,positions,*,camera_id,policy_sha256,permissions=None):
    """Pure local evaluation, not owner approval or enabled HTTP safety verdict.
    Position input is explicit per-zone: inside/outside/boundary/unknown.
    Permissions are explicit zone/person claims, never guessed from pixels.
    """
    policy,sha=validate_policy(doc)
    if sha!=policy_sha256 or camera_id!=policy['camera_id']:raise ValueError('Exact policy/camera binding required')
    permissions=permissions or {};output=[]
    ids=[p.get('id')for p in persons]
    if any(not isinstance(i,str)or not i for i in ids)or len(ids)!=len(set(ids)):raise ValueError('Unique person IDs required')
    for person in persons:
        if set(person)!={'id','helmet','vest'}or not isinstance(person['id'],str)or not person['id']or any(person[k]not in ('present','absent','unknown')for k in ('helmet','vest')):raise ValueError('Exact observed person PPE required')
        pos=positions.get(person['id'],{})
        if set(pos)-{z['id']for z in policy['zones']}:raise ValueError('Unknown zone in position claims')
        findings=[];evaluations=[]
        def apply(rule,zone,applicability,access_mode=None):
            check=rule['check'];state='not_applicable';reason='outside_rule_area'
            if applicability in ('unknown','boundary'):
                state='needs_review';reason='position_'+applicability
            elif applicability=='inside':
                if check=='access':
                    permission=permissions.get(person['id'],{}).get(zone)
                    if access_mode=='no_entry_all':state='observed_violation';reason='presence_in_no_entry_area_not_crossing'
                    elif permission=='authorised':state='no_observed_violation';reason='explicit_authorisation_claim'
                    elif permission=='not_authorised':state='observed_violation';reason='explicit_no_authorisation_claim'
                    else:state='needs_review';reason='permission_unresolved_not_inferred'
                else:
                    observation=person['helmet'if check=='helmet_worn'else'vest']
                    state={'present':'no_observed_violation','absent':'observed_violation','unknown':'needs_review'}[observation]
                    reason='visual_observation_'+observation+'_not_certification'
            row={'rule_id':rule['id'],'zone_id':zone,'status':state,'reason':reason,'priority':rule['priority']if state=='observed_violation'else None}
            if state=='observed_violation'and rule['priority']is None:row['rating_status']='not_configured_needs_review'
            evaluations.append(row)
            if state in ('observed_violation','needs_review'):findings.append(row)
        states=[]
        for zone in policy['zones']:
            state=pos.get(zone['id'],'unknown')
            if state not in ('inside','outside','boundary','unknown'):raise ValueError('Explicit position state required')
            states.append(state)
            for rule in zone['rules']:apply(rule,zone['id'],state,zone['access_mode'])
        outside='unknown'if any(s in ('unknown','boundary')for s in states)else('outside'if'inside'in states else'inside')
        for rule in policy['outside_rules']:apply(rule,None,outside)
        priorities=[f['priority']for f in findings if f['priority']is not None]
        highest=min(priorities,key=policy['priorities'].index)if priorities else None
        needs_review=any(f['status']=='needs_review'or f.get('rating_status')for f in findings)
        output.append({'person_id':person['id'],'findings':findings,'evaluations':evaluations,
                       'highest_configured_priority':highest,'needs_review':needs_review,
                       'summary':'needs_review'if needs_review else('observed_violations_under_configured_rules'if findings else'no_observed_violation_under_evaluated_rules'if any(e['status']!='not_applicable'for e in evaluations)else'no_applicable_rules_evaluated'),
                       'safe':None,'compliant':None})
    return {'policy_id':policy['policy_id'],'version':policy['version'],'policy_sha256':sha,
            'camera_id':camera_id,'scope':policy['scope'],'application_status':'local_configuration_evaluation_not_approved_release',
            'persons':output,'evidence_export_allowed':False,'regulatory_compliance_claim':False}
