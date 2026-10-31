"""Reusable pipeline local qualification, synthetic source/SAM/PPE transport, no network."""
import asyncio,io,json,hashlib,sqlite3
import pytest
from PIL import Image
from core import decode_image
from adapters import LiveTransportDisabled
from fresh_review.pipeline import FreshPipeline
import fresh_review.pipeline as m
from fresh_test_helpers import response

def approval_store(tmp_path,specs):
 from fresh_review.approvals import ApprovalStore
 for spec in specs.values():spec['provenance']={'owner_instruction_reference':'synthetic-test-only-no-owner-grant','rights_review_reference':'generated-pixels','reviewed_at':'synthetic-test-time','reviewer':'test-harness','scope':'synthetic_local_qualification'}
 path=tmp_path/'approvals.json';raw=(json.dumps({'version':1,'approvals':specs})+'\n').encode();path.write_bytes(raw);path.chmod(0o600)
 return ApprovalStore(path,hashlib.sha256(raw).hexdigest())
def add_approval(p,source,spec):
 doc=json.loads(p.approval_store.path.read_bytes());doc['approvals'][source]=spec;p.approval_store=approval_store(p.path.parent,doc['approvals'])
def carry(tmp_path):
 raw=json.dumps({'blocked_source_digests':[hashlib.sha256(b'generated-already-paid-source').hexdigest()],'provider_calls_total':0,'conservative_booked_usd':'0','aggregate_cap_usd':'5','provenance':'generated-test-only-not-real-budget'}).encode();path=tmp_path/'carry.json';path.write_bytes(raw);path.chmod(0o600)
 return {'carry_path':path,'carry_sha':hashlib.sha256(raw).hexdigest()}
def setup(tmp_path,monkeypatch,*,people=1,timeout=None):
 im=Image.new('RGB',(80,80),'blue');out=io.BytesIO();im.save(out,'PNG');raw=out.getvalue();frame=decode_image(raw,'image/png');calls=[]
 spec={frame.digest:{'size':[80,80],'rights_reference':'synthetic-generated-test-only','provider_upload_approved':True}}
 async def parse(*args,**kwargs):
  return {'objects':[{'object_id':str(i),'box_half_open':[i*30,0,i*30+20,60],'mask':Image.new('L',(20,60),255)}for i in range(people)]}
 monkeypatch.setattr(m,'parse_sam_image_text',parse)
 def transport(body):
  calls.append(body)
  if timeout==len(calls):raise TimeoutError()
  if body['model']=='sam-3.1':return b'data: {"type":"response.completed","response":{"model":"sam-3.1","id":"synthetic-sam","status":"completed","usage":{"images_processed":1},"output":[]}}\n\n'
  return response('unknown','absent')
 return FreshPipeline(tmp_path/'fresh.sqlite',**carry(tmp_path),execution_scope='synthetic_local_qualification',approval_store=approval_store(tmp_path,spec),transport=transport),raw,frame,calls

def test_fresh_complete_unknown_lossless_two_person_and_repeat_no_calls(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch,people=2)
 result=asyncio.run(p.run(raw,'image/png',[]));assert result['state']=='completed'and len(calls)==3
 assert result['result']['persons'][0]['helmet']=='unknown'and result['result']['persons'][1]['vest']=='absent'
 assert result['result']['findings']is None and result['result']['compliance_status']=='not_evaluated'
 from fresh_review.masks import decode_mask
 assert decode_mask(result['result']['persons'][0]['mask']).size==(20,60)
 assert asyncio.run(p.run(raw,'image/png',[]))['state']=='completed'and len(calls)==3
 assert all(body.get('store')is False for body in calls)

@pytest.mark.parametrize('timeout',[1,2,3])
def test_timeout_any_stage_no_partial_success_or_retry(tmp_path,monkeypatch,timeout):
 p,raw,frame,calls=setup(tmp_path,monkeypatch,people=2,timeout=timeout)
 result=asyncio.run(p.run(raw,'image/png',[]));assert result['state']=='running_uncertain'and result['result']is None
 assert result['reservation_usd']=='2.627012'
 assert asyncio.run(p.run(raw,'image/png',[]))['state']=='running_uncertain'and len(calls)==timeout

@pytest.mark.parametrize('people',[0,3])
def test_zero_or_too_many_people_no_ppe_calls(tmp_path,monkeypatch,people):
 p,raw,frame,calls=setup(tmp_path,monkeypatch,people=people)
 result=asyncio.run(p.run(raw,'image/png',[]));assert result['state']=='running_uncertain'and len(calls)==1 and result['result']is None

def test_default_disabled_creates_no_journal(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch);p.transport=m.disabled_transport
 with pytest.raises(LiveTransportDisabled):asyncio.run(p.run(raw,'image/png',[]))
 assert not p.path.exists()

def test_source_or_zone_not_approved_creates_no_claim(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 with pytest.raises(ValueError):asyncio.run(p.run(raw,'image/png',[{'id':'unapproved'}]))
 p.approval_store=approval_store(tmp_path,{})
 with pytest.raises(ValueError):asyncio.run(p.run(raw,'image/png',[]))
 assert not p.path.exists()and calls==[]

def test_ambiguous_cross_person_prevents_all_ppe(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 async def overlap(*args,**kwargs):return {'objects':[{'object_id':str(i),'box_half_open':[i*10,0,i*10+20,60],'mask':Image.new('L',(20,60),255)}for i in range(2)]}
 monkeypatch.setattr(m,'parse_sam_image_text',overlap)
 assert asyncio.run(p.run(raw,'image/png',[]))['state']=='running_uncertain'and len(calls)==1

def test_corrupted_result_read_fails_closed(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch);asyncio.run(p.run(raw,'image/png',[]))
 db=sqlite3.connect(p.path);db.execute('UPDATE jobs SET result=?',('{"forged":true}',));db.commit();db.close()
 with pytest.raises(ValueError):p.read(frame.digest)

def test_full_hold_blocks_second_different_source_under_same_aggregate(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch,timeout=1);asyncio.run(p.run(raw,'image/png',[]))
 im=Image.new('RGB',(80,80),'red');out=io.BytesIO();im.save(out,'PNG');new=out.getvalue();f=decode_image(new,'image/png')
 add_approval(p,f.digest,{'size':[80,80],'rights_reference':'synthetic-test-only','provider_upload_approved':True})
 with pytest.raises(ValueError):asyncio.run(p.run(new,'image/png',[]))
 assert len(calls)==1

def test_parallel_source_claim_one_slot(tmp_path,monkeypatch):
 import concurrent.futures
 p,raw,frame,calls=setup(tmp_path,monkeypatch);_,_,_,binding=p.prepare(raw,'image/png',[])
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:values=list(pool.map(lambda _:p.claim(binding),range(4)))
 assert sum(values)==1 and calls==[]

def test_tampered_private_raw_reply_blocks_completed_read(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch);asyncio.run(p.run(raw,'image/png',[]))
 path=p.path.parent/('fresh-'+frame.digest+'-1-reply.bin');path.write_bytes(response('present','present'))
 with pytest.raises(ValueError):p.read(frame.digest)

def test_previously_paid_source_never_recreates_legacy_journal(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 PAID_SOURCES=[hashlib.sha256(b'generated-already-paid-source').hexdigest()]
 _,_,_,binding=p.prepare(raw,'image/png',[])
 for source in PAID_SOURCES:
  binding['source_digest']=source
  with pytest.raises(ValueError):p.claim(binding)
  with pytest.raises(ValueError):p.validate_binding(binding)
 assert not p.path.exists()and calls==[]

@pytest.mark.parametrize('artifact',['source','request','cost','crop','geometry'])
def test_preserved_original_request_geometry_and_cost_rechecked(tmp_path,monkeypatch,artifact):
 p,raw,frame,calls=setup(tmp_path,monkeypatch);asyncio.run(p.run(raw,'image/png',[]))
 db=sqlite3.connect(p.path)
 if artifact=='source':
  path=p.path.parent/('fresh-'+frame.digest+'-source.png');path.write_bytes(b'bad source')
 elif artifact=='request':
  path=p.path.parent/('fresh-'+frame.digest+'-1-request.json');path.write_text('{}')
 elif artifact=='cost':db.execute('UPDATE jobs SET cost=?',('0',))
 else:
  from fresh_review.pipeline import digest
  result=json.loads(db.execute('SELECT result FROM jobs').fetchone()[0])
  if artifact=='crop':result['persons'][0]['crop_png_sha256']='changed'
  else:result['persons'][0]['id']='changed'
  db.execute('UPDATE jobs SET result=?,result_sha=?',(json.dumps(result),digest(result)))
 db.commit();db.close()
 with pytest.raises(Exception):p.read(frame.digest)

def test_exact_request_enforced_before_transport(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch);frame,png,sam,binding=p.prepare(raw,'image/png',[])
 assert p.claim(binding)
 p.save_private(p.path.parent/('fresh-'+frame.digest+'-source.png'),png)
 sam['tools']=[{'type':'unapproved'}]
 with pytest.raises(ValueError):p.dispatch(frame.digest,0,sam)
 assert calls==[]

def test_contact_foreground_hole_rejected(tmp_path,monkeypatch):
 # Route fixture result masks are normally solid; supply an empty centre through SAM.
 from fastapi.testclient import TestClient
 from app import create_app
 import fresh_review.api as routes
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 async def hole(*args,**kwargs):
  mask=Image.new('L',(20,60),255);mask.putpixel((8,40),0)
  return {'objects':[{'object_id':'0','box_half_open':[0,0,20,60],'mask':mask}]}
 monkeypatch.setattr(m,'parse_sam_image_text',hole);
 asyncio.run(p.run(raw,'image/png',[]))
 from test_fresh_upload_routes import prepare,OWNER
 c=TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Display-Session':OWNER});prepare(c,raw,frame)
 payload={'person_id':'0','point':[.1,.5],'exact_source_confirmed':True,'boots_ground_visible':True,'reviewer_label':'synthetic'}
 assert c.post('/fresh-review/'+frame.digest+'/contact',json=payload).status_code==409

def test_official_parser_not_injected_full_pipeline(tmp_path):
 #Generated320x334pixels plus official documentation geometry,synthetic wire reply.
 text="<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|><|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
 out=io.BytesIO();Image.new('RGB',(320,334),'#223344').save(out,'PNG');raw=out.getvalue();f=decode_image(raw,'image/png');calls=[]
 def transport(body):
  calls.append(body)
  if body['model']!='sam-3.1':return response('unknown','unknown')
  return ('data: '+json.dumps({'type':'response.completed','response':{'model':'sam-3.1','id':'synthetic-doc-parser','status':'completed','usage':{'images_processed':1},'output':[{'type':'message','content':[{'type':'output_text','text':text}]}]}})+'\n\n').encode()
 p=FreshPipeline(tmp_path/'fresh.sqlite',**carry(tmp_path),execution_scope='synthetic_local_qualification',approval_store=approval_store(tmp_path,{f.digest:{'size':[320,334],'rights_reference':'generated-doc-geometry-test','provider_upload_approved':True}}),transport=transport)
 result=asyncio.run(p.run(raw,'image/png',[]))
 assert result['state']=='completed'and result['provider_calls_this_request']==2
 assert result['result']['persons'][0]['box_half_open']==[211,228,271,255]
 assert p.read(f.digest)['result']==result['result']and len(calls)==2

@pytest.mark.parametrize('change',['incomplete','wrong_model','schema','duplicate','usage','refusal'])
def test_invalid_ppe_wire_full_hold_and_no_retry(tmp_path,monkeypatch,change):
 p,raw,frame,calls=setup(tmp_path,monkeypatch);original=p.transport
 def invalid(body):
  if body['model']=='sam-3.1':return original(body)
  calls.append(body);r=json.loads(response())
  if change=='incomplete':r['status']='incomplete'
  if change=='wrong_model':r['model']='wrong'
  if change=='schema':r['output'][0]['content'][0]['text']='{"helmet":"present"}'
  if change=='duplicate':r['output'][0]['content'][0]['text']='{"helmet":"present","helmet":"absent"}'
  if change=='usage':r['usage']['output_tokens']=513
  if change=='refusal':r['output'][0]['content'][0]={'type':'refusal'}
  return json.dumps(r).encode()
 p.transport=invalid
 out=asyncio.run(p.run(raw,'image/png',[]))
 assert out['state']=='running_uncertain'and out['result']is None and out['provider_calls_this_request']is None
 assert out['requires_operator_reconciliation']is True and out['reservation_usd']=='2.627012'
 repeat=asyncio.run(p.run(raw,'image/png',[]))
 assert repeat['provider_calls_this_request']==0 and len(calls)==2 and repeat['retry_allowed']is False

def test_corrupted_existing_completed_accounting_blocks_new_source(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch);asyncio.run(p.run(raw,'image/png',[]))
 db=sqlite3.connect(p.path);db.execute('UPDATE jobs SET cost=?',('0',));db.commit();db.close()
 out=io.BytesIO();Image.new('RGB',(80,80),'green').save(out,'PNG');new=out.getvalue();f=decode_image(new,'image/png')
 add_approval(p,f.digest,{'size':[80,80],'rights_reference':'generated-test','provider_upload_approved':True})
 with pytest.raises(ValueError):asyncio.run(p.run(new,'image/png',[]))
 assert len(calls)==2

@pytest.mark.parametrize('field,value',[('findings',[]),('compliance_status','pass'),('review_status','done'),('zones',[{'id':'forged'}]),('evidence_export_allowed',True),('privacy_review_status','validated')])
def test_rehashed_top_level_policy_rejected(tmp_path,monkeypatch,field,value):
 p,raw,frame,calls=setup(tmp_path,monkeypatch);asyncio.run(p.run(raw,'image/png',[]))
 db=sqlite3.connect(p.path);r=json.loads(db.execute('SELECT result FROM jobs').fetchone()[0]);r[field]=value
 db.execute('UPDATE jobs SET result=?,result_sha=?',(json.dumps(r),m.digest(r)));db.commit();db.close()
 with pytest.raises(ValueError):p.read(frame.digest)

@pytest.mark.parametrize('field,value',[('zones',[{'id':'forged'}]),('source_approval_snapshot',{}),('export_allowed',True)])
def test_binding_policy_or_approval_rejected_on_read(tmp_path,monkeypatch,field,value):
 p,raw,frame,calls=setup(tmp_path,monkeypatch);asyncio.run(p.run(raw,'image/png',[]))
 db=sqlite3.connect(p.path);b=json.loads(db.execute('SELECT binding FROM jobs').fetchone()[0]);b[field]=value
 db.execute('UPDATE jobs SET binding=?',(json.dumps(b),));db.commit();db.close()
 with pytest.raises(ValueError):p.read(frame.digest)

def test_approval_provenance_missing_and_store_tamper_rejected(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch)
 doc=json.loads(p.approval_store.path.read_bytes());del doc['approvals'][frame.digest]['provenance'];new=json.dumps(doc).encode();p.approval_store.path.write_bytes(new);p.approval_store.sha=hashlib.sha256(new).hexdigest()
 with pytest.raises(ValueError):p.prepare(raw,'image/png',[])
 p.approval_store.path.write_bytes(b'changed')
 with pytest.raises(ValueError):p.prepare(raw,'image/png',[])
 assert calls==[] and not p.path.exists()

def test_paid_source_block_dispatch_even_direct_call(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch);_,png,body,binding=p.prepare(raw,'image/png',[]);p.claim(binding)
 PAID_SOURCES=[hashlib.sha256(b'generated-already-paid-source').hexdigest()]
 source=next(iter(PAID_SOURCES));binding['source_digest']=source
 db=sqlite3.connect(p.path);db.execute('UPDATE jobs SET source=?,binding=?',(source,json.dumps(binding)));db.commit();db.close()
 p.save_private(p.path.parent/('fresh-'+source+'-source.png'),png)
 with pytest.raises(ValueError):p.dispatch(source,0,body)
 assert calls==[]

def test_uncertain_get_reports_attempted_total_and_debit_unknown(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch,timeout=2);asyncio.run(p.run(raw,'image/png',[]))
 import fresh_review.api as routes
 from fastapi.testclient import TestClient
 from app import create_app
 out=TestClient(create_app(fresh_service=p)).get('/fresh-review/'+frame.digest).json()
 assert out['provider_calls_this_request']==0 and out['attempted_provider_calls_total']==2
 assert out['provider_call_count_status']=='uncertain_requires_reconciliation'and out['actual_debit']=='unchecked'

def test_synthetic_approval_cannot_enable_private_provider_scope(tmp_path,monkeypatch):
 p,raw,frame,calls=setup(tmp_path,monkeypatch);p.execution_scope='private_provider_processing'
 with pytest.raises(ValueError):asyncio.run(p.run(raw,'image/png',[]))
 assert not p.path.exists()and calls==[]
