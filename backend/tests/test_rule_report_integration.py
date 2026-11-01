import copy,sqlite3
import pytest
from test_fresh_upload_routes import material,prepare,acknowledge,report,OWNER
from test_fresh_zones import ZONE,submit,contact
from fresh_review.pipeline import digest
from fresh_review.policy import FORMAT

def config():
 return {'format':FORMAT,'policy_id':'generated-test-settings','version':'1','scope':'illustrative_demo','camera_id':'generated-camera','approval_reference':'test-fixture-not-owner-approval','priorities':[],
 'zones':[{'id':ZONE['id'],'name':ZONE['name'],'points':copy.deepcopy(ZONE['points']),'access_mode':'no_entry_all','rules':[{'id':'entry','check':'access','priority':None},{'id':'vest','check':'vest_worn','priority':None}]}],'outside_rules':[]}
def rules(c,frame,job,patch=None):
 zones=c.get('/fresh-review/'+frame.digest+'/zone-review').json()['zone_snapshot']
 payload={'source_digest':frame.digest,'result_sha256':digest(job['result']),'zones_sha256':zones['zones_sha256'],'configuration':config()}
 if patch:payload.update(patch)
 return c.post('/fresh-review/'+frame.digest+'/rule-review',json=payload)

def test_complete_private_rule_report_source_geometry_and_observations(material,monkeypatch):
 # Downstream-mechanism test: treat the stored legacy person as clean-basis so this still exercises the display/rule path. Real legacy behavior (withheld) is covered in test_ppe_basis and test_fresh_upload_routes.
 monkeypatch.setattr('fresh_review.ppe_basis.basis_of',lambda person:'clean_crop')
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x)
 assert report(c,x,job).json()['configured_rule_review']['status']=='not_configured'
 submit(c,frame,job);first=rules(c,frame,job);assert first.status_code==200
 assert rules(c,frame,job).json()==first.json()
 # No contact is not proof of no entry.
 out=report(c,x,job).json()['configured_rule_review']
 assert all(f['status']=='needs_review'for f in out['persons'][0]['findings'])
 contact(c,frame)
 out=report(c,x,job).json()['configured_rule_review']
 assert {f['rule_id']for f in out['persons'][0]['findings']}=={'entry','vest'}
 assert all(f['status']=='observed_violation'and f['priority']is None for f in out['persons'][0]['findings'])
 assert out['persons'][0]['needs_review']and out['persons'][0]['safe']is None
 assert out['approval_status']=='not_verified_by_configuration'and not out['evidence_export_allowed']
 assert out['source_digest']==frame.digest and out['result_sha256']==digest(job['result'])
 assert len(calls)==2
 # Changing geometry invalidates settings, preserves history, never silently reuses rules.
 submit(c,frame,job,[])
 assert report(c,x,job).json()['configured_rule_review']['status']=='zone_geometry_changed_reconfigure_rules'
 db=sqlite3.connect(p.path);assert db.execute('SELECT count(*) FROM rule_events').fetchone()[0]==1;db.close()

def test_report_rules_use_hidden_evidence_as_unknown(material):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x);submit(c,frame,job);rules(c,frame,job);contact(c,frame)
 identity='fresh:'+frame.digest+':'+digest(job['result'])
 payload={'assessment_id':identity,'source_digest':frame.digest,'output_sha256':x['output_sha256'],'regions_digest':x['regions_digest'],'persons':{'0':{'exact_source_confirmed':True,'face_coverage_checked':True,'head_evidence_visible':True,'torso_evidence_visible':False}}}
 out=c.post('/fresh-private-report/'+x['session_id'],json=payload).json()
 assert out['persons'][0]['provider_vest_observation']=='absent'
 assert out['persons'][0]['report_display_vest']=='unknown'
 finding=next(f for f in out['configured_rule_review']['persons'][0]['findings']if f['rule_id']=='vest')
 assert finding['status']=='needs_review'
 assert len(calls)==2

@pytest.mark.parametrize('patch',[{'source_digest':'0'*64},{'result_sha256':'0'*64},{'zones_sha256':'0'*64},{'extra':True}])
def test_rule_review_rejects_changed_binding(material,patch):
 p,raw,frame,calls,c,job=material;prepare(c,raw,frame);submit(c,frame,job)
 assert rules(c,frame,job,patch).status_code==409 and len(calls)==2

def test_rule_geometry_and_tampering(material):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x);submit(c,frame,job)
 doc=config();doc['zones'][0]['points'][0]={'x':.01,'y':.2}
 assert rules(c,frame,job,{'configuration':doc}).status_code==409
 assert rules(c,frame,job).status_code==200
 db=sqlite3.connect(p.path);db.execute("UPDATE rule_events SET policy_sha='changed'");db.commit();db.close()
 assert report(c,x,job).status_code==409
 assert len(calls)==2
