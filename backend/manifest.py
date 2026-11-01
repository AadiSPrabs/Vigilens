"""Validate manually authored fixtures before any API success. No model claims."""
from core import fail, polygon, validate_zones, memberships

def validate_manifest(m):
    def bad(message):fail('INVALID_FIXTURE',message,500)
    if not isinstance(m,dict) or not isinstance(m.get('image_digest'),str) or len(m['image_digest'])!=64 or any(c not in '0123456789abcdef' for c in m['image_digest']):bad('Fixture needs a decoded image SHA256.')
    zones=validate_zones(m.get('zones'))
    audit=m.get('audit')
    if not isinstance(audit,dict) or not isinstance(audit.get('persons'),list):bad('Fixture needs persons array.')
    zid={z['id'] for z in zones};persons=set();findings=set()
    for p in audit['persons']:
        if not isinstance(p,dict) or not isinstance(p.get('id'),str) or not p['id'] or p['id'] in persons:bad('Person IDs must be unique nonempty strings.')
        persons.add(p['id']);polygon(p.get('polygon'))
        if type(p.get('contact_known',True)) is not bool:bad('contact_known must be boolean.')
        for item in ('helmet','vest'):
            if p.get(item) not in ('present','absent','unknown'):bad('Invalid PPE status.')
        fs=p.get('findings')
        if not isinstance(fs,list):bad('Person findings must be an array.')
        uncertainty=False
        for f in fs:
            if not isinstance(f,dict):bad('Invalid finding.')
            fid=f.get('id')
            if not isinstance(fid,str) or not fid or fid in findings:bad('Finding IDs must be stable, unique nonempty strings.')
            findings.add(fid)
            if not isinstance(f.get('rule_id'),str) or not f['rule_id']:bad('Finding needs rule_id.')
            if f.get('kind') not in ('violation','uncertainty'):bad('Finding needs kind.')
            if 'zone_id' not in f or (f['zone_id'] is not None and f['zone_id'] not in zid):bad('Finding zone_id is invalid.')
            if f.get('kind')=='uncertainty':
                uncertainty=True
                if f.get('severity','missing') is not None or f.get('review_state')!='needs_human_review':bad('Uncertainty needs null severity and human review.')
            elif f.get('severity') not in ('Critical','Medium','Low'):bad('Violation severity is invalid.')
            if f.get('review_state') not in ('auto','needs_human_review'):bad('Invalid review state.')
            if not isinstance(f.get('message'),str) or not isinstance(f.get('recheck_trace'),list) or any(not isinstance(t,str) for t in f['recheck_trace']):bad('Message and trace must be plain strings.')
        for item in ('helmet','vest'):
            if p[item]=='unknown' and not any(f['kind']=='uncertainty' and f['rule_id']==item.upper()+'_UNKNOWN' for f in fs):bad('Unknown PPE needs its explicit uncertainty finding.')
        if not p.get('contact_known',True) and not any(f['kind']=='uncertainty' and f['rule_id']=='ZONE_MEMBERSHIP_UNKNOWN' for f in fs):bad('Unknown contact needs a zone review finding.')
    return m
