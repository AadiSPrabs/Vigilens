"""Synthetic redaction plumbing only. Not a face detector or privacy assurance."""
from dataclasses import dataclass
from PIL import Image,ImageDraw
from core import fail
from pipeline import Frame

@dataclass(frozen=True)
class PrivacyReview:
    frame_identity:str
    width:int
    height:int
    completed:bool
    coverage_known:bool
    source:str='mock'

def redact_synthetic(image,frame,regions,review,margin=4):
    """Test explicit manually authored regions on synthetic pixels only.
Output is never labelled masked/no_faces clearance and never exportable evidence.
"""
    frame.validate()
    if not isinstance(image,Image.Image) or image.size!=(frame.width,frame.height):fail('PRIVACY_FRAME_MISMATCH','Image frame mismatch.',422)
    if not isinstance(review,PrivacyReview) or review.source not in ('mock','synthetic'):
        fail('LIVE_PRIVACY_DISABLED','Real privacy processing is not implemented.',503)
    if type(review.completed) is not bool or type(review.coverage_known) is not bool or not review.completed or not review.coverage_known:fail('PRIVACY_UNCERTAIN','Incomplete or uncertain coverage; block evidence.',422)
    if (review.frame_identity,review.width,review.height)!=(frame.identity,frame.width,frame.height):fail('PRIVACY_FRAME_MISMATCH','Mask review belongs to a different frame.',422)
    if not regions:fail('PRIVACY_ZERO_REGIONS','Zero masks do not establish no faces.',422)
    if type(margin) is not int or not 0<=margin<=64:fail('INVALID_MARGIN','Invalid synthetic redaction margin.')
    out=image.convert('RGB').copy();draw=ImageDraw.Draw(out)
    for r in regions:
        if not isinstance(r,(tuple,list)) or len(r)!=4 or any(type(v) is not int for v in r):fail('INVALID_PRIVACY_REGION','Use integer pixel boxes.')
        x1,y1,x2,y2=r
        if not 0<=x1<x2<=frame.width or not 0<=y1<y2<=frame.height:fail('INVALID_PRIVACY_REGION','Region outside frame.')
        # Opaque fill ensures deterministic synthetic tests, no blur-strength claim.
        draw.rectangle((max(0,x1-margin),max(0,y1-margin),min(frame.width-1,x2+margin-1),min(frame.height-1,y2+margin-1)),fill=(0,0,0))
    return out,{'source':'mock','evidence_status':'unavailable','evidence_export_allowed':False,
                'privacy_test_status':'synthetic_regions_redacted_only','frame_identity':frame.identity}
