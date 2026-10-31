"""Same-aggregate append-only deliberate recheck reservations. No provider dispatch.
No separate journal/reset; exact immutable original result and request plan bound.
"""
import json,time,sqlite3
from decimal import Decimal
from .pipeline import digest,RESERVE
from .ppe import MAX_COST
from .rechecks import plan_recheck
RECHECK_RESERVE=Decimal('.0025')+MAX_COST
MAX_ATTEMPTS_TOTAL=64

def reservation_total(connection):
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='recheck_attempts'").fetchone():return Decimal('0')
    rows=connection.execute('SELECT state,reserved,cost,plan,plan_sha,source,result_sha,person,ordinal,attempt_id FROM recheck_attempts').fetchall()
    total=Decimal('0')
    for state,reserved,cost,plan_raw,plan_sha,source,result_sha,person,ordinal,attempt_id in rows:
        plan=json.loads(plan_raw)
        if digest(plan)!=plan_sha or plan.get('source_digest')!=source or plan.get('result_sha256')!=result_sha or plan.get('person_id')!=person or plan.get('attempt')!=ordinal or digest({'source':source,'result_sha':result_sha,'person':person,'ordinal':ordinal,'plan_sha':plan_sha})!=attempt_id:raise ValueError('Recheck reservation identity changed')
        if state not in ('reserved_not_dispatched','attempted_uncertain','completed')or Decimal(reserved)!=RECHECK_RESERVE:raise ValueError('Recheck accounting state changed')
        cost=Decimal(cost)
        if not cost.is_finite()or not 0<=cost<=RECHECK_RESERVE:raise ValueError('Recheck accounting cost invalid')
        total+=cost if state=='completed'else RECHECK_RESERVE
    return total

class RecheckJournal:
    def __init__(self,service):self.service=service
    def schema(self,c):
        c.execute('CREATE TABLE IF NOT EXISTS recheck_attempts(attempt_id TEXT PRIMARY KEY,source TEXT,result_sha TEXT,person TEXT,ordinal INTEGER,plan TEXT,plan_sha TEXT,state TEXT,reserved TEXT,cost TEXT,authority_reference TEXT,created REAL,UNIQUE(source,result_sha,person,ordinal))')
    def reserve(self,source,person,*,max_attempts,authority_reference):
        if not isinstance(authority_reference,str)or not 1<=len(authority_reference.strip())<=200:raise ValueError('Explicit reviewed execution authority reference required; not inferred from source approval')
        job=self.service.read(source)
        if not job or job['state']!='completed':raise ValueError('Completed original result required')
        result_sha=digest(job['result']);raw=self.service.private_bytes(self.service.path.parent/('fresh-'+source+'-source.png'))
        c=self.service.connect()
        try:
            self.schema(c);c.commit();c.execute('BEGIN IMMEDIATE')
            existing=c.execute('SELECT attempt_id,plan,plan_sha,state,authority_reference FROM recheck_attempts WHERE source=? AND result_sha=? AND person=? ORDER BY ordinal DESC LIMIT 1',(source,result_sha,person)).fetchone()
            if existing:
                if digest(json.loads(existing[1]))!=existing[2]or existing[4]!=authority_reference:raise ValueError('Existing attempt binding/authority differs')
                # No implicit next attempt from repeated reserve; always deduplicates.
                return {'attempt_id':existing[0],'state':existing[3],'plan':json.loads(existing[1]),'new_reservation':False,'dispatch_enabled':False}
            if c.execute('SELECT count(*) FROM recheck_attempts').fetchone()[0]>=MAX_ATTEMPTS_TOTAL:raise ValueError('Recheck history cap reached; preserve attempts')
            plan=plan_recheck(raw,job['result'],person,attempts_so_far=0,max_attempts=max_attempts)
            if plan['status']!='planned_not_authorised_or_dispatched':return {**plan,'new_reservation':False,'dispatch_enabled':False}
            # Re-validate all prior original jobs/artifacts and aggregate before booking.
            rows=c.execute('SELECT source,state,cost FROM jobs').fetchall()
            for oldsource,_,_ in rows:self.service.read(oldsource)
            from .recheck_execution import verify_retained_rechecks
            verify_retained_rechecks(self.service,c)
            from .ppe_segmentation import total as mask_total,verify_retained
            verify_retained(self.service,c)
            from .explanation_execution import total as explanation_total,verify_retained as verify_explanations
            verify_explanations(self.service,c)
            prior=Decimal(self.service.carry()['conservative_booked_usd'])
            from .stopped_source import original_total
            booked=prior+original_total(self.service,c)+reservation_total(c)+mask_total(c)+explanation_total(c)
            if booked+RECHECK_RESERVE>Decimal('5'):raise ValueError('Same aggregate cap unavailable; recheck/original holds count in full')
            identity=digest({'source':source,'result_sha':result_sha,'person':person,'ordinal':1,'plan_sha':digest(plan)})
            c.execute('INSERT INTO recheck_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(identity,source,result_sha,person,1,json.dumps(plan,sort_keys=True),digest(plan),'reserved_not_dispatched',str(RECHECK_RESERVE),'0',authority_reference,time.time()));c.commit()
            return {'attempt_id':identity,'state':'reserved_not_dispatched','plan':plan,'new_reservation':True,'dispatch_enabled':False}
        finally:c.close()
