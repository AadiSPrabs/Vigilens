"""Disabled Muse Spark1.3 image PPE proposal boundary. No transport/accuracy proof."""
import base64
import copy
import json
from typing import Literal
from pydantic import BaseModel,ConfigDict,ValidationError
from core import decode_image,fail,pixel_only_png
from adapters import LiveTransportDisabled

class PPEProposal(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    person_id:str
    helmet:Literal['present','absent','unknown']
    vest:Literal['present','absent','unknown']
    observation_quality:Literal['usable','uncertain']

# Explicit finite subset; schema conformance is NOT visual correctness.
PPE_SCHEMA={'type':'object','additionalProperties':False,'properties':{
    'person_id':{'type':'string'},'helmet':{'type':'string','enum':['present','absent','unknown']},
    'vest':{'type':'string','enum':['present','absent','unknown']},
    'observation_quality':{'type':'string','enum':['usable','uncertain']}},
    'required':['person_id','helmet','vest','observation_quality']}

def build_muse_ppe_request(crop_bytes,mime,person_id):
    if not isinstance(person_id,str) or not 1<=len(person_id)<=128 or any(ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for ch in person_id):fail('INVALID_PERSON_ID','Use a bounded safe local person ID.')
    image=decode_image(crop_bytes,mime)
    if image.orientation!=1:fail('IMAGE_ORIENTATION_UNSUPPORTED','Use an upright crop.',422)
    clean_image=pixel_only_png(crop_bytes,mime)
    return {'model':'muse-spark-1.3','input':[{'type':'message','role':'user','content':[
        {'type':'input_text','text':f'For the single selected person crop {person_id}, report helmet and high-visibility vest observations only. Use unknown when unclear, occluded, missing detail or contradictory. Set observation_quality uncertain when the crop cannot establish these. Echo person_id exactly. Do not derive severity, zone policy, privacy clearance or a safety verdict.'},
        {'type':'input_image','image_url':'data:image/png;base64,'+base64.b64encode(clean_image).decode('ascii')}]}],
        'text':{'format':{'type':'json_schema','name':'ppe_observation_draft','schema':copy.deepcopy(PPE_SCHEMA),'strict':True}},
        'max_output_tokens':256,'stream':False}

def parse_muse_ppe_proposal(text,person_id,*,response_completed):
    if response_completed is not True:fail('MUSE_RESPONSE_INCOMPLETE','Incomplete response; no PPE proposal.',422)
    if not isinstance(text,str) or len(text.encode('utf-8'))>4096:fail('MUSE_OUTPUT_TOO_LARGE','PPE output exceeds local limit.',422)
    try:
        def unique(pairs):
            out={}
            for k,v in pairs:
                if k in out:raise ValueError('duplicate key')
                out[k]=v
            return out
        data=json.loads(text,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        p=PPEProposal.model_validate(data)
    except (ValueError,ValidationError):fail('INVALID_PPE_PROPOSAL','Output must be exact structured PPE fields.',422)
    if p.person_id!=person_id:fail('PPE_PERSON_MISMATCH','Proposal belongs to a different selected person.',422)
    # This is unvalidated model evidence, not a pipeline Observation or approved finding.
    out=p.model_dump()
    if p.observation_quality=='uncertain':out.update(helmet='unknown',vest='unknown')
    return dict(out,original_proposal=p.model_dump(),source='unvalidated_model_proposal',requires_human_review=True,evidence_export_allowed=False)

class DisabledMuseAdapter:
    def send(self,*args,**kwargs):raise LiveTransportDisabled('No Muse client/transport exists. Live authority and validation required.')

def parse_muse_response_envelope(response,person_id):
    """Parse saved nonstreaming Responses envelope, not arbitrary text from a tool.
Usage may be retained by caller for later reconciliation, never inferred as charge.
"""
    if not isinstance(response,dict) or response.get('status')!='completed' or response.get('model')!='muse-spark-1.3':fail('MUSE_RESPONSE_INCOMPLETE','Require completed expected-model response.',422)
    output=response.get('output')
    if not isinstance(output,list) or not 1<=len(output)<=8:fail('INVALID_MUSE_ENVELOPE','Missing bounded response output.',422)
    text=[];messages=0
    for item in output:
        if not isinstance(item,dict):fail('INVALID_MUSE_ENVELOPE','Malformed output item.',422)
        # Reasoning is not a PPE observation. Do not publish or parse it as one.
        if item.get('type')=='reasoning':continue
        if item.get('type')!='message' or item.get('role')!='assistant' or item.get('status')!='completed':fail('INVALID_MUSE_ENVELOPE','Unexpected or incomplete output item.',422)
        messages+=1;content=item.get('content')
        if not isinstance(content,list) or not 1<=len(content)<=8:fail('INVALID_MUSE_ENVELOPE','Missing bounded assistant content.',422)
        for part in content:
            if not isinstance(part,dict) or part.get('type')!='output_text' or not isinstance(part.get('text'),str):fail('MUSE_REFUSAL_OR_INVALID_OUTPUT','Nontext/refusal output requires review.',422)
            text.append(part['text'])
    if messages!=1 or len(text)!=1:fail('MUSE_OUTPUT_LANE_MISMATCH','Require one exact structured text lane.',422)
    return parse_muse_ppe_proposal(text[0],person_id,response_completed=True)
