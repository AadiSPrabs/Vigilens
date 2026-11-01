"""Draft matrix only. Never called by API until builders accept policy and real inputs exist."""
from core import fail, memberships, polygon
ORDER={'Critical':3,'Medium':2,'Low':1}

def assess(person,zones):
    """Consume explicit PPE observations, not model narrative or confidence guesses."""
    for key in ('helmet','vest'):
        if person.get(key) not in ('present','absent','unknown'):
            fail('INVALID_OBSERVATION','PPE must be present, absent or unknown.')
    membership=memberships(person['polygon'],zones,person.get('contact_known',True))
    findings=[]
    def add(rule,kind,severity,zone,message):
        findings.append({'id':f"{person['id']}:{rule}:{zone or 'global'}",'rule_id':rule,'kind':kind,
            'severity':severity,'zone_id':zone,'message':message,
            'review_state':'needs_human_review' if kind=='uncertainty' else 'auto',
            'recheck_trace':[]})
    if membership['status']=='unknown':
        add('ZONE_MEMBERSHIP_UNKNOWN','uncertainty',None,None,'Ground contact is uncertain; zone membership needs review.')
    for item in ('helmet','vest'):
        if person[item]=='unknown':
            add(item.upper()+'_UNKNOWN','uncertainty',None,None,f'{item.capitalize()} could not be confirmed.')
    by_id={z['id']:z for z in zones}
    for zid in membership['zone_ids']:
        z=by_id[zid]
        if not z['hazard']:
            add('INTRUSION_RESTRICTED','violation','Medium',zid,'Person in an operator-defined entry-forbidden zone.')
        for item in ('helmet','vest'):
            if person[item]=='absent':
                suffix='HAZARD' if z['hazard'] else 'RESTRICTED'
                add('NO_'+item.upper()+'_IN_'+suffix,'violation','Critical' if z['hazard'] else 'Medium',zid,f'{item.capitalize()} absent in zone {zid}.')
    # No-zone run means zone checks not run, not confirmed outside.
    if zones and membership['status']=='known' and not membership['zone_ids']:
        for item in ('helmet','vest'):
            if person[item]=='absent':
                add('NO_'+item.upper()+'_OUTSIDE','violation','Low',None,f'{item.capitalize()} absent outside the configured zones.')
    severities=[f['severity'] for f in findings if f['severity'] is not None]
    needs_review=any(f['kind']=='uncertainty' for f in findings)
    return dict(person,zone_id=membership['display_zone_id'],zone_ids=membership['zone_ids'],
        zone_membership_status=membership['status'],zone_checks_performed=bool(zones),
        findings=findings,worst_severity=max(severities,key=ORDER.get) if severities else None,
        assessment_status='needs_human_review' if needs_review else ('violations_found' if findings else 'no_listed_violations'),
        ruleset_version='draft-unapproved')
