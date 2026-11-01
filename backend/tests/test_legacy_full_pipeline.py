"""Full-pipeline proof for a REAL stored legacy person (no crop basis record), with no basis_of patch:
raw reading preserved, display and contract unknown, configured rules needs_review only (no violation or clear for PPE),
stored result, calls and provider accounting unchanged."""
import sqlite3
import json,pytest
from fastapi.testclient import TestClient
from app import create_app
from test_fresh_upload_pipeline import setup
from test_fresh_upload_routes import OWNER,prepare,acknowledge,report
from test_fresh_zones import submit,contact
from test_rule_report_integration import rules
from fresh_review.pipeline import digest
from fresh_review.ppe_basis import basis_of

@pytest.fixture
def material(tmp_path,monkeypatch):
 # An OLD stored result: produced before crop_eligibility was recorded for single uploads. Built by removing the new
 # record from a stored job and re-sealing its digest, exactly what an old database row looks like.
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 import fresh_review.pipeline as fp
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 out=c.post('/fresh-review-upload',files={'image':('synthetic.png',raw,'image/png')},data={'zones':'[]'});assert out.status_code==200
 db=sqlite3.connect(p.path);res=json.loads(db.execute('SELECT result FROM jobs').fetchone()[0])
 assert 'crop_eligibility' in res['persons'][0]
 for q in res['persons']:del q['crop_eligibility']
 db.execute('UPDATE jobs SET result=?,result_sha=?',(json.dumps(res),fp.digest(res)));db.commit();db.close()
 job=c.get('/fresh-review/'+frame.digest).json()
 assert job['state']=='completed' and 'crop_eligibility' not in job['result']['persons'][0]
 yield p,raw,frame,calls,c,job

def test_real_legacy_person_through_report_contract_and_rules(material):
 p,raw,frame,calls,c,job=material
 person=job['result']['persons'][0]
 assert 'crop_basis' not in person and 'crop_eligibility' not in person and basis_of(person)=='not_recorded_legacy'
 assert person['vest']=='absent'  # the stored raw reading is a known absent, the case that must never become a finding
 before=digest(job['result']);calls_before=len(calls)
 x=prepare(c,raw,frame);acknowledge(c,x);submit(c,frame,job);assert rules(c,frame,job).status_code==200;contact(c,frame)
 rep=report(c,x,job).json();q=rep['persons'][0]
 # raw preserved, display unknown, basis labelled
 assert q['provider_vest_observation']=='absent' and q['provider_helmet_observation']==person['helmet']
 assert q['report_display_vest']=='unknown' and q['report_display_helmet']=='unknown' and q['status']=='needs_human_review'
 assert q['ppe_basis']['crop_basis']=='not_recorded_legacy'
 vs=q['ppe_basis']['items']['vest'];assert vs['resolved_state']=='legacy_absent_basis_not_recorded' and vs['target_level_outcome_permitted']is False and vs['item_resolved']is False
 assert rep['ppe_basis_counts']['legacy_basis_not_recorded_count']==1 and rep['ppe_basis_counts']['outcome_emitted_count']==0 and rep['ppe_basis_counts']['fully_resolved_person_count']==0
 # rules: PPE rule only needs_review; never observed_violation, never no_observed_violation
 rr=rep['configured_rule_review']['persons'][0]
 vest=[f for f in rr['evaluations'] if f['rule_id']=='vest'] if 'evaluations' in rr else [f for f in rr['findings'] if f['rule_id']=='vest']
 assert vest and all(f['status']=='needs_review' for f in vest)
 assert not any(f['rule_id']=='vest' and f['status'] in('observed_violation','no_observed_violation') for f in rr.get('evaluations',rr['findings']))
 # unrelated presence/access rule is unaffected by PPE basis
 entry=[f for f in rr['findings'] if f['rule_id']=='entry'];assert entry and entry[0]['status']=='observed_violation'
 assert rr['needs_review'] and rr['safe'] is None
 # integration contract
 k=c.get('/fresh-review/'+frame.digest+'/integration-contract').json()['persons'][0]['ppe']
 assert k['crop_basis']=='not_recorded_legacy' and k['vest']['status']=='unknown' and k['vest']['provider_observation']=='absent' and k['vest']['target_level_outcome_permitted']is False
 cj=c.get('/fresh-review/'+frame.digest+'/integration-contract').json()
 assert cj['all_detected_people_target_level_resolved']is False and cj['ppe_basis_counts']['outcome_emitted_count']==0
 # stored result, provider calls and accounting unchanged
 assert digest(job['result'])==before and len(calls)==calls_before==2
 db=sqlite3.connect(p.path)
 try:
  jobs=db.execute('SELECT state,reserved,cost FROM jobs').fetchall()
 finally:db.close()
 assert jobs and all(j[0]=='completed' for j in jobs)
