"""Offline durable usage reservation model, integer micro-units only.
Not vendor billing, not currency conversion, not user spending authorization.
Uncertain dispatch retains its reservation until explicit reconciliation.
"""
from contextlib import contextmanager
import sqlite3
import uuid
from private_sqlite import require_private_file

class BudgetExceeded(Exception):pass
class UsageConflict(Exception):pass
class UsageLedger:
    def __init__(self,path):
        self.path=str(path)
        require_private_file(self.path)
        with self.tx() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS usage_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,reservation_id TEXT NOT NULL,state TEXT NOT NULL,reason TEXT NOT NULL)''')
            c.execute('''CREATE TABLE IF NOT EXISTS local_usage(scope TEXT NOT NULL,request_key TEXT NOT NULL,reservation_id TEXT NOT NULL UNIQUE,cap_units INTEGER NOT NULL,state TEXT NOT NULL,charged_units INTEGER,PRIMARY KEY(scope,request_key))''')
    @contextmanager
    def tx(self):
        c=sqlite3.connect(self.path,timeout=10,isolation_level=None);c.row_factory=sqlite3.Row;c.execute('PRAGMA synchronous=FULL');c.execute('BEGIN IMMEDIATE')
        try:yield c;c.commit()
        except BaseException:c.rollback();raise
        finally:c.close()
    def reserve(self,scope,key,cap_units,budget_units):
        if not all(isinstance(v,str) and 1<=len(v)<=128 for v in (scope,key)) or any(type(v) is not int or not 0<=v<=10**12 for v in (cap_units,budget_units)):raise ValueError('Explicit local scope/key and integer test units required')
        with self.tx() as c:
            old=c.execute('SELECT * FROM local_usage WHERE scope=? AND request_key=?',(scope,key)).fetchone()
            if old:
                if old['cap_units']!=cap_units:raise UsageConflict('Key binds a different reservation cap')
                return old['reservation_id'],False
            used=c.execute("SELECT COALESCE(SUM(CASE WHEN state='settled' THEN charged_units WHEN state IN ('reserved','uncertain') THEN cap_units ELSE 0 END),0) FROM local_usage WHERE scope=?",(scope,)).fetchone()[0]
            if used+cap_units>budget_units:raise BudgetExceeded('Local reservation budget exceeded')
            rid='reservation-'+uuid.uuid4().hex;c.execute('INSERT INTO local_usage VALUES(?,?,?,?,?,NULL)',(scope,key,rid,cap_units,'reserved'));c.execute('INSERT INTO usage_events(reservation_id,state,reason) VALUES(?,?,?)',(rid,'reserved','local test reservation'));return rid,True
    def uncertain(self,rid,scope):
        with self.tx() as c:
            r=self._row(c,rid,scope)
            if r['state']!='reserved':raise UsageConflict('Only reserved work can become uncertain')
            c.execute("UPDATE local_usage SET state='uncertain' WHERE reservation_id=?",(rid,))
            c.execute('INSERT INTO usage_events(reservation_id,state,reason) VALUES(?,?,?)',(rid,'uncertain','local simulated dispatch boundary; outcome unknown'))
    def release_before_dispatch(self,rid,scope):
        with self.tx() as c:
            r=self._row(c,rid,scope)
            if r['state']!='reserved':raise UsageConflict('Uncertain or settled reservations cannot be released as unbilled')
            c.execute("UPDATE local_usage SET state='released',charged_units=0 WHERE reservation_id=?",(rid,))
            c.execute('INSERT INTO usage_events(reservation_id,state,reason) VALUES(?,?,?)',(rid,'released','explicit local pre-dispatch release'))
    def reconcile(self,rid,scope,actual_units,reason):
        if type(actual_units) is not int or not 0<=actual_units<=10**12 or not isinstance(reason,str) or not reason.strip():raise ValueError('Explicit measured test amount and review reason required')
        with self.tx() as c:
            r=self._row(c,rid,scope)
            if r['state']=='settled':
                if r['charged_units']==actual_units:return False
                raise UsageConflict('Settled amount cannot be changed by duplicate reconciliation')
            if r['state'] not in ('reserved','uncertain') or actual_units>r['cap_units']:raise UsageConflict('Cannot reconcile outside reserved maximum or terminal state')
            c.execute("UPDATE local_usage SET state='settled',charged_units=? WHERE reservation_id=?",(actual_units,rid))
            c.execute('INSERT INTO usage_events(reservation_id,state,reason) VALUES(?,?,?)',(rid,'settled','explicit local reconciliation reviewed'))
            return True
    def _row(self,c,rid,scope):
        r=c.execute('SELECT * FROM local_usage WHERE reservation_id=? AND scope=?',(rid,scope)).fetchone()
        if r is None:raise KeyError(rid)
        return r
    def get(self,rid,scope):
        with self.tx() as c:return dict(self._row(c,rid,scope))

    def events(self,rid,scope):
        with self.tx() as c:
            self._row(c,rid,scope)
            return [dict(r) for r in c.execute('SELECT * FROM usage_events WHERE reservation_id=? ORDER BY seq',(rid,))]
