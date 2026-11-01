"""Strict private PPE request/reply helpers, no dispatch or saved-source data."""
import base64,hashlib,json
from decimal import Decimal as D
MAX_COST=D('1.312256')
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
PROMPT='Inspect only this person crop. Is a protective hardhat WORN ON THE HEAD? Is a high-visibility reflective safety vest WORN ON THE TORSO? Gear held or in background is not worn. Return present, absent, or unknown for each, unknown if relevant pixels cannot decide. Give short visible evidence. No identity, compliance or safety claim.'
SCHEMA={'type':'object','properties':{'helmet':{'type':'string','enum':['present','absent','unknown']},'vest':{'type':'string','enum':['present','absent','unknown']},'helmet_evidence':{'type':'string'},'vest_evidence':{'type':'string'}},'required':['helmet','vest','helmet_evidence','vest_evidence'],'additionalProperties':False}
def canonical_body(crop):
    return {'model':'muse-spark-1.3','input':image_input(crop,PROMPT),'stream':False,'store':False,'reasoning':{'effort':'minimal'},'max_output_tokens':512,'text':{'format':{'type':'json_schema','name':'worn_ppe','strict':True,'schema':SCHEMA}}}

def parse_reply(raw):
    if not isinstance(raw,bytes)or len(raw)>256000:raise ValueError('Bounded PPE response required')
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise ValueError('Duplicate response key')
            d[k]=v
        return d
    response=json.loads(raw,object_pairs_hook=unique)
    if response.get('status')!='completed'or response.get('model')!='muse-spark-1.3'or not isinstance(response.get('id'),str)or not response['id']:raise ValueError('Expected completed PPE model response')
    lanes=[]
    for item in response.get('output',[]):
        if item.get('type')=='reasoning':continue
        if item.get('type')!='message'or item.get('role')!='assistant'or item.get('status')!='completed':raise ValueError('Unexpected PPE output lane')
        for part in item.get('content',[]):
            if part.get('type')!='output_text'or not isinstance(part.get('text'),str):raise ValueError('Refusal or malformed PPE text')
            lanes.append(part['text'])
    if len(lanes)!=1 or len(lanes[0].encode())>4096:raise ValueError('One bounded structured PPE observation required')
    observed=json.loads(lanes[0],object_pairs_hook=unique)
    if set(observed)!=set(SCHEMA['required'])or any(observed[k]not in ('present','absent','unknown')for k in ('helmet','vest'))or any(not isinstance(v,str)for v in observed.values()):raise ValueError('PPE schema mismatch')
    cost=listed_cost(response.get('usage',{}))
    if cost>MAX_COST:raise ValueError('PPE usage exceeds reserved bound')
    return {'observation':observed,'response_id':response['id'],'response_sha256':hashlib.sha256(raw).hexdigest(),'usage':response['usage'],'listed_cost_usd':str(cost),'model':'muse-spark-1.3','provider_revision':'not_returned','accuracy_status':'not_validated','actual_debit':'unchecked','evidence_export_allowed':False}

def wire_completed(data):
 ev=[json.loads(l[6:]) for l in data.decode().splitlines() if l.startswith('data: ') and l[6:]!='[DONE]'];ends=[e['response'] for e in ev if e.get('type')=='response.completed']
 if len(ends)!=1 or ends[0].get('status')!='completed':raise ValueError('SAM incomplete')
 return ends[0]
def image_input(image,prompt):return [{'role':'user','content':[{'type':'input_text','text':prompt},{'type':'input_image','image_url':'data:image/png;base64,'+base64.b64encode(image).decode()}]}]
def listed_cost(usage):
 cached=usage.get('input_tokens_details',{}).get('cached_tokens',0)
 values=[usage.get('input_tokens'),usage.get('output_tokens'),cached]
 if any(type(v)is not int or v<0 for v in values) or cached>usage['input_tokens'] or usage['input_tokens']+512>1048576 or usage['output_tokens']>512:raise ValueError('Invalid reported usage; retain reservation')
 return (D(usage['input_tokens']-cached)*D('1.25')+D(cached)*D('.15')+D(usage['output_tokens'])*D('4.25'))/1000000
