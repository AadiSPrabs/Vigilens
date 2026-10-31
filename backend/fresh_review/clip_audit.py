"""Local clip-to-existing-image orchestration, no new model or public decoder.
Exact sampled frame approvals and existing same-aggregate accounting apply.
"""
from adapters import LiveTransportDisabled
from .clips import extract_clip_frames

async def audit_clip(raw,offsets,limits,service):
    clip=extract_clip_frames(raw,offsets,limits)
    return await audit_prepared_clip(clip,service)

async def audit_prepared_clip(clip,service):
    # Complete approval/config/derivative preflight before any frame dispatch.
    # This is not an atomic multi-frame reservation; each existing image job
    # claims against the shared aggregate and an interrupted clip stays partial.
    for frame in clip['frames']:
        service.prepare(frame['png'],'image/png',[])
    frames=[];seen={};calls=0;count_known=True
    for frame in clip['frames']:
        source=frame['pixel_digest']
        if source in seen:
            job=seen[source];new_calls=0
        else:
            try:job=await service.run(frame['png'],'image/png',[])
            except Exception as error:
                # Rejected before any frame work: a configuration refusal, not a partial. Later failures keep partial semantics.
                if isinstance(error,LiveTransportDisabled)and not frames:raise
                # Read exact retained state where possible, never retry.
                job=service.read(source)
                if job is None:job={'state':'not_started_or_pre_dispatch_rejected','result':None,'provider_calls_this_request':0,'retry_allowed':False}
            seen[source]=job;new_calls=job.get('provider_calls_this_request',0)
        if new_calls is None:count_known=False
        else:calls+=new_calls
        frames.append({k:frame[k]for k in ('sample_index','requested_offset_seconds','timestamp_basis','source_clip_sha256','pixel_digest','width','height') }|{
            'image_job':job,'provider_calls_this_sample':new_calls,'repeated_pixels_share_image_job':sum(f['pixel_digest']==source for f in clip['frames'])>1})
        if job['state']!='completed':
            return summary(clip,frames,calls if count_known else None,'partial_requires_operator_reconciliation')
    return summary(clip,frames,calls if count_known else None,'sampled_image_jobs_completed_not_clip_safety_clearance')

def unassessed(job):
    r=job.get('result')or{}
    w=r.get('wide_scene')
    if isinstance(w,dict):return w.get('all_detected_people_assessed')is not True
    return any(p.get('ppe_assessed')is False for p in r.get('persons',[]))

def unresolved_people(job):
    from .ppe_basis import unresolved
    r=job.get('result')or{}
    return unassessed(job)or any(unresolved(p)for p in r.get('persons',[]))

def summary(clip,frames,calls,status):
    return {'source_clip_sha256':clip['source_clip_sha256'],'duration_seconds':clip['duration_seconds'],
            'requested_sample_count':len(clip['frames']),'completed_sample_count':sum(f['image_job']['state']=='completed'for f in frames),
            'frames':frames,'provider_calls_this_request':calls,'status':status,
            'frames_with_unassessed_people':[f['sample_index']for f in frames if unassessed(f['image_job'])],'frames_with_unassessed_people_meaning':'frames with a person whose provider observation was not attempted (older field name, unchanged)','frames_with_unresolved_people':[f['sample_index']for f in frames if unresolved_people(f['image_job'])],'frames_with_unresolved_people_meaning':'frames with any person not fully resolved: not attempted, partial evidence, legacy missing-basis, or any unknown item','attempted_is_not_resolved_assessment':True,'completed_state_is_execution_terminal_not_assessment_complete':True,
            'cross_frame_person_identity':'not_inferred','sampled_frames_are_not_complete_clip_coverage':True,
            'clip_intrusion_or_crossing':'not_inferred_from_sampled_presence','privacy_review_status':'not_validated',
            'evidence_export_allowed':False,'automatic_retry_allowed':False,
            'report_integration':'per_frame_private_image_review_required','decoder_scope':'local_trusted_clip_only_not_public_upload_service'}
