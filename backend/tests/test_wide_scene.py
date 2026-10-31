import asyncio,io,json,hashlib,sqlite3
import pytest
from PIL import Image
from core import decode_image
from test_fresh_upload_pipeline import carry,approval_store
from fresh_review.wide_scene import WideScenePipeline,WideLimits
from fresh_test_helpers import response

def wide(tmp_path,monkeypatch,*,selected=None,timeout=False):
 import fresh_review.wide_scene as m
 im=Image.new('RGB',(1000,600),'#223344');b=io.BytesIO();im.save(b,'PNG');raw=b.getvalue();f=decode_image(raw,'image/png');calls=[]
 objects=[]
 for i in range(12):
  x=20+(i%6)*150;y=20+(i//6)*260;w,h=(10,15)if i==10 else(70,180)
  if i==11:x,y=30,30
  objects.append({'object_id':str(i),'box_half_open':[x,y,x+w,y+h],'mask':Image.new('L',(w,h),255)})
 async def parse(*a,**k):return {'objects':objects}
 monkeypatch.setattr(m,'parse_sam_image_text',parse)
 def transport(body):
  calls.append(body)
  if timeout and len(calls)==2:raise TimeoutError()
  if body['model']=='sam-3.1':return b'data: {"type":"response.completed","response":{"model":"sam-3.1","id":"synthetic-wide-SAM","status":"completed","usage":{"images_processed":1},"output":[]}}\n\n'
  return response('unknown','absent')
 spec={f.digest:{'size':[1000,600],'rights_reference':'generated-wide-scene','provider_upload_approved':True,'wide_scene':{'selected_person_ids':selected if selected is not None else['1','2'],'authority_reference':'synthetic-only'}}}
 p=WideScenePipeline(tmp_path/'wide.sqlite',**carry(tmp_path),execution_scope='synthetic_local_qualification',approval_store=approval_store(tmp_path,spec),transport=transport,wide_limits=WideLimits())
 return p,raw,f,calls,objects

def test_twelve_person_retained_selected_unknown_tiny_overlap_unassessed(tmp_path,monkeypatch):
 p,raw,f,calls,objects=wide(tmp_path,monkeypatch);out=asyncio.run(p.run(raw,'image/png',[]));assert out['state']=='completed'and len(calls)==3
 people=out['result']['persons'];assert len(people)==12 and sum(q['ppe_assessed']for q in people)==2
 assert people[10]['ppe_evidence_status']=='crop_evidence_ineligible'and people[0]['ppe_evidence_status']=='crop_evidence_ineligible'
 assert people[3]['helmet']=='unknown'and people[3]['ppe_assessed']is False
 assert asyncio.run(p.run(raw,'image/png',[]))['provider_calls_this_request']==0 and len(calls)==3
 assert p.read(f.digest)['result']==out['result']

def test_selected_ineligible_not_sent_or_forced(tmp_path,monkeypatch):
 p,raw,f,calls,o=wide(tmp_path,monkeypatch,selected=['0','10']);out=asyncio.run(p.run(raw,'image/png',[]));assert out['state']=='completed'and len(calls)==1
 assert all(q['helmet']=='unknown'and q['vest']=='unknown'and not q['ppe_assessed']for q in out['result']['persons'])

def test_wide_timeout_no_partial_result_or_retry(tmp_path,monkeypatch):
 p,raw,f,calls,o=wide(tmp_path,monkeypatch,timeout=True);out=asyncio.run(p.run(raw,'image/png',[]));assert out['state']=='running_uncertain'and out['result']is None
 assert asyncio.run(p.run(raw,'image/png',[]))['state']=='running_uncertain'and len(calls)==2

@pytest.mark.parametrize('damage',['reply','result','cost','geometry'])
def test_wide_tamper_revalidated(tmp_path,monkeypatch,damage):
 p,raw,f,calls,o=wide(tmp_path,monkeypatch);asyncio.run(p.run(raw,'image/png',[]));c=p.connect()
 if damage=='reply':(tmp_path/('fresh-'+f.digest+'-1-reply.bin')).write_bytes(b'changed')
 elif damage=='result':c.execute("UPDATE jobs SET result='{}'")
 elif damage=='cost':c.execute("UPDATE calls SET cost='0' WHERE ordinal=1")
 else:
  b=json.loads(c.execute('SELECT binding FROM jobs').fetchone()[0]);b['persons'][0]['id']='changed';c.execute('UPDATE jobs SET binding=?',(json.dumps(b),))
 c.commit();c.close()
 with pytest.raises(Exception):p.read(f.digest)

@pytest.mark.parametrize('kwargs',[{'max_people':9},{'max_people':33},{'max_ppe_calls':4},{'max_ppe_calls':True}])
def test_explicit_wide_limits(kwargs):
 with pytest.raises(ValueError):WideLimits(**kwargs).validate()

def run_twelve_person_multizone_private_HTTP_report(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 from app import create_app
 from fresh_review.pipeline import digest
 from fresh_review.policy import FORMAT
 from test_fresh_upload_routes import OWNER
 p,raw,f,calls,objects=wide(tmp_path,monkeypatch)
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 out=c.post('/fresh-review-upload',files={'image':('generated.png',raw,'image/png')},data={'zones':'[]'});assert out.status_code==200;job=out.json();assert job['state']=='completed'
 review={'source_digest':f.digest,'frame_size':[1000,600],'regions':[{'person_id':str(i),'box':[o['box_half_open'][0],o['box_half_open'][1],o['box_half_open'][0]+5,o['box_half_open'][1]+5]}for i,o in enumerate(objects)],'reviewer_label':'synthetic-12person-review','redaction_method':'opaque'}
 x=c.post('/fresh-review/'+f.digest+'/private-display',files={'image':('generated.png',raw,'image/png')},data={'review':json.dumps(review)});assert x.status_code==200;x=x.json()
 ack={k:x[k]for k in ['source_digest','output_sha256','regions_digest']};ack.update(frame_size=[1000,600],foreground_checked=True,background_checked=True,reflections_checked=True,derivative_checked=True);assert c.post('/private-display/'+x['session_id']+'/review',json=ack).status_code==200
 # Person1 reviewed contact exactly on x=.2 zone boundary; person2 inside overlap.
 for pid,point in [('1',[.2,.2]),('2',[.35,.2]),('3',[.5,.2])]:
  assert c.post('/fresh-review/'+f.digest+'/contact',json={'person_id':pid,'point':point,'exact_source_confirmed':True,'boots_ground_visible':True,'reviewer_label':'synthetic-contact'}).status_code==200
 zones=[{'id':'left','name':'left demo','hazard':True,'points':[{'x':.2,'y':.1},{'x':.6,'y':.1},{'x':.6,'y':.8},{'x':.2,'y':.8}]},{'id':'overlap','name':'overlap demo','hazard':True,'points':[{'x':.3,'y':.1},{'x':.7,'y':.1},{'x':.7,'y':.8},{'x':.3,'y':.8}]}]
 identity={'source_digest':f.digest,'result_sha256':digest(job['result'])};z=c.post('/fresh-review/'+f.digest+'/zone-review',json={**identity,'zones':zones,'reviewer_label':'synthetic-zones'});assert z.status_code==200
 config={'format':FORMAT,'policy_id':'synthetic-wide-not-owner-policy','version':'1','scope':'illustrative_demo','camera_id':'synthetic','approval_reference':'synthetic-only','priorities':['Medium'],'zones':[{'id':z['id'],'name':z['name'],'points':z['points'],'access_mode':'allowed','rules':[{'id':'helmet','check':'helmet_worn','priority':'Medium'}]}for z in zones],'outside_rules':[]}
 assert c.post('/fresh-review/'+f.digest+'/rule-review',json={**identity,'zones_sha256':z.json()['zone_snapshot']['zones_sha256'],'configuration':config}).status_code==200
 body={'assessment_id':'fresh:'+f.digest+':'+digest(job['result']),'source_digest':f.digest,'output_sha256':x['output_sha256'],'regions_digest':x['regions_digest'],'persons':{str(i):{'exact_source_confirmed':True,'face_coverage_checked':True,'head_evidence_visible':True,'torso_evidence_visible':True}for i in range(12)}}
 path='/fresh-private-report/'+x['session_id'];report=c.post(path,json=body);assert report.status_code==200;doc=report.json();assert len(doc['persons'])==12
 persons={q['person_id']:q for q in doc['zone_review']['persons']};assert persons['1']['status']=='boundary_needs_review';assert persons['2']['zone_ids']==['left','overlap'];assert persons['4']['zone_ids']is None
 assert all(q['report_display_helmet']=='unknown'for q in doc['persons']);assert sum(q['ppe_assessed']for q in doc['persons'])==2
 pdf=c.post(path+'/pdf-preview',json=body);assert pdf.status_code==200 and pdf.content.startswith(b'%PDF');assert len(calls)==3
 # Save generated only artifacts for visual inspection outside the suite.
 destination=getattr(p,'smoke_destination',None)
 if destination:
  (destination/'wide-report.pdf').write_bytes(pdf.content)
 return p,raw,f,calls,c,job,doc,pdf.content,x,body


def test_twelve_person_multizone_private_HTTP_report(tmp_path,monkeypatch):
 run_twelve_person_multizone_private_HTTP_report(tmp_path,monkeypatch)

def test_unassessed_people_are_not_genuine_initial_unknown(tmp_path,monkeypatch):
 from fresh_review.agent_loop import run_review_loop
 from fresh_review.rechecks import plan_recheck
 p,raw,f,calls,o=wide(tmp_path,monkeypatch);job=asyncio.run(p.run(raw,'image/png',[]))
 loop=asyncio.run(run_review_loop(p,f.digest,attempt_ids=[]));assert loop['original_unknown_person_ids']==['1','2']
 assert plan_recheck(raw,job['result'],'3',attempts_so_far=0,max_attempts=1)['reason']=='not_original_PPE_unknown_unassessed_person'
 assert plan_recheck(raw,job['result'],'1',attempts_so_far=0,max_attempts=1)['status']=='planned_not_authorised_or_dispatched'
 assert len(calls)==3

def test_selected_nonexistent_id_stops_before_PPE(tmp_path,monkeypatch):
 p,raw,f,calls,o=wide(tmp_path,monkeypatch,selected=['not-found']);out=asyncio.run(p.run(raw,'image/png',[]));assert out['state']=='running_uncertain'and out['result']is None and len(calls)==1

def test_wide_cap_does_not_truncate(tmp_path,monkeypatch):
 p,raw,f,calls,o=wide(tmp_path,monkeypatch);p.wide_limits=WideLimits(max_people=10);out=asyncio.run(p.run(raw,'image/png',[]));assert out['state']=='running_uncertain'and out['result']is None and len(calls)==1

def test_wide_same_cap_preflight_no_partial_dispatch(tmp_path,monkeypatch):
 p,raw,f,calls,o=wide(tmp_path,monkeypatch)
 d=json.loads(p.carry_path.read_text());d['conservative_booked_usd']='3';p.carry_path.write_text(json.dumps(d));p.carry_sha=hashlib.sha256(p.carry_path.read_bytes()).hexdigest()
 with pytest.raises(ValueError):asyncio.run(p.run(raw,'image/png',[]))
 assert calls==[]

def test_parallel_wide_claim_deduplicates(tmp_path,monkeypatch):
 import concurrent.futures
 p,raw,f,calls,o=wide(tmp_path,monkeypatch);_,_,_,b=p.prepare(raw,'image/png',[])
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:claims=list(pool.map(lambda _:p.claim(b),range(4)))
 assert sum(claims)==1 and calls==[]

def test_official_parser_twelve_records_retained_without_PPE(tmp_path):
 record="<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|><|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
 text='<0f>'+''.join(str(i)+record for i in range(12));b=io.BytesIO();Image.new('RGB',(320,334),'#334455').save(b,'PNG');raw=b.getvalue();f=decode_image(raw,'image/png');calls=[]
 def transport(body):
  calls.append(body);return ('data: '+json.dumps({'type':'response.completed','response':{'model':'sam-3.1','id':'synthetic12docrecords','status':'completed','usage':{'images_processed':1},'output':[{'type':'message','content':[{'type':'output_text','text':text}]}]}})+'\n\n').encode()
 spec={f.digest:{'size':[320,334],'rights_reference':'generated-docgeometry','provider_upload_approved':True,'wide_scene':{'selected_person_ids':[],'authority_reference':'synthetic-only'}}}
 p=WideScenePipeline(tmp_path/'wide.sqlite',**carry(tmp_path),execution_scope='synthetic_local_qualification',approval_store=approval_store(tmp_path,spec),transport=transport,wide_limits=WideLimits())
 out=asyncio.run(p.run(raw,'image/png',[]));assert out['state']=='completed'and len(out['result']['persons'])==12 and len(calls)==1
 assert all(not q['ppe_assessed']and q['helmet']=='unknown'for q in out['result']['persons'])
 assert p.read(f.digest)['result']==out['result']
