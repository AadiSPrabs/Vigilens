import copy,io,sqlite3
import pytest
from PIL import Image
from core import decode_image
from fresh_review.pipeline import digest
from test_fresh_upload_routes import material,prepare,OWNER
from test_fresh_zones import submit,ZONE

def camera():return {'camera_id':'synthetic-fixed-camera','scene_revision':'scene1','width':80,'height':80,'coordinate_space':'normalized_upright_source_v1','transform':'identity'}
def action(c,frame,job,operation,**extra):
 body={'source_digest':frame.digest,'result_sha256':digest(job['result']),'camera_binding':camera(),'reviewer_label':'synthetic operator','fixed_scene_confirmed':True,**extra}
 return c.post('/fresh-review/'+frame.digest+'/camera-zones/'+operation,json=body)

def test_draw_once_reuse_new_source_no_contact_or_rule_transfer(material):
 from test_fresh_upload_pipeline import add_approval
 p,raw,frame,calls,c,job=material
 assert action(c,frame,job,'save').status_code==409
 prepare(c,raw,frame);submit(c,frame,job)
 first=action(c,frame,job,'save');assert first.status_code==200
 identity=first.json()['template_id'];assert action(c,frame,job,'save').json()['template_id']==identity
 out=io.BytesIO();Image.new('RGB',(80,80),'green').save(out,'PNG');new=out.getvalue();f=decode_image(new,'image/png')
 add_approval(p,f.digest,{'size':[80,80],'rights_reference':'generated-test','provider_upload_approved':True})
 r=c.post('/fresh-review-upload',files={'image':('generated.png',new,'image/png')},data={'zones':'[]'});assert r.status_code==200
 newjob=r.json();prepare(c,new,f);before=len(calls)
 applied=action(c,f,newjob,'apply',template_id=identity);assert applied.status_code==200
 doc=applied.json();assert len(calls)==before and doc['rules_or_contacts_transferred']is False
 assert doc['zone_review']['zone_snapshot']['zones']==[ZONE]
 assert doc['zone_review']['persons'][0]['status']=='needs_manual_contact_review'
 assert doc['template']['source_digest']==frame.digest and doc['zone_review']['source_digest']==f.digest
 # A historical exact template remains explicit, not silently changed by source edits.
 submit(c,frame,job,[])
 assert action(c,f,newjob,'apply',template_id=identity).json()['zone_review']['zone_snapshot']['zones']==[ZONE]

@pytest.mark.parametrize('patch',[{'scene_revision':'scene2'},{'camera_id':'other'},{'width':160},{'height':True},{'transform':'crop'},{'coordinate_space':'raw_exif'}])
def test_camera_rejects_changed_scene_size_transform(material,patch):
 p,raw,frame,calls,c,job=material;prepare(c,raw,frame);submit(c,frame,job)
 identity=action(c,frame,job,'save').json()['template_id'];b=camera();b.update(patch)
 assert action(c,frame,job,'apply',template_id=identity,camera_binding=b).status_code==409 and len(calls)==2

def test_camera_tamper_missing_confirmation_and_owner(material):
 p,raw,frame,calls,c,job=material;prepare(c,raw,frame);submit(c,frame,job)
 assert action(c,frame,job,'save',fixed_scene_confirmed=1).status_code==409
 identity=action(c,frame,job,'save').json()['template_id']
 from fresh_review.camera_zones import CameraZoneStore
 with pytest.raises(ValueError):CameraZoneStore(p).read(identity,'different_browser')
 db=sqlite3.connect(p.path);db.execute("UPDATE camera_zone_templates SET body_sha='changed'");db.commit();db.close()
 assert action(c,frame,job,'apply',template_id=identity).status_code==409 and len(calls)==2
