"""Append-only SAM helmet/vest masks, separate from immutable person/PPE result.
Exact request grant and shared aggregate required. Empty masks never prove absence.
"""
import json,hashlib,time,concurrent.futures,asyncio
from decimal import Decimal
from pathlib import Path
from PIL import Image
from core import decode_image
from pipeline import Frame
from adapters import build_sam_image_request,LiveTransportDisabled
from sam_parser import parse_sam_image_text
from .pipeline import digest,RESERVE,disabled_transport
from .masks import encode_mask,decode_mask
from .ppe import wire_completed
from .recheck_journal import reservation_total
COST=Decimal('.0025');BATCH_RESERVE=COST*2
CONCEPTS=('helmet','vest')

def total(connection):
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='ppe_mask_batches'").fetchone():return Decimal('0')
    value=Decimal('0')
    for identity,source,result_sha,plan_raw,plan_sha,state,cost in connection.execute('SELECT id,source,result_sha,plan,plan_sha,state,cost FROM ppe_mask_batches'):
        plan=json.loads(plan_raw)
        if digest(plan)!=plan_sha or digest({'source':source,'result_sha':result_sha,'plan_sha':plan_sha})!=identity or plan.get('source_digest')!=source or plan.get('result_sha256')!=result_sha:raise ValueError('SAM PPE batch identity changed')
        if state not in ('reserved_not_dispatched','attempted_uncertain','completed'):raise ValueError('Invalid SAM PPE state')
        if not Decimal(cost).is_finite()or not 0<=Decimal(cost)<=BATCH_RESERVE:raise ValueError('Invalid SAM PPE cost')
        value+=Decimal(cost)if state=='completed'else BATCH_RESERVE
    return value

class PpeSegmentation:
    def __init__(self,service,*,approval_path=None,approval_sha256=None):
        self.service=service;self.approval_path=Path(approval_path)if approval_path else None;self.approval_sha=approval_sha256
    def schema(self,c):
        c.execute('CREATE TABLE IF NOT EXISTS ppe_mask_batches(id TEXT PRIMARY KEY,source TEXT,result_sha TEXT,plan TEXT,plan_sha TEXT,state TEXT,cost TEXT,result TEXT,result_hash TEXT,created REAL,UNIQUE(source,result_sha))')
        c.execute('CREATE TABLE IF NOT EXISTS ppe_mask_calls(id TEXT,ordinal INTEGER,state TEXT,request_sha TEXT,response_sha TEXT,cost TEXT,PRIMARY KEY(id,ordinal))')
    def plan(self,source):
        job=self.service.read(source)
        if not job or job['state']!='completed':raise ValueError('Completed original image required')
        raw=self.service.private_bytes(self.service.path.parent/('fresh-'+source+'-source.png'))
        requests=[]
        for concept in CONCEPTS:
            body=build_sam_image_request(raw,'image/png',concept);body['store']=False
            requests.append({'concept':concept,'request':body,'request_sha256':digest(body)})
        return {'source_digest':source,'result_sha256':digest(job['result']),'steps':requests,'scope':'original_source_auxiliary_ppe_masks','empty_detection':'not_proof_of_absence','source_geometry_update_allowed':False}
    def approve(self,plan):
        if self.approval_path is None:raise ValueError('Exact auxiliary segmentation grant required')
        raw=self.service.private_bytes(self.approval_path)
        if hashlib.sha256(raw).hexdigest()!=self.approval_sha:raise ValueError('Grant pin changed')
        grant=json.loads(raw)
        expected={'format':'vigilens.exact-ppe-mask-grant.v1','execution_scope':self.service.execution_scope,'source_digest':plan['source_digest'],'result_sha256':plan['result_sha256'],'plan_sha256':digest(plan),'max_reserved_usd':str(BATCH_RESERVE)}
        if set(grant)!=set(expected)|{'authority_reference'}or any(grant[k]!=v for k,v in expected.items())or not isinstance(grant['authority_reference'],str)or not grant['authority_reference'].strip():raise ValueError('Grant must cover exact source/requests/amount')
        return grant
    def reserve(self,source):
        plan=self.plan(source);self.approve(plan);sha=digest(plan);identity=digest({'source':source,'result_sha':plan['result_sha256'],'plan_sha':sha})
        c=self.service.connect()
        try:
            self.schema(c);c.commit();c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM ppe_mask_batches WHERE id=?',(identity,)).fetchone():return identity
            if c.execute('SELECT count(*) FROM ppe_mask_batches').fetchone()[0]>=64:raise ValueError('PPE mask history full')
            rows=c.execute('SELECT source,state,cost FROM jobs').fetchall()
            for old,_,_ in rows:self.service.read(old)
            from .recheck_execution import verify_retained_rechecks
            verify_retained_rechecks(self.service,c);verify_retained(self.service,c)
            from .explanation_execution import total as explanation_total,verify_retained as verify_explanations
            verify_explanations(self.service,c)
            from .stopped_source import original_total
            booked=Decimal(self.service.carry()['conservative_booked_usd'])+original_total(self.service,c)+reservation_total(c)+total(c)+explanation_total(c)
            if booked+BATCH_RESERVE>Decimal('5'):raise ValueError('Shared aggregate insufficient')
            c.execute('INSERT INTO ppe_mask_batches VALUES(?,?,?,?,?,?,?,?,?,?)',(identity,source,plan['result_sha256'],json.dumps(plan,sort_keys=True),sha,'reserved_not_dispatched','0',None,None,time.time()));c.commit()
            return identity
        finally:c.close()
    def artifact(self,identity,ordinal,suffix):return self.service.path.parent/('ppe-masks-'+identity+'-'+str(ordinal)+'-'+suffix)
    async def parse(self,raw,source,concept):
        response=wire_completed(raw)
        if response.get('model')!='sam-3.1'or not response.get('id')or response.get('usage',{}).get('images_processed')!=1:raise ValueError('Expected SAM PPE completion')
        source_png=self.service.private_bytes(self.service.path.parent/('fresh-'+source+'-source.png'));frame=decode_image(source_png,'image/png')
        text=''.join(p['text']for item in response.get('output',[])for p in item.get('content',[])if p.get('type')=='output_text')
        parsed=await parse_sam_image_text(text,Frame(frame.width,frame.height,source),wire_completed=True)
        return {'concept':concept,'response_id':response['id'],'objects':[{'object_id':str(o['object_id']),'box_half_open':list(o['box_half_open']),'mask':encode_mask(o['mask'],list(o['box_half_open']),[frame.width,frame.height])}for o in parsed['objects']],
                'empty_detection':'not_proof_of_absence','worn_by_person':'not_inferred_by_segmentation','listed_cost_usd':str(COST)}
    def read(self,identity,connection=None):
        c=connection or self.service.connect()
        try:
            total(c)
            row=c.execute('SELECT source,result_sha,plan,state,cost,result,result_hash FROM ppe_mask_batches WHERE id=?',(identity,)).fetchone()
            if row is None:raise ValueError('Unknown SAM PPE batch')
            plan=json.loads(row[2])
            if self.plan(row[0])!=plan:raise ValueError('Original source/request plan changed')
            calls=c.execute('SELECT ordinal,state,request_sha,response_sha,cost FROM ppe_mask_calls WHERE id=? ORDER BY ordinal',(identity,)).fetchall()
            parsed=[]
            if [r[0]for r in calls]!=list(range(len(calls)))or len(calls)>2:raise ValueError('PPE mask call ordering changed')
            for ordinal,state,req_sha,resp_sha,cost in calls:
                body=json.loads(self.service.private_bytes(self.artifact(identity,ordinal,'request.json')))
                if body!=plan['steps'][ordinal]['request']or digest(body)!=req_sha:raise ValueError('PPE mask request changed')
                if state=='completed':
                    raw=self.service.private_bytes(self.artifact(identity,ordinal,'reply.bin'))
                    if hashlib.sha256(raw).hexdigest()!=resp_sha or Decimal(cost)!=COST:raise ValueError('PPE mask response/cost changed')
                    def parse():return asyncio.run(self.parse(raw,row[0],CONCEPTS[ordinal]))
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1)as pool:parsed.append(pool.submit(parse).result())
                elif state!='attempted_uncertain':raise ValueError('PPE mask stage changed')
            result=json.loads(row[5])if row[5]else None
            if row[3]!='completed'and(result is not None or Decimal(row[4])!=0):raise ValueError('Uncertain PPE result/cost changed')
            if row[3]=='completed'and(len(calls)!=2 or len(parsed)!=2 or Decimal(row[4])!=BATCH_RESERVE or result is None or digest(result)!=row[6]or result['segmentations']!=parsed):raise ValueError('PPE mask completion association changed')
            return {'batch_id':identity,'source_digest':row[0],'result_sha256':row[1],'state':row[3],'segmentations':result['segmentations']if result else None,'provider_calls_this_request':0,'retry_allowed':False,'evidence_export_allowed':False,'absence_or_worn_status':'not_inferred_from_masks','original_result_unchanged':True}
        finally:
            if connection is None:c.close()
    async def run(self,identity):
        current=self.read(identity)
        if current['state']!='reserved_not_dispatched':return current
        if self.service.transport is disabled_transport:raise LiveTransportDisabled('SAM PPE dispatch not enabled; no claim, state change or call created')
        plan=self.plan(current['source_digest']);self.approve(plan);c=self.service.connect()
        try:
            c.execute('BEGIN IMMEDIATE');total(c)
            changed=c.execute('UPDATE ppe_mask_batches SET state=? WHERE id=? AND state=?',('attempted_uncertain',identity,'reserved_not_dispatched')).rowcount;c.commit()
        finally:c.close()
        if changed!=1:return self.read(identity)
        results=[]
        try:
            for ordinal,step in enumerate(plan['steps']):
                self.approve(plan);self.plan(current['source_digest']);self.service.carry()
                body=step['request'];c=self.service.connect()
                try:
                    c.execute('BEGIN IMMEDIATE');total(c);verify_retained(self.service,c)
                    rows=c.execute('SELECT state FROM ppe_mask_calls WHERE id=?',(identity,)).fetchall()
                    if len(rows)!=ordinal or any(r[0]!='completed'for r in rows):raise ValueError('No skipped/retried SAM PPE stage')
                    self.service.save_private(self.artifact(identity,ordinal,'request.json'),json.dumps(body,sort_keys=True).encode())
                    c.execute('INSERT INTO ppe_mask_calls VALUES(?,?,?,?,?,?)',(identity,ordinal,'attempted_uncertain',digest(body),None,'0'));c.commit()
                finally:c.close()
                raw=self.service.transport(body)
                if not isinstance(raw,bytes)or len(raw)>4_000_000:raise ValueError('Bounded SAM PPE response required')
                self.service.save_private(self.artifact(identity,ordinal,'reply.bin'),raw)
                parsed=await self.parse(raw,current['source_digest'],step['concept']);results.append(parsed)
                c=self.service.connect()
                try:c.execute('UPDATE ppe_mask_calls SET state=?,response_sha=?,cost=? WHERE id=? AND ordinal=?',('completed',hashlib.sha256(raw).hexdigest(),str(COST),identity,ordinal));c.commit()
                finally:c.close()
            result={'segmentations':results};c=self.service.connect()
            try:c.execute('UPDATE ppe_mask_batches SET state=?,cost=?,result=?,result_hash=? WHERE id=?',('completed',str(BATCH_RESERVE),json.dumps(result,sort_keys=True),digest(result),identity));c.commit()
            finally:c.close()
        except Exception:return {**self.read(identity),'provider_calls_this_request':None,'notice':'Retained uncertain auxiliary segmentation; no retry or original overwrite'}
        return {**self.read(identity),'provider_calls_this_request':2}

def verify_retained(service,connection):
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='ppe_mask_batches'").fetchone():return
    helper=PpeSegmentation(service)
    for identity, in connection.execute('SELECT id FROM ppe_mask_batches').fetchall():helper.read(identity,connection)
