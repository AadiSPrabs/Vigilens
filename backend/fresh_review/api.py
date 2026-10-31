"""Private integration preparation. Empty source approvals and disabled transport by default."""
import json,os,sqlite3,time,hashlib
from pathlib import Path
from fastapi import APIRouter,UploadFile,File,Form,Header,HTTPException
from adapters import LiveTransportDisabled
from core import AuditError,decode_image
from .pipeline import FreshPipeline,digest
from .reports import build_private_report
from .contacts import ContactStore
from .zones import ZoneStore,assess_zones
from .rule_review import RuleStore,evaluate_report_rules
from .ppe_basis import contract_ppe as _contract_ppe,counts as _pb_counts,unresolved as _unresolved

def create_router(service,display):
    SERVICE=service
    router=APIRouter()
    BOUND=set()   # (owner session, source digest): a session is bound to a source only by presenting that exact image (possession proof) to a frontend-audit POST. In memory, single local process; not an account system.
    def source_result(source):
        if not isinstance(source,str)or len(source)!=64 or any(c not in '0123456789abcdef'for c in source):raise ValueError('Source identity required')
        job=SERVICE.read(source)
        partial=bool(job)and job['state']=='partial_completed'and bool(job['result'])and job['result'].get('wide_scene',{}).get('sequential')is True and job['result']['wide_scene'].get('job_state')=='partial_completed'and bool(job['result']['wide_scene'].get('budget_deferred_never_attempted'))
        if not job or (job['state']not in ('completed','archived_verified')and not partial)or not job['result']:raise ValueError('Verified exact source result required')
        if job['state']=='archived_verified'and not getattr(SERVICE,'archive_verification_only',False):raise ValueError('Explicit archive verification harness required')
        return job

    def metadata_check(meta):
        b=meta.get('fresh_assessment_binding')
        if b:
            job=source_result(b['source'])
            if digest(job['result'])!=b['result_sha256']:raise ValueError('Fresh result changed; preview review invalidated')
        return True

    @router.post('/fresh-review-upload')
    async def upload(image:UploadFile=File(...),zones:str=Form('[]')):
        try:
            raw=await image.read(15_000_001);z=json.loads(zones)
            frame=decode_image(raw,image.content_type);display.reject_display_input(frame.digest)
            return await SERVICE.run(raw,image.content_type,z)
        except HTTPException:raise
        except LiveTransportDisabled:raise HTTPException(503,'Fresh provider execution disabled; no claim or call created')
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Fresh source/config/accounting unavailable or unapproved; no automatic retry')

    @router.post('/fresh-review-clip-upload')
    async def clip_upload(clip:UploadFile=File(...),offsets:str=Form(...),x_vigilens_display_session:str=Header('')):
        try:
            display.owner_check(x_vigilens_display_session)
            limits=getattr(SERVICE,'trusted_clip_limits',None)
            if limits is None:raise ValueError('Local trusted clip decoder not explicitly enabled')
            limits.validate()
            if clip.content_type!='video/mp4':raise ValueError('MP4 media type required')
            raw=await clip.read(limits.max_bytes+1)
            # Decoder runs off the event loop, then all image processing uses the
            # existing approval/journal pipeline. Never installs source approvals.
            import asyncio
            from .clips import extract_clip_frames
            from .clip_audit import audit_prepared_clip
            prepared=await asyncio.to_thread(extract_clip_frames,raw,json.loads(offsets),limits)
            summary=await audit_prepared_clip(prepared,SERVICE)
            from .clip_review import ClipReviewStore
            summary['private_clip_review_id']=ClipReviewStore(SERVICE).register(summary,x_vigilens_display_session)
            return summary
        except LiveTransportDisabled:raise HTTPException(503,'Clip provider execution disabled; no automatic retry')
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Trusted clip preparation/source approval unavailable; no automatic retry')

    @router.post('/fresh-review-audit')
    async def frontend_audit_upload(image:UploadFile=File(...),zones:str=Form('[]'),x_vigilens_display_session:str=Header('')):
        # STORED-ONLY: reads an already stored, verified result for the exact pixel digest. No dispatch code exists in this handler and no switch enables it.
        try:
            from .frontend_audit import to_frontend_audit
            display.owner_check(x_vigilens_display_session)
            raw=await image.read(15_000_001);from core import validate_zones;vz=validate_zones(zones)
            frame=decode_image(raw,image.content_type);display.reject_display_input(frame.digest)
            job=source_result(frame.digest)
            if not job or job.get('state')not in('completed','partial_completed','archived_verified')or not job.get('result'):raise ValueError('Terminal result required')
            out=to_frontend_audit(job['result'],audit_id='fresh:'+frame.digest+':'+digest(job['result']),job_state=job['state'],source_digest=frame.digest,zones=vz)
            BOUND.add((x_vigilens_display_session,frame.digest))
            out['zones_applied']=False;out['zones_semantics']='Posted zones are validated and echoed only. The stored result was produced without zones: no zone membership was determined (no ground-contact review exists), every person is unknown for every zone, and zones_applied=false means no zone check happened.'
            return out
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'No presentable stored result for this exact image (none stored, or not safe to present); new-image analysis is not enabled here')

    @router.get('/fresh-review/{source}')
    async def status(source:str):
        try:
            job=SERVICE.read(source)
            if not job:raise ValueError('Unknown fresh source')
            return job
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):raise HTTPException(409,'Fresh source result unavailable or changed')

    def recheck_view(attempt):
        # Canonical requests contain original unredacted crop data URLs. Never
        # place them in reports/status replies or offer original-image fallback.
        plan=attempt['plan']
        return {k:attempt[k]for k in ('attempt_id','state','result','retry_allowed','provider_calls_this_request','evidence_export_allowed')}|{
            'binding':{k:plan[k]for k in ('source_digest','result_sha256','person_id','attempt','crop_png_sha256')},
            'original_result_unchanged':True,'candidate_adoption':'requires_separate_human_review'}

    @router.post('/fresh-review/{source}/recheck/{attempt_id}')
    async def execute_recheck(source:str,attempt_id:str,payload:dict,x_vigilens_display_session:str=Header('')):
        try:
            job=source_result(source);current_preview(source,job,x_vigilens_display_session)
            if set(payload)!={'source_digest','result_sha256'}or payload['source_digest']!=source or payload['result_sha256']!=digest(job['result']):raise ValueError('Exact original result required')
            executor=getattr(SERVICE,'recheck_executor',None)
            if executor is None:raise ValueError('No exact reviewed recheck executor configured')
            attempt=executor.read(attempt_id)
            if attempt['plan']['source_digest']!=source or attempt['plan']['result_sha256']!=digest(job['result']):raise ValueError('Attempt belongs to another immutable source/result')
            return recheck_view(await executor.run(attempt_id))
        except LiveTransportDisabled:raise HTTPException(503,'Recheck execution disabled; no claim or call created')
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Explicit recheck unavailable; no new reservation, grant or automatic retry')

    @router.post('/fresh-review/{source}/bounded-review-loop')
    async def bounded_review_loop(source:str,payload:dict,x_vigilens_display_session:str=Header('')):
        from .agent_loop import run_review_loop
        try:
            job=source_result(source);current_preview(source,job,x_vigilens_display_session)
            if set(payload)!={'source_digest','result_sha256'}or payload['source_digest']!=source or payload['result_sha256']!=digest(job['result']):raise ValueError('Exact immutable original required')
            configured=getattr(SERVICE,'review_loop_attempts',None)
            if not isinstance(configured,dict)or source not in configured:raise ValueError('Explicit server-side bounded loop configuration required')
            return await run_review_loop(SERVICE,source,attempt_ids=configured[source])
        except LiveTransportDisabled:raise HTTPException(503,'Recheck execution disabled; no claim or call created')
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Configured exact recheck loop unavailable; no new grant/reservation or retry')

    @router.post('/fresh-review/{source}/ppe-segmentation/{batch_id}')
    async def ppe_segmentation(source:str,batch_id:str,payload:dict,x_vigilens_display_session:str=Header('')):
        try:
            job=source_result(source);current_preview(source,job,x_vigilens_display_session)
            if set(payload)!={'source_digest','result_sha256'}or payload['source_digest']!=source or payload['result_sha256']!=digest(job['result']):raise ValueError('Exact original result required')
            helper=getattr(SERVICE,'ppe_segmentation',None)
            if helper is None:raise ValueError('No exact-granted SAM PPE batch configured')
            batch=helper.read(batch_id)
            if batch['source_digest']!=source or batch['result_sha256']!=digest(job['result']):raise ValueError('Batch belongs to another source/result')
            return await helper.run(batch_id)
        except LiveTransportDisabled:raise HTTPException(503,'SAM PPE execution disabled; no claim or call created')
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Explicit SAM PPE masks unavailable; no grant/reservation created by request')

    @router.post('/fresh-review/{source}/face-proposals')
    async def face_proposals(source:str,image:UploadFile=File(...),x_vigilens_display_session:str=Header('')):
        try:
            from .face_proposals import propose_faces
            display.owner_check(x_vigilens_display_session);job=source_result(source)
            raw=await image.read(15_000_001);frame=decode_image(raw,image.content_type)
            if frame.digest!=source or (frame.width,frame.height)!=(job['result']['image']['width'],job['result']['image']['height']):raise ValueError('Exact original source required')
            path=getattr(SERVICE,'face_proposal_model_path',None)
            if path is None:raise ValueError('Optional local detector not configured')
            out=propose_faces(raw,image.content_type,path)
            out['result_sha256']=digest(job['result']);out['automatic_treatment_applied']=False;out['provider_calls_this_request']=0
            out['mandatory_next_step']='operator_edit_and_whole_frame_coverage_review_before_private_display'
            return out
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Face proposals unavailable; manual whole-frame coverage review still required')

    @router.post('/fresh-review/{source}/private-display')
    async def prepare_display(source:str,image:UploadFile=File(...),review:str=Form(...),x_vigilens_display_session:str=Header('')):
        try:
            job=source_result(source);r=json.loads(review)
            if 'assessment_id'in r:raise ValueError('Fresh review uses job binding, not saved rooftop assessment')
            if r.get('source_digest')!=source:raise ValueError('Exact source review required')
            if 'face_coverings'in r:
                ids={p['id']for p in job['result']['persons']}
                covering_ids={c['person_id']for c in r['face_coverings']}
                region_ids={c['person_id']for c in r['regions']}
                if not covering_ids<=ids or covering_ids&region_ids or not ids<=covering_ids|region_ids:raise ValueError('Every assessed person needs a separate treatment or shield coverage review')
            out=await display.create(image,review,x_vigilens_display_session)
            with display.LOCK:
                current=source_result(source)
                if digest(current['result'])!=digest(job['result']):
                    display.SESSIONS.pop(out['session_id'],None);raise ValueError('Result changed during preview preparation')
                session=display.SESSIONS[out['session_id']]
                session.meta['fresh_assessment_binding']={'source':source,'result_sha256':digest(job['result'])}
                session.verify=metadata_check
                if not session.meta.get('display_pixels_unchanged'):SERVICE.register_derivative(session.png,source)
                return display.report(out['session_id'],session)
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):raise HTTPException(409,'Fresh preview binding unavailable or changed')

    def current_ppe_masks(source,result_sha):
        helper=getattr(SERVICE,'ppe_segmentation',None)
        if helper is None:return []
        c=SERVICE.connect()
        try:
            exists=c.execute("SELECT 1 FROM sqlite_master WHERE name='ppe_mask_batches'").fetchone()
            ids=[r[0]for r in c.execute('SELECT id FROM ppe_mask_batches WHERE source=? AND result_sha=?',(source,result_sha))]if exists else[]
        finally:c.close()
        masks=[]
        for identity in ids:
            batch=helper.read(identity)
            if batch['state']=='completed':masks.extend(batch['segmentations'])
        return masks

    def current_preview(source,job,owner):
        display.owner_check(owner)
        with display.LOCK:
            display.prune()
            for sid,s in list(display.SESSIONS.items()):
                if s.owner==owner and s.meta.get('fresh_assessment_binding')=={'source':source,'result_sha256':digest(job['result'])}:
                    display.lookup(sid,owner)
                    return
        raise ValueError('Current exact source-bound browser preview required')

    def zone_view(source,job,owner):
        snapshot=ZoneStore(SERVICE).latest(source,digest(job['result']),owner)
        contacts=ContactStore(SERVICE).latest(source,digest(job['result']),owner)
        zones=snapshot['zones']if snapshot else[]
        return {'contract_version':'vigilens.zone-review.proposal.v1','source_digest':source,
                'result_sha256':digest(job['result']),'zone_snapshot':snapshot,
                'persons':assess_zones(job['result']['persons'],zones,contacts),
                'policy_status':'not_applied','compliance_status':'not_evaluated',
                'automatic_contact':False,'privacy_review_status':'not_validated',
                'evidence_export_allowed':False,'provider_calls_this_request':0}

    @router.post('/fresh-review/{source}/zone-review')
    async def set_zones(source:str,payload:dict,x_vigilens_display_session:str=Header('')):
        try:
            job=source_result(source);current_preview(source,job,x_vigilens_display_session)
            if set(payload)!={'source_digest','result_sha256','zones','reviewer_label'}or payload['source_digest']!=source or payload['result_sha256']!=digest(job['result']):raise ValueError('Exact source/result zone snapshot required')
            ZoneStore(SERVICE).append(source,digest(job['result']),x_vigilens_display_session,payload['zones'],payload['reviewer_label'])
            return zone_view(source,job,x_vigilens_display_session)
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Zone review unavailable or invalid; no safety policy applied')

    @router.get('/fresh-review/{source}/zone-review')
    async def get_zones(source:str,x_vigilens_display_session:str=Header('')):
        try:
            job=source_result(source);current_preview(source,job,x_vigilens_display_session)
            return zone_view(source,job,x_vigilens_display_session)
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Zone review unavailable or changed')

    @router.post('/fresh-review/{source}/camera-zones/{operation}')
    async def camera_zones(source:str,operation:str,payload:dict,x_vigilens_display_session:str=Header('')):
        try:
            from .camera_zones import CameraZoneStore
            job=source_result(source);current_preview(source,job,x_vigilens_display_session)
            base={'source_digest','result_sha256','camera_binding','reviewer_label','fixed_scene_confirmed'}
            if operation not in ('save','apply')or set(payload)!=(base if operation=='save'else base|{'template_id'}):raise ValueError('Exact template action required')
            if payload['source_digest']!=source or payload['result_sha256']!=digest(job['result'])or payload['fixed_scene_confirmed']is not True:raise ValueError('Exact source and operator fixed-scene confirmation required')
            store=CameraZoneStore(SERVICE)
            if operation=='save':identity=store.save(source,job,x_vigilens_display_session,payload['camera_binding'],payload['reviewer_label'])
            else:
                identity=payload['template_id'];store.apply(identity,source,job,x_vigilens_display_session,payload['camera_binding'],payload['reviewer_label'])
            return {'template_id':identity,'template':store.read(identity,x_vigilens_display_session),'zone_review':zone_view(source,job,x_vigilens_display_session),'automatic_scene_verification':False,'rules_or_contacts_transferred':False,'provider_calls_this_request':0,'evidence_export_allowed':False}
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Camera geometry unavailable; exact fixed-scene/raster confirmation required, no automatic transform')

    @router.post('/fresh-review/{source}/rule-review')
    async def set_rule_review(source:str,payload:dict,x_vigilens_display_session:str=Header('')):
        try:
            job=source_result(source);current_preview(source,job,x_vigilens_display_session)
            if set(payload)!={'source_digest','result_sha256','zones_sha256','configuration'}or payload['source_digest']!=source or payload['result_sha256']!=digest(job['result']):raise ValueError('Exact source/result configuration required')
            zones=ZoneStore(SERVICE).latest(source,digest(job['result']),x_vigilens_display_session)
            if zones is None or payload['zones_sha256']!=zones['zones_sha256']:raise ValueError('Exact current geometry required')
            snapshot=RuleStore(SERVICE).append(source,digest(job['result']),x_vigilens_display_session,zones,payload['configuration'])
            return {'rule_snapshot':snapshot,'approval_status':'not_verified_by_configuration','evidence_export_allowed':False,'provider_calls_this_request':0}
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Rule configuration unavailable or changed; no defaults or approval inferred')

    @router.post('/fresh-review/{source}/contact')
    async def contact(source:str,payload:dict,x_vigilens_display_session:str=Header('')):
        try:
            display.owner_check(x_vigilens_display_session)
            job=source_result(source)
            with display.LOCK:
                display.prune()
                if not any(s.owner==x_vigilens_display_session and s.meta.get('fresh_assessment_binding')=={'source':source,'result_sha256':digest(job['result'])}for s in display.SESSIONS.values()):raise ValueError('Exact source-bound browser preview required')
            people=job['result']['persons'];image=job['result']['image']
            if set(payload)!={'person_id','point','exact_source_confirmed','boots_ground_visible','reviewer_label'}:raise ValueError('Exact manual contact claim required')
            if any(type(payload[k])is not bool for k in ('exact_source_confirmed','boots_ground_visible'))or not all(payload[k]for k in ('exact_source_confirmed','boots_ground_visible')):raise ValueError('Explicit operator confirmations required')
            p=next((p for p in people if p['id']==payload['person_id']),None);point=payload['point']
            import math
            if p is None or not isinstance(point,list)or len(point)!=2 or any(type(v)not in (int,float)or not math.isfinite(v)or not 0<=v<=1 for v in point):raise ValueError('Exact person and normalized point required')
            x,y=point[0]*image['width'],point[1]*image['height'];l,t,r,b=p['box_half_open']
            if not l<=x<r or not t<=y<b:raise ValueError('Point outside this person source box')
            from .masks import decode_mask
            if p.get('mask')is None:raise ValueError('Geometry-unverified person cannot take a manual contact point')
            if not decode_mask(p['mask']).getpixel((int(x)-l,int(y)-t)):raise ValueError('Point outside verified person foreground')
            label=payload['reviewer_label']
            if not isinstance(label,str)or not 1<=len(label.strip())<=80:raise ValueError('Bounded reviewer claim label required')
            claim={'point':point,'reviewer_label':label.strip(),'basis':'original_source_and_person_mask_operator_claim','zone_status':'not_checked','face_coverage_approved':False,'compliance_status':'not_evaluated'}
            event=ContactStore(SERVICE).append(source,digest(job['result']),p['id'],x_vigilens_display_session,claim)
            return {'manual_contact':event,'automatic_contact':False,'ownership_basis':'private_access_token_and_browser_nonce_not_verified_human','evidence_export_allowed':False}
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):raise HTTPException(409,'Fresh manual contact claim unavailable or invalid')

    @router.get('/fresh-private-report/{sid}/overlay')
    async def private_overlay(sid:str,x_vigilens_display_session:str=Header('')):
        from fastapi.responses import Response
        from .overlays import render_overlay
        with display.LOCK:
            session=display.lookup(sid,x_vigilens_display_session)
            if not session.reviewed:raise HTTPException(409,'Exact whole-frame preview acknowledgment required')
            try:
                metadata_check(session.meta);binding=session.meta['fresh_assessment_binding'];job=source_result(binding['source'])
                snapshot=ZoneStore(SERVICE).latest(binding['source'],binding['result_sha256'],x_vigilens_display_session)
                png,sha=render_overlay(session.png,job['result'],snapshot['zones']if snapshot else[],session.meta['regions'],current_ppe_masks(binding['source'],binding['result_sha256']))
                SERVICE.register_derivative(png,binding['source'])
                return Response(png,media_type='image/png',headers={'Cache-Control':'no-store','Content-Disposition':'inline',
                    'X-Vigilens-Overlay-SHA256':sha,'X-Vigilens-Export-Allowed':'false',
                    'X-Vigilens-Overlay-Basis':'treated-private-preview-and-source-masks-not-released-evidence'})
            except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Private overlay unavailable or changed')

    @router.post('/fresh-private-report/{sid}')
    async def report(sid:str,payload:dict,x_vigilens_display_session:str=Header('')):
        with display.LOCK:
            s=display.lookup(sid,x_vigilens_display_session)
            if not s.reviewed:raise HTTPException(409,'Exact whole-frame preview acknowledgment required')
            try:
                metadata_check(s.meta);binding=s.meta['fresh_assessment_binding'];job=source_result(binding['source']);result=job['result'];identity=('archive-review:'if job['state']=='archived_verified'else'fresh:')+binding['source']+':'+binding['result_sha256']
                contacts=ContactStore(SERVICE).latest(binding['source'],binding['result_sha256'],x_vigilens_display_session)
                assessment={**result,'source':('verified_archive_provider_review'if job['state']=='archived_verified'else'fresh_upload_provider_review'),'ground_assessment_id':identity,'manual_contact_review':contacts}
                out=build_private_report(assessment,s.meta,payload,full_frame_review=s.review_ack)
                if job['state']=='archived_verified':out['archive_provenance']=job['archive_provenance']
                out['contact_review_status']='operator_claims_only'if len(contacts)==len(result['persons'])else'needs_manual_contact_review'
                out['zone_review']=zone_view(binding['source'],job,x_vigilens_display_session)
                rules=RuleStore(SERVICE).latest(binding['source'],binding['result_sha256'],x_vigilens_display_session)
                out['configured_rule_review']=evaluate_report_rules(rules,out['zone_review'],out['persons'])
                helper=getattr(SERVICE,'ppe_segmentation',None)
                out['ppe_segmentation']={'status':'not_configured','batches':[]}
                if helper is not None:
                    connection=SERVICE.connect()
                    try:
                        table=connection.execute("SELECT 1 FROM sqlite_master WHERE name='ppe_mask_batches'").fetchone()
                        ids=[r[0]for r in connection.execute('SELECT id FROM ppe_mask_batches WHERE source=? AND result_sha=?',(binding['source'],binding['result_sha256']))]if table else[]
                    finally:connection.close()
                    out['ppe_segmentation']={'status':'separate_verified_masks_not_worn_or_absence_verdict','batches':[helper.read(i)for i in ids]}
                from .ppe_consistency import review_signals
                out['ppe_cross_stage_review']=review_signals([{'id':person['person_id'],'helmet':person['report_display_helmet'],'vest':person['report_display_vest']}for person in out['persons']],current_ppe_masks(binding['source'],binding['result_sha256']))
                executor=getattr(SERVICE,'recheck_executor',None)
                out['deliberate_rechecks']={'status':'not_configured','attempts':[],'original_result_unchanged':True}
                if executor is not None:
                    connection=SERVICE.connect()
                    try:
                        table=connection.execute("SELECT 1 FROM sqlite_master WHERE name='recheck_attempts'").fetchone()
                        ids=[r[0]for r in connection.execute('SELECT attempt_id FROM recheck_attempts WHERE source=? AND result_sha=? ORDER BY ordinal',(binding['source'],binding['result_sha256']))]if table else[]
                    finally:connection.close()
                    # Separate candidate observations only. Original report-visible
                    # PPE and geometry are never silently replaced by a recheck.
                    attempts=[recheck_view(executor.read(aid))for aid in ids]
                    out['deliberate_rechecks']={'status':'separate_candidates_require_review','attempts':attempts,'original_result_unchanged':True,'automatic_candidate_adoption':False}
                executor=getattr(SERVICE,'explanation_executor',None)
                out['spatial_explanations']={'status':'not_configured','attempts':[]}
                if executor is not None and out['configured_rule_review'].get('status')=='private_operator_rules_evaluated_not_safety_clearance':
                    plan=explanation_plan(out,job)
                    connection=SERVICE.connect()
                    try:
                        table=connection.execute("SELECT 1 FROM sqlite_master WHERE name='explanation_attempts'").fetchone()
                        ids=[r[0]for r in connection.execute('SELECT id FROM explanation_attempts WHERE source=? AND context_sha=?',(binding['source'],plan['context_sha256']))]if table else[]
                    finally:connection.close()
                    from .spatial_explanation import commentary_review
                    attempts=[executor.read(i)for i in ids]
                    for attempt in attempts:attempt['content_review']=commentary_review(attempt,ppe_masks=current_ppe_masks(binding['source'],binding['result_sha256']))
                    out['spatial_explanations']={'status':'model_commentary_requires_human_review','attempts':attempts,'deterministic_fields_unchanged':True,
                        'input_basis_notice':'Missing auxiliary PPE masks means not supplied, not evidence that segmentation or PPE is absent. Commentary must be checked against the original pixels and reviewed geometry.'}
                out['status']='needs_human_review' # No safety/release decisions.
                return out
            except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Fresh private report source/person/preview binding changed')


    def explanation_plan(document,job):
        from .spatial_explanation import build_spatial_request
        raw=SERVICE.original_source_png(document['source_digest'])if getattr(SERVICE,'archive_verification_only',False)else SERVICE.private_bytes(SERVICE.path.parent/('fresh-'+document['source_digest']+'-source.png'))
        masks=current_ppe_masks(document['source_digest'],digest(job['result']))
        return build_spatial_request(raw,job['result'],document['zone_review'],document['configured_rule_review'],masks)

    @router.post('/fresh-private-report/{sid}/explanation/{attempt_id}')
    async def explain(sid:str,attempt_id:str,payload:dict,x_vigilens_display_session:str=Header('')):
        try:
            executor=getattr(SERVICE,'explanation_executor',None)
            if executor is None:raise ValueError('No explicitly granted explanation configured')
            with display.LOCK:
                document=await report(sid,payload,x_vigilens_display_session)
                job=source_result(document['source_digest']);plan=explanation_plan(document,job)
                out=executor.run(attempt_id,plan)
                out['commentary_display']='unvalidated_model_text_never_rule_authority'
                return out
        except LiveTransportDisabled:raise HTTPException(503,'Explanation execution disabled; no claim or call created')
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Explanation source/review/rules unavailable or changed; no defaults/retry')

    @router.post('/fresh-private-report/{sid}/pdf-preview')
    async def pdf_preview(sid:str,payload:dict,x_vigilens_display_session:str=Header('')):
        from fastapi.responses import Response
        from .overlays import render_overlay
        from .report_document import render_private_pdf
        with display.LOCK:
            # Reuse every source/person/visibility/ack check of the JSON report.
            document=await report(sid,payload,x_vigilens_display_session)
            session=display.lookup(sid,x_vigilens_display_session)
            try:
                binding=session.meta['fresh_assessment_binding'];job=source_result(binding['source'])
                zones=ZoneStore(SERVICE).latest(binding['source'],binding['result_sha256'],x_vigilens_display_session)
                png,_=render_overlay(session.png,job['result'],zones['zones']if zones else[],session.meta['regions'],current_ppe_masks(binding['source'],binding['result_sha256']))
                SERVICE.register_derivative(png,binding['source'])
                pdf,sha=render_private_pdf(document,png)
                return Response(pdf,media_type='application/pdf',headers={'Cache-Control':'no-store','Content-Disposition':'inline; filename="vigilens-private-preview.pdf"','X-Vigilens-Export-Allowed':'false','X-Vigilens-PDF-SHA256':sha})
            except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Private PDF preview unavailable; no original fallback or release')

    @router.post('/fresh-private-clip-report/{clip_id}')
    async def clip_report(clip_id:str,payload:dict,x_vigilens_display_session:str=Header('')):
        from .clip_review import ClipReviewStore
        try:
            display.owner_check(x_vigilens_display_session)
            if set(payload)!={'frames'}or not isinstance(payload['frames'],list):raise ValueError('Exact sample review list required')
            manifest=ClipReviewStore(SERVICE).read(clip_id,x_vigilens_display_session)
            if len(payload['frames'])!=len(manifest['frames']):raise ValueError('Every sampled frame requires review')
            reports=[]
            with display.LOCK:
                for frame,review in zip(manifest['frames'],payload['frames']):
                    if set(review)!={'sample_index','session_id','review'}or type(review['sample_index'])is not int or review['sample_index']!=frame['sample_index']:raise ValueError('Exact ordered samples required')
                    session=display.lookup(review['session_id'],x_vigilens_display_session)
                    if session.meta['fresh_assessment_binding']!={'source':frame['pixel_digest'],'result_sha256':frame['result_sha256']}:raise ValueError('Sample preview source/result differs')
                    document=await report(review['session_id'],review['review'],x_vigilens_display_session)
                    reports.append({'sample':frame,'report':document})
            return {'source':'private_sampled_clip_report_not_released','clip_review_id':clip_id,'source_clip_sha256':manifest['source_clip_sha256'],'duration_seconds':manifest['duration_seconds'],'frames':reports,'sample_count':len(reports),'sampled_frames_are_not_complete_clip_coverage':True,'timestamp_basis':'requested_decode_offset_not_exact_presentation_timestamp','cross_frame_person_identity':'not_inferred','clip_intrusion_or_crossing':'not_inferred_from_sampled_presence','privacy_review_status':'not_validated','evidence_export_allowed':False,'provider_calls_this_request':0}
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):raise HTTPException(409,'All exact current sample reviews required; no clip safety clearance')

    @router.post('/fresh-private-clip-report/{clip_id}/pdf-preview')
    async def clip_pdf(clip_id:str,payload:dict,x_vigilens_display_session:str=Header('')):
        from fastapi.responses import Response
        from .overlays import render_overlay
        from .report_document import render_clip_pdf
        with display.LOCK:
            document=await clip_report(clip_id,payload,x_vigilens_display_session)
            try:
                samples=[]
                for frame,review in zip(document['frames'],payload['frames']):
                    session=display.lookup(review['session_id'],x_vigilens_display_session)
                    binding=session.meta['fresh_assessment_binding'];job=source_result(binding['source'])
                    zone=ZoneStore(SERVICE).latest(binding['source'],binding['result_sha256'],x_vigilens_display_session)
                    png,_=render_overlay(session.png,job['result'],zone['zones']if zone else[],session.meta['regions'],current_ppe_masks(binding['source'],binding['result_sha256']))
                    if decode_image(png,'image/png').digest!=binding['source']:SERVICE.register_derivative(png,binding['source'])
                    sample=frame['sample']
                    label='Sample '+str(sample['sample_index'])+' | requested offset '+str(sample['requested_offset_seconds'])+'s. Sampled evidence only, not complete clip coverage or tracking.'
                    samples.append((frame['report'],png,label))
                pdf,sha=render_clip_pdf(samples)
                return Response(pdf,media_type='application/pdf',headers={'Cache-Control':'no-store','Content-Disposition':'inline; filename="vigilens-private-clip-preview.pdf"','X-Vigilens-Export-Allowed':'false','X-Vigilens-PDF-SHA256':sha})
            except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Private sampled clip PDF unavailable; no original fallback or release')

    @router.post('/fresh-private-report/{sid}/private-download')
    async def private_download(sid:str,payload:dict,x_vigilens_display_session:str=Header('')):
        if getattr(SERVICE,'operator_private_download_enabled',False)is not True:raise HTTPException(409,'Private operator download scope not enabled; preview only')
        with display.LOCK:
            response=await pdf_preview(sid,payload,x_vigilens_display_session)
            response.headers['Content-Disposition']='attachment; filename="vigilens-private-operator-preview.pdf"'
            response.headers['X-Vigilens-Use-Restriction']='private-operator-preview-not-certified-safe-to-share'
            return response

    @router.post('/fresh-private-clip-report/{clip_id}/private-download')
    async def private_clip_download(clip_id:str,payload:dict,x_vigilens_display_session:str=Header('')):
        if getattr(SERVICE,'operator_private_download_enabled',False)is not True:raise HTTPException(409,'Private operator download scope not enabled; preview only')
        with display.LOCK:
            response=await clip_pdf(clip_id,payload,x_vigilens_display_session)
            response.headers['Content-Disposition']='attachment; filename="vigilens-private-sampled-clip-preview.pdf"'
            response.headers['X-Vigilens-Use-Restriction']='private-operator-preview-not-certified-safe-to-share'
            return response

    @router.post('/fresh-review-audit-governed')
    async def frontend_audit_governed(image:UploadFile=File(...),zones:str=Form('[]'),x_vigilens_display_session:str=Header('')):
        # NEW-IMAGE contract. Dispatch is NOT decided here: this handler calls the same governed SERVICE.run as /fresh-review-upload, which
        # itself refuses without a source approval, a ledger reservation and a configured transport (LiveTransportDisabled -> 503, refusal -> 409).
        # Being callable is not permission to dispatch. A stored result for the exact digest is served without a call. Posted zones are ignored.
        try:
            from .frontend_audit import to_frontend_audit
            display.owner_check(x_vigilens_display_session)
            raw=await image.read(15_000_001);from core import validate_zones;vz=validate_zones(zones)
            frame=decode_image(raw,image.content_type);display.reject_display_input(frame.digest)
            ran=False
            def uncertain(j):
                # A dispatch may have been attempted and may have consumed calls. This view cannot know the count; it never settles the ledger and never permits a retry.
                return HTTPException(409,{'code':'ATTEMPT_UNCERTAIN','state':j.get('state'),'provider_calls_this_request':None,'message':'A provider attempt for this exact image was started and did not finish. Calls may have been made and the count is not known here. It is held, not retried, and not reconciled by this route; the backend ledger and journal hold the record.'})
            prior=SERVICE.read(frame.digest)
            if prior and prior.get('state')not in('completed','partial_completed','archived_verified'):raise uncertain(prior)
            try:job=source_result(frame.digest)
            except (ValueError,KeyError):
                job=await SERVICE.run(raw,image.content_type,[]);ran=True
                if job and job.get('state')not in('completed','partial_completed','archived_verified'):raise uncertain(job)
            if not job or job.get('state')not in('completed','partial_completed','archived_verified')or not job.get('result'):raise ValueError('Terminal result required')
            out=to_frontend_audit(job['result'],audit_id='fresh:'+frame.digest+':'+digest(job['result']),job_state=job['state'],source_digest=frame.digest,zones=vz)
            BOUND.add((x_vigilens_display_session,frame.digest))
            if ran:out['provider_calls_this_request']=None;out['provider_calls_note']='A governed run happened for this request; the call count is recorded only by the backend ledger, not by this view.'
            out['zones_applied']=False;out['zones_semantics']='Posted zones are validated and echoed only. No zone membership was determined (no ground-contact review exists), so every person is unknown for every zone; zones_applied=false means no zone check happened.'
            return out
        except HTTPException:raise
        except LiveTransportDisabled:raise HTTPException(503,'Fresh provider execution disabled; no claim or call created')
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Fresh source/config/accounting unavailable, unapproved or not presentable; no automatic retry')

    @router.get('/fresh-review/{source}/frontend-audit')
    async def frontend_audit(source:str,x_vigilens_display_session:str=Header('')):
        # Read-only: maps the stored result to the frontend v0.2 shape. Never calls the provider. Readable only by a session that presented this exact image to a frontend-audit POST (possession-bound).
        try:
            from .frontend_audit import to_frontend_audit
            display.owner_check(x_vigilens_display_session)
            if (x_vigilens_display_session,source)not in BOUND:raise ValueError('Source not bound to this session')
            job=source_result(source);result=job['result']
            return to_frontend_audit(result,audit_id=('archive-review:'if job['state']=='archived_verified'else'fresh:')+source+':'+digest(result),job_state=job['state'],source_digest=source)
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):raise HTTPException(409,'Frontend audit view unavailable or changed')

    @router.get('/fresh-review/{source}/integration-contract')
    async def integration_contract(source:str):
        try:
            job=source_result(source);result=job['result']
            persons=[]
            for p in result['persons']:
                if p.get('provider_observation')is None:ppe={'assessment_status':'not_assessed','reason':p.get('ppe_evidence_status','not_assessed'),'helmet':{'status':'unknown'},'vest':{'status':'unknown'}}
                else:
                    ppe=_contract_ppe(p)
                persons.append({'id':p['id'],'mask':p['mask'],'geometry_status':p.get('geometry_status','mask_verified'),'ppe':ppe,'zone_membership':{'assessment_status':'not_checked','zone_ids':None},'findings_status':'not_evaluated','findings':None,'compliance':{'status':'not_evaluated'},'review_status':'needs_human_review'})
            return {'contract_version':'vigilens.private-review.proposal.v1','contract_status':'local_proposal_not_agreed_with_frontend','assessment_id':('archive-review:'if job['state']=='archived_verified'else'fresh:')+source+':'+digest(result),'input_provenance':job.get('archive_provenance',{'kind':'fresh_provider_result'}),'image':result['image'],'persons':persons,'zones':[],'assessment_status':'provider_observations_require_manual_review','coverage':(result.get('wide_scene')or{}).get('coverage','not_wide_scene'),'all_detected_people_assessed':all(q.get('ppe_assessed',True)for q in result['persons']),'all_detected_people_assessed_meaning':'provider_observation_attempted_for_every_detected_person_not_resolved_assessment','all_detected_people_target_level_resolved':not any(_unresolved(q)for q in result['persons']),'ppe_withheld_unverified_geometry':bool((result.get('wide_scene')or{}).get('ppe_withheld_unverified_geometry')),'execution_state_is_not_assessment_completeness':True,'ppe_basis_counts':_pb_counts(result['persons']),'compliance':{'status':'not_evaluated'},'evidence_image':None,'evidence_status':'not_released','privacy_review_status':'not_validated','evidence_export_allowed':False,'provider_calls_this_request':0}
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):raise HTTPException(409,'Fresh integration proposal unavailable or changed')
    return router
