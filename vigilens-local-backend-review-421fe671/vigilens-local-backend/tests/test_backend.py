import io,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from core import AuditError,decode_image,validate_zones,memberships
from app import create_app

P=[{'x':.1,'y':.2},{'x':.6,'y':.2},{'x':.6,'y':.8},{'x':.1,'y':.8}]
Z=[{'id':'zone-1','name':'Crane Zone','hazard':True,'points':P}]
PERSON=[{'x':.5,'y':.1},{'x':.58,'y':.1},{'x':.58,'y':.4},{'x':.5,'y':.4}]
def png(size=(128,72),colour='white'):
    b=io.BytesIO();Image.new('RGB',size,colour).save(b,'PNG');return b.getvalue()
def manifest(data=None):
    data=data or png()
    return {'image_digest':decode_image(data,'image/png').digest,'zones':Z,'audit':{'persons':[{'id':'person-4','polygon':PERSON,'helmet':'present','vest':'present','findings':[]}]}}
def post(c,data=None,zones=None,key='one'):
    return c.post('/audit',files={'image':('fixture.png',data or png(),'image/png')},data={'zones':json.dumps(Z if zones is None else zones)},headers={'Idempotency-Key':key})

@pytest.mark.parametrize('value',[True,False,float('nan'),float('inf'),-0.1,1.1,'0.2',None])
def test_bad_coordinate(value):
    z=json.loads(json.dumps(Z));z[0]['points'][0]['x']=value
    with pytest.raises(AuditError):validate_zones(z)
@pytest.mark.parametrize('points',[[{'x':0,'y':0}]*3,[{'x':0,'y':0},{'x':1,'y':1},{'x':0,'y':1},{'x':1,'y':0}],P+[P[0]],P[:2]])
def test_invalid_polygons(points):
    with pytest.raises(AuditError):validate_zones([dict(Z[0],points=points)])
def test_empty_zones(): assert validate_zones('[]')==[]
def test_duplicate_zone_id():
    with pytest.raises(AuditError):validate_zones(Z+Z)
def test_person4_known_inside(): assert memberships(PERSON,Z)['display_zone_id']=='zone-1'
def test_unknown_is_not_outside(): assert memberships(PERSON,Z,False)['status']=='unknown'
def test_boundary_inside():
    p=[{'x':0,'y':0},{'x':.2,'y':0},{'x':.2,'y':.2},{'x':0,'y':.2}]
    assert memberships(p,Z)['display_zone_id']=='zone-1'
def test_overlap_all_and_tie():
    z=Z+[dict(Z[0],id='zone-2',hazard=False)]
    assert memberships(PERSON,z)['zone_ids']==['zone-1','zone-2']
def test_mime_mismatch():
    with pytest.raises(AuditError):decode_image(png(),'image/jpeg')
def test_corrupt_image():
    with pytest.raises(AuditError):decode_image(b'not an image','image/png')
def test_truncated_image():
    with pytest.raises(AuditError):decode_image(png()[:40],'image/png')
def test_dimension_cap():
    with pytest.raises(AuditError):decode_image(png((4097,1)),'image/png')
def test_missing_fixture_fails_closed():
    c=TestClient(create_app());r=post(c);assert r.status_code==503;assert r.json()['error']['code']=='FIXTURE_NOT_CONFIGURED'
def test_exact_fixture_safe_response():
    r=post(TestClient(create_app(manifest())));assert r.status_code==200
    x=r.json();assert x['source']=='fixture';assert x['created_at'] is None
    assert x['evidence_image'] is None and x['evidence_status']=='unavailable' and not x['evidence_export_allowed']
    assert x['persons'][0]['zone_id']=='zone-1'
def test_wrong_photo_rejected(): assert post(TestClient(create_app(manifest())),png(colour='red')).status_code==422
def test_same_ids_different_geometry_rejected():
    z=json.loads(json.dumps(Z));z[0]['points'][0]['x']=.12
    assert post(TestClient(create_app(manifest())),zones=z).status_code==422
def test_no_zones_not_silent_filter(): assert post(TestClient(create_app(manifest())),zones=[]).status_code==422
def test_idempotent_repeat():
    c=TestClient(create_app(manifest()));assert post(c).json()==post(c).json()
def test_no_evidence_for_any_id():
    r=TestClient(create_app()).get('/evidence/anything.png');assert r.status_code==404 and 'error' in r.json()
def test_missing_fields_error_envelope():
    r=TestClient(create_app()).post('/audit');assert r.status_code==400 and 'error' in r.json()
def test_cors():
    c=TestClient(create_app());h={'Origin':'http://localhost:5173','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'Idempotency-Key,Content-Type'}
    r=c.options('/audit',headers=h);assert r.status_code==200 and r.headers['access-control-allow-origin']=='http://localhost:5173'
    h['Origin']='https://unapproved.invalid';r=c.options('/audit',headers=h);assert 'access-control-allow-origin' not in r.headers
from rules import assess

def person(helmet='present',vest='present',known=True):
    return dict(id='p',polygon=PERSON,helmet=helmet,vest=vest,contact_known=known)
def test_unknown_ppe_not_compliant():
    x=assess(person(vest='unknown'),Z)
    assert x['assessment_status']=='needs_human_review' and x['worst_severity'] is None
    assert x['findings'][0]['rule_id']=='VEST_UNKNOWN' and x['findings'][0]['severity'] is None

def test_unknown_contact_no_outside_low():
    x=assess(person(helmet='absent',known=False),Z)
    assert x['zone_membership_status']=='unknown' and not any(f['severity']=='Low' for f in x['findings'])
def test_all_overlapping_rules_preserved():
    z=Z+[dict(Z[0],id='restricted',hazard=False)]
    x=assess(person(helmet='absent'),z)
    assert {f['rule_id'] for f in x['findings']}=={'NO_HELMET_IN_HAZARD','NO_HELMET_IN_RESTRICTED','INTRUSION_RESTRICTED'}
    assert len({f['id'] for f in x['findings']})==3 and x['worst_severity']=='Critical'
def test_no_zone_run_not_clearance():
    x=assess(person(helmet='absent'),[])
    assert not x['zone_checks_performed'] and x['assessment_status']=='no_listed_violations'
def test_future_real_audit_disabled():
    assert not TestClient(create_app()).get('/health').json()['real_analysis_enabled']

def test_idempotency_conflict_service():
    from app import FixtureService
    im=decode_image(png(),'image/png'); s=FixtureService(manifest());s.audit(im,validate_zones(Z),'one')
    s.manifest=manifest(png(colour='red'))
    with pytest.raises(AuditError) as e:s.audit(decode_image(png(colour='red'),'image/png'),validate_zones(Z),'one')
    assert e.value.code=='IDEMPOTENCY_CONFLICT'

def test_rotated_exif_rejected_pending_preview_agreement():
    b=io.BytesIO();im=Image.new('RGB',(128,72),'white');ex=im.getexif();ex[274]=6;im.save(b,'JPEG',exif=ex)
    from app import FixtureService
    with pytest.raises(AuditError) as e:FixtureService(manifest()).audit(decode_image(b.getvalue(),'image/jpeg'),Z,'k')
    assert e.value.code=='IMAGE_ORIENTATION_UNSUPPORTED'
