"""Source-bound deliberate recheck plans. No dispatch, approval or retry authority.
Original result/geometry is never overwritten by a later candidate observation.
"""
import hashlib,io
from PIL import Image
from core import decode_image
from .pipeline import digest
from .ppe import canonical_body
from adapters import build_sam_image_request

def plan_recheck(source_png,result,person_id,*,attempts_so_far,max_attempts):
    if type(max_attempts)is not int or not 0<=max_attempts<=2 or type(attempts_so_far)is not int or not 0<=attempts_so_far<=max_attempts:raise ValueError('Explicit bounded recheck policy required')
    frame=decode_image(source_png,'image/png')
    if result['image']!={'pixel_digest':frame.digest,'width':frame.width,'height':frame.height}:raise ValueError('Exact original source/result frame required')
    persons=result['persons'];person=next((p for p in persons if p['id']==person_id),None)
    if person is None or len({p['id']for p in persons})!=len(persons):raise ValueError('Unique exact person required')
    if person.get('ppe_assessed')is False:return {'status':'escalate_human_review','reason':'not_original_PPE_unknown_unassessed_person','person_id':person_id,'provider_calls':0}
    unknown=[k for k in ('helmet','vest')if person[k]=='unknown']
    if not unknown:return {'status':'not_needed','provider_calls':0,'person_id':person_id}
    if attempts_so_far>=max_attempts:return {'status':'escalate_human_review','reason':'configured_recheck_bound_reached','person_id':person_id,'provider_calls':0}
    box=person['box_half_open']
    if not isinstance(box,list)or len(box)!=4 or any(type(v)is not int for v in box)or not 0<=box[0]<box[2]<=frame.width or not 0<=box[1]<box[3]<=frame.height:raise ValueError('Exact original person crop required')
    with Image.open(io.BytesIO(source_png))as image:
        crop=image.crop(box).convert('RGB');buf=io.BytesIO();crop.save(buf,'PNG');raw=buf.getvalue()
    if hashlib.sha256(raw).hexdigest()!=person['crop_png_sha256']:raise ValueError('Original crop changed')
    sam=build_sam_image_request(raw,'image/png','person');sam['store']=False
    ppe=canonical_body(raw)
    return {'status':'planned_not_authorised_or_dispatched','source_digest':frame.digest,'result_sha256':digest(result),
            'person_id':person_id,'attempt':attempts_so_far+1,'original_person_box':box,
            'crop_png_sha256':person['crop_png_sha256'],'unknown_items':unknown,
            'steps':[{'stage':'crop_person_resegmentation','request':sam,'request_sha256':digest(sam)},
                     {'stage':'original_crop_ppe_reassessment','request':ppe,'request_sha256':digest(ppe)}],
            'source_geometry_update_allowed':False,'provider_calls':0,
            'execution_requires':'reviewed crop-person association, exact request authority, current pricing and SAME aggregate reservation/journal',
            'uncertain_attempt_retry_allowed':False,'evidence_export_allowed':False}

def compare_candidate(original,candidate):
    if set(original)!={'helmet','vest'}or set(candidate)!={'helmet','vest'}or any(v not in ('present','absent','unknown')for v in list(original.values())+list(candidate.values())):raise ValueError('Strict original/candidate observations required')
    merged={};contradictions=[]
    for item in ('helmet','vest'):
        before,after=original[item],candidate[item]
        if before!='unknown'and after!='unknown'and before!=after:merged[item]='unknown';contradictions.append(item)
        elif before=='unknown':merged[item]=after
        else:merged[item]=before
    return {'original_observations':dict(original),'candidate_observations':dict(candidate),
            'review_display_proposal':merged,'contradictions':contradictions,
            'status':'needs_human_review','original_overwrite_allowed':False,'evidence_export_allowed':False}
