"""One explicit granted Muse commentary stage, append-only shared accounting.
No authority to alter deterministic fields or run from unreviewed/currently stale context.
"""
import json,hashlib,time
from pathlib import Path
from decimal import Decimal
from adapters import LiveTransportDisabled
from .pipeline import digest,RESERVE,disabled_transport
from .ppe import MAX_COST
from .spatial_explanation import parse_spatial_reply

def total(c):
    if not c.execute("SELECT 1 FROM sqlite_master WHERE name='explanation_attempts'").fetchone():return Decimal('0')
    value=Decimal('0')
    for identity,plan_raw,plan_sha,state,cost,result,result_sha in c.execute('SELECT id,plan,plan_sha,state,cost,result,result_sha FROM explanation_attempts'):
        plan=json.loads(plan_raw)
        if digest(plan)!=plan_sha or identity!=digest({'source':plan['source_digest'],'context':plan['context_sha256'],'request':plan['request_sha256']}):raise ValueError('Explanation identity changed')
        if state not in ('reserved_not_dispatched','attempted_uncertain','completed')or not Decimal(cost).is_finite()or not 0<=Decimal(cost)<=MAX_COST:raise ValueError('Explanation accounting state changed')
        if state=='completed'and(result is None or digest(json.loads(result))!=result_sha):raise ValueError('Explanation result changed')
        value+=Decimal(cost)if state=='completed'else MAX_COST
    return value

class ExplanationExecutor:
    def __init__(self,service,*,approval_path=None,approval_sha256=None):
        self.service=service;self.path=Path(approval_path)if approval_path else None;self.sha=approval_sha256
    def schema(self,c):c.execute('CREATE TABLE IF NOT EXISTS explanation_attempts(id TEXT PRIMARY KEY,source TEXT,context_sha TEXT,plan TEXT,plan_sha TEXT,state TEXT,cost TEXT,result TEXT,result_sha TEXT,created REAL)')
    def approve(self,plan):
        if self.path is None:raise ValueError('Exact explanation grant required')
        raw=self.service.private_bytes(self.path)
        if hashlib.sha256(raw).hexdigest()!=self.sha:raise ValueError('Explanation grant changed')
        grant=json.loads(raw);expected={'format':'vigilens.exact-explanation-grant.v1','execution_scope':self.service.execution_scope,'plan_sha256':digest(plan),'maximum_reserved_usd':str(MAX_COST)}
        if set(grant)!=set(expected)|{'authority_reference'}or any(grant[k]!=v for k,v in expected.items())or not isinstance(grant['authority_reference'],str)or not grant['authority_reference'].strip():raise ValueError('Exact request/context/bound grant required')
    def artifact(self,identity,suffix):return self.service.path.parent/('explanation-'+identity+'-'+suffix)
    def reserve(self,plan):
        self.approve(plan)
        job=self.service.read(plan['source_digest'])
        if job is None or digest(job['result'])!=plan['result_sha256']or digest(plan['request'])!=plan['request_sha256']:raise ValueError('Exact original/request binding required')
        identity=digest({'source':plan['source_digest'],'context':plan['context_sha256'],'request':plan['request_sha256']});c=self.service.connect()
        try:
            self.schema(c);c.commit();c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM explanation_attempts WHERE id=?',(identity,)).fetchone():return identity
            if c.execute('SELECT count(*) FROM explanation_attempts').fetchone()[0]>=64:raise ValueError('Explanation history full')
            from .recheck_journal import reservation_total
            from .recheck_execution import verify_retained_rechecks
            from .ppe_segmentation import total as mask_total,verify_retained as verify_masks
            has_jobs=c.execute("SELECT 1 FROM sqlite_master WHERE name='jobs'").fetchone()
            if not has_jobs and not getattr(self.service,'archive_verification_only',False):raise ValueError('Original jobs or explicit archive verifier required')
            rows=c.execute('SELECT source,state,cost FROM jobs').fetchall()if has_jobs else[]
            for source,_,_ in rows:self.service.read(source)
            verify_retained_rechecks(self.service,c);verify_masks(self.service,c);verify_retained(self.service,c)
            from .stopped_source import original_total
            booked=Decimal(self.service.carry()['conservative_booked_usd'])+(original_total(self.service,c)if has_jobs else Decimal('0'))+reservation_total(c)+mask_total(c)+total(c)
            if booked+MAX_COST>Decimal('5'):raise ValueError('Same aggregate cap insufficient for explanation')
            c.execute('INSERT INTO explanation_attempts VALUES(?,?,?,?,?,?,?,?,?,?)',(identity,plan['source_digest'],plan['context_sha256'],json.dumps(plan,sort_keys=True),digest(plan),'reserved_not_dispatched','0',None,None,time.time()));c.commit()
            return identity
        finally:c.close()
    def read(self,identity,c=None):
        connection=c or self.service.connect()
        try:
            total(connection)
            row=connection.execute('SELECT plan,state,cost,result FROM explanation_attempts WHERE id=?',(identity,)).fetchone()
            if row is None:raise ValueError('Unknown explanation attempt')
            plan=json.loads(row[0]);job=self.service.read(plan['source_digest'])
            if job is None or digest(job['result'])!=plan['result_sha256']:raise ValueError('Original source/result changed')
            result=json.loads(row[3])if row[3]else None
            if row[1]=='completed':
                body=json.loads(self.service.private_bytes(self.artifact(identity,'request.json')))
                raw=self.service.private_bytes(self.artifact(identity,'reply.bin'))
                if body!=plan['request']or parse_spatial_reply(raw,plan)!=result or Decimal(result['listed_cost_usd'])!=Decimal(row[2]):raise ValueError('Explanation request/response/cost association changed')
            elif result is not None or Decimal(row[2])!=0:raise ValueError('Uncertain explanation cannot publish result')
            return {'attempt_id':identity,'state':row[1],'context_sha256':plan['context_sha256'],'source_digest':plan['source_digest'],'result_sha256':plan['result_sha256'],'result':result,'retry_allowed':False,'provider_calls_this_request':0,'evidence_export_allowed':False}
        finally:
            if c is None:connection.close()
    def run(self,identity,current_plan):
        existing=self.read(identity)
        if existing['context_sha256']!=current_plan['context_sha256']:raise ValueError('Current review context changed')
        if existing['state']=='reserved_not_dispatched'and self.service.transport is disabled_transport:raise LiveTransportDisabled('Explanation dispatch not enabled; no claim, state change or call created')
        self.approve(current_plan);c=self.service.connect()
        try:
            c.execute('BEGIN IMMEDIATE');total(c)
            row=c.execute('SELECT plan FROM explanation_attempts WHERE id=?',(identity,)).fetchone()
            if json.loads(row[0])!=current_plan:raise ValueError('Exact retained request plan required')
            if existing['state']!='reserved_not_dispatched':return existing
            changed=c.execute('UPDATE explanation_attempts SET state=? WHERE id=? AND state=?',('attempted_uncertain',identity,'reserved_not_dispatched')).rowcount;c.commit()
        finally:c.close()
        if changed!=1:return self.read(identity)
        try:
            self.service.read(current_plan['source_digest']);self.service.carry();self.approve(current_plan)
            c=self.service.connect()
            try:
                from .recheck_execution import verify_retained_rechecks
                from .ppe_segmentation import verify_retained as verify_masks
                verify_retained_rechecks(self.service,c);verify_masks(self.service,c);verify_retained(self.service,c)
            finally:c.close()
            self.service.save_private(self.artifact(identity,'request.json'),json.dumps(current_plan['request'],sort_keys=True).encode())
            raw=self.service.transport(current_plan['request'])
            if not isinstance(raw,bytes)or len(raw)>256_000:raise ValueError('Bounded explanation response required')
            self.service.save_private(self.artifact(identity,'reply.bin'),raw);result=parse_spatial_reply(raw,current_plan)
            c=self.service.connect()
            try:c.execute('UPDATE explanation_attempts SET state=?,cost=?,result=?,result_sha=? WHERE id=?',('completed',result['listed_cost_usd'],json.dumps(result,sort_keys=True),digest(result),identity));c.commit()
            finally:c.close()
        except Exception:return {**self.read(identity),'provider_calls_this_request':None,'notice':'Uncertain explanation held; no retry or deterministic result change'}
        return {**self.read(identity),'provider_calls_this_request':1}

def verify_retained(service,c):
    if not c.execute("SELECT 1 FROM sqlite_master WHERE name='explanation_attempts'").fetchone():return
    for identity, in c.execute('SELECT id FROM explanation_attempts').fetchall():ExplanationExecutor(service).read(identity,c)
