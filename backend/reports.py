"""Fail-closed offline report boundary. Does not authorize privacy or safety release."""
from typing import Any,Literal
from pydantic import BaseModel,ConfigDict,model_validator,Field
from core import validate_zones
from explanations import explanation_for

class OfflinePerson(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    id:str
    polygon:list[dict[str,float]]
    helmet:Literal['present','absent','unknown']
    vest:Literal['present','absent','unknown']
    contact_known:bool
    zone_id:str|None
    zone_ids:list[str]
    zone_membership_status:Literal['known','unknown']
    zone_checks_performed:bool
    findings:list[dict[str,Any]]
    worst_severity:Literal['Critical','Medium','Low']|None
    assessment_status:Literal['needs_human_review','violations_found','no_listed_violations']
    ruleset_version:Literal['draft-unapproved']
    recheck_observations:list[dict[str,Any]]
    original_observations:dict[str,Any]
    contradictions:list[Literal['helmet','vest']]
    explanation:dict[str,Any]
    recheck_trace:list[dict[str,Any]]

class ReportFrame(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    identity:str
    width:int=Field(gt=0,le=4096)
    height:int=Field(gt=0,le=4096)
    orientation:Literal[1]

class OfflineReport(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    schema_version:Literal['offline-pipeline-draft']
    source:Literal['mock']
    frame:ReportFrame
    persons:list[OfflinePerson]=Field(max_length=256)
    zones:list[dict[str,Any]]
    recheck_attempts:int=Field(ge=0,le=8)
    recheck_trace:list[dict[str,Any]]=Field(max_length=8)
    evidence_image:None
    evidence_status:Literal['unavailable']
    evidence_export_allowed:Literal[False]
    privacy_review_status:Literal['not_validated']
    assessment_notice:Literal['SYNTHETIC/MOCK TEST - not real model output or a safety clearance.']
    person_detection_status:Literal['no_people_detected','local_observations_only']
    ruleset_version:Literal['draft-unapproved']
    @model_validator(mode='after')
    def coherent(self):
        from rules import assess
        zones=validate_zones(self.zones)
        if self.frame.width*self.frame.height>16_000_000:raise ValueError('Frame pixel bound')
        if len({p.id for p in self.persons})!=len(self.persons):raise ValueError('Duplicate person IDs')
        if self.person_detection_status!=('local_observations_only' if self.persons else 'no_people_detected'):raise ValueError('Detection status mismatch')
        if self.recheck_attempts!=len(self.recheck_trace):raise ValueError('Recheck count mismatch')
        if any(t.get('person_id') not in {p.id for p in self.persons} or t.get('action')!='local_mock_recheck' or t.get('outcome') not in ('returned','failed','contradiction') for t in self.recheck_trace):raise ValueError('Unrecognized recheck event')
        for p in self.persons:
            person=p.model_dump()
            if any(getattr(p,key)!='unknown' for key in p.contradictions):raise ValueError('Contradiction cannot be decided favourably')
            if p.original_observations.get('attempt')!=0 or p.original_observations.get('source') not in ('fixture','mock'):raise ValueError('Original provenance missing')
            if any(o.get('attempt')!=i+1 or o.get('source') not in ('fixture','mock') for i,o in enumerate(p.recheck_observations)):raise ValueError('Recheck observations out of order')
            recomputed=assess({k:person[k] for k in ('id','polygon','helmet','vest','contact_known')},zones)
            if any(person[k]!=recomputed[k] for k in ('zone_id','zone_ids','zone_membership_status','zone_checks_performed','findings','worst_severity','assessment_status','ruleset_version')):raise ValueError('Report differs from deterministic rules')
            if p.explanation!=explanation_for(recomputed):raise ValueError('Contradictory explanation')
            if p.recheck_trace!=[t for t in self.recheck_trace if t.get('person_id')==p.id]:raise ValueError('Recheck provenance mismatch')
        return self

def validate_offline_report(report):
    return OfflineReport.model_validate(report).model_dump()
