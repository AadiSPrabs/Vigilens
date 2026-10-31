"""Local fixture-only API. No network model adapter, no real-audit success path."""
import copy
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, File, Form, Header, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from core import AuditError, MAX_BYTES, decode_image, fail, memberships, request_digest, validate_zones

class FixtureService:
    """A fixture manifest is trusted local test configuration, never supplied by HTTP."""
    def __init__(self, manifest=None):
        self.manifest=copy.deepcopy(manifest)
        self.lock=threading.Lock()
        self.cache={}
    def audit(self, image, zones, key):
        if not isinstance(key,str) or not 1<=len(key)<=128 or not all(33<=ord(c)<=126 for c in key):
            fail('INVALID_IDEMPOTENCY_KEY','Supply an ASCII Idempotency-Key of 1 to 128 characters.')
        # Coordinates refer to exactly the browser-preview raster. Reject rotated EXIF
        # until the frontend confirms oriented-preview handling, rather than guess.
        if image.orientation != 1:
            fail('IMAGE_ORIENTATION_UNSUPPORTED','Normalize EXIF orientation before drawing zones and uploading.',422)
        if self.manifest is None:
            fail('FIXTURE_NOT_CONFIGURED','No paired fixture configured. Real analysis is disabled.',503)
        m=self.manifest
        if image.digest != m['image_digest'] or zones != validate_zones(m['zones']):
            fail('FIXTURE_MISMATCH','This stub accepts only its exact paired fixture image and zones.',422)
        digest=request_digest(image,zones)
        with self.lock:
            now=time.monotonic()
            self.cache={k:v for k,v in self.cache.items() if now-v[0]<3600}
            if key in self.cache:
                _,old_digest,old_result=self.cache[key]
                if old_digest!=digest: fail('IDEMPOTENCY_CONFLICT','Key was used with different input.',409)
                return copy.deepcopy(old_result)
            if len(self.cache)>=256: fail('LOCAL_CACHE_FULL','Local test cache is full; retry later.',503)
            out=copy.deepcopy(m['audit'])
            out.update(audit_id='fixture-'+uuid.uuid4().hex, schema_version='0.2-local-draft',
                       ruleset_version='draft-unapproved', source='fixture',
                       created_at=None, fixture_loaded_at=datetime.now(timezone.utc).isoformat(),
                       evidence_image=None, evidence_status='unavailable', evidence_export_allowed=False,
                       fixture_notice='SAMPLE DATA - synthetic or manually authored fixture; no model analysis.')
            out['image']={'id':'fixture-image','width':image.width,'height':image.height}
            out['zones']=copy.deepcopy(zones)
            ids=set()
            for person in out.get('persons',[]):
                if person.get('id') in ids: fail('INVALID_FIXTURE','Duplicate person ID in local manifest.',500)
                ids.add(person.get('id'))
                membership=memberships(person['polygon'],zones,person.get('contact_known',True))
                person['zone_membership_status']=membership['status']
                person['zone_id']=membership['display_zone_id']
                person['zone_ids']=membership['zone_ids']
                person['trace_provenance']='illustrative_fixture_only'
            self.cache[key]=(now,digest,copy.deepcopy(out))
            return out

def load_manifest():
    path=os.getenv('VIGILENS_FIXTURE_MANIFEST')
    return json.loads(Path(path).read_text()) if path else None

def create_app(manifest=None):
    service=FixtureService(manifest)
    app=FastAPI(title='Vigilens local fixture backend',version='0.2-local-draft')
    app.state.service=service
    app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],
                       allow_methods=['POST','GET','OPTIONS'],allow_headers=['Content-Type','Idempotency-Key'])
    @app.exception_handler(AuditError)
    async def audit_error(_,e):
        return JSONResponse(status_code=e.status,content={'error':{'code':e.code,'message':e.message}})
    @app.exception_handler(RequestValidationError)
    async def missing_fields(_request,_exc):
        return JSONResponse(status_code=400,content={'error':{'code':'INVALID_REQUEST','message':'Provide image, zones and Idempotency-Key.'}})
    @app.get('/health')
    def health():
        return {'status':'ok','mode':'fixture_only','real_analysis_enabled':False,'fixture_configured':service.manifest is not None}
    @app.post('/audit')
    async def audit(image:UploadFile=File(...),zones:str=Form(...),idempotency_key:str=Header(...)):
        if len(zones)>100_000: fail('ZONES_TOO_LARGE','Zone JSON exceeds 100,000 characters.',413)
        validated=validate_zones(zones)
        # Stop reading application bytes at the file cap, rather than read all into RAM.
        # Multipart parsing happens earlier: deployment still requires an ingress body cap.
        chunks=[]; size=0
        try:
            while True:
                chunk=await image.read(min(65536,MAX_BYTES+1-size))
                if not chunk: break
                chunks.append(chunk); size+=len(chunk)
                if size>MAX_BYTES: fail('IMAGE_TOO_LARGE','File exceeds 15,000,000 bytes.',413)
            decoded=decode_image(b''.join(chunks),image.content_type)
        finally:
            await image.close()
        return service.audit(decoded,validated,idempotency_key)
    @app.get('/evidence/{audit_id}.png')
    def evidence(audit_id:str):
        fail('EVIDENCE_UNAVAILABLE','Fixture API never serves real or placeholder audit evidence.',404)
    return app

app=create_app(load_manifest())
