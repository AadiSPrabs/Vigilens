"""Explicit, one-attempt crop recheck execution. Mounted only when a pinned recheck grant is configured.
Requires a pinned private exact-request approval file, same-aggregate reservation,
and original immutable result. No automatic retry, fallback or result overwrite.
"""
import asyncio,json,hashlib,sqlite3,base64,concurrent.futures
from decimal import Decimal
from pathlib import Path
from pipeline import Frame
from core import decode_image
from sam_parser import parse_sam_image_text
from adapters import LiveTransportDisabled
from .pipeline import digest,disabled_transport
from .recheck_journal import RecheckJournal,RECHECK_RESERVE,reservation_total
from .rechecks import compare_candidate,plan_recheck
from .ppe import wire_completed,parse_reply

class RecheckExecutor:
    def __init__(self,service,*,approval_path=None,approval_sha256=None):
        self.service=service;self.approval_path=Path(approval_path)if approval_path is not None else None;self.approval_sha256=approval_sha256
    def approval(self,attempt):
        if self.approval_path is None:raise ValueError('Pinned execution grant required')
        raw=self.service.private_bytes(self.approval_path)
        if hashlib.sha256(raw).hexdigest()!=self.approval_sha256:raise ValueError('Exact pinned recheck approval required')
        doc=json.loads(raw);plan=attempt['plan']
        required={'format','execution_scope','source_digest','result_sha256','person_id','plan_sha256','authority_reference','request_sha256','max_reserved_usd'}
        if set(doc)!=required or doc['format']!='vigilens.exact-recheck-approval.v1':raise ValueError('Exact recheck grant shape required')
        expected={'execution_scope':self.service.execution_scope,'source_digest':plan['source_digest'],'result_sha256':plan['result_sha256'],'person_id':plan['person_id'],'plan_sha256':digest(plan),'request_sha256':[s['request_sha256']for s in plan['steps']],'max_reserved_usd':str(RECHECK_RESERVE)}
        if any(doc[k]!=v for k,v in expected.items())or not isinstance(doc['authority_reference'],str)or not doc['authority_reference'].strip():raise ValueError('Approval does not cover this exact crop/requests/bound')
        return doc
    def schema(self,c):
        c.execute('CREATE TABLE IF NOT EXISTS recheck_calls(attempt_id TEXT,ordinal INTEGER,state TEXT,request_sha TEXT,response_sha TEXT,cost TEXT,PRIMARY KEY(attempt_id,ordinal))')
        c.execute('CREATE TABLE IF NOT EXISTS recheck_results(attempt_id TEXT PRIMARY KEY,result TEXT,result_sha TEXT)')
    def artifact(self,aid,ordinal,suffix):return self.service.path.parent/('recheck-'+aid+'-'+str(ordinal)+'-'+suffix)
    def read(self,aid,connection=None):
        c=connection or self.service.connect()
        try:
            reservation_total(c)
            row=c.execute('SELECT state,plan,plan_sha,cost FROM recheck_attempts WHERE attempt_id=?',(aid,)).fetchone()
            if row is None:raise ValueError('Unknown recheck attempt')
            plan=json.loads(row[1]);job=self.service.read(plan['source_digest'])
            if job is None or digest(job['result'])!=plan['result_sha256']:raise ValueError('Original result changed')
            source_png=self.service.private_bytes(self.service.path.parent/('fresh-'+plan['source_digest']+'-source.png'))
            if plan!=plan_recheck(source_png,job['result'],plan['person_id'],attempts_so_far=0,max_attempts=1):raise ValueError('Recheck plan differs from canonical original crop')
            tables={r[0]for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            calls=c.execute('SELECT ordinal,state,request_sha,response_sha,cost FROM recheck_calls WHERE attempt_id=? ORDER BY ordinal',(aid,)).fetchall()if'recheck_calls'in tables else[]
            result=c.execute('SELECT result,result_sha FROM recheck_results WHERE attempt_id=?',(aid,)).fetchone()if'recheck_results'in tables else None
            costs=Decimal('0')
            for ordinal,state,req,reply,cost in calls:
                body=json.loads(self.service.private_bytes(self.artifact(aid,ordinal,'request.json')))
                if body!=plan['steps'][ordinal]['request']or digest(body)!=req:raise ValueError('Recheck request artifact changed')
                if state=='completed':
                    raw=self.service.private_bytes(self.artifact(aid,ordinal,'reply.bin'))
                    if hashlib.sha256(raw).hexdigest()!=reply:raise ValueError('Recheck reply artifact changed')
                    if ordinal==0:
                        completion=wire_completed(raw)
                        if completion.get('model')!='sam-3.1'or completion.get('usage',{}).get('images_processed')!=1 or not completion.get('id'):raise ValueError('Recheck SAM completion changed')
                    expected=Decimal('.0025')if ordinal==0 else Decimal(parse_reply(raw)['listed_cost_usd'])
                    if Decimal(cost)!=expected:raise ValueError('Recheck cost association changed')
                    costs+=expected
                elif state!='attempted_uncertain':raise ValueError('Recheck call state changed')
            if row[0]=='completed':
                if len(calls)!=2 or any(call[1]!='completed'for call in calls)or costs!=Decimal(row[3])or result is None or digest(json.loads(result[0]))!=result[1]:raise ValueError('Completed recheck binding incomplete')
                candidate=parse_reply(self.service.private_bytes(self.artifact(aid,1,'reply.bin')))
                person=next(p for p in job['result']['persons']if p['id']==plan['person_id'])
                expected=compare_candidate({k:person[k]for k in ('helmet','vest')},{k:candidate['observation'][k]for k in ('helmet','vest')})
                def association_check():return asyncio.run(self.associate_crop({'plan':plan},wire_completed(self.service.private_bytes(self.artifact(aid,0,'reply.bin'))),person))
                with concurrent.futures.ThreadPoolExecutor(max_workers=1)as pool:association=pool.submit(association_check).result()
                retained=json.loads(result[0])
                if retained.get('crop_person_association')!=association or any(retained.get(k)!=v for k,v in expected.items())or retained.get('candidate_response')!=candidate or retained.get('source_digest')!=plan['source_digest']or retained.get('result_sha256')!=plan['result_sha256']or retained.get('person_id')!=plan['person_id']:raise ValueError('Recheck candidate/original association changed')
            return {'attempt_id':aid,'state':row[0],'plan':plan,'result':json.loads(result[0])if result else None,'retry_allowed':False,'provider_calls_this_request':0,'evidence_export_allowed':False}
        finally:
            if connection is None:c.close()
    def dispatch(self,attempt,ordinal):
        self.approval(attempt);self.service.read(attempt['plan']['source_digest']);self.service.carry()
        aid=attempt['attempt_id'];body=attempt['plan']['steps'][ordinal]['request']
        c=self.service.connect()
        try:
            self.schema(c);c.commit();c.execute('BEGIN IMMEDIATE');reservation_total(c)
            verify_retained_rechecks(self.service,c)
            if c.execute('SELECT state FROM recheck_attempts WHERE attempt_id=?',(aid,)).fetchone()[0]!='attempted_uncertain':raise ValueError('Active retained recheck claim required')
            rows=c.execute('SELECT ordinal,state FROM recheck_calls WHERE attempt_id=? ORDER BY ordinal',(aid,)).fetchall()
            if len(rows)!=ordinal or any(s!='completed'for _,s in rows):raise ValueError('No retry or skipped stage')
            # Save first; any interruption leaves a file or row that blocks reuse.
            self.service.save_private(self.artifact(aid,ordinal,'request.json'),json.dumps(body,sort_keys=True,separators=(',',':')).encode())
            c.execute('INSERT INTO recheck_calls VALUES(?,?,?,?,?,?)',(aid,ordinal,'attempted_uncertain',digest(body),None,'0'));c.commit()
        finally:c.close()
        reply=self.service.transport(body)
        if not isinstance(reply,bytes)or len(reply)>(4_000_000 if ordinal==0 else 256_000):raise ValueError('Bounded recheck response required')
        self.service.save_private(self.artifact(aid,ordinal,'reply.bin'),reply)
        return reply
    async def associate_crop(self,attempt,response,person):
        from PIL import Image,ImageChops
        from .masks import decode_mask
        uri=attempt['plan']['steps'][0]['request']['input'][0]['content'][1]['image_url']
        crop=base64.b64decode(uri.split(',',1)[1],validate=True);frame=decode_image(crop,'image/png')
        text=''.join(p['text']for item in response.get('output',[])for p in item.get('content',[])if p.get('type')=='output_text')
        parsed=await parse_sam_image_text(text,Frame(frame.width,frame.height,frame.digest),wire_completed=True)
        if len(parsed['objects'])!=1:raise ValueError('Ambiguous crop-person association')
        obj=parsed['objects'][0];l,t,r,b=obj['box_half_open'];cx,cy=frame.width//2,frame.height//2
        if not l<=cx<r or not t<=cy<b or not obj['mask'].getpixel((cx-l,cy-t)):raise ValueError('Crop centre association missing')
        candidate=Image.new('L',(frame.width,frame.height));candidate.paste(obj['mask'],(l,t))
        original=decode_mask(person['mask'])
        if original.size!=candidate.size:raise ValueError('Original crop mask size changed')
        intersection=sum(v//255 for v in ImageChops.darker(original,candidate).tobytes())
        union=sum(v//255 for v in ImageChops.lighter(original,candidate).tobytes())
        if not union or intersection/union<.5:raise ValueError('Crop overlap association insufficient')
        return {'basis':'single_crop_mask_centre_and_original_foreground_overlap_not_identity_proof','intersection_pixels':intersection,'union_pixels':union,'minimum_iou':.5}
    def settle_call(self,aid,ordinal,raw,cost):
        c=self.service.connect()
        try:c.execute('UPDATE recheck_calls SET state=?,response_sha=?,cost=? WHERE attempt_id=? AND ordinal=?',('completed',hashlib.sha256(raw).hexdigest(),str(cost),aid,ordinal));c.commit()
        finally:c.close()
    async def run(self,aid):
        attempt=self.read(aid)
        if attempt['state']!='reserved_not_dispatched':return attempt
        if self.service.transport is disabled_transport:raise LiveTransportDisabled('Recheck dispatch not enabled; no claim, state change or call created')
        grant=self.approval(attempt)
        c=self.service.connect()
        try:
            self.schema(c);c.commit();c.execute('BEGIN IMMEDIATE');reservation_total(c)
            ref=c.execute('SELECT authority_reference FROM recheck_attempts WHERE attempt_id=?',(aid,)).fetchone()[0]
            if ref!=grant['authority_reference']:raise ValueError('Reservation authority reference differs')
            changed=c.execute('UPDATE recheck_attempts SET state=? WHERE attempt_id=? AND state=?',('attempted_uncertain',aid,'reserved_not_dispatched')).rowcount;c.commit()
        finally:c.close()
        if changed!=1:return self.read(aid)
        try:
            raw=self.dispatch(attempt,0);response=wire_completed(raw)
            if response.get('model')!='sam-3.1'or response.get('usage',{}).get('images_processed')!=1 or not response.get('id'):raise ValueError('Exact SAM crop completion required')
            self.settle_call(aid,0,raw,Decimal('.0025'))
            job=self.service.read(attempt['plan']['source_digest']);person=next(p for p in job['result']['persons']if p['id']==attempt['plan']['person_id'])
            association=await self.associate_crop(attempt,response,person)
            raw=self.dispatch(attempt,1);candidate=parse_reply(raw);self.settle_call(aid,1,raw,Decimal(candidate['listed_cost_usd']))
            job=self.service.read(attempt['plan']['source_digest']);person=next(p for p in job['result']['persons']if p['id']==attempt['plan']['person_id'])
            out=compare_candidate({k:person[k]for k in ('helmet','vest')},{k:candidate['observation'][k]for k in ('helmet','vest')})
            out.update(source_digest=attempt['plan']['source_digest'],result_sha256=attempt['plan']['result_sha256'],person_id=person['id'],crop_person_association=association,candidate_response=candidate)
            c=self.service.connect()
            try:
                cost=sum((Decimal(r[0])for r in c.execute('SELECT cost FROM recheck_calls WHERE attempt_id=?',(aid,))),Decimal('0'))
                if cost>RECHECK_RESERVE:raise ValueError('Recheck reserved bound exceeded')
                c.execute('INSERT INTO recheck_results VALUES(?,?,?)',(aid,json.dumps(out,sort_keys=True),digest(out)))
                c.execute('UPDATE recheck_attempts SET state=?,cost=? WHERE attempt_id=?',('completed',str(cost),aid));c.commit()
            finally:c.close()
        except Exception:
            return {**self.read(aid),'provider_calls_this_request':None,'notice':'Retained uncertain recheck. No retry, original unchanged; human review required.'}
        return {**self.read(aid),'provider_calls_this_request':2}


def verify_retained_rechecks(service,connection):
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='recheck_attempts'").fetchone():return
    ids=[r[0]for r in connection.execute('SELECT attempt_id FROM recheck_attempts')]
    verifier=RecheckExecutor(service)
    for aid in ids:verifier.read(aid,connection=connection)
