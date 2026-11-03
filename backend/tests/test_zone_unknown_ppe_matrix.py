"""Reviewer reconciliation probes: unknown-PPE behavior across hazard/nonhazard/mixed zones."""
from PIL import Image
from fresh_review.frontend_audit import to_frontend_audit
from fresh_review.masks import encode_mask
from test_frontend_audit_route import person, result

HAZ = [{'id': 'zh', 'name': 'Haz', 'hazard': True,
        'points': [{'x': 0.1, 'y': 0.5}, {'x': 0.9, 'y': 0.5}, {'x': 0.9, 'y': 0.95}, {'x': 0.1, 'y': 0.95}]}]
NON = [{'id': 'zn', 'name': 'NonHaz', 'hazard': False,
        'points': [{'x': 0.1, 'y': 0.5}, {'x': 0.9, 'y': 0.5}, {'x': 0.9, 'y': 0.95}, {'x': 0.1, 'y': 0.95}]}]

def masked(pid, box, helmet):
    m = Image.new('L', (box[2]-box[0], box[3]-box[1]), 0)
    for y in range(35, m.size[1]):
        for x in range(m.size[0]//3, 2*m.size[0]//3):
            m.putpixel((x, y), 255)
    return person(pid, box=box, helmet=helmet, vest='present', eligible=True,
                  mask=encode_mask(m, list(box), [100, 100]))

def view(prs, z):
    return to_frontend_audit(result(*prs), audit_id='fresh:x', job_state='completed',
                             source_digest='ab'*32, zones=z)

def zone_findings(q):
    return [(f['rule_id'], f['kind']) for f in q['findings'] if f['rule_id'].startswith(('NO_', 'INTRUSION'))]

def test_unknown_ppe_hazard_zone_no_zone_candidates():
    v = view([masked('0', (10, 50, 30, 90), 'unknown')], HAZ)
    q = v['persons'][0]
    assert zone_findings(q) == []
    assert q['zone_membership_status'] == 'known' and q['zone_ids'] == ['zh']
    assert any(f['rule_id'] == 'helmet_reading' and f['kind'] == 'uncertainty' for f in q['findings'])
    assert v['zones_applied'] is True  # membership known; PPE state does not gate this flag

def test_unknown_ppe_nonhazard_zone_still_emits_location_only_intrusion():
    v = view([masked('0', (10, 50, 30, 90), 'unknown')], NON)
    q = v['persons'][0]
    assert zone_findings(q) == [('INTRUSION_RESTRICTED', 'uncertainty')]
    f = next(f for f in q['findings'] if f['rule_id'] == 'INTRUSION_RESTRICTED')
    assert 'deterministic class Medium' in f['message'] and 'entry-forbidden' in f['message']
    assert 'helmet' not in f['message'].lower().split('Inputs:')[0]  # rule text itself carries no PPE claim
    assert q['worst_severity'] is None

def test_absent_ppe_hazard_zone_emits_no_helmet_only():
    v = view([masked('0', (10, 50, 30, 90), 'absent')], HAZ)
    assert zone_findings(v['persons'][0]) == [('NO_HELMET_IN_HAZARD', 'uncertainty')]

def test_absent_ppe_nonhazard_zone_emits_intrusion_and_no_helmet():
    v = view([masked('0', (10, 50, 30, 90), 'absent')], NON)
    assert sorted(zone_findings(v['persons'][0])) == [('INTRUSION_RESTRICTED', 'uncertainty'), ('NO_HELMET_IN_RESTRICTED', 'uncertainty')]

def test_mixed_persons_evaluated_independently():
    v = view([masked('0', (10, 50, 30, 90), 'unknown'), masked('1', (60, 50, 80, 90), 'absent')], HAZ)
    assert zone_findings(v['persons'][0]) == []
    assert zone_findings(v['persons'][1]) == [('NO_HELMET_IN_HAZARD', 'uncertainty')]
    assert v['zones_applied'] is True
