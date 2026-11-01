"""Backend-only record of operator evidence sufficiency. Never adds a PPE verdict or releases export."""

def assess_evidence(*, source_digest, derivative_sha256, regions_digest, person_id, helmet_observation,
                    exact_source_confirmed=False, face_coverage_checked=False, head_evidence_visible=False):
    for v in [source_digest,derivative_sha256,regions_digest]:
        if not isinstance(v,str) or len(v)!=64 or any(c not in '0123456789abcdef' for c in v):raise ValueError('Exact source/derivative/regions digests required')
    if not isinstance(person_id,str) or not person_id.strip():raise ValueError('Exact person ID required')
    if helmet_observation not in ('present','absent','unknown'):raise ValueError('Observation enum required, not a new inference')
    if any(type(v)is not bool for v in [exact_source_confirmed,face_coverage_checked,head_evidence_visible]):raise ValueError('Explicit operator booleans required')
    supported=exact_source_confirmed and face_coverage_checked and head_evidence_visible and helmet_observation!='unknown'
    return {'source':'offline_operator_evidence_review','source_digest':source_digest,'derivative_sha256':derivative_sha256,
            'regions_digest':regions_digest,'person_id':person_id,'input_helmet_observation':helmet_observation,
            'display_finding_allowed':supported,'evidence_status':'operator_judged_readable_only' if supported else 'needs_human_review',
            'derived_helmet_verdict':None,'automatic_privacy_clearance':False,'privacy_review_status':'not_validated',
            'evidence_export_allowed':False,'notice':'Operator evidence sufficiency only, not model verification, anonymity or release approval.'}
