import asyncio,io,json,hashlib
from decimal import Decimal
import pytest
from PIL import Image
from core import decode_image
from test_fresh_upload_pipeline import carry,approval_store
import fresh_review.wide_scene as ws
import fresh_review.wide_sequential as sq
from fresh_review.wide_sequential import SequentialWidePipeline,SequentialLimits
from fresh_review.ppe import parse_reply,MAX_COST
from fresh_test_helpers import response

def big(tokens):
 d=json.loads(response('unknown','absent'));d['usage']={'input_tokens':tokens,'output_tokens':80};return json.dumps(d).encode()

def seq(tmp_path,monkeypatch,*,eligible=12,assess='all_eligible',limits=None,booked=None,fail_at=None,tokens=100):
 im=Image.new('RGB',(1500,600),'#223344');calls=[];objects=[]
 for i in range(eligible+2):
  w,h=(10,15)if i>=eligible else(100,180);x=10+(i%14)*105;y=20
  im.paste((10+i*15,200-i*10,30+i*9),(x,y,x+w,y+h));objects.append({'object_id':str(i),'box_half_open':[x,y,x+w,y+h],'mask':Image.new('L',(w,h),255)})
 b=io.BytesIO();im.save(b,'PNG');raw=b.getvalue();f=decode_image(raw,'image/png')
 async def parse(*a,**k):return {'objects':objects}
 monkeypatch.setattr(ws,'parse_sam_image_text',parse)
 def transport(body):
  calls.append(body)
  if fail_at is not None and len(calls)==fail_at:raise TimeoutError()
  if body['model']=='sam-3.1':return b'data: {"type":"response.completed","response":{"model":"sam-3.1","id":"synthetic-seq-SAM","status":"completed","usage":{"images_processed":1},"output":[]}}\n\n'
  return big(tokens)
 spec={f.digest:{'size':[1500,600],'rights_reference':'generated','provider_upload_approved':True,'wide_scene':{'assess':assess,'authority_reference':'synthetic-only'}}}
 c=carry(tmp_path)
 if booked is not None:
  d=json.loads(c['carry_path'].read_text());d['conservative_booked_usd']=str(booked);c['carry_path'].write_text(json.dumps(d));c['carry_sha']=hashlib.sha256(c['carry_path'].read_bytes()).hexdigest()
 p=SequentialWidePipeline(tmp_path/'seq.sqlite',**c,execution_scope='synthetic_local_qualification',approval_store=approval_store(tmp_path,spec),transport=transport,wide_limits=limits or SequentialLimits(max_ppe_calls=16))
 return p,raw,f,calls

def run(p,raw):return asyncio.run(p.run(raw,'image/png',[]))
def unique(calls):return len({json.dumps(c,sort_keys=True)for c in calls})==len(calls)

def test_limits():
 for bad in [17,-1,True]:
  with pytest.raises(ValueError):SequentialLimits(max_ppe_calls=bad).validate()
 SequentialLimits(max_ppe_calls=16).validate()

def test_twelve_eligible_complete_sequential_zero_repeats(tmp_path,monkeypatch):
 p,raw,f,calls=seq(tmp_path,monkeypatch);out=run(p,raw);assert out['state']=='completed'and len(calls)==13 and unique(calls)
 r=out['result'];assert len(r['persons'])==14 and r['wide_scene']['PPE_assessed_count']==12 and r['wide_scene']['coverage']=='all_eligible_people_assessed'
 assert sum(q['ppe_evidence_status']=='crop_evidence_ineligible'for q in r['persons'])==2 and not r['wide_scene']['budget_deferred_never_attempted']
 assert Decimal(out['reservation_usd'])==Decimal(out['known_listed_usd'])
 again=run(p,raw);assert again['provider_calls_this_request']==0 and len(calls)==13 and again['result']==r

def force_cost(monkeypatch,cost):
 orig=parse_reply
 def pr(raw):
  d=orig(raw);d['listed_cost_usd']=str(cost);return d
 monkeypatch.setattr(sq,'parse_reply',pr)

def grant(tmp_path,p,f,out,ids,n=[0],**over):
 n[0]+=1;doc={'format':'vigilens.wide-continuation-grant.v1','execution_scope':'synthetic_local_qualification','source_digest':f.digest,'prior_result_sha256':hashlib.sha256(json.dumps(out['result'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),'prior_carry_sha256':out['binding']['carry_sha256'],'carry_sha256':p.carry_sha,'person_ids':ids,'max_additional_calls':len(ids),'aggregate_cap_usd':'5','per_stage_reserve_usd':str(MAX_COST),'authority_reference':'synthetic-test-fixture-not-owner-evidence'}
 doc.update(over);path=tmp_path/('grant%d.json'%n[0]);raw=json.dumps(doc).encode();path.write_bytes(raw);path.chmod(0o600);return str(path),hashlib.sha256(raw).hexdigest()

def newcarry(p,tmp,booked):
 d=json.loads(p.carry_path.read_text());d['conservative_booked_usd']=str(booked);p.carry_path.write_text(json.dumps(d));p.carry_sha=hashlib.sha256(p.carry_path.read_bytes()).hexdigest()

def test_budget_exhaustion_stops_before_spend_with_partial_state(tmp_path,monkeypatch):
 force_cost(monkeypatch,Decimal('.5'));p,raw,f,calls=seq(tmp_path,monkeypatch,booked='2.5');out=run(p,raw)
 assert out['state']=='partial_completed'and out['continuation_requires_new_authority']
 r=out['result'];n=r['wide_scene']['PPE_assessed_count'];assert 1<=n<12 and len(calls)==n+1 and r['wide_scene']['job_state']=='partial_completed'
 d=r['wide_scene']['budget_deferred_never_attempted'];assert len(d)==12-n and all(q['ppe_evidence_status']=='budget_deferred_never_attempted'and q['helmet']=='unknown'and not q['ppe_assessed']for q in r['persons']if q['id']in d)
 assert Decimal(out['reservation_usd'])==Decimal(out['known_listed_usd'])==Decimal('.0025')+n*Decimal('.5')
 assert Decimal('2.5')+Decimal(out['known_listed_usd'])+MAX_COST>5
 before=len(calls);again=run(p,raw);assert again['state']=='partial_completed'and len(calls)==before and again['result']==r
 # Same carry/cap: a valid grant is still stopped before spending (no room), not forced.
 o=p.continue_partial(f.digest,*grant(tmp_path,p,f,out,d[:1]));assert len(calls)==before and o['state']=='partial_completed'

def test_authorized_continuation_succeeds_after_settled_carry_change(tmp_path,monkeypatch):
 force_cost(monkeypatch,Decimal('.5'));p,raw,f,calls=seq(tmp_path,monkeypatch,booked='2.5');out=run(p,raw);n=out['result']['wide_scene']['PPE_assessed_count'];d=out['result']['wide_scene']['budget_deferred_never_attempted'];before=len(calls)
 newcarry(p,tmp_path,'0.5')
 with pytest.raises(ValueError):p.continue_partial(f.digest,*grant(tmp_path,p,f,out,d[:2],prior_carry_sha256='0'*64))
 with pytest.raises(ValueError):p.continue_partial(f.digest,*grant(tmp_path,p,f,out,d[:2],carry_sha256='1'*64))
 with pytest.raises(ValueError):p.continue_partial(f.digest,*grant(tmp_path,p,f,out,d[:2],aggregate_cap_usd='6'))
 with pytest.raises(ValueError):p.continue_partial(f.digest,*grant(tmp_path,p,f,out,d[:2],prior_result_sha256='2'*64))
 with pytest.raises(ValueError):p.continue_partial(f.digest,*grant(tmp_path,p,f,out,d[:2],max_additional_calls=1))
 with pytest.raises(ValueError):p.continue_partial(f.digest,*grant(tmp_path,p,f,out,d[:2],extra='x'))
 assert len(calls)==before
 gp,gs=grant(tmp_path,p,f,out,d[:2]);o=p.continue_partial(f.digest,gp,gs)
 assert len(calls)==before+2 and o['provider_calls_this_request']==2 and o['result']['wide_scene']['PPE_assessed_count']==n+2 and o['state']=='partial_completed'
 assert set(o['result']['wide_scene']['budget_deferred_never_attempted'])==set(d[2:]) and unique(calls)
 assert Decimal(o['reservation_usd'])==Decimal(o['known_listed_usd'])==Decimal('.0025')+(n+2)*Decimal('.5')
 with pytest.raises(ValueError):p.continue_partial(f.digest,gp,gs)  # replay
 assert run(p,raw)['provider_calls_this_request']==0 and len(calls)==before+2
 # Granted people only: remaining deferred are untouched. Final grant for the rest completes within room.
 o2=p.read(f.digest);gp2,gs2=grant(tmp_path,p,f,o2,d[2:4]);o3=p.continue_partial(f.digest,gp2,gs2);assert len(calls)==before+4 and o3['result']['wide_scene']['PPE_assessed_count']==n+4

def test_cap_limited_continuation_needs_grant_and_never_repeats(tmp_path,monkeypatch):
 p,raw,f,calls=seq(tmp_path,monkeypatch,limits=SequentialLimits(max_ppe_calls=4));out=run(p,raw)
 assert out['state']=='completed'and len(calls)==5 and out['result']['wide_scene']['coverage']=='partial_eligible_people_unassessed'
 first=[q['id']for q in out['result']['persons']if q['ppe_assessed']]
 for bad in (first[:1],['12'],['99']):
  with pytest.raises(ValueError):p.continue_partial(f.digest,*grant(tmp_path,p,f,out,bad))
 more=[q['id']for q in out['result']['persons']if q['crop_eligibility']['eligible_for_selected_crop_call']and not q['ppe_assessed']][:3]
 o=p.continue_partial(f.digest,*grant(tmp_path,p,f,out,more));assert o['state']=='completed'and len(calls)==8 and unique(calls)
 assert p.read(f.digest)['result']['wide_scene']['PPE_assessed_count']==7
 assert run(p,raw)['provider_calls_this_request']==0

def test_uncertain_call_stops_terminal_no_later_stage(tmp_path,monkeypatch):
 p,raw,f,calls=seq(tmp_path,monkeypatch,fail_at=5);out=run(p,raw);assert out['state']=='running_uncertain'and out['result']is None and len(calls)==5
 s=p.read(f.digest);assert s['requires_operator_reconciliation']and not s['resumable_without_repeat']
 assert Decimal(s['reservation_usd'])==Decimal(s['known_listed_usd'])+MAX_COST
 assert run(p,raw)['state']=='running_uncertain'and len(calls)==5
 with pytest.raises(ValueError):p.continue_partial(f.digest,*grant(tmp_path,p,f,{'result':{},'binding':{'carry_sha256':p.carry_sha}},['9']))

def test_crash_between_stages_resumes_without_repeat(tmp_path,monkeypatch):
 p,raw,f,calls=seq(tmp_path,monkeypatch);orig=p.dispatch
 def crash(source,ordinal,body):
  if ordinal==4:raise KeyboardInterrupt()
  return orig(source,ordinal,body)
 p.dispatch=crash
 with pytest.raises(KeyboardInterrupt):run(p,raw)
 assert len(calls)==4;s=p.read(f.digest);assert s['resumable_without_repeat']and s['state']=='running_uncertain'
 p.dispatch=orig;out=run(p,raw);assert out['state']=='completed'and len(calls)==13 and unique(calls)

def test_crash_after_SAM_before_queue_resumes(tmp_path,monkeypatch):
 p,raw,f,calls=seq(tmp_path,monkeypatch);orig=p.start
 def crash(*a):raise KeyboardInterrupt()
 p.start=crash
 with pytest.raises(KeyboardInterrupt):run(p,raw)
 assert len(calls)==1;p.start=orig;out=run(p,raw);assert out['state']=='completed'and len(calls)==13 and unique(calls)

def test_exact_selected_ids_and_ineligible_never_sent(tmp_path,monkeypatch):
 p,raw,f,calls=seq(tmp_path,monkeypatch,assess=['1','12','3']);out=run(p,raw);assert out['state']=='completed'and len(calls)==3
 st={q['id']:q['ppe_evidence_status']for q in out['result']['persons']};assert st['12']=='crop_evidence_ineligible'and st['2']=='not_selected_within_explicit_PPE_call_budget'
 p,raw,f,calls=seq(tmp_path/'x'if False else tmp_path,monkeypatch)
 
def test_nonexistent_selected_id_stops_before_PPE(tmp_path,monkeypatch):
 p,raw,f,calls=seq(tmp_path,monkeypatch,assess=['nope']);out=run(p,raw);assert out['state']=='running_uncertain'and len(calls)==1 and out['result']is None

@pytest.mark.parametrize('damage',['reply','result','cost','reserved','queue','state'])
def test_tamper_detected(tmp_path,monkeypatch,damage):
 p,raw,f,calls=seq(tmp_path,monkeypatch);run(p,raw);c=p.connect()
 if damage=='reply':(tmp_path/('fresh-'+f.digest+'-2-reply.bin')).write_bytes(b'changed')
 elif damage=='result':c.execute("UPDATE jobs SET result='{}'")
 elif damage=='cost':c.execute("UPDATE calls SET cost='0' WHERE ordinal=2")
 elif damage=='reserved':c.execute("UPDATE jobs SET reserved='0'")
 elif damage=='state':c.execute("UPDATE jobs SET state='partial_completed'")
 else:
  b=json.loads(c.execute('SELECT binding FROM jobs').fetchone()[0]);b['queue']=b['queue'][:-1];c.execute('UPDATE jobs SET binding=?',(json.dumps(b),))
 c.commit();c.close()
 with pytest.raises(Exception):p.read(f.digest)

def test_other_job_reservation_counts_against_same_cap(tmp_path,monkeypatch):
 p,raw,f,calls=seq(tmp_path,monkeypatch,booked='4.9')
 out=run(p,raw);assert out['state']=='partial_completed'and len(calls)==1 and out['result']['wide_scene']['PPE_assessed_count']==0

def sequential_http_report(tmp_path,monkeypatch,partial=True,limits=None,hook=None):
 from fastapi.testclient import TestClient
 from app import create_app
 from fresh_review.pipeline import digest
 from test_fresh_upload_routes import OWNER
 force_cost(monkeypatch,Decimal('.5'))
 p,raw,f,calls=seq(tmp_path,monkeypatch,booked='2.5'if partial else None,limits=limits)
 if hook:hook()
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER})
 out=c.post('/fresh-review-upload',files={'image':('generated.png',raw,'image/png')},data={'zones':'[]'});assert out.status_code==200;job=out.json()
 assert job['state']==('partial_completed'if partial else'completed')
 res=job['result'];ids=[q['id']for q in res['persons']]
 review={'source_digest':f.digest,'frame_size':[1500,600],'regions':[{'person_id':q['id'],'box':[q['box_half_open'][0],q['box_half_open'][1],q['box_half_open'][0]+5,q['box_half_open'][1]+5]}for q in res['persons']],'reviewer_label':'synthetic-seq-review','redaction_method':'opaque'}
 x=c.post('/fresh-review/'+f.digest+'/private-display',files={'image':('generated.png',raw,'image/png')},data={'review':json.dumps(review)});assert x.status_code==200,x.text;x=x.json()
 ack={k:x[k]for k in ['source_digest','output_sha256','regions_digest']};ack.update(frame_size=[1500,600],foreground_checked=True,background_checked=True,reflections_checked=True,derivative_checked=True);assert c.post('/private-display/'+x['session_id']+'/review',json=ack).status_code==200
 body={'assessment_id':'fresh:'+f.digest+':'+digest(res),'source_digest':f.digest,'output_sha256':x['output_sha256'],'regions_digest':x['regions_digest'],'persons':{i:{'exact_source_confirmed':True,'face_coverage_checked':True,'head_evidence_visible':True,'torso_evidence_visible':True}for i in ids}}
 path='/fresh-private-report/'+x['session_id'];report=c.post(path,json=body);assert report.status_code==200,report.text;doc=report.json()
 pdf=c.post(path+'/pdf-preview',json=body);assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
 p._c=c;p._path=path;p._body=body
 return p,f,res,doc,pdf.content,calls

def test_partial_job_report_stays_partial_and_distinguishes_statuses(tmp_path,monkeypatch):
 p,f,res,doc,pdf,calls=sequential_http_report(tmp_path,monkeypatch)
 w=doc['wide_scene'];assert w['job_state']=='partial_completed'and w['sequential']and w['budget_deferred_never_attempted']
 st={q['person_id']:q['ppe_evidence_status']for q in doc['persons']}
 assert set(st.values())=={'provider_observed','budget_deferred_never_attempted','crop_evidence_ineligible'}
 assert all(q['report_display_helmet']=='unknown'for q in doc['persons']if not q['ppe_assessed'])
 import os
 if os.environ.get('SEQ_PDF_OUT'):open(os.environ['SEQ_PDF_OUT'],'wb').write(pdf)


def second_job(p,tmp_path):
 from test_fresh_upload_pipeline import add_approval
 im=Image.new('RGB',(1500,600),'#332244');b=io.BytesIO();im.save(b,'PNG');raw2=b.getvalue();f2=decode_image(raw2,'image/png')
 add_approval(p,f2.digest,{'size':[1500,600],'rights_reference':'generated2','provider_upload_approved':True,'provenance':{'owner_instruction_reference':'synthetic-test-only-no-owner-grant','rights_review_reference':'generated-pixels','reviewed_at':'synthetic-test-time','reviewer':'test-harness','scope':'synthetic_local_qualification'},'wide_scene':{'assess':['0'],'authority_reference':'synthetic-only'}})
 return raw2,f2

def test_multi_job_checkpoint_rebind_fails_closed_without_invalidating_others(tmp_path,monkeypatch):
 force_cost(monkeypatch,Decimal('.5'));p,raw,f,calls=seq(tmp_path,monkeypatch,booked='2.5');out=run(p,raw);d=out['result']['wide_scene']['budget_deferred_never_attempted']
 raw2,f2=second_job(p,tmp_path);o2=run(p,raw2);assert o2['state']in('completed','partial_completed')and p.read(f2.digest)['state']==o2['state']
 before=len(calls);old_sha=p.carry_sha;newcarry(p,tmp_path,'0.5')
 with pytest.raises(ValueError,match='Checkpoint change refused'):p.continue_partial(f.digest,*grant(tmp_path,p,f,out,d[:1],prior_carry_sha256=out['binding']['carry_sha256']))
 assert len(calls)==before
 # Nothing was rewritten: restoring the original checkpoint, both jobs still verify.
 p.carry_sha=old_sha;newcarry(p,tmp_path,'2.5');assert p.carry_sha==old_sha
 assert p.read(f.digest)['state']=='partial_completed'and p.read(f2.digest)['state']==o2['state']

def test_multi_job_same_checkpoint_continuation_still_budget_gated(tmp_path,monkeypatch):
 force_cost(monkeypatch,Decimal('.5'));p,raw,f,calls=seq(tmp_path,monkeypatch,booked='2.5');out=run(p,raw);d=out['result']['wide_scene']['budget_deferred_never_attempted']
 raw2,f2=second_job(p,tmp_path);run(p,raw2);before=len(calls)
 o=p.continue_partial(f.digest,*grant(tmp_path,p,f,out,d[:1]));assert len(calls)==before and o['state']=='partial_completed'
 assert p.read(f2.digest)is not None

def test_overlay_labels_color_by_status_only_for_sequential(tmp_path,monkeypatch):
 from fresh_review.overlays import render_overlay
 force_cost(monkeypatch,Decimal('.5'));p,raw,f,calls=seq(tmp_path,monkeypatch,booked='2.5');res=run(p,raw)['result']
 png,_=render_overlay(raw,res,[]);im=Image.open(io.BytesIO(png)).convert('RGB')
 want={'provider_observed':(20,120,60),'budget_deferred_never_attempted':(200,110,0),'crop_evidence_ineligible':(110,110,110)}
 for q in res['persons']:
  l,t,r,b=q['box_half_open'];fs=max(13,round(1500/90));th=fs+4;y=t-th-1 if t>=th+1 else t+1;x=min(max(0,l),1500-1)
  assert im.getpixel((x+1,y+th-1))==want[q['ppe_evidence_status']],q['id']
 plain=dict(res);plain['wide_scene']={k:v for k,v in res['wide_scene'].items()if k!='sequential'}
 png2,_=render_overlay(raw,plain,[]);assert png2!=png

ACTUAL_CARRY_BOOKED=Decimal('0.05457125')  # settled-19 conservative booked, copied from the verified private accounting record

def test_twelve_stage_with_settled19_booked_low_cost_completes_beyond_three_calls(tmp_path,monkeypatch):
 # Release-after-each-stage: low verified cost lets all 12 stages reserve MAX_COST in turn; never pre-reserves 12x.
 p,raw,f,calls=seq(tmp_path,monkeypatch,booked=ACTUAL_CARRY_BOOKED);out=run(p,raw)
 assert out['state']=='completed'and out['result']['wide_scene']['PPE_assessed_count']==12 and len(calls)==13 and unique(calls)
 assert ACTUAL_CARRY_BOOKED+Decimal(out['known_listed_usd'])<5

def test_twelve_stage_with_settled19_booked_expensive_stops_before_spend_never_exceeds_cap(tmp_path,monkeypatch):
 force_cost(monkeypatch,Decimal('1.2'));p,raw,f,calls=seq(tmp_path,monkeypatch,booked=ACTUAL_CARRY_BOOKED);out=run(p,raw)
 n=out['result']['wide_scene']['PPE_assessed_count'];assert out['state']=='partial_completed'and 3<=n<12
 total=ACTUAL_CARRY_BOOKED+Decimal(out['known_listed_usd']);assert total<=5 and total+MAX_COST>5 and len(calls)==n+1

def test_twelve_stage_with_settled19_uncertain_call_is_terminal(tmp_path,monkeypatch):
 p,raw,f,calls=seq(tmp_path,monkeypatch,booked=ACTUAL_CARRY_BOOKED,fail_at=6);out=run(p,raw);k=len(calls)
 assert k==6 and out['state']!='completed';again=run(p,raw);assert len(calls)==k


def test_wide_sequential_partial_job_supports_post_analysis_multizone_manual_contact_review(tmp_path,monkeypatch):
 # No zones at intake (zones=[]); explicit operator zones are applied AFTER person results, via the existing reviewed path.
 from fresh_review.pipeline import digest
 p,f,res,doc,pdf,calls=sequential_http_report(tmp_path,monkeypatch);c=p._c;before=len(calls)
 A={'id':'zone-a','name':'Illustrative A','hazard':False,'points':[{'x':0,'y':0},{'x':.35,'y':0},{'x':.35,'y':1},{'x':0,'y':1}]}
 B={'id':'zone-b','name':'Illustrative B','hazard':True,'points':[{'x':.36,'y':0},{'x':.9,'y':0},{'x':.9,'y':1},{'x':.36,'y':1}]}
 r=c.post('/fresh-review/'+f.digest+'/zone-review',json={'source_digest':f.digest,'result_sha256':digest(res),'zones':[A,B],'reviewer_label':'synthetic zone reviewer'});assert r.status_code==200,r.text
 v=r.json();assert v['policy_status']=='not_applied'and v['compliance_status']=='not_evaluated'and v['provider_calls_this_request']==0
 assert all(q['status']=='needs_manual_contact_review'and q['safety_decision']is False for q in v['persons'])
 by={q['id']:q for q in res['persons']};deferred=res['wide_scene']['budget_deferred_never_attempted'];assert deferred
 def contact(pid,x):return c.post('/fresh-review/'+f.digest+'/contact',json={'person_id':pid,'point':[x,.18],'exact_source_confirmed':True,'boots_ground_visible':True,'reviewer_label':'synthetic operator'})
 assert contact('0',.04).status_code==200
 d=deferred[-1];l,t,rr,b=by[d]['box_half_open'];assert contact(d,((l+rr)/2)/1500).status_code==200
 z={q['person_id']:q for q in c.get('/fresh-review/'+f.digest+'/zone-review').json()['persons']}
 assert z['0']['zone_ids']==['zone-a']and z[d]['zone_ids'] and z[d]['safety_decision']is False
 assert len(calls)==before  # zone work never calls the provider and never changes PPE evidence status
 assert by[d]['ppe_evidence_status']=='budget_deferred_never_attempted'

def test_crowded_scene_above_old_32_cap_is_never_silently_truncated_and_caps_ppe_explicitly(tmp_path,monkeypatch):
 p,raw,f,calls=seq(tmp_path,monkeypatch,eligible=40,limits=SequentialLimits(max_people=64,max_ppe_calls=16),booked=ACTUAL_CARRY_BOOKED);out=run(p,raw)
 r=out['result'];ws=r['wide_scene']
 assert len(r['persons'])==42 and out['state']in('completed','partial_completed') and ws['PPE_assessed_count']<=16
 assert len(calls)<=17  # one SAM + at most 16 PPE
 st=[q['ppe_evidence_status']for q in r['persons']]
 assert sum(1 for s in st if s=='provider_observed')==ws['PPE_assessed_count']
 assert all(s in('provider_observed','budget_deferred_never_attempted','crop_evidence_ineligible','eligible_not_selected')for s in st)
 assert len(r['persons'])==len(set(q['id']for q in r['persons']))

def test_scene_over_new_64_cap_stops_whole_source_without_truncation(tmp_path,monkeypatch):
 p,raw,f,calls=seq(tmp_path,monkeypatch,eligible=70,limits=SequentialLimits(max_people=64,max_ppe_calls=16));out=run(p,raw)
 assert out.get('result')is None and len(calls)==1  # SAM only, no PPE, no silent subset

def test_wide_partial_report_and_pdf_include_post_analysis_zone_review(tmp_path,monkeypatch):
 import subprocess,os
 from fresh_review.pipeline import digest
 p,f,res,doc,pdf,calls=sequential_http_report(tmp_path,monkeypatch);c=p._c
 A={'id':'zone-a','name':'Illustrative A','hazard':False,'points':[{'x':0,'y':0},{'x':.35,'y':0},{'x':.35,'y':1},{'x':0,'y':1}]}
 B={'id':'zone-b','name':'Illustrative B','hazard':True,'points':[{'x':.36,'y':0},{'x':.9,'y':0},{'x':.9,'y':1},{'x':.36,'y':1}]}
 assert c.post('/fresh-review/'+f.digest+'/zone-review',json={'source_digest':f.digest,'result_sha256':digest(res),'zones':[A,B],'reviewer_label':'synthetic zone reviewer'}).status_code==200
 deferred=res['wide_scene']['budget_deferred_never_attempted'];by={q['id']:q for q in res['persons']}
 def contact(pid,x):return c.post('/fresh-review/'+f.digest+'/contact',json={'person_id':pid,'point':[x,.18],'exact_source_confirmed':True,'boots_ground_visible':True,'reviewer_label':'synthetic operator'})
 assert contact('0',.04).status_code==200
 d=deferred[-1];l,t,r,b=by[d]['box_half_open'];assert contact(d,((l+r)/2)/1500).status_code==200
 before=len(calls)
 rep=c.post(p._path,json=p._body);assert rep.status_code==200,rep.text;doc2=rep.json()
 zr=doc2.get('zone_review');assert zr and zr['policy_status']=='not_applied'and zr['compliance_status']=='not_evaluated'
 pv=c.post(p._path+'/pdf-preview',json=p._body);assert pv.status_code==200 and pv.content.startswith(b'%PDF');assert len(calls)==before
 out=os.environ.get('SEQ_ZONE_PDF_OUT')
 if out:open(out,'wb').write(pv.content)
 return pv.content
