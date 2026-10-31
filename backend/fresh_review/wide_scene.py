"""Explicit opt-in bounded wide scenes. Not enabled by legacy startup or caller JSON.
All parsed people retained. Unselected/tiny/cross-person crops remain unassessed
unknown; no forced verdict, silent truncation or inferred model-call authority.
"""
import asyncio,concurrent.futures,hashlib,io,json,sqlite3,time
from dataclasses import dataclass,asdict
from decimal import Decimal
from PIL import Image
from core import decode_image,pixel_only_png
from adapters import build_sam_image_request,LiveTransportDisabled
from pipeline import Frame
from sam_parser import parse_sam_image_text,parse_sam_image_text_quarantine
from .pipeline import FreshPipeline,digest,disabled_transport
from .ppe import MAX_COST,canonical_body,parse_reply,wire_completed
from .masks import encode_mask,decode_mask

@dataclass(frozen=True)
class WideLimits:
 max_people:int=16
 max_ppe_calls:int=2
 min_crop_width:int=32
 min_crop_height:int=64
 geometry_quarantine:bool=False
 def validate(self):
  if type(self.geometry_quarantine)is not bool:raise ValueError('Explicit boolean quarantine mode required')
  for v,lo,hi in [(self.max_people,10,32),(self.max_ppe_calls,0,3),(self.min_crop_width,16,512),(self.min_crop_height,32,1024)]:
   if type(v)is not int or not lo<=v<=hi:raise ValueError('Explicit bounded wide-scene limits required')
 @property
 def reserve(self):return Decimal('.0025')+self.max_ppe_calls*MAX_COST

def eligibility(objects,limits):
 out={}
 for obj in objects:
  l,t,r,b=obj['box_half_open'];reasons=[]
  if obj.get('mask')is None:reasons.append('geometry_unverified_person_not_assessed')
  if r-l<limits.min_crop_width or b-t<limits.min_crop_height:reasons.append('crop_too_small_for_configured_evidence_threshold')
  for other in objects:
   if other is obj:continue
   x,y,rr,bb=other['box_half_open'];a,c,d,e=max(l,x),max(t,y),min(r,rr),min(b,bb)
   if a<d and c<e and other.get('mask')is None:reasons.append('overlaps_unverified_geometry_person_box');break
   if a<d and c<e and other['mask'].crop((a-x,c-y,d-x,e-y)).getbbox():reasons.append('other_person_foreground_in_crop');break
  out[str(obj['object_id'])]={'eligible_for_selected_crop_call':not reasons,'review_reasons':reasons,'identity_or_visibility_validated':False}
 return out

class WideScenePipeline(FreshPipeline):
 def __init__(self,*a,wide_limits=None,**kw):
  super().__init__(*a,**kw);self.wide_limits=wide_limits or WideLimits();self.wide_limits.validate()
 def plan(self,spec):
  plan=spec.get('wide_scene')
  if not isinstance(plan,dict)or set(plan)!={'selected_person_ids','authority_reference'}or not isinstance(plan['authority_reference'],str)or not plan['authority_reference'].strip():raise ValueError('Explicit source-bound wide-scene execution plan required')
  ids=plan['selected_person_ids']
  if not isinstance(ids,list)or len(ids)>self.wide_limits.max_ppe_calls or len(set(ids))!=len(ids)or any(not isinstance(i,str)or not i for i in ids):raise ValueError('Bounded exact PPE person selection required')
  return plan
 def validate_binding(self,b):
  spec=self.approval_store.lookup(b['source_digest'],b['frame_size'])
  if spec['provenance']['scope']!=self.execution_scope or b['source_digest']in self.carry()['blocked_source_digests']:raise ValueError('Exact approved non-repeated source scope required')
  expected={'kind':'wide_scene.v1','limits':asdict(self.wide_limits),'carry_sha256':self.carry_sha,'source_approval_snapshot':spec,'wide_plan':self.plan(spec),'zones':[],'export_allowed':False}
  if any(type(b.get(k))is not type(v)or b[k]!=v for k,v in expected.items()):raise ValueError('Wide source limits/plan/approval changed')
 def prepare(self,raw,mime,zones):
  if zones!=[]:raise ValueError('Wide provider intake does not infer zone policy')
  f=decode_image(raw,mime);self.reject_derivative(f.digest)
  if f.orientation!=1:raise ValueError('Explicit upright source required')
  spec=self.approval_store.lookup(f.digest,[f.width,f.height]);png=pixel_only_png(raw,mime);sam=build_sam_image_request(png,'image/png','person');sam['store']=False
  b={'kind':'wide_scene.v1','source_digest':f.digest,'frame_size':[f.width,f.height],'canonical_png_sha256':hashlib.sha256(png).hexdigest(),'sam_request_sha256':digest(sam),'limits':asdict(self.wide_limits),'carry_sha256':self.carry_sha,'source_approval_snapshot':spec,'wide_plan':self.plan(spec),'zones':[],'export_allowed':False}
  self.validate_binding(b);return f,png,sam,b
 def claim(self,b):
  self.validate_binding(b);c=self.connect()
  try:
   c.execute('BEGIN IMMEDIATE')
   if c.execute('SELECT 1 FROM jobs WHERE source=?',(b['source_digest'],)).fetchone():return False
   if c.execute('SELECT count(*) FROM jobs').fetchone()[0]>=64:raise ValueError('Wide source history full')
   from .stopped_source import original_total
   from .recheck_journal import reservation_total
   from .recheck_execution import verify_retained_rechecks
   from .ppe_segmentation import total as masks,verify_retained as verify_masks
   from .explanation_execution import total as explanations,verify_retained as verify_explanations
   verify_retained_rechecks(self,c);verify_masks(self,c);verify_explanations(self,c)
   booked=Decimal(self.carry()['conservative_booked_usd'])+original_total(self,c)+reservation_total(c)+masks(c)+explanations(c)
   if booked+self.wide_limits.reserve>5:raise ValueError('Same aggregate cap unavailable for exact wide plan')
   c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)',(b['source_digest'],'running_uncertain',str(self.wide_limits.reserve),'0',json.dumps(b),None,None,time.time()));c.commit();return True
  finally:c.close()
 def dispatch(self,source,ordinal,body):
  c=self.connect()
  try:
   c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT state,binding FROM jobs WHERE source=?',(source,)).fetchone()
   if not row or row[0]!='running_uncertain':raise ValueError('Wide source must hold active exact claim')
   b=json.loads(row[1]);self.validate_binding(b);calls=c.execute('SELECT state FROM calls WHERE source=? ORDER BY ordinal',(source,)).fetchall()
   if len(calls)!=ordinal or any(r[0]!='completed'for r in calls)or not 0<=ordinal<=self.wide_limits.max_ppe_calls:raise ValueError('No skipped/repeated wide stage')
   raw=self.private_bytes(self.path.parent/('fresh-'+source+'-source.png'))
   if hashlib.sha256(raw).hexdigest()!=b['canonical_png_sha256']:raise ValueError('Original source changed')
   if ordinal==0:expected=build_sam_image_request(raw,'image/png','person');expected['store']=False
   else:
    f=decode_image(raw,'image/png');_,objects=self.parsed(self.private_bytes(self.path.parent/('fresh-'+source+'-0-reply.bin')),f)
    gates=eligibility(objects,self.wide_limits)
    selected=[i for i in b['wide_plan']['selected_person_ids']if i in gates and gates[i]['eligible_for_selected_crop_call']]
    if self.geometry(objects,f)!=b['persons']or selected!=b['assessed_person_ids']:raise ValueError('Wide original geometry/selection changed before spending')
    if ordinal>len(selected):raise ValueError('No extra person call')
    samrow=c.execute('SELECT state,request_sha,response_sha,cost FROM calls WHERE source=? AND ordinal=0',(source,)).fetchone()
    samrequest=json.loads(self.private_bytes(self.path.parent/('fresh-'+source+'-0-request.json')));samreply=self.private_bytes(self.path.parent/('fresh-'+source+'-0-reply.bin'))
    expected_sam=build_sam_image_request(raw,'image/png','person');expected_sam['store']=False
    if samrow!=('completed',digest(samrequest),hashlib.sha256(samreply).hexdigest(),'0.0025')or samrequest!=expected_sam:raise ValueError('Original SAM accounting/artifacts changed before wide PPE dispatch')
    obj=next(p for p in b['persons']if p['id']==selected[ordinal-1])
    with Image.open(io.BytesIO(raw))as im:buf=io.BytesIO();im.crop(obj['box_half_open']).save(buf,'PNG');expected=canonical_body(buf.getvalue())
   if body!=expected:raise ValueError('Canonical selected original crop required')
   c.execute('INSERT INTO calls VALUES(?,?,?,?,?,?,?)',(source,ordinal,body['model'],'attempted_uncertain',digest(body),None,'0'));c.commit()
  finally:c.close()
  self.save_private(self.path.parent/('fresh-'+source+'-'+str(ordinal)+'-request.json'),json.dumps(body,sort_keys=True).encode());raw=self.transport(body)
  if not isinstance(raw,bytes)or len(raw)>(4_000_000 if ordinal==0 else 256_000):raise ValueError('Wide response quota exceeded')
  self.save_private(self.path.parent/('fresh-'+source+'-'+str(ordinal)+'-reply.bin'),raw)
  c=self.connect()
  try:c.execute('UPDATE calls SET state=?,response_sha=? WHERE source=? AND ordinal=?',('received_unparsed',hashlib.sha256(raw).hexdigest(),source,ordinal));c.commit()
  finally:c.close()
  return raw
 def parsed(self,raw,frame):
  d=wire_completed(raw)
  if d.get('model')!='sam-3.1'or not d.get('id')or d.get('usage',{}).get('images_processed')!=1:raise ValueError('Completed SAM image required')
  text=''.join(p['text']for i in d.get('output',[])for p in i.get('content',[])if p.get('type')=='output_text')
  def parse():return asyncio.run((parse_sam_image_text_quarantine if self.wide_limits.geometry_quarantine else parse_sam_image_text)(text,Frame(frame.width,frame.height,frame.digest),wire_completed=True))
  with concurrent.futures.ThreadPoolExecutor(max_workers=1)as pool:objects=pool.submit(parse).result()['objects']
  if not 1<=len(objects)<=self.wide_limits.max_people:raise ValueError('Wide person capacity exceeded; whole source stopped')
  if len({str(o['object_id'])for o in objects})!=len(objects):raise ValueError('Distinct person IDs required')
  return d,objects
 def geometry(self,objects,f):return [{'id':str(o['object_id']),'box_half_open':list(o['box_half_open']),'mask':None,'geometry_status':'unverified_box_only','quarantine_reason':o['quarantine_reason'],'declared_mask_size':list(o['declared_mask_size']),'box_size':list(o['box_size'])}if o.get('mask')is None else {'id':str(o['object_id']),'box_half_open':list(o['box_half_open']),'mask':encode_mask(o['mask'],list(o['box_half_open']),[f.width,f.height])}for o in objects]
 def result(self,source,b,frame,objects,response,ppe):
  gates=eligibility(objects,self.wide_limits);persons=[]
  for obj in self.geometry(objects,frame):
   pid=obj['id'];obs=ppe.get(pid);selected=pid in b['wide_plan']['selected_person_ids'];reason='provider_observed'if obs else 'crop_evidence_ineligible'if not gates[pid]['eligible_for_selected_crop_call']else'not_selected_within_explicit_PPE_call_budget'
   with Image.open(io.BytesIO(self.private_bytes(self.path.parent/('fresh-'+source+'-source.png'))))as im:buf=io.BytesIO();im.crop(obj['box_half_open']).save(buf,'PNG');crop_sha=hashlib.sha256(buf.getvalue()).hexdigest()
   persons.append({**obj,'crop_png_sha256':crop_sha,'helmet':obs['observation']['helmet']if obs else'unknown','vest':obs['observation']['vest']if obs else'unknown','ppe_assessed':obs is not None,'provider_observation':obs,'ppe_evidence_status':reason,'crop_eligibility':gates[pid],'selected_for_PPE':selected,'contact_status':'not_checked','compliance_status':'not_evaluated'})
  return {'source':'fresh_upload_provider_review','image':{'pixel_digest':source,'width':frame.width,'height':frame.height},'persons':persons,'zones':[],'zone_status':'not_checked','compliance_status':'not_evaluated','findings':None,'review_status':'needs_human_review','privacy_review_status':'not_validated','evidence_export_allowed':False,'sam_response_id':response['id'],'wide_scene':{'capacity':self.wide_limits.max_people,'detected_person_count':len(persons),'PPE_assessed_count':len(ppe),'all_detected_persons_retained':True,'coverage':'selected_crops_only_not_all_people_PPE','minimum_crop_size_is_technical_not_accuracy_validation':True},'provider_proof':'local_request_response_consistency_not_provider_signature'}
 def read(self,source):
  if not self.path.exists():return None
  self.private_bytes(self.path);c=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)
  try:row=c.execute('SELECT state,reserved,cost,binding,result,result_sha FROM jobs WHERE source=?',(source,)).fetchone();calls=c.execute('SELECT ordinal,model,state,request_sha,response_sha,cost FROM calls WHERE source=? ORDER BY ordinal',(source,)).fetchall()
  finally:c.close()
  if not row:return None
  b=json.loads(row[3]);self.validate_binding(b)
  if row[0]not in ('completed','running_uncertain')or Decimal(row[1])!=self.wide_limits.reserve:raise ValueError('Wide hold/state changed')
  result=json.loads(row[4])if row[4]else None
  if result is not None:
   raw=self.private_bytes(self.path.parent/('fresh-'+source+'-source.png'));f=decode_image(raw,'image/png')
   if f.digest!=source or hashlib.sha256(raw).hexdigest()!=b['canonical_png_sha256']:raise ValueError('Wide source changed')
   response,objects=self.parsed(self.private_bytes(self.path.parent/('fresh-'+source+'-0-reply.bin')),f);gates=eligibility(objects,self.wide_limits)
   if self.geometry(objects,f)!=b['persons']:raise ValueError('Wide geometry changed')
   expected_ids=[i for i in b['wide_plan']['selected_person_ids']if i in gates and gates[i]['eligible_for_selected_crop_call']]
   if expected_ids!=b['assessed_person_ids']or len(calls)!=len(expected_ids)+1:raise ValueError('Selected assessment association changed')
   ppe={};total=Decimal('0')
   for index,model,state,req,rep,cost in calls:
    if index!=len(ppe)+(1 if index else 0)or state!='completed':raise ValueError('Wide call ordering changed')
    request=json.loads(self.private_bytes(self.path.parent/('fresh-'+source+'-'+str(index)+'-request.json')));reply=self.private_bytes(self.path.parent/('fresh-'+source+'-'+str(index)+'-reply.bin'))
    if digest(request)!=req or hashlib.sha256(reply).hexdigest()!=rep:raise ValueError('Wide artifacts changed')
    if index==0:expected=build_sam_image_request(raw,'image/png','person');expected['store']=False;listed=Decimal('.0025')
    else:
     pid=expected_ids[index-1];person=next(p for p in b['persons']if p['id']==pid)
     with Image.open(io.BytesIO(raw))as im:buf=io.BytesIO();im.crop(person['box_half_open']).save(buf,'PNG');expected=canonical_body(buf.getvalue())
     ppe[pid]=parse_reply(reply);listed=Decimal(ppe[pid]['listed_cost_usd'])
    if request!=expected or model!=expected['model']or Decimal(cost)!=listed:raise ValueError('Wide canonical request/cost changed')
    total+=listed
   if row[0]!='completed'or digest(result)!=row[5]or result!=self.result(source,b,f,objects,response,ppe)or total!=Decimal(row[2])or total>self.wide_limits.reserve:raise ValueError('Wide result/accounting changed')
  elif row[0]=='completed':raise ValueError('Missing completed wide result')
  return {'state':row[0],'result':result,'binding':b,'reservation_usd':row[1],'known_listed_usd':row[2],'requires_operator_reconciliation':row[0]!='completed','retry_allowed':False,'provider_calls_this_request':0,'actual_debit':'unchecked','evidence_export_allowed':False,'execution_status':'selected_wide_observations_not_full_PPE_coverage'if result else'terminal_uncertain_no_retry'}
 async def run(self,raw,mime,zones):
  f,png,sam,b=self.prepare(raw,mime,zones);source=f.digest;old=self.read(source)
  if old:return old
  if self.transport is disabled_transport:raise LiveTransportDisabled('Wide dispatch disabled')
  if not self.claim(b):return self.read(source)
  try:
   self.save_private(self.path.parent/('fresh-'+source+'-source.png'),png);reply=self.dispatch(source,0,sam);completion=wire_completed(reply)
   if completion.get('model')!='sam-3.1'or not completion.get('id')or completion.get('usage',{}).get('images_processed')!=1:raise ValueError('Completed SAM image required')
   self.record_cost(source,0,Decimal('.0025'));response,objects=self.parsed(reply,f);gates=eligibility(objects,self.wide_limits)
   if any(i not in gates for i in b['wide_plan']['selected_person_ids']):raise ValueError('Selected person ID absent; no PPE dispatch')
   b['persons']=self.geometry(objects,f);b['assessed_person_ids']=[i for i in b['wide_plan']['selected_person_ids']if gates[i]['eligible_for_selected_crop_call']]
   c=self.connect()
   try:c.execute('UPDATE jobs SET binding=? WHERE source=?',(json.dumps(b),source));c.commit()
   finally:c.close()
   ppe={}
   for index,pid in enumerate(b['assessed_person_ids'],1):
    person=next(p for p in b['persons']if p['id']==pid)
    with Image.open(io.BytesIO(png))as im:buf=io.BytesIO();im.crop(person['box_half_open']).save(buf,'PNG');body=canonical_body(buf.getvalue())
    ppe[pid]=parse_reply(self.dispatch(source,index,body));self.record_cost(source,index,Decimal(ppe[pid]['listed_cost_usd']))
   result=self.result(source,b,f,objects,response,ppe);c=self.connect()
   try:c.execute('UPDATE jobs SET state=?,result=?,result_sha=? WHERE source=?',('completed',json.dumps(result),digest(result),source));c.commit()
   finally:c.close()
  except Exception:return {**self.read(source),'provider_calls_this_request':None,'notice':'Wide source stopped, full hold retained, no partial result or retry'}
  return {**self.read(source),'provider_calls_this_request':1+len(ppe)}
