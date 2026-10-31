import os
"""Opt-in sequential per-person wide-scene assessment. Local capability, no startup dispatch.
One exact person crop per stage. Each stage reserves only its own worst case on top of
verified completed cost, releases it on verified completion, and stops BEFORE spending when
the same aggregate cap cannot hold the next stage. A stop leaves persisted partial state
(partial_completed); people never attempted stay budget_deferred, not assessed and not
clear. Continuation needs an explicit new authority reference and exact never-attempted
IDs. An uncertain call is terminal: no retry, no later stage, hold retained.
"""
import hashlib,io,json,sqlite3,time
from dataclasses import dataclass,asdict
from decimal import Decimal
from PIL import Image
from core import decode_image,pixel_only_png
from adapters import build_sam_image_request,LiveTransportDisabled
from .pipeline import digest,disabled_transport
from .ppe import MAX_COST,canonical_body,parse_reply,wire_completed
from .wide_scene import WideScenePipeline,WideLimits,eligibility
SAM=Decimal('.0025')
KIND='wide_scene_sequential.v1'

class BudgetDeferred(Exception):pass

@dataclass(frozen=True)
class SequentialLimits(WideLimits):
 def validate(self):
  if type(self.geometry_quarantine)is not bool:raise ValueError('Explicit boolean quarantine mode required')
  for v,lo,hi in [(self.max_people,10,64),(self.max_ppe_calls,0,16),(self.min_crop_width,16,512),(self.min_crop_height,32,1024)]:
   if type(v)is not int or not lo<=v<=hi:raise ValueError('Explicit bounded sequential wide-scene limits required')

def crop_png(raw,box):
 with Image.open(io.BytesIO(raw))as im:b=io.BytesIO();im.crop(box).save(b,'PNG');return b.getvalue()

class SequentialWidePipeline(WideScenePipeline):
 def __init__(self,*a,wide_limits=None,chain_manifest=None,chain_proof_dir=None,**kw):
  super().__init__(*a,wide_limits=wide_limits or SequentialLimits(),**kw)
  self.chain_manifest=chain_manifest;self.chain_proof_dir=chain_proof_dir
  if not isinstance(self.wide_limits,SequentialLimits):raise ValueError('SequentialLimits required')
 def carry(self):
  c=super().carry()
  m=getattr(self,'chain_manifest',None)
  if m is not None:
   from .carry_chain import verify_chain
   srcs=[]
   if os.path.exists(self.path):  # never create a journal as a side effect of an accounting read
    cn=self.connect()  # an unreadable existing journal fails closed
    try:srcs=[r[0]for r in cn.execute('SELECT source FROM jobs').fetchall()]
    finally:cn.close()
   verify_chain(m,self.carry_sha,c,journal_sources=srcs,proof_dir=getattr(self,'chain_proof_dir',None))
  return c
 def plan(self,spec):
  p=spec.get('wide_scene')
  if not isinstance(p,dict)or set(p)!={'assess','authority_reference'}or not isinstance(p['authority_reference'],str)or not p['authority_reference'].strip():raise ValueError('Explicit source-bound sequential plan required')
  a=p['assess']
  if a!='all_eligible'and(not isinstance(a,list)or len(set(a))!=len(a)or any(not isinstance(i,str)or not i for i in a)):raise ValueError('all_eligible or exact unique person IDs required')
  return p
 def validate_binding(self,b):
  spec=self.approval_store.lookup(b['source_digest'],b['frame_size'])
  if spec['provenance']['scope']!=self.execution_scope or b['source_digest']in self.carry()['blocked_source_digests']:raise ValueError('Exact approved non-repeated source scope required')
  expected={'kind':KIND,'limits':asdict(self.wide_limits),'carry_sha256':self.carry_sha,'source_approval_snapshot':spec,'wide_plan':self.plan(spec),'zones':[],'export_allowed':False}
  if getattr(self,'_rebind',False):expected.pop('carry_sha256')  # only while the pinned continuation grant itself names prior and new checkpoints
  if any(type(b.get(k))is not type(v)or b[k]!=v for k,v in expected.items()):raise ValueError('Sequential limits/plan/approval changed')
 def prepare(self,raw,mime,zones):
  if zones!=[]:raise ValueError('Wide provider intake does not infer zone policy')
  f=decode_image(raw,mime);self.reject_derivative(f.digest)
  if f.orientation!=1:raise ValueError('Explicit upright source required')
  spec=self.approval_store.lookup(f.digest,[f.width,f.height]);png=pixel_only_png(raw,mime);sam=build_sam_image_request(png,'image/png','person');sam['store']=False
  b={'kind':KIND,'source_digest':f.digest,'frame_size':[f.width,f.height],'canonical_png_sha256':hashlib.sha256(png).hexdigest(),'sam_request_sha256':digest(sam),'limits':asdict(self.wide_limits),'carry_sha256':self.carry_sha,'source_approval_snapshot':spec,'wide_plan':self.plan(spec),'zones':[],'export_allowed':False}
  self.validate_binding(b);return f,png,sam,b
 def others_booked(self,c,source):
  from .stopped_source import original_total
  from .recheck_journal import reservation_total
  from .recheck_execution import verify_retained_rechecks
  from .ppe_segmentation import total as masks,verify_retained as verify_masks
  from .explanation_execution import total as explanations,verify_retained as verify_explanations
  verify_retained_rechecks(self,c);verify_masks(self,c);verify_explanations(self,c)
  mine=c.execute('SELECT reserved FROM jobs WHERE source=?',(source,)).fetchone();mine=Decimal(mine[0])if mine else Decimal('0')
  return Decimal(self.carry()['conservative_booked_usd'])+original_total(self,c)-mine+reservation_total(c)+masks(c)+explanations(c)
 def claim(self,b):
  self.validate_binding(b);c=self.connect()
  try:
   c.execute('BEGIN IMMEDIATE')
   if c.execute('SELECT 1 FROM jobs WHERE source=?',(b['source_digest'],)).fetchone():return False
   if c.execute('SELECT count(*) FROM jobs').fetchone()[0]>=64:raise ValueError('Wide source history full')
   if self.others_booked(c,b['source_digest'])+SAM>5:raise ValueError('Same aggregate cap unavailable for SAM stage')
   c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)',(b['source_digest'],'running_uncertain',str(SAM),'0',json.dumps(b),None,None,time.time()));c.commit()
   self.schema(c);return True
  finally:c.close()
 @staticmethod
 def schema(c):
  c.execute('CREATE TABLE IF NOT EXISTS wide_continuations(source TEXT,seq INTEGER,authority TEXT,person_ids TEXT,prior_result TEXT,prior_result_sha TEXT,at REAL,PRIMARY KEY(source,seq))');c.commit()
 def continuations(self,c,source):
  if not c.execute("SELECT 1 FROM sqlite_master WHERE name='wide_continuations'").fetchone():return []
  return c.execute('SELECT seq,authority,person_ids,prior_result,prior_result_sha FROM wide_continuations WHERE source=? ORDER BY seq',(source,)).fetchall()
 def authorized_ever(self,c,source,b):
  ids=list(b['plan_queue'])
  for r in self.continuations(c,source):ids+=[i for i in json.loads(r[2])['granted']if i not in ids]
  return ids
 def queue_ok(self,c,source,b):
  rows=self.continuations(c,source);run=b['queue']
  if len(set(run))!=len(run)or len(run)>self.wide_limits.max_people:raise ValueError('Run list invalid')
  if not rows:
   if b['plan_queue'][:len(run)]!=run:raise ValueError('Run list is not a prefix of the initial plan')
   return
  prev_carry=None;prev_all=None
  for i,(seq,grant,ids,pr,prs) in enumerate(rows):
   g=json.loads(grant);d=json.loads(ids)
   if seq!=i+1 or not isinstance(g.get('authority_reference'),str)or not g['authority_reference'].strip()or digest(json.loads(pr))!=prs:raise ValueError('Continuation record changed')
   if g['person_ids']!=d['granted']or g['source_digest']!=source or g['prior_carry_sha256']!=(prev_carry or g['prior_carry_sha256']):raise ValueError('Continuation grant/record mismatch')
   if prev_all is not None and prev_all[:len(d['prior_run'])]!=d['prior_run']:raise ValueError('Continuation chain changed')
   if len(set(d['prior_run']+d['granted']))!=len(d['prior_run']+d['granted']):raise ValueError('Duplicate person stage')
   prev_carry=g['carry_sha256'];prev_all=d['prior_run']+d['granted']
  d=json.loads(rows[-1][2]);full=d['prior_run']+d['granted']
  if full[:len(run)]!=run or len(run)<len(d['prior_run'])or b['carry_sha256']!=prev_carry:raise ValueError('Run list/carry does not match last authorized continuation')
 def expected_body(self,raw,b,index):
  if index==0:e=build_sam_image_request(raw,'image/png','person');e['store']=False;return e
  person=next(p for p in b['persons']if p['id']==b['queue'][index-1]);return canonical_body(crop_png(raw,person['box_half_open']))
 def dispatch(self,source,ordinal,body):
  c=self.connect()
  try:
   c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT state,binding FROM jobs WHERE source=?',(source,)).fetchone()
   if not row or row[0]!='running_uncertain':raise ValueError('Active exact sequential claim required')
   b=json.loads(row[1]);self.validate_binding(b)
   calls=c.execute('SELECT state,cost FROM calls WHERE source=? ORDER BY ordinal',(source,)).fetchall()
   if len(calls)!=ordinal or any(r[0]!='completed'for r in calls):raise ValueError('No skipped, repeated or post-uncertain stage')
   if ordinal>0:
    self.queue_ok(c,source,b)
    if ordinal>len(b['queue']):raise ValueError('No extra person call')
   raw=self.private_bytes(self.path.parent/('fresh-'+source+'-source.png'))
   if hashlib.sha256(raw).hexdigest()!=b['canonical_png_sha256']:raise ValueError('Original source changed')
   if body!=self.expected_body(raw,b,ordinal):raise ValueError('Canonical exact request required')
   known=sum((Decimal(r[1])for r in calls),Decimal('0'));need=known+(SAM if ordinal==0 else MAX_COST)
   if ordinal>0 and self.others_booked(c,source)+need>5:raise BudgetDeferred('Aggregate cap cannot hold next person stage')
   c.execute('INSERT INTO calls VALUES(?,?,?,?,?,?,?)',(source,ordinal,body['model'],'attempted_uncertain',digest(body),None,'0'));c.execute('UPDATE jobs SET reserved=? WHERE source=?',(str(need),source));c.commit()
  finally:c.close()
  self.save_private(self.path.parent/('fresh-'+source+'-'+str(ordinal)+'-request.json'),json.dumps(body,sort_keys=True).encode());raw=self.transport(body)
  if not isinstance(raw,bytes)or len(raw)>(4_000_000 if ordinal==0 else 256_000):raise ValueError('Response quota exceeded')
  self.save_private(self.path.parent/('fresh-'+source+'-'+str(ordinal)+'-reply.bin'),raw)
  c=self.connect()
  try:c.execute('UPDATE calls SET state=?,response_sha=? WHERE source=? AND ordinal=?',('received_unparsed',hashlib.sha256(raw).hexdigest(),source,ordinal));c.commit()
  finally:c.close()
  return raw
 def record_cost(self,source,ordinal,cost):
  c=self.connect()
  try:
   c.execute('BEGIN IMMEDIATE');c.execute('UPDATE calls SET state=?,cost=? WHERE source=? AND ordinal=?',('completed',str(cost),source,ordinal))
   total=sum((Decimal(r[0])for r in c.execute('SELECT cost FROM calls WHERE source=?',(source,))),Decimal('0'))
   c.execute('UPDATE jobs SET cost=?,reserved=? WHERE source=?',(str(total),str(total),source));c.commit()
  finally:c.close()
 def result(self,source,b,frame,objects,response,ppe,deferred):
  gates=eligibility(objects,self.wide_limits);persons=[];raw=self.private_bytes(self.path.parent/('fresh-'+source+'-source.png'))
  for obj in self.geometry(objects,frame):
   pid=obj['id'];obs=ppe.get(pid)
   withheld=any(q.get('mask')is None for q in objects)
   reason='provider_observed'if obs else'geometry_unverified_not_assessed'if obj.get('mask')is None else'budget_deferred_never_attempted'if pid in deferred else'crop_evidence_ineligible'if not gates[pid]['eligible_for_selected_crop_call']else'ppe_withheld_source_has_unverified_geometry'if withheld else'not_selected_within_explicit_PPE_call_budget'
   persons.append({**obj,'crop_png_sha256':hashlib.sha256(crop_png(raw,obj['box_half_open'])).hexdigest(),'helmet':obs['observation']['helmet']if obs else'unknown','vest':obs['observation']['vest']if obs else'unknown','ppe_assessed':obs is not None,'provider_observation':obs,'ppe_evidence_status':reason,'crop_eligibility':gates[pid],'selected_for_PPE':pid in b['plan_queue']or pid in b['queue'],'contact_status':'not_checked','compliance_status':'not_evaluated'})
  elig=[p['id']for p in persons if p['crop_eligibility']['eligible_for_selected_crop_call']]
  cov='all_eligible_people_assessed'if all(p['ppe_assessed']for p in persons if p['id']in elig)else'partial_eligible_people_unassessed'
  unverified=any(p.get('geometry_status')=='unverified_box_only'for p in persons)
  if unverified:cov='ppe_withheld_source_unverified_geometry'
  return {'source':'fresh_upload_provider_review','image':{'pixel_digest':source,'width':frame.width,'height':frame.height},'persons':persons,'zones':[],'zone_status':'not_checked','compliance_status':'not_evaluated','findings':None,'review_status':'needs_human_review','privacy_review_status':'not_validated','evidence_export_allowed':False,'sam_response_id':response['id'],'wide_scene':{'capacity':self.wide_limits.max_people,'detected_person_count':len(persons),'PPE_assessed_count':len(ppe),'eligible_person_count':len(elig),'budget_deferred_never_attempted':sorted(deferred),'all_detected_persons_retained':True,'geometry_unverified_count':sum(p.get('geometry_status')=='unverified_box_only'for p in persons),'geometry_quarantine_mode':self.wide_limits.geometry_quarantine,'ppe_withheld_unverified_geometry':unverified,'all_detected_people_assessed':all(p['ppe_assessed']for p in persons),'job_state_is_execution_terminal_not_assessment_complete':True,'coverage':cov,'job_state':'partial_completed'if deferred else 'completed','ineligible_unassessed_count':sum(p['ppe_evidence_status']=='crop_evidence_ineligible'for p in persons),'not_selected_eligible_count':sum(p['ppe_evidence_status']=='not_selected_within_explicit_PPE_call_budget'for p in persons),'minimum_crop_size_is_technical_not_accuracy_validation':True,'sequential':True},'provider_proof':'local_request_response_consistency_not_provider_signature'}
 def collect(self,source,b,raw,f,calls,c):
  """Verify every completed stage from retained artifacts; returns objects,response,ppe,known,pending."""
  response,objects=self.parsed(self.private_bytes(self.path.parent/('fresh-'+source+'-0-reply.bin')),f)
  if self.geometry(objects,f)!=b['persons']:raise ValueError('Wide geometry changed')
  self.queue_ok(c,source,b);ppe={};known=Decimal('0');pending=False
  for pos,(index,model,state,req,rep,cost) in enumerate(calls):
   if index!=pos or pending:raise ValueError('Call ordering changed')
   if state!='completed':pending=True;continue
   request=json.loads(self.private_bytes(self.path.parent/('fresh-'+source+'-'+str(index)+'-request.json')));reply=self.private_bytes(self.path.parent/('fresh-'+source+'-'+str(index)+'-reply.bin'))
   if digest(request)!=req or hashlib.sha256(reply).hexdigest()!=rep or request!=self.expected_body(raw,b,index)or model!=request['model']:raise ValueError('Artifacts/canonical request changed')
   if index==0:listed=SAM
   else:ppe[b['queue'][index-1]]=parse_reply(reply);listed=Decimal(ppe[b['queue'][index-1]]['listed_cost_usd'])
   if Decimal(cost)!=listed:raise ValueError('Listed cost changed')
   known+=listed
  return objects,response,ppe,known,pending
 def read(self,source):
  if not self.path.exists():return None
  self.private_bytes(self.path);c=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)
  try:
   row=c.execute('SELECT state,reserved,cost,binding,result,result_sha FROM jobs WHERE source=?',(source,)).fetchone()
   if not row:return None
   calls=c.execute('SELECT ordinal,model,state,request_sha,response_sha,cost FROM calls WHERE source=? ORDER BY ordinal',(source,)).fetchall()
   b=json.loads(row[3]);self.validate_binding(b)
   if row[0]not in('running_uncertain','partial_completed','completed'):raise ValueError('Sequential state changed')
   result=json.loads(row[4])if row[4]else None;known=Decimal('0');pending=False;ppe={}
   if calls:
    raw=self.private_bytes(self.path.parent/('fresh-'+source+'-source.png'));f=decode_image(raw,'image/png')
    if f.digest!=source or hashlib.sha256(raw).hexdigest()!=b['canonical_png_sha256']:raise ValueError('Source changed')
    if calls[0][2]=='completed':
     if 'queue'not in b:
      if len(calls)!=1:raise ValueError('Plan queue not yet persisted')
      known=SAM
     else:objects,response,ppe,known,pending=self.collect(source,b,raw,f,calls,c)
    else:pending=True
   exp=Decimal(row[1]);last=len(calls)-1
   if pending:need=SAM if last==0 else known+MAX_COST
   else:need=known if calls else SAM
   if exp!=need:raise ValueError('Reservation does not match verified stage state')
   if row[0]!='running_uncertain'and(pending or Decimal(row[2])!=known or exp!=known):raise ValueError('Final accounting mismatch')
   if row[0]=='running_uncertain'and Decimal(row[2])!=known:raise ValueError('Cost mismatch')
   if row[0]=='running_uncertain'and result is not None:raise ValueError('Unexpected result')
   if row[0]!='running_uncertain':
    if 'queue'not in b:raise ValueError('Final state without queue')
    if result is None or digest(result)!=row[5]:raise ValueError('Result missing/changed')
    deferred=[i for i in self.authorized_ever(c,source,b)if i not in ppe]
    if len(b['queue'])!=len(calls)-1:raise ValueError('Final run list does not match completed stages')
    if row[0]=='completed'and deferred:raise ValueError('Completed with deferred people')
    if row[0]=='partial_completed'and not deferred:raise ValueError('Partial without deferred people')
    if result!=self.result(source,b,f,objects,response,ppe,deferred):raise ValueError('Wide result changed')
  finally:c.close()
  return {'state':row[0],'result':result,'binding':b,'reservation_usd':row[1],'known_listed_usd':row[2],'requires_operator_reconciliation':row[0]=='running_uncertain'and(pending if calls else True),'resumable_without_repeat':row[0]=='running_uncertain'and bool(calls)and not pending and calls[0][2]=='completed','continuation_requires_new_authority':row[0]=='partial_completed','retry_allowed':False,'provider_calls_this_request':0,'actual_debit':'unchecked','evidence_export_allowed':False,'execution_status':{'completed':'sequential_queue_complete_not_accuracy_qualification','partial_completed':'partial_budget_deferred_never_attempted','running_uncertain':'in_progress_or_terminal_uncertain_no_retry'}[row[0]]}
 def settle(self,source):
  raw=self.private_bytes(self.path.parent/('fresh-'+source+'-source.png'));f=decode_image(raw,'image/png');c=self.connect()
  try:
   row=c.execute('SELECT binding FROM jobs WHERE source=?',(source,)).fetchone();b=json.loads(row[0])
   calls=c.execute('SELECT ordinal,model,state,request_sha,response_sha,cost FROM calls WHERE source=? ORDER BY ordinal',(source,)).fetchall()
   if any(r[2]!='completed'for r in calls):raise ValueError('Pending call: terminal uncertain')
   b['queue']=b['queue'][:len(calls)-1]  # unattempted authorized stages become deferred, never silently kept
   objects,response,ppe,known,pending=self.collect(source,b,raw,f,calls,c)
   deferred=[i for i in self.authorized_ever(c,source,b)if i not in ppe];r=self.result(source,b,f,objects,response,ppe,deferred);state='partial_completed'if deferred else'completed'
   c.execute('UPDATE jobs SET state=?,binding=?,result=?,result_sha=?,reserved=?,cost=? WHERE source=?',(state,json.dumps(b),json.dumps(r),digest(r),str(known),str(known),source));c.commit()
  finally:c.close()
 def advance(self,source,f):
  """Run remaining queue stages. Budget stop -> partial_completed. Any other failure -> terminal uncertain."""
  while True:
   c=self.connect()
   try:
    row=c.execute('SELECT state,binding FROM jobs WHERE source=?',(source,)).fetchone();b=json.loads(row[1])
    n=c.execute('SELECT count(*) FROM calls WHERE source=?',(source,)).fetchone()[0]
   finally:c.close()
   if row[0]!='running_uncertain':return
   if 'queue'not in b:
    if n!=1:raise ValueError('Cannot derive queue')
    self.start(source,f,b);continue
   if n-1>=len(b['queue']):self.settle(source);return
   raw=self.private_bytes(self.path.parent/('fresh-'+source+'-source.png'));body=self.expected_body(raw,b,n)
   try:reply=self.dispatch(source,n,body)
   except BudgetDeferred:self.settle(source);return
   pid=b['queue'][n-1];parsed=parse_reply(reply);self.record_cost(source,n,Decimal(parsed['listed_cost_usd']))
 def start(self,source,f,b):
  """After SAM completed: persist deterministic person geometry and queue once."""
  raw=self.private_bytes(self.path.parent/('fresh-'+source+'-source.png'))
  response,objects=self.parsed(self.private_bytes(self.path.parent/('fresh-'+source+'-0-reply.bin')),f);gates=eligibility(objects,self.wide_limits);plan=b['wide_plan']
  if plan['assess']=='all_eligible':ids=[str(o['object_id'])for o in objects if gates[str(o['object_id'])]['eligible_for_selected_crop_call']]
  else:
   if any(i not in gates for i in plan['assess']):raise ValueError('Selected person ID absent; no PPE dispatch')
   ids=[i for i in plan['assess']if gates[i]['eligible_for_selected_crop_call']]
  if any(o.get('mask')is None for o in objects):ids=[]  # any unverified geometry: new PPE dispatch withheld for the whole source
  b['persons']=self.geometry(objects,f);b['queue']=ids[:self.wide_limits.max_ppe_calls];b['plan_queue']=list(b['queue'])
  c=self.connect()
  try:c.execute('UPDATE jobs SET binding=? WHERE source=? AND state=?',(json.dumps(b),source,'running_uncertain'));c.commit()
  finally:c.close()
 GRANT_KEYS={'format','execution_scope','source_digest','prior_result_sha256','prior_carry_sha256','carry_sha256','person_ids','max_additional_calls','aggregate_cap_usd','per_stage_reserve_usd','authority_reference'}
 def continue_partial(self,source,grant_path,grant_sha256):
  """Exact pinned grant only. Binds source, prior result, prior/current accounting checkpoint,
  exact person IDs, call count, cap and per-stage reserve. Software verifies binding, not that
  the owner really gave it: the grant file's provenance is owner evidence outside this module."""
  from pathlib import Path
  if self.transport is disabled_transport:raise LiveTransportDisabled('Wide dispatch disabled')
  raw=self.private_bytes(Path(grant_path))
  if not isinstance(grant_sha256,str)or hashlib.sha256(raw).hexdigest()!=grant_sha256:raise ValueError('Exact pinned continuation grant required')
  g=json.loads(raw);self._rebind=True
  try:old=self.read(source)
  finally:self._rebind=False
  if not old or old['state']not in('partial_completed','completed'):raise ValueError('Verified partial or cap-limited job required')
  if any(p.get('geometry_status')=='unverified_box_only'for p in (old['result']or{}).get('persons',[])):raise ValueError('No PPE continuation for a source with unverified geometry')
  b=old['binding'];res=old['result']
  ids=g.get('person_ids')
  if set(g)!=self.GRANT_KEYS or g['format']!='vigilens.wide-continuation-grant.v1'or not isinstance(g['authority_reference'],str)or not g['authority_reference'].strip():raise ValueError('Exact continuation grant shape required')
  if not isinstance(ids,list)or not ids or len(set(ids))!=len(ids)or type(g['max_additional_calls'])is not int or isinstance(g['max_additional_calls'],bool)or not 1<=g['max_additional_calls']<=16 or len(ids)>g['max_additional_calls']:raise ValueError('Exact person IDs and call bound required')
  exp={'execution_scope':self.execution_scope,'source_digest':source,'prior_result_sha256':digest(res),'prior_carry_sha256':b['carry_sha256'],'carry_sha256':self.carry_sha,'aggregate_cap_usd':'5','per_stage_reserve_usd':str(MAX_COST)}
  if any(g[k]!=v for k,v in exp.items()):raise ValueError('Grant does not match this exact source/result/accounting/cap')
  elig={p['id']:p['crop_eligibility']['eligible_for_selected_crop_call']for p in res['persons']};assessed={p['id']for p in res['persons']if p['ppe_assessed']}
  for i in ids:
   if i not in elig or not elig[i]or i in assessed:raise ValueError('Only eligible not-yet-assessed people may continue')
  if len(b['queue'])+len(ids)>self.wide_limits.max_people:raise ValueError('Capacity')
  if g['carry_sha256']!=g['prior_carry_sha256']:
   c=self.connect()
   try:others=c.execute('SELECT count(*) FROM jobs WHERE source!=?',(source,)).fetchone()[0]
   finally:c.close()
   # Every other job binds the old checkpoint; rebinding would invalidate them. Fail closed, change nothing.
   if others:raise ValueError('Checkpoint change refused: other journal jobs are bound to the prior accounting checkpoint')
  f=decode_image(self.private_bytes(self.path.parent/('fresh-'+source+'-source.png')),'image/png');c=self.connect()
  try:
   self.schema(c);c.execute('BEGIN IMMEDIATE')
   r=c.execute('SELECT state,binding,result,result_sha FROM jobs WHERE source=?',(source,)).fetchone()
   if r[0]not in('partial_completed','completed')or r[3]!=g['prior_result_sha256']:raise ValueError('Grant already used or job changed')
   nb=json.loads(r[1]);seq=len(self.continuations(c,source))+1;prior=list(nb['queue']);nb['queue']=prior+ids;nb['carry_sha256']=self.carry_sha
   c.execute('INSERT INTO wide_continuations VALUES(?,?,?,?,?,?,?)',(source,seq,json.dumps(g,sort_keys=True),json.dumps({'prior_run':prior,'granted':ids}),r[2],r[3],time.time()))
   c.execute('UPDATE jobs SET state=?,binding=?,result=NULL,result_sha=NULL WHERE source=?',('running_uncertain',json.dumps(nb),source));c.commit()
  finally:c.close()
  before=self.attempted_count(source)
  try:self.advance(source,f)
  except Exception:pass
  return {**self.read(source),'provider_calls_this_request':self.attempted_count(source)-before}
 async def run(self,raw,mime,zones):
  f,png,sam,b=self.prepare(raw,mime,zones);source=f.digest;old=self.read(source)
  if old and not old['resumable_without_repeat']:return old
  if self.transport is disabled_transport:raise LiveTransportDisabled('Wide dispatch disabled')
  if old:
   before=self.attempted_count(source)
   try:self.advance(source,f)
   except Exception:pass
   out=self.read(source);return {**out,'provider_calls_this_request':self.attempted_count(source)-before}
  if not self.claim(b):return self.read(source)
  try:
   self.save_private(self.path.parent/('fresh-'+source+'-source.png'),png);reply=self.dispatch(source,0,sam);completion=wire_completed(reply)
   if completion.get('model')!='sam-3.1'or not completion.get('id')or completion.get('usage',{}).get('images_processed')!=1:raise ValueError('Completed SAM image required')
   self.record_cost(source,0,SAM);self.start(source,f,b);self.advance(source,f)
  except Exception:return {**self.read_safe(source),'provider_calls_this_request':self.attempted_count(source),'notice':'Sequential source stopped, hold retained, no retry'}
  out=self.read(source);return {**out,'provider_calls_this_request':self.attempted_count(source)}
 def read_safe(self,source):
  try:return self.read(source)
  except ValueError:
   # Between SAM completion and queue persistence the strict read refuses; report held state.
   return {'state':'running_uncertain','result':None,'requires_operator_reconciliation':True,'retry_allowed':False,'resumable_without_repeat':False}
