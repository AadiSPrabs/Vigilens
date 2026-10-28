"""Persistent local request journal. No network, models, credentials or automatic retries.
SQLite serializes state transitions across processes. It cannot guarantee that an
external vendor did not bill a request; uncertain outcomes require reconciliation.
"""
import math
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from private_sqlite import require_private_file

class Conflict(Exception): pass
class QueueFull(Exception): pass
class InvalidTransition(Exception): pass
class LeaseLost(Exception): pass

STATES={'queued','running','completed','failed','needs_review','cancelled'}

def fingerprint(image_digest,zones,schema_version,ruleset_version):
    """Inputs must be validated first. Bind policy/schema versions to request identity."""
    blob=json.dumps(dict(image_digest=image_digest,zones=zones,schema=schema_version,rules=ruleset_version),sort_keys=True,separators=(',',':'),allow_nan=False)
    return hashlib.sha256(blob.encode()).hexdigest()

class Ledger:
    def __init__(self,path,clock=time.time,max_active=None,max_records=None,max_result_bytes=2_000_000):
        if max_active is not None and (type(max_active) is not int or not 1<=max_active<=10000):raise ValueError('Invalid local queue limit')
        if max_records is not None and (type(max_records) is not int or not 1<=max_records<=1_000_000):raise ValueError('Invalid journal record bound')
        if type(max_result_bytes) is not int or not 1<=max_result_bytes<=16_000_000:raise ValueError('Invalid local result bound')
        self.path=str(path);self.clock=clock;self.max_active=max_active;self.max_records=max_records;self.max_result_bytes=max_result_bytes
        require_private_file(self.path)
        with self._connection() as c:
            version=c.execute('PRAGMA user_version').fetchone()[0]
            if version>1:raise ValueError('Journal schema is newer than this backend; do not downgrade')
            self._enable_wal(c)
        with self._tx() as c:
            if c.execute('PRAGMA user_version').fetchone()[0]>1:raise ValueError('Journal schema is newer than this backend')
            c.execute('''CREATE TABLE IF NOT EXISTS jobs(
                scope TEXT NOT NULL, request_key TEXT NOT NULL, job_id TEXT NOT NULL UNIQUE,
                digest TEXT NOT NULL, state TEXT NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL, lease_until REAL,
                owner TEXT, external_started INTEGER NOT NULL DEFAULT 0,
                result TEXT, error_code TEXT, cost_state TEXT NOT NULL DEFAULT 'unknown', result_expired INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(scope,request_key))''')
            columns={r['name'] for r in c.execute('PRAGMA table_info(jobs)')}
            if 'cost_state' not in columns:
                c.execute("ALTER TABLE jobs ADD COLUMN cost_state TEXT NOT NULL DEFAULT 'unknown'")
            if 'result_expired' not in columns:
                c.execute("ALTER TABLE jobs ADD COLUMN result_expired INTEGER NOT NULL DEFAULT 0")
            c.execute('''CREATE TABLE IF NOT EXISTS events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT NOT NULL,
                occurred REAL NOT NULL, old_state TEXT,new_state TEXT NOT NULL,reason TEXT NOT NULL)''')
            c.execute('PRAGMA user_version=1')
    @staticmethod
    def _enable_wal(c, *, timeout=10, clock=time.monotonic, pause=time.sleep):
        # SQLite may bypass busy_timeout while changing journal mode concurrently.
        # Retry only local BUSY/LOCKED setup, never a job or external call.
        deadline=clock()+timeout
        while True:
            try:
                row=c.execute('PRAGMA journal_mode=WAL').fetchone()
                if not row or row[0].lower()!='wal':raise ValueError('WAL journal mode required')
                return
            except sqlite3.OperationalError as e:
                code=getattr(e,'sqlite_errorcode',None)
                busy=((code&255)in (5,6))if code is not None else str(e)in ('database is locked','database table is locked','database schema is locked','database is busy')
                if not busy or clock()>=deadline:raise
                pause(min(.025,max(0,deadline-clock())))

    @contextmanager
    def _connection(self):
        c=sqlite3.connect(self.path,timeout=10,isolation_level=None)
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA synchronous=FULL')
        c.execute('PRAGMA secure_delete=ON')
        try: yield c
        finally: c.close()
    @contextmanager
    def _tx(self):
        with self._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                yield c
                c.commit()
            except BaseException:
                c.rollback();raise
    def _event(self,c,j,old,new,reason):
        c.execute('INSERT INTO events(job_id,occurred,old_state,new_state,reason) VALUES(?,?,?,?,?)',(j,self.clock(),old,new,reason))
    def _row(self,c,j):
        r=c.execute('SELECT * FROM jobs WHERE job_id=?',(j,)).fetchone()
        if r is None:raise KeyError(j)
        return r
    def scoped_get(self,j,scope):
        with self._connection() as c:
            r=self._row(c,j)
            if r['scope']!=scope:raise KeyError(j)
        return self.get(j)
    def scoped_cancel(self,j,scope):
        with self._tx() as c:
            r=self._row(c,j)
            if r['scope']!=scope:raise KeyError(j)
            if r['state']=='queued':
                self._finish(c,j,'cancelled',None,None,'cancelled before execution');return True
            return False
    def expire_completed_results(self,completed_before):
        """Explicit local cleanup. Keep dedup tombstone/history; never re-execute."""
        if type(completed_before) not in (int,float) or not math.isfinite(completed_before):raise ValueError('Finite cleanup cutoff required')
        completed_before=float(completed_before)
        with self._tx() as c:
            rows=c.execute("SELECT job_id FROM jobs WHERE state='completed' AND updated<? AND result IS NOT NULL AND result_expired=0 AND cost_state='zero_local_only'",(completed_before,)).fetchall()
            for r in rows:
                c.execute('UPDATE jobs SET result=NULL,result_expired=1 WHERE job_id=?',(r['job_id'],))
                self._event(c,r['job_id'],'completed','completed','result payload expired; dedup tombstone retained')
            return len(rows)
    def get(self,j):
        with self._connection() as c:
            r=dict(self._row(c,j));r['result']=json.loads(r['result']) if r['result'] is not None else None
            r.pop('owner',None)
            return r
    def register(self,scope,key,digest):
        if not all(isinstance(v,str) and 0<len(v)<=256 for v in (scope,key,digest)):raise ValueError('Invalid request identity')
        with self._tx() as c:
            r=c.execute('SELECT * FROM jobs WHERE scope=? AND request_key=?',(scope,key)).fetchone()
            if r:
                if r['digest']!=digest:raise Conflict('Key already binds different input or policy')
                return r['job_id'],False
            if self.max_records is not None and c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]>=self.max_records:raise QueueFull('Local journal record bound reached; preserve existing rows')
            if self.max_active is not None and c.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]>=self.max_active:raise QueueFull('Local queue capacity reached')
            j='job-'+uuid.uuid4().hex;t=self.clock()
            c.execute('INSERT INTO jobs(scope,request_key,job_id,digest,state,created,updated) VALUES(?,?,?,?,?,?,?)',(scope,key,j,digest,'queued',t,t))
            self._event(c,j,None,'queued','registered')
            return j,True
    def claim(self,j,lease_seconds=30):
        if type(lease_seconds) not in (int,float) or not math.isfinite(lease_seconds) or lease_seconds<=0:raise ValueError('Positive finite lease required')
        with self._tx() as c:
            r=self._row(c,j)
            if r['state']!='queued':return None
            token=uuid.uuid4().hex;t=self.clock()
            c.execute('UPDATE jobs SET state=?,owner=?,lease_until=?,updated=? WHERE job_id=?',('running',token,t+lease_seconds,t,j))
            self._event(c,j,'queued','running','claimed')
            return token
    def _owned(self,c,j,token):
        r=self._row(c,j)
        if r['state']!='running' or r['owner']!=token or r['lease_until']<=self.clock():raise LeaseLost('Job ownership expired or changed; no further work allowed')
        return r
    def mark_local_interrupted(self,j,token):
        with self._tx() as c:
            r=self._row(c,j)
            if r['state']=='running' and r['owner']==token:
                self._finish(c,j,'needs_review',None,'LOCAL_WORK_INTERRUPTED','cooperative stop or timeout; no automatic retry')
                return
            if r['state']=='needs_review':return
            raise LeaseLost('Cannot alter a different owner or terminal job')
    def heartbeat(self,j,token,lease_seconds=30):
        if type(lease_seconds) not in (int,float) or not math.isfinite(lease_seconds) or lease_seconds<=0:raise ValueError('Positive finite lease required')
        with self._tx() as c:
            self._owned(c,j,token)
            c.execute('UPDATE jobs SET lease_until=?,updated=? WHERE job_id=?',(self.clock()+lease_seconds,self.clock(),j))
    def mark_external_started(self,j,token):
        """Record BEFORE any external side effect; this package never performs one."""
        with self._tx() as c:
            self._owned(c,j,token)
            c.execute('UPDATE jobs SET external_started=1,updated=? WHERE job_id=?',(self.clock(),j))
    def _finish(self,c,j,state,result,code,reason):
        old=self._row(c,j)['state']
        c.execute('UPDATE jobs SET state=?,result=?,error_code=?,owner=NULL,lease_until=NULL,updated=? WHERE job_id=?',(state,result,code,self.clock(),j))
        self._event(c,j,old,state,reason)
    def complete(self,j,token,result):
        if isinstance(result,dict) and result.get('source') in ('fixture','mock') and any(k in result for k in ('evidence_image','evidence_status','evidence_export_allowed','privacy_review_status')):
            result=dict(result,evidence_image=None,evidence_status='unavailable',evidence_export_allowed=False,privacy_review_status='not_validated')
        data=json.dumps(result,allow_nan=False,separators=(',',':'))
        if len(data.encode('utf-8'))>self.max_result_bytes:raise ValueError('Local result payload exceeds bound')
        with self._tx() as c:
            r=self._owned(c,j,token);self._finish(c,j,'completed',data,None,'completed')
            if not r['external_started'] and isinstance(result,dict) and result.get('source') in ('fixture','mock'):
                c.execute('UPDATE jobs SET cost_state=? WHERE job_id=?',('zero_local_only',j))
    def fail(self,j,token,code='LOCAL_FAILURE'):
        """No arbitrary raw exception text is persisted; safe error codes only."""
        if not code or len(code)>80 or any(ch not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for ch in code):raise ValueError('Use safe error code')
        with self._tx() as c:
            r=self._owned(c,j,token)
            target='needs_review' if r['external_started'] else 'failed'
            self._finish(c,j,target,None,code,'uncertain external outcome' if r['external_started'] else 'failed before external start')
    def cancel(self,j):
        with self._tx() as c:
            r=self._row(c,j)
            if r['state']=='queued':self._finish(c,j,'cancelled',None,None,'cancelled before execution');return True
            # User cancel is not evidence an in-flight request stopped or was unbilled.
            return False
    def recover_expired(self):
        with self._tx() as c:
            rows=c.execute('SELECT job_id FROM jobs WHERE state=? AND lease_until<=?',('running',self.clock())).fetchall()
            for r in rows:self._finish(c,r['job_id'],'needs_review',None,'WORKER_INTERRUPTED','expired lease; never automatically re-execute')
            return len(rows)
    def retry_pre_external(self,j):
        """Explicit retry allowed only for a recorded local pre-external failure."""
        with self._tx() as c:
            r=self._row(c,j)
            if r['state']!='failed' or r['external_started']:raise InvalidTransition('No automatic or uncertain retry')
            c.execute('UPDATE jobs SET state=?,error_code=NULL,updated=? WHERE job_id=?',('queued',self.clock(),j))
            self._event(c,j,'failed','queued','explicit pre-external retry')
    def reconcile_local_late_result(self,j,result,reason):
        """Explicit local-only reconciliation, never an automatic retry or paid-cost claim."""
        if not isinstance(result,dict) or result.get('source') not in ('fixture','mock'):
            raise ValueError('Only verified local fixture/mock reconciliation is supported')
        if not isinstance(reason,str) or not reason.strip():raise ValueError('Review reason required')
        result=dict(result,evidence_image=None,evidence_status='unavailable',evidence_export_allowed=False,privacy_review_status='not_validated')
        data=json.dumps(result,allow_nan=False,separators=(',',':'))
        if len(data.encode('utf-8'))>self.max_result_bytes:raise ValueError('Local result payload exceeds bound')
        with self._tx() as c:
            r=self._row(c,j)
            if r['state']!='needs_review' or r['external_started']:
                raise InvalidTransition('Only local uncertain work can be explicitly reconciled')
            self._finish(c,j,'completed',data,None,'explicit local late-result reconciliation')
            c.execute('UPDATE jobs SET cost_state=? WHERE job_id=?',('zero_local_only',j))
    def events(self,j):
        with self._connection() as c:
            self._row(c,j)
            return [dict(r) for r in c.execute('SELECT * FROM events WHERE job_id=? ORDER BY seq',(j,))]
