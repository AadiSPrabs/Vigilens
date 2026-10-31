"""Bounded reusable camera geometry. Scene equivalence is an operator claim.
No automatic registration, transform, rule/permission transfer or source approval.
"""
import hashlib,json,time,re
from .pipeline import digest
from .zones import canonical_zones,zone_digest,ZoneStore

FORMAT='vigilens.camera-zone-template.v1'

def binding(value,image):
    keys={'camera_id','scene_revision','width','height','coordinate_space','transform'}
    if not isinstance(value,dict)or set(value)!=keys:raise ValueError('Exact scene/resolution/transform binding required')
    for k in ('camera_id','scene_revision'):
        if not isinstance(value[k],str)or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}',value[k]):raise ValueError('Bounded immutable camera/scene identifier required')
    if any(type(value[k])is not int or value[k]!=image[k]for k in ('width','height')):raise ValueError('Exact upright raster size required')
    if value['coordinate_space']!='normalized_upright_source_v1'or value['transform']!='identity':raise ValueError('No resize/crop/rotation/homography reuse supported')
    return dict(value)

class CameraZoneStore:
    def __init__(self,service):self.service=service
    def connect(self):
        c=self.service.connect()
        c.execute('CREATE TABLE IF NOT EXISTS camera_zone_templates(id TEXT PRIMARY KEY,owner_hash TEXT,body TEXT,body_sha TEXT,at REAL)')
        return c
    def read(self,identity,owner):
        c=self.connect()
        try:row=c.execute('SELECT body,body_sha FROM camera_zone_templates WHERE id=? AND owner_hash=?',(identity,hashlib.sha256(owner.encode()).hexdigest())).fetchone()
        finally:c.close()
        if row is None:raise ValueError('No camera template for this browser')
        doc=json.loads(row[0])
        if digest(doc)!=row[1]or digest({'owner':hashlib.sha256(owner.encode()).hexdigest(),'template':doc})!=identity or canonical_zones(doc['zones'])!=doc['zones']or zone_digest(doc['zones'])!=doc['zones_sha256']:raise ValueError('Camera template changed')
        original=self.service.read(doc['source_digest'])
        if original is None or digest(original['result'])!=doc['result_sha256']:raise ValueError('Template original binding changed')
        binding(doc['camera_binding'],original['result']['image'])
        return doc
    def save(self,source,job,owner,camera,reviewer):
        camera=binding(camera,job['result']['image'])
        zones=ZoneStore(self.service).latest(source,digest(job['result']),owner)
        if zones is None:raise ValueError('Draw explicit geometry first')
        if not isinstance(reviewer,str)or not 1<=len(reviewer.strip())<=80:raise ValueError('Bounded reviewer required')
        doc={'format':FORMAT,'camera_binding':camera,'source_digest':source,'result_sha256':digest(job['result']),
             'zone_event_id':zones['event_id'],'zones':zones['zones'],'zones_sha256':zones['zones_sha256'],
             'reviewer_label':reviewer.strip(),'basis':'operator_confirmed_fixed_scene_not_automatic_registration'}
        identity=digest({'owner':hashlib.sha256(owner.encode()).hexdigest(),'template':doc});c=self.connect()
        try:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute('SELECT 1 FROM camera_zone_templates WHERE id=?',(identity,)).fetchone():
                if c.execute('SELECT count(*) FROM camera_zone_templates').fetchone()[0]>=64:raise ValueError('Camera template history full')
                c.execute('INSERT INTO camera_zone_templates VALUES(?,?,?,?,?)',(identity,hashlib.sha256(owner.encode()).hexdigest(),json.dumps(doc,sort_keys=True),digest(doc),time.time()))
            c.commit()
        finally:c.close()
        self.read(identity,owner)
        return identity
    def apply(self,identity,source,job,owner,camera,reviewer):
        doc=self.read(identity,owner)
        if binding(camera,job['result']['image'])!=doc['camera_binding']:raise ValueError('Camera scene or raster changed; redraw zones')
        return ZoneStore(self.service).append(source,digest(job['result']),owner,doc['zones'],reviewer)
