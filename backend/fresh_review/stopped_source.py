"""Narrow no-call settlement for completed SAM cardinality stops only.
Never changes original jobs/calls, publishes observations or permits another dispatch.
Every settled read revalidates exact artifacts and official parser cardinality.
"""
import asyncio,concurrent.futures,hashlib,json,time
from decimal import Decimal
from core import decode_image
from pipeline import Frame
from adapters import build_sam_image_request
from sam_parser import parse_sam_image_text
from .ppe import wire_completed
from .pipeline import digest,RESERVE

TABLE='source_stop_settlements'
def schema(c):c.execute('CREATE TABLE IF NOT EXISTS source_stop_settlements(source TEXT PRIMARY KEY,proof TEXT NOT NULL,proof_sha TEXT NOT NULL,at REAL NOT NULL)')
def retained(c,source):
 if not c.execute("SELECT 1 FROM sqlite_master WHERE name=?",(TABLE,)).fetchone():return None
 return c.execute('SELECT proof,proof_sha FROM source_stop_settlements WHERE source=?',(source,)).fetchone()
def proof(service,c,source):
 row=c.execute('SELECT state,reserved,cost,binding,result,result_sha FROM jobs WHERE source=?',(source,)).fetchone()
 if row is None or row[:3]!=('running_uncertain',str(RESERVE),'0.0025')or row[4]is not None or row[5]is not None:raise ValueError('Exact held source with SAM-only listed cost required')
 binding=json.loads(row[3]);service.validate_binding(binding)
 if binding.get('source_digest')!=source or 'persons'in binding:raise ValueError('Pre-PPE original binding required')
 calls=c.execute('SELECT ordinal,model,state,request_sha,response_sha,cost FROM calls WHERE source=? ORDER BY ordinal',(source,)).fetchall()
 if len(calls)!=1 or calls[0][:3]!=(0,'sam-3.1','completed')or calls[0][5]!='0.0025':raise ValueError('Exactly one terminal completed SAM call required; uncertainty retains full hold')
 root=service.path.parent;prefix='fresh-'+source
 # Any later-stage artifact, even with a missing row, blocks release.
 if any(root.glob(prefix+'-[12]-*')):raise ValueError('Later dispatch artifact present')
 raw=service.private_bytes(root/(prefix+'-source.png'));frame=decode_image(raw,'image/png')
 if frame.digest!=source or[frame.width,frame.height]!=binding['frame_size']or hashlib.sha256(raw).hexdigest()!=binding['canonical_png_sha256']:raise ValueError('Original source pin changed')
 request=json.loads(service.private_bytes(root/(prefix+'-0-request.json')));expected=build_sam_image_request(raw,'image/png','person');expected['store']=False
 reply=service.private_bytes(root/(prefix+'-0-reply.bin'));response=wire_completed(reply)
 if request!=expected or digest(request)!=binding['sam_request_sha256']or digest(request)!=calls[0][3]or hashlib.sha256(reply).hexdigest()!=calls[0][4]:raise ValueError('Exact original SAM artifacts required')
 if response.get('model')!='sam-3.1'or response.get('status')!='completed'or not response.get('id')or response.get('usage',{}).get('images_processed')!=1:raise ValueError('Terminal image completion required')
 text=''.join(p['text']for item in response.get('output',[])for p in item.get('content',[])if p.get('type')=='output_text')
 def parse():return asyncio.run(parse_sam_image_text(text,Frame(frame.width,frame.height,source),wire_completed=True))
 with concurrent.futures.ThreadPoolExecutor(max_workers=1)as pool:objects=pool.submit(parse).result()['objects']
 if 1<=len(objects)<=2:raise ValueError('Not a verified unsupported-cardinality stop')
 return {'format':'vigilens.sam-cardinality-stop-settlement.v1','source_digest':source,'binding_sha256':digest(binding),'request_sha256':calls[0][3],'reply_sha256':calls[0][4],'response_id':response['id'],'parsed_person_count':len(objects),'stop_reason':'unsupported_person_cardinality','known_listed_usd':'0.0025','original_reservation_usd':str(RESERVE),'unused_reservation_released_usd':str(RESERVE-Decimal('.0025')),'actual_debit':'unchecked','result_published':False,'retry_allowed':False}
def verify(service,c,source):
 r=retained(c,source)
 if r is None:return None
 current=proof(service,c,source)
 if digest(json.loads(r[0]))!=r[1]or json.loads(r[0])!=current:raise ValueError('Stopped-source settlement changed')
 return current
def settle(service,source):
 c=service.connect()
 try:
  schema(c);c.commit();c.execute('BEGIN IMMEDIATE')
  prior=verify(service,c,source)
  if prior:return prior
  current=proof(service,c,source)
  c.execute('INSERT INTO source_stop_settlements VALUES(?,?,?,?)',(source,json.dumps(current,sort_keys=True),digest(current),time.time()));c.commit();return current
 finally:c.close()
def original_total(service,c):
 total=Decimal('0')
 for source,state,reserved,cost in c.execute('SELECT source,state,reserved,cost FROM jobs').fetchall():
  service.read(source)
  settled=verify(service,c,source)
  total+=Decimal(settled['known_listed_usd'])if settled else Decimal(cost)if state=='completed'else Decimal(reserved)
 return total
