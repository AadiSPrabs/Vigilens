"""Explicit loopback entrypoint. Does not claim public authentication."""
import argparse
import os
import json
from pathlib import Path
import uvicorn
from job_api import create_job_app
from limits import LocalAdmissionLimits
from access import LocalBearerGate
from operations import LocalOperations

def build(database,manifest=None,scope='local-fixture-review',body_limit=16_000_000,concurrency=2,queue_limit=32,local_token=None,journal_record_limit=1024,local_rate_limit=120):
    data=json.loads(Path(manifest).read_text()) if manifest else None
    app=create_job_app(database,data,scope,queue_limit=queue_limit,cooperative_worker=True,journal_record_limit=journal_record_limit)
    bounded=LocalAdmissionLimits(app,body_limit,concurrency)
    operational=LocalOperations(bounded,max_requests=local_rate_limit)
    return LocalBearerGate(operational,local_token) if local_token is not None else operational

def main():
    p=argparse.ArgumentParser(description='Vigilens LOCAL review server; no real model analysis or public access')
    p.add_argument('--database',required=True);p.add_argument('--manifest')
    p.add_argument('--port',type=int,default=8000)
    a=p.parse_args()
    if not 1024<=a.port<=65535:p.error('Use an unprivileged local port 1024..65535')
    # Bind is deliberately not caller-selectable. Existing external setup needs review.
    uvicorn.run(build(a.database,a.manifest,local_token=os.environ.get('VIGILENS_LOCAL_ACCESS_TOKEN')),host='127.0.0.1',port=a.port,access_log=False)

if __name__=='__main__':main()
