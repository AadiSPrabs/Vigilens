"""Per-install aggregate cap: explicit sha-pinned carry value, fail closed, default '5' unchanged."""
import asyncio,io,json,hashlib
import pytest
from PIL import Image
from core import decode_image
from fresh_review.pipeline import FreshPipeline, aggregate_cap
import fresh_review.pipeline as m
from test_fresh_upload_pipeline import approval_store, add_approval

def carry_with(tmp_path,cap='5',booked='0',blocked=None):
 doc={'blocked_source_digests':blocked if blocked is not None else [],'provider_calls_total':0,
      'conservative_booked_usd':booked,'aggregate_cap_usd':cap,'provenance':'generated-test-only-not-real-budget'}
 if cap is None:doc.pop('aggregate_cap_usd')
 raw=json.dumps(doc).encode();path=tmp_path/'carry.json';path.write_bytes(raw);path.chmod(0o600)
 return {'carry_path':path,'carry_sha':hashlib.sha256(raw).hexdigest()}

def setup_cap(tmp_path,monkeypatch,cap='5',booked='0',timeout=None):
 im=Image.new('RGB',(80,80),'blue');out=io.BytesIO();im.save(out,'PNG');raw=out.getvalue();frame=decode_image(raw,'image/png');calls=[]
 spec={frame.digest:{'size':[80,80],'rights_reference':'synthetic-generated-test-only','provider_upload_approved':True}}
 async def parse(*args,**kwargs):
  return {'objects':[{'object_id':'0','box_half_open':[0,0,20,60],'mask':Image.new('L',(20,60),255)}]}
 monkeypatch.setattr(m,'parse_sam_image_text',parse)
 def transport(body):
  calls.append(body)
  if timeout=='sam'and body['model']=='sam-3.1':raise TimeoutError()
  if timeout==len(calls):raise TimeoutError()
  if body['model']=='sam-3.1':return b'data: {"type":"response.completed","response":{"model":"sam-3.1","id":"synthetic-sam","status":"completed","usage":{"images_processed":1},"output":[]}}\n\n'
  from fresh_test_helpers import response
  return response('unknown','absent')
 return FreshPipeline(tmp_path/'fresh.sqlite',**carry_with(tmp_path,cap,booked),execution_scope='synthetic_local_qualification',approval_store=approval_store(tmp_path,spec),transport=transport),raw,frame,calls

def test_default_cap_unchanged_and_booked_bound_uses_cap(tmp_path,monkeypatch):
 p,raw,frame,calls=setup_cap(tmp_path,monkeypatch)
 assert p.carry()['aggregate_cap_usd']=='5'
 p2,_,_,_=setup_cap(tmp_path,monkeypatch,cap='25',booked='6')
 assert p2.carry()['aggregate_cap_usd']=='25'
 p3,_,_,_=setup_cap(tmp_path,monkeypatch,cap='5',booked='6')
 with pytest.raises(ValueError):p3.carry()
 assert calls==[]

@pytest.mark.parametrize('cap',['abc','-1','1000001','0.5x','','NaN','Infinity',None])
def test_invalid_or_missing_cap_fails_closed(tmp_path,monkeypatch,cap):
 p,_,_,_=setup_cap(tmp_path,monkeypatch,cap=cap)
 with pytest.raises(ValueError):p.carry()

def test_aggregate_cap_helper_requires_explicit_string():
 for bad in [{'aggregate_cap_usd':5},{'aggregate_cap_usd':0.5},{},{'aggregate_cap_usd':'1000000.01'}]:
  with pytest.raises(ValueError):aggregate_cap(bad)
 assert aggregate_cap({'aggregate_cap_usd':'0'})==0 and aggregate_cap({'aggregate_cap_usd':'1000000'})==1000000

def test_tiny_cap_blocks_claim_before_any_call(tmp_path,monkeypatch):
 p,raw,frame,calls=setup_cap(tmp_path,monkeypatch,cap='0.001')
 with pytest.raises(ValueError):asyncio.run(p.run(raw,'image/png',[]))
 assert calls==[]

def test_larger_cap_admits_more_uncertain_full_holds(tmp_path,monkeypatch):
 # Under the '5' default a full 2.627012 uncertain hold blocks a second different source
 # (test_full_hold_blocks_second_different_source_under_same_aggregate). An explicit larger
 # per-install cap admits several full holds; holds still count in full against it.
 p,raw,frame,calls=setup_cap(tmp_path,monkeypatch,cap='25',timeout='sam')
 assert asyncio.run(p.run(raw,'image/png',[]))['state']=='running_uncertain'
 for color in ('red','green','yellow'):
  im=Image.new('RGB',(80,80),color);out=io.BytesIO();im.save(out,'PNG');new=out.getvalue();f=decode_image(new,'image/png')
  add_approval(p,f.digest,{'size':[80,80],'rights_reference':'synthetic-test-only','provider_upload_approved':True})
  assert asyncio.run(p.run(new,'image/png',[]))['state']=='running_uncertain'
 assert len(calls)==4
 # Nine full holds book 9 x 2.627012 = 23.643108; the tenth needs 26.27 > 25 and is refused at claim.
 for color in ('black','white','gray','purple','orange'):
  im=Image.new('RGB',(80,80),color);out=io.BytesIO();im.save(out,'PNG');new=out.getvalue();f=decode_image(new,'image/png')
  add_approval(p,f.digest,{'size':[80,80],'rights_reference':'synthetic-test-only','provider_upload_approved':True})
  asyncio.run(p.run(new,'image/png',[]))
 im=Image.new('RGB',(80,80),'pink');out=io.BytesIO();im.save(out,'PNG');new=out.getvalue();f=decode_image(new,'image/png')
 add_approval(p,f.digest,{'size':[80,80],'rights_reference':'synthetic-test-only','provider_upload_approved':True})
 with pytest.raises(ValueError):asyncio.run(p.run(new,'image/png',[]))
 assert len(calls)==9

def _wide_cap(tmp_path,monkeypatch,cap):
 from fresh_review.wide_scene import WideScenePipeline,WideLimits
 import fresh_review.wide_scene as wsm
 im=Image.new('RGB',(1000,600),'#223344');b=io.BytesIO();im.save(b,'PNG');raw=b.getvalue();f=decode_image(raw,'image/png');calls=[]
 objects=[]
 for i in range(12):
  x=20+(i%6)*150;y=20+(i//6)*260;w,h=(10,15)if i==10 else(70,180)
  if i==11:x,y=30,30
  objects.append({'object_id':str(i),'box_half_open':[x,y,x+w,y+h],'mask':Image.new('L',(w,h),255)})
 async def parse(*a,**k):return {'objects':objects}
 monkeypatch.setattr(wsm,'parse_sam_image_text',parse)
 from fresh_test_helpers import response
 def transport(body):
  calls.append(body)
  if body['model']=='sam-3.1':return b'data: {"type":"response.completed","response":{"model":"sam-3.1","id":"synthetic-wide-SAM","status":"completed","usage":{"images_processed":1},"output":[]}}\n\n'
  return response('unknown','absent')
 spec={f.digest:{'size':[1000,600],'rights_reference':'generated-wide-scene','provider_upload_approved':True,'wide_scene':{'selected_person_ids':['1','2'],'authority_reference':'synthetic-only'}}}
 p=WideScenePipeline(tmp_path/'wide.sqlite',**carry_with(tmp_path,cap),execution_scope='synthetic_local_qualification',approval_store=approval_store(tmp_path,spec),transport=transport,wide_limits=WideLimits())
 return p,raw,f,calls

def test_wide_scene_tiny_cap_blocks_claim_before_any_call(tmp_path,monkeypatch):
 p,raw,f,calls=_wide_cap(tmp_path,monkeypatch,'0.001')
 with pytest.raises(ValueError):asyncio.run(p.run(raw,'image/png',[]))
 assert calls==[]

def test_wide_scene_larger_cap_completes_consistently(tmp_path,monkeypatch):
 p,raw,f,calls=_wide_cap(tmp_path,monkeypatch,'25')
 out=asyncio.run(p.run(raw,'image/png',[]))
 assert out['state']=='completed' and len(calls)==3

def test_sequential_tiny_cap_blocks_sam_claim_before_any_call(tmp_path,monkeypatch):
 from fresh_review.wide_sequential import SequentialWidePipeline,SequentialLimits
 import fresh_review.wide_scene as wsm
 im=Image.new('RGB',(1500,600),'#223344');objects=[]
 for i in range(14):
  w,h=(10,15)if i>=12 else(100,180);x=10+(i%14)*105;y=20
  im.paste((10+i*15,200-i*10,30+i*9),(x,y,x+w,y+h));objects.append({'object_id':str(i),'box_half_open':[x,y,x+w,y+h],'mask':Image.new('L',(w,h),255)})
 b=io.BytesIO();im.save(b,'PNG');raw=b.getvalue();f=decode_image(raw,'image/png');calls=[]
 async def parse(*a,**k):return {'objects':objects}
 monkeypatch.setattr(wsm,'parse_sam_image_text',parse)
 def transport(body):
  calls.append(body)
  if body['model']=='sam-3.1':return b'data: {"type":"response.completed","response":{"model":"sam-3.1","id":"synthetic-seq-SAM","status":"completed","usage":{"images_processed":1},"output":[]}}\n\n'
  from fresh_test_helpers import response
  return response('unknown','absent')
 spec={f.digest:{'size':[1500,600],'rights_reference':'generated','provider_upload_approved':True,'wide_scene':{'assess':'all_eligible','authority_reference':'synthetic-only'}}}
 p=SequentialWidePipeline(tmp_path/'seq.sqlite',**carry_with(tmp_path,'0.001'),execution_scope='synthetic_local_qualification',approval_store=approval_store(tmp_path,spec),transport=transport,wide_limits=SequentialLimits(max_ppe_calls=16))
 with pytest.raises(ValueError):asyncio.run(p.run(raw,'image/png',[]))
 assert calls==[]
