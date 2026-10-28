"""Private integration preparation. Empty source approvals and disabled transport by default."""
import json,os,sqlite3,time,hashlib
from pathlib import Path
from fastapi import APIRouter,UploadFile,File,Form,Header,HTTPException
from adapters import LiveTransportDisabled
from core import AuditError,decode_image
from .pipeline import FreshPipeline,digest
from .reports import build_private_report
from .contacts import ContactStore

def create_router(service,display):
    SERVICE=service
    router=APIRouter()
    def source_result(source):
        if not isinstance(source,str)or len(source)!=64 or any(c not in '0123456789abcdef'for c in source):raise ValueError('Source identity required')
        job=SERVICE.read(source)
        if not job or job['state']!='completed'or not job['result']:raise ValueError('Completed exact fresh result required')
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
        except LiveTransportDisabled:raise HTTPException(503,'Fresh provider execution disabled; no claim or call created')
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,AuditError):raise HTTPException(409,'Fresh source/config/accounting unavailable or unapproved; no automatic retry')

    @router.get('/fresh-review/{source}')
    async def status(source:str):
        try:
            job=SERVICE.read(source)
            if not job:raise ValueError('Unknown fresh source')
            return job
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):raise HTTPException(409,'Fresh source result unavailable or changed')

    @router.post('/fresh-review/{source}/private-display')
    async def prepare_display(source:str,image:UploadFile=File(...),review:str=Form(...),x_vigilens_display_session:str=Header('')):
        try:
            job=source_result(source);r=json.loads(review)
            if 'assessment_id'in r:raise ValueError('Fresh review uses job binding, not saved rooftop assessment')
            if r.get('source_digest')!=source:raise ValueError('Exact source review required')
            out=await display.create(image,review,x_vigilens_display_session)
            with display.LOCK:
                current=source_result(source)
                if digest(current['result'])!=digest(job['result']):
                    display.SESSIONS.pop(out['session_id'],None);raise ValueError('Result changed during preview preparation')
                session=display.SESSIONS[out['session_id']]
                session.meta['fresh_assessment_binding']={'source':source,'result_sha256':digest(job['result'])}
                session.verify=metadata_check
                SERVICE.register_derivative(session.png,source)
                return display.report(out['session_id'],session)
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):raise HTTPException(409,'Fresh preview binding unavailable or changed')

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
            if not decode_mask(p['mask']).getpixel((int(x)-l,int(y)-t)):raise ValueError('Point outside verified person foreground')
            label=payload['reviewer_label']
            if not isinstance(label,str)or not 1<=len(label.strip())<=80:raise ValueError('Bounded reviewer claim label required')
            claim={'point':point,'reviewer_label':label.strip(),'basis':'original_source_and_person_mask_operator_claim','zone_status':'not_checked','face_coverage_approved':False,'compliance_status':'not_evaluated'}
            event=ContactStore(SERVICE).append(source,digest(job['result']),p['id'],x_vigilens_display_session,claim)
            return {'manual_contact':event,'automatic_contact':False,'ownership_basis':'private_access_token_and_browser_nonce_not_verified_human','evidence_export_allowed':False}
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):raise HTTPException(409,'Fresh manual contact claim unavailable or invalid')

    @router.post('/fresh-private-report/{sid}')
    async def report(sid:str,payload:dict,x_vigilens_display_session:str=Header('')):
        with display.LOCK:
            s=display.lookup(sid,x_vigilens_display_session)
            if not s.reviewed:raise HTTPException(409,'Exact whole-frame preview acknowledgment required')
            try:
                metadata_check(s.meta);binding=s.meta['fresh_assessment_binding'];job=source_result(binding['source']);result=job['result'];identity='fresh:'+binding['source']+':'+binding['result_sha256']
                contacts=ContactStore(SERVICE).latest(binding['source'],binding['result_sha256'],x_vigilens_display_session)
                assessment={**result,'source':'fresh_upload_provider_review','ground_assessment_id':identity,'manual_contact_review':contacts}
                out=build_private_report(assessment,s.meta,payload,full_frame_review=s.review_ack)
                out['contact_review_status']='operator_claims_only'if len(contacts)==len(result['persons'])else'needs_manual_contact_review'
                out['status']='needs_human_review' #No zones/safety/release decisions in this preparation.
                return out
            except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):raise HTTPException(409,'Fresh private report source/person/preview binding changed')


    @router.get('/fresh-review/{source}/integration-contract')
    async def integration_contract(source:str):
        try:
            job=source_result(source);result=job['result']
            persons=[]
            for p in result['persons']:
                observation=p['provider_observation']['observation']
                persons.append({'id':p['id'],'mask':p['mask'],'ppe':{'assessment_status':'provider_observation_unvalidated',**{k:{'status':p[k],'reason':'provider_observation_not_safety_clearance','visible_evidence':observation[k+'_evidence']}for k in ('helmet','vest')}},'zone_membership':{'assessment_status':'not_checked','zone_ids':None},'findings_status':'not_evaluated','findings':None,'compliance':{'status':'not_evaluated'},'review_status':'needs_human_review'})
            return {'contract_version':'vigilens.private-review.proposal.v1','contract_status':'local_proposal_not_agreed_with_frontend','assessment_id':'fresh:'+source+':'+digest(result),'image':result['image'],'persons':persons,'zones':[],'assessment_status':'provider_observations_require_manual_review','compliance':{'status':'not_evaluated'},'evidence_image':None,'evidence_status':'not_released','privacy_review_status':'not_validated','evidence_export_allowed':False,'provider_calls_this_request':0}
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):raise HTTPException(409,'Fresh integration proposal unavailable or changed')
    return router
