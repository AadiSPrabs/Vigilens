"""Private report preview construction from server-owned assessment and exact derivative.
No public release or export. Caller must supply a trusted stored assessment, never a client PPE verdict.
"""
from copy import deepcopy
from .visibility import assess_evidence

def build_private_report(assessment, derivative, review, *, full_frame_review=None):
    if not isinstance(assessment,dict) or assessment.get('source')not in ('live_real_upload_crop_review','current_verified_sam_only_review','current_verified_ppe_review','fresh_upload_provider_review'):raise ValueError('Stored real assessment required')
    image=assessment.get('image',{})
    if derivative.get('source_digest')!=image.get('pixel_digest') or (derivative.get('width'),derivative.get('height'))!=(image.get('width'),image.get('height')):raise ValueError('Derivative source/frame mismatch')
    if derivative.get('privacy_review_status')!='not_validated' or derivative.get('evidence_export_allowed')is not False:raise ValueError('Private derivative provenance required')
    if set(review)!={'assessment_id','source_digest','output_sha256','regions_digest','persons'}:raise ValueError('Exact report review shape required')
    expected=(assessment.get('ground_assessment_id'),image.get('pixel_digest'),derivative.get('output_sha256'),derivative.get('regions_digest'))
    if not all(expected) or (review['assessment_id'],review['source_digest'],review['output_sha256'],review['regions_digest'])!=expected:raise ValueError('Review belongs to another assessment/source/derivative')
    persons=assessment.get('persons');checks=review['persons']
    if not isinstance(persons,list) or not persons or not isinstance(checks,dict):raise ValueError('Assessment people and per-person review required')
    ids=[p.get('id') for p in persons]
    if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids) or set(checks)!=set(ids):raise ValueError('Exact per-person review required')
    expected_frame={'source_digest':expected[1],'output_sha256':expected[2],
                    'regions_digest':expected[3],'frame_size':[image['width'],image['height']],
                    'foreground_checked':True,'background_checked':True,'reflections_checked':True,'derivative_checked':True}
    frame_reviewed=False
    if full_frame_review is not None:
        if not isinstance(full_frame_review,dict) or set(full_frame_review)!=set(expected_frame):raise ValueError('Exact whole-frame operator review shape required')
        for key,value in expected_frame.items():
            actual=full_frame_review[key]
            if type(actual)is not type(value):raise ValueError('Strict whole-frame review types required')
            if type(value)is not bool and actual!=value:raise ValueError('Whole-frame review identity changed')
        frame_reviewed=all(full_frame_review[k]is True for k in ['foreground_checked','background_checked','reflections_checked','derivative_checked'])
    result=[]
    for person in persons:
        fields=checks[person['id']]
        if not isinstance(fields,dict) or set(fields)not in ({'exact_source_confirmed','face_coverage_checked','head_evidence_visible'},{'exact_source_confirmed','face_coverage_checked','head_evidence_visible','torso_evidence_visible'}):raise ValueError('No client PPE verdict accepted')
        # Observation is copied only from the stored provider-derived assessment, never from review payload.
        verdict=person.get('helmet','unknown')
        evidence=assess_evidence(source_digest=expected[1],derivative_sha256=expected[2],regions_digest=expected[3],person_id=person['id'],helmet_observation=verdict,**{k:fields[k]for k in ['exact_source_confirmed','face_coverage_checked','head_evidence_visible']})
        if not frame_reviewed:
            evidence.update(display_finding_allowed=False,evidence_status='needs_human_review',whole_frame_review_missing_or_unchecked=True)
        torso=fields.get('torso_evidence_visible',False)
        if type(torso)is not bool:raise ValueError('Explicit torso visibility boolean required')
        vest=person.get('vest','unknown')
        if vest not in ('present','absent','unknown'):raise ValueError('Stored vest observation enum required')
        vest_allowed=frame_reviewed and fields['exact_source_confirmed']and fields['face_coverage_checked']and torso and vest!='unknown'
        result.append({'person_id':person['id'],'provider_helmet_observation':verdict,'ppe_assessed':person.get('ppe_assessed',True),
                       'report_display_helmet':verdict if evidence['display_finding_allowed'] else 'unknown',
                       'provider_vest_observation':vest,'report_display_vest':vest if vest_allowed else'unknown',
                       'vest_evidence_review':{'torso_evidence_visible':torso,'display_finding_allowed':vest_allowed,'basis':'operator_evidence_claim_only'},
                       'evidence_review':evidence,'status':'operator_reviewed_private_only' if evidence['display_finding_allowed']and vest_allowed else 'needs_human_review'})
    return {'source':'private_report_preview_not_released','assessment_source':assessment['source'],'current_assessment_binding':deepcopy(assessment.get('current_assessment_binding')),
            'ppe_summary_status':assessment.get('ppe_attempt_status','not_assessed'if assessment['source']=='current_verified_sam_only_review'else'preserved_provider_observations'),
            'ppe_stage':deepcopy(assessment.get('ppe_stage')),'sam_configuration':deepcopy(assessment.get('sam_configuration')),'sam_configuration_sha256':assessment.get('sam_configuration_sha256'),
            'manual_contact_review':deepcopy(assessment.get('manual_contact_review',{})),'automatic_contact':False,'compliance_decision':False,'assessment_id':expected[0],'source_digest':expected[1],
            'derivative_sha256':expected[2],'regions_digest':expected[3],'persons':result,
            'status':'needs_human_review' if any(p['status']=='needs_human_review' for p in result) else 'private_operator_preview_only',
            'whole_frame_operator_review':{'checked':frame_reviewed,'basis':'operator_claim_only_not_detector_coverage','ack':deepcopy(full_frame_review)},
            'privacy_review_status':'not_validated','evidence_export_allowed':False,
            'notice':'Faces-in-reports requirement still needs reliable coverage/release validation. This private preview is not safe-to-share evidence.'}
