"""Pure no-network runner with dependency-injected local work only.
There is deliberately no model client or paid execution path in this slice.
"""
from ledger import LeaseLost

class LocalRunner:
    def __init__(self,ledger):self.ledger=ledger
    def run(self,job_id,work,lease_seconds=30):
        # A caller could inject arbitrary Python, so this is NOT a sandbox. The
        # application must supply reviewed LOCAL work; never compile user input.
        token=self.ledger.claim(job_id,lease_seconds)
        if token is None:return self.ledger.get(job_id)
        try:
            result=work()
            if not isinstance(result,dict) or result.get('source') not in ('fixture','mock'):
                self.ledger.fail(job_id,token,'UNAPPROVED_RESULT_SOURCE')
            else:self.ledger.complete(job_id,token,result)
        except LeaseLost:
            # Expiry means outcome unknown: reconciliation is required, not retry.
            self.ledger.recover_expired()
        except Exception:
            try:self.ledger.fail(job_id,token,'LOCAL_EXECUTION_FAILED')
            except LeaseLost:self.ledger.recover_expired()
        return self.ledger.get(job_id)
