"""Private operator-zone geometry, not safety policy or inferred ground contact."""
import hashlib,json,time
from core import validate_zones,contains,on_segment,area
from .contacts import ContactStore
MAX_EVENTS=128

def canonical_zones(zones):
    return validate_zones(zones)

def zone_digest(zones):
    return hashlib.sha256(json.dumps(zones,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def assess_zones(persons,zones,contacts):
    zones=canonical_zones(zones)
    out=[]
    for person in persons:
        row={'person_id':person['id'],'zone_ids':None,'display_zone_id':None,
             'status':'not_configured'if not zones else'needs_manual_contact_review',
             'basis':'operator_zones_and_current_manual_contact_not_automatic',
             'safety_decision':False}
        event=contacts.get(person['id'])
        if zones and event:
            claim=event['claim'];point={'x':claim['point'][0],'y':claim['point'][1]}
            # Exact polygon-edge ambiguity abstains; no invented proximity threshold.
            boundary=[z['id']for z in zones if any(on_segment(a,b,point)for a,b in zip(z['points'],z['points'][1:]+z['points'][:1]))]
            if boundary:
                row.update(status='boundary_needs_review',boundary_zone_ids=sorted(boundary),contact_event_id=event['event_id'])
            else:
                found=[z for z in zones if contains(point,z['points'])]
                # Display order is deterministic, never a policy-priority claim.
                found.sort(key=lambda z:(area(z['points']),z['id']))
                row.update(status='operator_contact_geometry',zone_ids=[z['id']for z in found],
                           display_zone_id=found[0]['id']if found else None,contact_event_id=event['event_id'])
        out.append(row)
    return out

class ZoneStore:
    def __init__(self,service):self.service=service
    def connect(self):
        c=self.service.connect()
        c.execute('CREATE TABLE IF NOT EXISTS zone_events(id INTEGER PRIMARY KEY,source TEXT,result_sha TEXT,owner_hash TEXT,zones TEXT,zones_sha TEXT,reviewer TEXT,at REAL)')
        return c
    def latest(self,source,result_sha,owner):
        c=self.connect()
        try:row=c.execute('SELECT id,zones,zones_sha,reviewer,at FROM zone_events WHERE source=? AND result_sha=? AND owner_hash=? ORDER BY id DESC LIMIT 1',(source,result_sha,hashlib.sha256(owner.encode()).hexdigest())).fetchone()
        finally:c.close()
        if row is None:return None
        zones=canonical_zones(json.loads(row[1]))
        if zone_digest(zones)!=row[2]:raise ValueError('Stored zones changed')
        return {'event_id':row[0],'zones':zones,'zones_sha256':row[2],'reviewer_label':row[3],'at':row[4]}
    def append(self,source,result_sha,owner,zones,reviewer):
        zones=canonical_zones(zones)
        if not isinstance(reviewer,str)or not 1<=len(reviewer.strip())<=80:raise ValueError('Bounded reviewer label required')
        reviewer=reviewer.strip();existing=self.latest(source,result_sha,owner)
        if existing and existing['zones']==zones and existing['reviewer_label']==reviewer:return existing
        c=self.connect()
        try:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT count(*) FROM zone_events').fetchone()[0]>=MAX_EVENTS:raise ValueError('Zone history full; preserve history')
            c.execute('INSERT INTO zone_events(source,result_sha,owner_hash,zones,zones_sha,reviewer,at) VALUES(?,?,?,?,?,?,?)',(source,result_sha,hashlib.sha256(owner.encode()).hexdigest(),json.dumps(zones,sort_keys=True),zone_digest(zones),reviewer,time.time()));c.commit()
        finally:c.close()
        return self.latest(source,result_sha,owner)
