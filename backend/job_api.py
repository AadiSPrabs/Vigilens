"""Local-only fixture job API. Durable ledger, no paid or external execution.
Separate /local/jobs routes avoid silently changing published /audit semantics.
Bind to loopback. There is no public-auth or multi-user access policy here.
"""
from fastapi import File,Form,Header,UploadFile
from starlette.concurrency import run_in_threadpool
from contextlib import asynccontextmanager
from worker import LocalWorker,WorkerBusy
from fastapi.responses import JSONResponse
from app import create_app
from core import MAX_BYTES,decode_image,fail,validate_zones,AuditError
from ledger import Ledger,Conflict,QueueFull,fingerprint
from runner import LocalRunner
from schemas import LocalJob,JobResponse,CancelResponse,ErrorResponse

def create_job_app(database_path,manifest=None,local_scope='local-fixture-review',queue_limit=32,cooperative_worker=False,journal_record_limit=None):
    if not isinstance(local_scope,str) or not local_scope or len(local_scope)>256:raise ValueError('Invalid trusted local scope')
    app=create_app(manifest)
    ledger=Ledger(database_path,max_active=queue_limit,max_records=journal_record_limit)
    runner=LocalWorker(ledger) if cooperative_worker else LocalRunner(ledger)
    app.state.local_worker=runner if cooperative_worker else None
    if cooperative_worker:
        @asynccontextmanager
        async def lifespan(_app):
            ledger.recover_expired()
            try:yield
            finally:runner.shutdown()
        app.router.lifespan_context=lifespan
    app.state.ledger=ledger
    scope=local_scope  # Trusted app configuration, NEVER caller header/body input.
    @app.post('/local/jobs',response_model=JobResponse,responses={s:{'model':ErrorResponse} for s in (400,409,413,415,422,503)})
    async def submit(image:UploadFile=File(...),zones:str=Form(...),idempotency_key:str=Header(...)):
        if len(idempotency_key)>128 or not idempotency_key or not all(33<=ord(ch)<=126 for ch in idempotency_key):fail('INVALID_IDEMPOTENCY_KEY','Invalid request key.')
        if len(zones)>100_000:fail('ZONES_TOO_LARGE','Zones exceed local limit.',413)
        z=validate_zones(zones)
        data=bytearray()
        try:
            while True:
                chunk=await image.read(min(65536,MAX_BYTES+1-len(data)))
                if not chunk:break
                data.extend(chunk)
                if len(data)>MAX_BYTES:fail('IMAGE_TOO_LARGE','Image exceeds local file limit.',413)
            decoded=decode_image(bytes(data),image.content_type)
        finally:await image.close()
        service=app.state.service
        # Fail configuration/pairing BEFORE durable registration; only trusted fixture
        # execution is allowed. Original API still owns its documented input checks.
        if decoded.orientation!=1:fail('IMAGE_ORIENTATION_UNSUPPORTED','Use the same upright raster for preview, zones and upload.',422)
        if service.manifest is None:fail('FIXTURE_NOT_CONFIGURED','No paired fixture; real analysis disabled.',503)
        if decoded.digest!=service.manifest['image_digest'] or z!=validate_zones(service.manifest['zones']):fail('FIXTURE_MISMATCH','Input does not match the configured fixture.',422)
        digest=fingerprint(decoded.digest,z,'0.2-local-draft','draft-unapproved')
        try:j,created=ledger.register(scope,idempotency_key,digest)
        except QueueFull:fail('LOCAL_QUEUE_FULL','Local queue is full; no job registered.',503)
        except Conflict:fail('IDEMPOTENCY_CONFLICT','Request key already binds different input or policy.',409)
        # A review-only synchronous runner: no background task or model/network call.
        # Fixture execution does not mark external_started because no external side effect exists.
        if cooperative_worker:
            def work(checkpoint):
                checkpoint()
                result=service.audit(decoded,z,idempotency_key)
                checkpoint()
                return result
            try:job=await run_in_threadpool(runner.run,j,work)
            except WorkerBusy:
                # No claim occurred for this job. Same key may resume its queued work.
                # This is not a new registration or automatic uncertain retry.
                job=ledger.scoped_get(j,scope)
        else:job=await run_in_threadpool(runner.run,j,lambda:service.audit(decoded,z,idempotency_key))
        return JSONResponse(status_code=(202 if job['state'] in ('queued','running') else (201 if created else 200)),content={'job':public(job)})
    @app.get('/local/jobs/{job_id}',response_model=JobResponse,responses={404:{'model':ErrorResponse}})
    def status(job_id:str):
        try:job=ledger.scoped_get(job_id,scope)
        except KeyError:fail('JOB_NOT_FOUND','Unknown local fixture job.',404)
        return {'job':public(job)}
    @app.post('/local/jobs/{job_id}/cancel',response_model=CancelResponse,responses={404:{'model':ErrorResponse}})
    def cancel(job_id:str):
        try:accepted=ledger.scoped_cancel(job_id,scope);job=ledger.scoped_get(job_id,scope)
        except KeyError:fail('JOB_NOT_FOUND','Unknown local fixture job.',404)
        return {'cancelled_before_execution':accepted,'job':public(job)}
    return app

def public(job):
    # Local fixture semantics only, not provider billing or public authentication.
    state=job['state'];expired=bool(job['result_expired'])
    reason=('result_expired' if expired else
            'cancelled_before_local_execution' if state=='cancelled' else
            'awaiting_operator_review' if state=='needs_review' else
            'local_failure_requires_explicit_retry' if state=='failed' else
            'local_work_in_progress' if state in ('queued','running') else 'local_result_completed')
    out={k:job[k] for k in ('job_id','state','created','updated','result','error_code','cost_state')}
    out.update(result_expired=expired,result_available=job['result'] is not None and not expired,
               retryable_with_same_key=False,status_reason=reason,
               cancellation_kind='before_local_execution' if state=='cancelled' else None,
               result_expires_at=None,dedup_expires_at=None,
               retention_policy='manual_local_cleanup_no_dedup_expiry_configured',
               same_key_behavior='may_start_queued_local_work' if state=='queued' else 'retrieve_only_no_new_execution')
    return LocalJob.model_validate(out).model_dump()
