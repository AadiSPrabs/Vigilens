"""Optional offline YuNet proposals. Never privacy clearance or a PPE input transform."""
import hashlib,io,math
from pathlib import Path
from PIL import Image
from core import decode_image
MODEL_SHA256='8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4'

def propose_faces(source,mime,model_path):
    frame=decode_image(source,mime) # validated upright source; same identity as PPE branch
    result=dict(source_pixel_digest=frame.digest,frame=[frame.width,frame.height],
                detector='YuNet2023mar',model_sha256=MODEL_SHA256,threshold=.6,
                proposals=[],status='needs_manual_review',coverage='unverified',
                zero_detections_means_safe=False,privacy_review_status='not_validated',
                evidence_export_allowed=False,inference_source_unchanged=True)
    path=Path(model_path)
    if not path.is_file():return dict(result,reason='model_unavailable')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=MODEL_SHA256:return dict(result,reason='model_digest_mismatch')
    try:
        import cv2,numpy as np
    except ImportError:return dict(result,reason='optional_runtime_unavailable')
    # Entire frame, including background outside person boxes. Fixed native and
    # enlarged passes only. Enlarged side capped to limit CPU/memory expansion.
    image=Image.open(io.BytesIO(source)).convert('RGB')
    scales=[1.]
    larger=min(2.,1600/max(image.size))
    if larger>1.05:scales.append(larger)
    candidates=[]
    try:
        for scale in scales:
            size=(round(image.width*scale),round(image.height*scale))
            im=image.resize(size) if scale!=1 else image
            bgr=cv2.cvtColor(np.asarray(im),cv2.COLOR_RGB2BGR)
            model=cv2.FaceDetectorYN.create(str(path),'',size,.6,.3,5000)
            _,faces=model.detect(bgr)
            if faces is None:continue
            for face in faces:
                values=[float(v)for v in face]
                if len(values)!=15 or not all(math.isfinite(v)for v in values):raise ValueError('Malformed detector output')
                x,y,w,h=values[:4]
                if w<=0 or h<=0:raise ValueError('Nonpositive face')
                # Coordinate rounding uses real resize ratios, not nominal scale.
                sx=size[0]/image.width;sy=size[1]/image.height
                box=[max(0,math.floor(x/sx)),max(0,math.floor(y/sy)),min(image.width,math.ceil((x+w)/sx)),min(image.height,math.ceil((y+h)/sy))]
                if box[2]<=box[0] or box[3]<=box[1]:continue
                # Margin is a review proposal, never a coverage guarantee. It can
                # collide with helmet evidence, which operator must check.
                px=max(3,math.ceil((box[2]-box[0])*.15));py=max(3,math.ceil((box[3]-box[1])*.15))
                expanded=[max(0,box[0]-px),max(0,box[1]-py),min(image.width,box[2]+px),min(image.height,box[3]+py)]
                candidates.append(dict(box=box,review_region=expanded,confidence=values[-1],pass_scale=scale,helmet_overlap_unchecked=True))
    except Exception:return dict(result,reason='detector_failure_discarded_partial_output')
    # Keep overlapping multiscale candidates instead of aggressive NMS that
    # could erase an adjacent/background face. Operator must edit/merge/review.
    return dict(result,proposals=candidates,reason='proposals_require_face_and_helmet_review' if candidates else 'no_faces_detected_still_requires_review',passes=scales,runtime=cv2.__version__,box_semantics='half_open_candidate_face_not_full_head',margin_policy='15pct minimum3px proposal only; operator face coverage and helmet overlap review required')
