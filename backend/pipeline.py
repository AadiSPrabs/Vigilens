"""Offline pipeline contracts. Only synthetic fixture/mock observations supported.
No client credentials, network transport or real privacy clearance is implemented.
"""
from dataclasses import dataclass
import math
import copy
from core import fail,polygon,validate_zones,MAX_DIM,MAX_PIXELS
from rules import assess
from explanations import explanation_for

@dataclass(frozen=True)
class Frame:
    width:int
    height:int
    identity:str
    orientation:int=1
    def validate(self):
        if type(self.width) is not int or type(self.height) is not int or min(self.width,self.height)<=0 or max(self.width,self.height)>MAX_DIM or self.width*self.height>MAX_PIXELS or not isinstance(self.identity,str) or not 1<=len(self.identity)<=128 or type(self.orientation) is not int or self.orientation!=1:
            fail('INVALID_FRAME','Use a named upright positive-size coordinate frame.')

@dataclass(frozen=True)
class Observation:
    person_id:str
    polygon:tuple
    helmet:str
    vest:str
    contact_known:bool=True
    source:str='mock'

@dataclass(frozen=True)
class SegmentationBatch:
    frame:Frame
    observations:tuple
    completed:bool
    source:str='mock'

@dataclass(frozen=True)
class RecheckPolicy:
    max_person_attempts:int=1
    max_total_attempts:int=4
    def validate(self):
        if type(self.max_person_attempts) is not int or type(self.max_total_attempts) is not int or not 0<=self.max_person_attempts<=2 or not 0<=self.max_total_attempts<=8:
            fail('INVALID_RECHECK_POLICY','Local test recheck limits out of range.')

def pixel_polygon_to_normalized(points,frame,*,crop=None):
    """Explicit crop(x,y,width,height) in source pixels; never infer mask scaling."""
    frame.validate()
    if crop is None:crop=(0,0,frame.width,frame.height)
    if not isinstance(crop,(tuple,list)) or len(crop)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in crop):fail('INVALID_CROP','Invalid crop.')
    x0,y0,w,h=crop
    if w<=0 or h<=0 or x0<0 or y0<0 or x0+w>frame.width or y0+h>frame.height:fail('INVALID_CROP','Crop outside source frame.')
    out=[]
    if not isinstance(points,(tuple,list)) or not 3<=len(points)<=100:fail('INVALID_MASK_GEOMETRY','Use bounded pixel polygon points.')
    for p in points:
        if not isinstance(p,(tuple,list)) or len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p):fail('INVALID_MASK_GEOMETRY','Invalid pixel point.')
        x,y=p
        if not 0<=x<=w or not 0<=y<=h:fail('INVALID_MASK_GEOMETRY','Point outside crop.')
        out.append({'x':(x0+x)/frame.width,'y':(y0+y)/frame.height})
    return polygon(out)

def validate_observation(o):
    if not isinstance(o,Observation) or not isinstance(o.person_id,str) or not 1<=len(o.person_id)<=128 or not isinstance(o.polygon,(tuple,list)) or o.source not in ('fixture','mock') or type(o.contact_known) is not bool:
        fail('INVALID_OBSERVATION','Only explicit local fixture/mock observations are allowed.')
    points=polygon(list(o.polygon))
    if o.helmet not in ('present','absent','unknown') or o.vest not in ('present','absent','unknown'):
        fail('INVALID_OBSERVATION','Invalid PPE observation.')
    return points

class OfflinePipeline:
    def __init__(self,policy=RecheckPolicy()):policy.validate();self.policy=policy
    def run(self,batch,zones,*,recheck=None,cancelled=lambda:False):
        if not isinstance(batch,SegmentationBatch):fail('INVALID_BATCH','Invalid segmentation batch.')
        if not isinstance(batch.frame,Frame):fail('INVALID_FRAME','Missing explicit coordinate frame.')
        batch.frame.validate()
        if type(batch.completed) is not bool or not isinstance(batch.observations,(tuple,list)) or len(batch.observations)>256:fail('INVALID_BATCH','Require bounded observations and explicit completion status.')
        if batch.source not in ('fixture','mock'):fail('LIVE_ADAPTER_DISABLED','Real observations are not enabled.',503)
        if not batch.completed:fail('SEGMENTATION_INCOMPLETE','Incomplete segmentation cannot become successful empty results.',422)
        zones=validate_zones(zones)
        batch=copy.deepcopy(batch)
        ids=set();persons=[];total=0;trace=[]
        for original in batch.observations:
            points=validate_observation(original)
            if original.person_id in ids:fail('DUPLICATE_PERSON_ID','Duplicate person observation.')
            ids.add(original.person_id);current=original
            attempts=0;contradictions=[];observed_passes=[]
            while (current.helmet=='unknown' or current.vest=='unknown') and recheck is not None and attempts<self.policy.max_person_attempts and total<self.policy.max_total_attempts:
                if cancelled():fail('LOCAL_CANCELLED','Local pipeline stopped before next test step.',409)
                attempts+=1;total+=1
                # Record action only when the callback was actually invoked.
                try:
                    revised=recheck(copy.deepcopy(current),batch.frame)
                    validate_observation(revised)
                    if revised.person_id!=original.person_id or revised.polygon!=original.polygon or revised.source not in ('fixture','mock'):
                        fail('RECHECK_IDENTITY_MISMATCH','Recheck changed identity/geometry.')
                    observed_passes.append({'attempt':attempts,'source':revised.source,'helmet':revised.helmet,'vest':revised.vest,'contact_known':revised.contact_known})
                    changed=[key for key in ('helmet','vest') if getattr(current,key)!='unknown' and getattr(revised,key)!='unknown' and getattr(current,key)!=getattr(revised,key)]
                    if revised.contact_known!=original.contact_known:fail('RECHECK_IDENTITY_MISMATCH','Recheck changed ground-contact certainty.')
                    if changed:
                        contradictions=changed
                        revised=Observation(current.person_id,current.polygon,
                            'unknown' if 'helmet' in changed else revised.helmet,
                            'unknown' if 'vest' in changed else revised.vest,current.contact_known,current.source)
                    current=revised;trace.append({'person_id':original.person_id,'attempt':attempts,'action':'local_mock_recheck','outcome':'contradiction' if changed else 'returned'})
                    if changed:break
                except Exception:
                    # Do not drop previous uncertainty or publish exception/private content.
                    trace.append({'person_id':original.person_id,'attempt':attempts,'action':'local_mock_recheck','outcome':'failed'})
                    break
            if cancelled():fail('LOCAL_CANCELLED','Local result withheld after cancellation.',409)
            p=assess(dict(id=current.person_id,polygon=points,helmet=current.helmet,vest=current.vest,contact_known=current.contact_known),zones)
            p['recheck_observations']=observed_passes
            p['original_observations']={'helmet':original.helmet,'vest':original.vest,'contact_known':original.contact_known,'source':original.source,'attempt':0}
            p['contradictions']=contradictions
            p['explanation']=explanation_for(p)
            p['recheck_trace']=[t for t in trace if t['person_id']==current.person_id]
            persons.append(p)
        if cancelled():fail('LOCAL_CANCELLED','Local result withheld after cancellation.',409)
        from reports import validate_offline_report
        return validate_offline_report({'schema_version':'offline-pipeline-draft','source':'mock','frame':{'identity':batch.frame.identity,'width':batch.frame.width,'height':batch.frame.height,'orientation':1},
                'persons':persons,'zones':zones,'recheck_attempts':total,'recheck_trace':trace,
                'evidence_image':None,'evidence_status':'unavailable','evidence_export_allowed':False,'privacy_review_status':'not_validated',
                'assessment_notice':'SYNTHETIC/MOCK TEST - not real model output or a safety clearance.',
                'person_detection_status':'no_people_detected' if not persons else 'local_observations_only',
                'ruleset_version':'draft-unapproved'})
