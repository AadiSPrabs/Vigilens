"""Small source-bound operator rule snapshots for private reports, never approval.
No default priorities, reusable camera calibration or live provider calls.
"""
import hashlib,json,time
from .policy import validate_policy,evaluate_configured_rules

class RuleStore:
    def __init__(self,service):self.service=service
    def connect(self):
        c=self.service.connect()
        c.execute('CREATE TABLE IF NOT EXISTS rule_events(id INTEGER PRIMARY KEY,source TEXT,result_sha TEXT,owner_hash TEXT,zone_sha TEXT,policy TEXT,policy_sha TEXT,at REAL)')
        return c
    def latest(self,source,result_sha,owner):
        c=self.connect()
        try:row=c.execute('SELECT id,zone_sha,policy,policy_sha,at FROM rule_events WHERE source=? AND result_sha=? AND owner_hash=? ORDER BY id DESC LIMIT 1',(source,result_sha,hashlib.sha256(owner.encode()).hexdigest())).fetchone()
        finally:c.close()
        if row is None:return None
        policy,sha=validate_policy(json.loads(row[2]))
        if sha!=row[3]:raise ValueError('Stored rule snapshot changed')
        return {'event_id':row[0],'zones_sha256':row[1],'configuration':policy,'policy_sha256':sha,'at':row[4],'status':'operator_configuration_not_verified_approval'}
    def append(self,source,result_sha,owner,zone_snapshot,doc):
        policy,sha=validate_policy(doc)
        # A matching name alone is not camera calibration. Require exact current polygons.
        expected={z['id']:(z['name'],z['points'])for z in zone_snapshot['zones']}
        actual={z['id']:(z['name'],z['points'])for z in policy['zones']}
        if expected!=actual:raise ValueError('Rules must match the complete current zone geometry')
        old=self.latest(source,result_sha,owner)
        if old and old['policy_sha256']==sha and old['zones_sha256']==zone_snapshot['zones_sha256']:return old
        c=self.connect()
        try:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT count(*) FROM rule_events').fetchone()[0]>=128:raise ValueError('Rule history full; preserve history')
            c.execute('INSERT INTO rule_events(source,result_sha,owner_hash,zone_sha,policy,policy_sha,at) VALUES(?,?,?,?,?,?,?)',(source,result_sha,hashlib.sha256(owner.encode()).hexdigest(),zone_snapshot['zones_sha256'],json.dumps(policy,sort_keys=True),sha,time.time()));c.commit()
        finally:c.close()
        return self.latest(source,result_sha,owner)

def evaluate_report_rules(snapshot,zone_view,persons):
    """Consume only report-visible observations. Hidden evidence remains unknown."""
    if snapshot is None:return {'status':'not_configured','findings':None,'evidence_export_allowed':False}
    current=zone_view['zone_snapshot']
    if current is None or snapshot['zones_sha256']!=current['zones_sha256']:
        return {'status':'zone_geometry_changed_reconfigure_rules','findings':None,'evidence_export_allowed':False}
    policy=snapshot['configuration'];positions={}
    for row in zone_view['persons']:
        # On a boundary or missing contact do not claim an outside position.
        known=row['status']=='operator_contact_geometry'
        positions[row['person_id']]={z['id']:('inside'if z['id']in row['zone_ids']else'outside')if known else'unknown'for z in policy['zones']}
    observed=[{'id':p['person_id'],'helmet':p['report_display_helmet'],'vest':p['report_display_vest']}for p in persons]
    out=evaluate_configured_rules(policy,observed,positions,camera_id=policy['camera_id'],policy_sha256=snapshot['policy_sha256'])
    out.update(configuration_scope=policy['scope'],status='private_operator_rules_evaluated_not_safety_clearance',configuration_event_id=snapshot['event_id'],
               source_digest=zone_view['source_digest'],result_sha256=zone_view['result_sha256'],
               zones_sha256=current['zones_sha256'],camera_binding='operator_label_only_not_verified_camera_reuse',
               approval_status='not_verified_by_configuration',position_basis='current_manual_contact_claims',
               observation_basis='private_report_visible_observations',report_visible_observations=observed,provider_calls_this_request=0)
    return out
