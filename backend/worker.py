"""Bounded local-fixture worker with cooperative heartbeat/cancel checks.
No background thread, process killing, model dispatch or automatic uncertain retry.
"""
import threading
import math
from ledger import LeaseLost

class WorkerBusy(Exception):pass
class CooperativeStop(Exception):pass

class LocalWorker:
    def __init__(self,ledger,lease_seconds=30,timeout_seconds=60):
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (lease_seconds,timeout_seconds)):raise ValueError('Positive finite limits required')
        self.ledger=ledger;self.lease_seconds=lease_seconds;self.timeout_seconds=timeout_seconds
        self.lock=threading.Lock();self.stopping=False
    def shutdown(self):self.stopping=True
    def run(self,job_id,work):
        if self.stopping:return self.ledger.get(job_id)
        if not self.lock.acquire(blocking=False):raise WorkerBusy('Local concurrency limit reached')
        try:
            token=self.ledger.claim(job_id,self.lease_seconds)
            if token is None:return self.ledger.get(job_id)
            started=self.ledger.clock()
            def checkpoint():
                if self.stopping or self.ledger.clock()-started>=self.timeout_seconds:raise CooperativeStop()
                self.ledger.heartbeat(job_id,token,self.lease_seconds)
            try:
                checkpoint();result=work(checkpoint);checkpoint()
                if not isinstance(result,dict) or result.get('source') not in ('fixture','mock'):raise ValueError('Unapproved local result source')
                self.ledger.complete(job_id,token,result)
            except CooperativeStop:
                # Never overwrite a row concurrently reconciled by an operator.
                try:self.ledger.mark_local_interrupted(job_id,token)
                except LeaseLost:self.ledger.recover_expired()
            except LeaseLost:
                self.ledger.recover_expired()
            except Exception:
                try:self.ledger.fail(job_id,token,'LOCAL_EXECUTION_FAILED')
                except LeaseLost:self.ledger.recover_expired()
            return self.ledger.get(job_id)
        finally:self.lock.release()
