"""Run a complete labelled LOCAL synthetic HTTP demo with no model calls.
Creates temporary journal and pixels, never downloads worksite media or secrets.
"""
import io
import json
import tempfile
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from core import decode_image
from job_api import create_job_app
from limits import LocalAdmissionLimits
from pipeline import Frame,Observation,SegmentationBatch,OfflinePipeline
from worker import LocalWorker
from ledger import Ledger

def run_demo():
    b=io.BytesIO();Image.new('RGB',(160,90),'#ddeeff').save(b,'PNG');pixels=b.getvalue()
    polygon=[{'x':.1,'y':.1},{'x':.3,'y':.1},{'x':.3,'y':.8},{'x':.1,'y':.8}]
    zones=[{'id':'synthetic-zone','name':'SYNTHETIC test zone','hazard':True,'points':[{'x':0,'y':0},{'x':1,'y':0},{'x':1,'y':1},{'x':0,'y':1}]}]
    digest=decode_image(pixels,'image/png').digest
    manifest={'image_digest':digest,'zones':zones,'audit':{'persons':[{'id':'synthetic-person','polygon':polygon,'helmet':'present','vest':'present','findings':[]}]}}
    with tempfile.TemporaryDirectory(prefix='vigilens-offline-') as d:
        app=create_job_app(Path(d)/'http.sqlite',manifest,cooperative_worker=True,journal_record_limit=16)
        with TestClient(LocalAdmissionLimits(app)) as c:
            def submit():return c.post('/local/jobs',files={'image':('synthetic.png',pixels,'image/png')},data={'zones':json.dumps(zones)},headers={'Idempotency-Key':'synthetic-demo-key'})
            first=submit();repeat=submit();job=first.json()['job']
            assert first.status_code==201 and repeat.status_code==200 and job==repeat.json()['job']
            assert job['state']=='completed' and not job['result']['evidence_export_allowed']
        # Second path is explicit mock observations -> draft rules -> durable result.
        l=Ledger(Path(d)/'pipeline.sqlite');j,_=l.register('synthetic-demo','pipeline-key','local-labelled-input')
        batch=SegmentationBatch(Frame(160,90,digest),(Observation('synthetic-person',tuple(polygon),'absent','unknown'),),True)
        def work(checkpoint):checkpoint();return OfflinePipeline().run(batch,zones)
        result=LocalWorker(l).run(j,work)['result'];p=result['persons'][0]
        assert p['assessment_status']=='needs_human_review' and not result['evidence_export_allowed']
        return {'notice':'SYNTHETIC LOCAL DEMO ONLY - no model call, no real person or evidence release.',
                'http_fixture_job':{'state':job['state'],'duplicate_created_new_execution':False,'source':job['result']['source']},
                'offline_pipeline':{'state':'completed','assessment_status':p['assessment_status'],
                    'helmet':p['helmet'],'vest':p['vest'],'ruleset_version':p['ruleset_version'],
                    'finding_rule_ids':[f['rule_id'] for f in p['findings']]},
                'evidence_status':'unavailable','evidence_export_allowed':False}

if __name__=='__main__':print(json.dumps(run_demo(),indent=2))
