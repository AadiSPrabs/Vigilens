import copy,json,sqlite3
import pytest
from test_fresh_upload_routes import material,prepare,acknowledge,report,OWNER
from fresh_review.pipeline import digest
from fresh_review.zones import assess_zones,ZoneStore
ZONE={'id':'yard','name':'Yard','hazard':True,'points':[{'x':.05,'y':.2},{'x':.4,'y':.2},{'x':.4,'y':.9},{'x':.05,'y':.9}]}
def submit(c,frame,job,zones=None):
 return c.post('/fresh-review/'+frame.digest+'/zone-review',json={'source_digest':frame.digest,'result_sha256':digest(job['result']),'zones':[ZONE]if zones is None else zones,'reviewer_label':'synthetic reviewer'})
def contact(c,frame):
 return c.post('/fresh-review/'+frame.digest+'/contact',json={'person_id':'0','point':[.1,.5],'exact_source_confirmed':True,'boots_ground_visible':True,'reviewer_label':'synthetic operator'})
def test_zone_geometry_abstains_and_overlaps():
 p=[{'id':'p'}];event={'claim':{'point':[.1,.5]},'event_id':7}
 assert assess_zones(p,[],{})[0]['status']=='not_configured'
 assert assess_zones(p,[ZONE],{})[0]['zone_ids']is None
 other={**ZONE,'id':'overlap','hazard':False}
 x=assess_zones(p,[ZONE,other],{'p':event})[0]
 assert x['zone_ids']==['overlap','yard']and x['safety_decision']is False
 event['claim']['point']=[.05,.5]
 assert assess_zones(p,[ZONE],{'p':event})[0]['status']=='boundary_needs_review'
 event['claim']['point']=[.8,.5]
 assert assess_zones(p,[ZONE],{'p':event})[0]['zone_ids']==[]
def test_real_factory_zone_review_contact_report_and_expiry(material):
 p,raw,frame,calls,c,job=material
 assert submit(c,frame,job).status_code==409
 x=prepare(c,raw,frame);acknowledge(c,x)
 r=submit(c,frame,job);assert r.status_code==200
 assert r.json()['persons'][0]['status']=='needs_manual_contact_review'
 first=r.json()['zone_snapshot']['event_id']
 assert submit(c,frame,job).json()['zone_snapshot']['event_id']==first
 assert contact(c,frame).status_code==200
 out=c.get('/fresh-review/'+frame.digest+'/zone-review').json()
 assert out['persons'][0]['zone_ids']==['yard']and out['provider_calls_this_request']==0
 full=report(c,x,job).json()
 assert full['zone_review']['persons'][0]['zone_ids']==['yard']and full['compliance_decision']is False and full['evidence_export_allowed']is False
 db=sqlite3.connect(p.path);db.execute('UPDATE contact_events SET at=0');db.commit();db.close()
 assert c.get('/fresh-review/'+frame.digest+'/zone-review').json()['persons'][0]['zone_ids']is None
 assert len(calls)==2
 c.app.state.fresh_display.SESSIONS.clear()
 assert c.get('/fresh-review/'+frame.digest+'/zone-review').status_code==409
 prepare(c,raw,frame)
 assert c.get('/fresh-review/'+frame.digest+'/zone-review').json()['zone_snapshot']['event_id']==first
@pytest.mark.parametrize('field,value',[('source_digest','0'*64),('result_sha256','0'*64),('zones',[{**ZONE,'hazard':1}]),('reviewer_label','')])
def test_zone_invalid_bindings(material,field,value):
 p,raw,frame,calls,c,job=material;prepare(c,raw,frame)
 payload={'source_digest':frame.digest,'result_sha256':digest(job['result']),'zones':[ZONE],'reviewer_label':'reviewer',field:value}
 assert c.post('/fresh-review/'+frame.digest+'/zone-review',json=payload).status_code==409
 assert len(calls)==2

def test_zone_owner_and_tamper(material):
 p,raw,frame,calls,c,job=material;prepare(c,raw,frame);assert submit(c,frame,job).status_code==200
 assert c.get('/fresh-review/'+frame.digest+'/zone-review',headers={'X-Vigilens-Display-Session':'other_browser_nonce_123456789012345'}).status_code==409
 db=sqlite3.connect(p.path);db.execute("UPDATE zone_events SET zones_sha='wrong'");db.commit();db.close()
 assert c.get('/fresh-review/'+frame.digest+'/zone-review').status_code==409

def test_zone_restart_clear_history_and_capacity(material):
 from fastapi.testclient import TestClient
 from fresh_review.zones import MAX_EVENTS
 from app import create_app
 p,raw,frame,calls,c,job=material;prepare(c,raw,frame)
 initial=submit(c,frame,job).json()['zone_snapshot']
 restarted=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 assert restarted.get('/fresh-review/'+frame.digest+'/zone-review').status_code==409
 prepare(restarted,raw,frame)
 assert restarted.get('/fresh-review/'+frame.digest+'/zone-review').json()['zone_snapshot']==initial
 cleared=submit(restarted,frame,job,[]).json()
 assert cleared['persons'][0]['status']=='not_configured'and cleared['zone_snapshot']['event_id']!=initial['event_id']
 db=sqlite3.connect(p.path)
 assert db.execute('SELECT count(*) FROM zone_events').fetchone()[0]==2
 for _ in range(MAX_EVENTS-2):db.execute('INSERT INTO zone_events(source) VALUES(?)',('synthetic-history-capacity',))
 db.commit();db.close()
 assert submit(restarted,frame,job).status_code==409
 assert len(calls)==2
