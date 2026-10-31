"""Reusable fresh-upload backend preparation. Default transport disabled, no public-upload grant."""
import hashlib,io,json,sqlite3,time,os,asyncio,concurrent.futures
from decimal import Decimal as D
from pathlib import Path
from PIL import Image
from core import decode_image,pixel_only_png
from private_sqlite import require_private_file
from pipeline import Frame
from adapters import build_sam_image_request,LiveTransportDisabled
from sam_parser import parse_sam_image_text
from .masks import encode_mask,decode_mask
from .approvals import ApprovalStore
from .ppe import canonical_body,parse_reply,digest,MAX_COST
RESERVE=D('.0025')+2*MAX_COST
CARRY_PATH=None
# Pinned by this work's reviewed source/accounting checkpoint, never caller-provided credit allowance.
CARRY_SHA=None

def disabled_transport(_):raise LiveTransportDisabled('Fresh-upload provider dispatch not enabled')

def _single_upload_eligibility(objects):
    """Record the ACTUAL crop-evidence checks for new single-upload crops (runtime delta seq18 proposal).
    Same function and default limits as the wide-scene gate: verified mask, no other person's foreground
    in the crop, minimum crop size. Never a blanket 'clean': ineligible crops are recorded as ineligible
    and then count as unresolved partial evidence. Older stored results are untouched (no record = legacy).
    Eligible here is the retained crop rule only; person association is not proven."""
    from .wide_scene import eligibility,WideLimits
    limits=WideLimits();gates=eligibility(objects,limits)
    return {k:{**g,'recorded_by':'single_upload_same_eligibility_function','limits_applied':{'min_crop_width':limits.min_crop_width,'min_crop_height':limits.min_crop_height,'source':'WideLimits defaults; technical threshold, not accuracy validation'}}for k,g in gates.items()}


class FreshPipeline:
    def __init__(self,database,*,approval_store=None,transport=None,execution_scope='private_provider_processing',carry_path=CARRY_PATH,carry_sha=None):
        self.path=Path(database);self.approval_store=approval_store or ApprovalStore();self.transport=transport or disabled_transport
        self.carry_path=Path(carry_path)if carry_path is not None else None;self.carry_sha=carry_sha
        self.execution_scope=execution_scope
        if execution_scope not in ('private_provider_processing','synthetic_local_qualification'):raise ValueError('Explicit execution scope required')
    def carry(self):
        if self.carry_path is None or not isinstance(self.carry_sha,str)or len(self.carry_sha)!=64:raise ValueError('Trusted private accounting checkpoint required')
        raw=self.private_bytes(self.carry_path)
        if hashlib.sha256(raw).hexdigest()!=self.carry_sha:raise ValueError('Accounting changed; reconcile before dispatch')
        c=json.loads(raw)
        if c.get('aggregate_cap_usd')!='5'or type(c.get('provider_calls_total'))is not int or c['provider_calls_total']<0:raise ValueError('Explicit aggregate accounting required')
        blocked=c.get('blocked_source_digests')
        if not isinstance(blocked,list)or any(not isinstance(v,str)or len(v)!=64 or any(x not in '0123456789abcdef'for x in v)for v in blocked):raise ValueError('Reconciled prior source tombstones required')
        booked=D(c['conservative_booked_usd'])
        if not booked.is_finite()or not 0<=booked<=D('5'):raise ValueError('Valid conservative prior booking required')
        return c
    def connect(self):
        require_private_file(self.path);c=sqlite3.connect(self.path,timeout=10)
        c.execute('CREATE TABLE IF NOT EXISTS jobs(source TEXT PRIMARY KEY,state TEXT,reserved TEXT,cost TEXT,binding TEXT,result TEXT,result_sha TEXT,started REAL)')
        c.execute('CREATE TABLE IF NOT EXISTS calls(source TEXT,ordinal INTEGER,model TEXT,state TEXT,request_sha TEXT,response_sha TEXT,cost TEXT,PRIMARY KEY(source,ordinal))')
        return c
    def read(self,source):
        if not self.path.is_file():return None
        if self.path.is_symlink()or self.path.stat().st_mode&0o077:raise ValueError('Private journal required')
        c=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)
        try:r=c.execute('SELECT state,reserved,cost,binding,result,result_sha FROM jobs WHERE source=?',(source,)).fetchone()
        finally:c.close()
        if not r:return None
        binding=json.loads(r[3])
        if binding.get('source_digest')!=source:raise ValueError('Job source binding changed')
        self.validate_binding(binding)
        result=json.loads(r[4])if r[4]else None
        if result is not None:
            if digest(result)!=r[5]:raise ValueError('Stored fresh result changed')
            if result['image']['pixel_digest']!=source or[result['image']['width'],result['image']['height']]!=binding['frame_size']:raise ValueError('Stored source frame changed')
            self.verify_artifacts(source,result,binding)
            total=self.call_cost(source)
            if D(r[2])!=total or total>RESERVE or D(r[1])!=RESERVE or r[0]!='completed':raise ValueError('Job accounting changed')
        if r[0]not in ('completed','running_uncertain')or D(r[1])!=RESERVE or binding.get('carry_sha256')!=self.carry_sha:raise ValueError('Job hold or state changed')
        self.carry()
        from .stopped_source import verify
        c=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)
        try:settlement=verify(self,c,source)
        finally:c.close()
        return {'accounting_settlement':settlement,'requires_operator_reconciliation':r[0]!='completed','execution_status':'completed_provider_observations'if r[0]=='completed'else'attempt_uncertain_terminal_no_retry','state':r[0],'reservation_usd':r[1],'known_listed_usd':r[2],'binding':json.loads(r[3]),'result':result,'retry_allowed':False,'provider_calls_this_request':0,'attempted_provider_calls_total':self.attempted_count(source),'provider_call_count_status':'attempts_recorded_debit_unchecked'if r[0]=='completed'else'uncertain_requires_reconciliation','actual_debit':'unchecked','evidence_export_allowed':False}
    def validate_binding(self,binding):
        if binding['source_digest']in self.carry()['blocked_source_digests']:raise ValueError('Previously paid source blocked throughout lifecycle')
        spec=self.approval_store.lookup(binding['source_digest'],binding['frame_size'])
        if spec['provenance']['scope']!=self.execution_scope:raise ValueError('Approval scope differs from execution scope')
        expected={'sam_model':'sam-3.1','ppe_model':'muse-spark-1.3','ppe_max_output_tokens':512,'max_people':2,'carry_sha256':self.carry_sha,'zones':[],'zone_policy':'not_applied','export_allowed':False,'source_approval_snapshot':spec,'source_approval_reference':spec['rights_reference']}
        if any(type(binding.get(k))is not type(v)or binding[k]!=v for k,v in expected.items()):raise ValueError('Source approval/configuration changed')
    def verify_artifacts(self,source,result,binding):
        expected={'source':'fresh_upload_provider_review','zones':[],'zone_status':'not_checked','compliance_status':'not_evaluated','findings':None,'review_status':'needs_human_review','privacy_review_status':'not_validated','evidence_export_allowed':False,'provider_proof':'local_request_response_consistency_not_provider_signature'}
        if any(type(result.get(k))is not type(v)or result[k]!=v for k,v in expected.items()):raise ValueError('Top-level private result policy changed')
        if any(p.get('ppe_assessed')is not True or p.get('contact_status')!='not_checked'or p.get('compliance_status')!='not_evaluated'for p in result['persons']):raise ValueError('Person policy fields changed')
        source_path=self.path.parent/('fresh-'+source+'-source.png')
        source_raw=self.private_bytes(source_path)
        source_frame=decode_image(source_raw,'image/png')
        if source_frame.digest!=source or hashlib.sha256(source_raw).hexdigest()!=binding['canonical_png_sha256']or binding['carry_sha256']!=self.carry_sha:raise ValueError('Preserved source changed')
        c=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)
        try:rows=c.execute('SELECT ordinal,model,state,request_sha,response_sha,cost FROM calls WHERE source=? ORDER BY ordinal',(source,)).fetchall()
        finally:c.close()
        if len(rows)!=len(result['persons'])+1 or rows[0][0]!=0:raise ValueError('Call association incomplete')
        if [r[0]for r in rows]!=list(range(len(rows))):raise ValueError('Call ordering changed')
        for ordinal,model,state,request_sha,response_sha,cost in rows:
            request_raw=self.private_bytes(self.path.parent/('fresh-'+source+'-'+str(ordinal)+'-request.json'))
            body=json.loads(request_raw)
            if digest(body)!=request_sha or body.get('model')!=model:raise ValueError('Request artifact changed')
            path=self.path.parent/('fresh-'+source+'-'+str(ordinal)+'-reply.bin')
            if not path.is_file()or path.is_symlink()or path.stat().st_mode&0o077 or hashlib.sha256(path.read_bytes()).hexdigest()!=response_sha:raise ValueError('Private response artifact changed')
            if state!='completed':raise ValueError('Incomplete provider stage')
            if ordinal==0:
                from .ppe import wire_completed
                sam=wire_completed(path.read_bytes())
                expected=build_sam_image_request(source_raw,'image/png','person');expected['store']=False
                text=''.join(c['text']for item in sam.get('output',[])for c in item.get('content',[])if c.get('type')=='output_text')
                def reparse():return asyncio.run(parse_sam_image_text(text,Frame(source_frame.width,source_frame.height,source),wire_completed=True))
                with concurrent.futures.ThreadPoolExecutor(max_workers=1)as pool:parsed=pool.submit(reparse).result()
                geometry=[{'id':str(o['object_id']),'box_half_open':list(o['box_half_open']),'mask':encode_mask(o['mask'],list(o['box_half_open']),[source_frame.width,source_frame.height])}for o in parsed['objects']]
                if geometry!=binding['persons']or geometry!=[{k:p[k]for k in ('id','box_half_open','mask')}for p in result['persons']]:raise ValueError('Original SAM geometry association changed')
                if body!=expected or model!='sam-3.1'or D(cost)!=D('.0025')or sam.get('id')!=result['sam_response_id']or request_sha!=result['sam_request_sha256']:raise ValueError('SAM response association changed')
            else:
                person=result['persons'][ordinal-1];ppe=parse_reply(path.read_bytes());decode_mask(person['mask'])
                with Image.open(io.BytesIO(source_raw))as im:
                    crop=im.crop(person['box_half_open']);out=io.BytesIO();crop.save(out,'PNG');crop_raw=out.getvalue()
                if hashlib.sha256(crop_raw).hexdigest()!=person['crop_png_sha256']or body!=canonical_body(crop_raw)or model!='muse-spark-1.3'or D(cost)!=D(ppe['listed_cost_usd']):raise ValueError('Original crop/request/cost association changed')
                if person['mask']['box_half_open_pixels']!=person['box_half_open']or person['mask']['source_frame_size']!=[result['image']['width'],result['image']['height']]:raise ValueError('Mask source placement changed')
                if ppe!=person['provider_observation']or request_sha!=person['ppe_request_sha256']or ppe['response_id']!=person['ppe_response_id']or(person['helmet'],person['vest'])!=(ppe['observation']['helmet'],ppe['observation']['vest']):raise ValueError('PPE response association changed')
        self.carry()

    @staticmethod
    def private_bytes(path):
        if not path.is_file()or path.is_symlink()or path.stat().st_mode&0o077:raise ValueError('Private preserved artifact required')
        return path.read_bytes()
    @staticmethod
    def save_private(path,raw):
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
    def register_derivative(self,png,source):
        pixel=decode_image(png,'image/png').digest
        c=self.connect()
        try:
            c.execute('CREATE TABLE IF NOT EXISTS display_derivatives(pixel_digest TEXT PRIMARY KEY,source_digest TEXT NOT NULL)')
            c.execute('INSERT OR IGNORE INTO display_derivatives VALUES(?,?)',(pixel,source));c.commit()
        finally:c.close()
    def reject_derivative(self,pixel):
        if not self.path.is_file():return
        c=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)
        try:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='display_derivatives'").fetchone()and c.execute('SELECT 1 FROM display_derivatives WHERE pixel_digest=?',(pixel,)).fetchone():raise ValueError('Display derivative cannot be provider source')
        finally:c.close()
    def prepare(self,raw,mime,zones):
        if zones!=[]:raise ValueError('Fresh preparation supports no-zone policy only')
        frame=decode_image(raw,mime)
        self.reject_derivative(frame.digest)
        if frame.orientation!=1:raise ValueError('Explicit upright input required')
        spec=self.approval_store.lookup(frame.digest,[frame.width,frame.height])
        if spec['provenance']['scope']!=self.execution_scope:raise ValueError('Approval scope differs from execution scope')
        carry=self.carry()
        if frame.digest in carry['blocked_source_digests']:raise ValueError('Previously paid source blocked throughout lifecycle')

        png=pixel_only_png(raw,mime);sam=build_sam_image_request(png,'image/png','person');sam['store']=False
        binding={'source_digest':frame.digest,'frame_size':[frame.width,frame.height],'canonical_png_sha256':hashlib.sha256(png).hexdigest(),'sam_request_sha256':digest(sam),'sam_model':'sam-3.1','ppe_model':'muse-spark-1.3','ppe_max_output_tokens':512,'max_people':2,'source_approval_reference':spec['rights_reference'],'source_approval_snapshot':json.loads(json.dumps(spec)),'carry_sha256':self.carry_sha,'zones':[],'zone_policy':'not_applied','export_allowed':False}
        return frame,png,sam,binding
    def claim(self,binding):
        carry=self.carry();source=binding['source_digest'];self.validate_binding(binding);c=self.connect()
        try:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT state FROM jobs WHERE source=?',(source,)).fetchone()
            if r:return False
            if c.execute('SELECT count(*) FROM jobs').fetchone()[0]>=64:raise ValueError('Journal bound reached; retain tombstones')
            rows=c.execute('SELECT source,state,reserved,cost FROM jobs').fetchall()
            for oldsource,state,reserved,cost in rows:
                self.read(oldsource) #Verify persisted completed cost/artifacts and all retained holds before new spend.
            from .recheck_journal import reservation_total
            from .recheck_execution import verify_retained_rechecks
            verify_retained_rechecks(self,c)
            from .ppe_segmentation import total as mask_total,verify_retained
            verify_retained(self,c)
            from .explanation_execution import total as explanation_total,verify_retained as verify_explanations
            verify_explanations(self,c)
            from .stopped_source import original_total
            booked=D(carry['conservative_booked_usd'])+original_total(self,c)+reservation_total(c)+mask_total(c)+explanation_total(c)
            if booked+RESERVE>D('5'):raise ValueError('Same aggregate cap unavailable; held reservations count in full')
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)',(source,'running_uncertain',str(RESERVE),'0',json.dumps(binding),None,None,time.time()));c.commit();return True
        finally:c.close()
    def attempted_count(self,source):
        c=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)
        try:return c.execute('SELECT count(*) FROM calls WHERE source=?',(source,)).fetchone()[0]
        finally:c.close()
    def call_cost(self,source):
        c=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)
        try:return sum((D(r[0])for r in c.execute('SELECT cost FROM calls WHERE source=?',(source,))),D('0'))
        finally:c.close()
    def dispatch(self,source,ordinal,body):
        source_raw=self.private_bytes(self.path.parent/('fresh-'+source+'-source.png'))
        c=self.connect()
        try:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT state,binding FROM jobs WHERE source=?',(source,)).fetchone()
            if not row or row[0]!='running_uncertain':raise ValueError('Active paid claim required')
            from .stopped_source import retained
            if retained(c,source)is not None:raise ValueError('Settled stopped source is terminal; no dispatch')
            binding=json.loads(row[1])
            self.validate_binding(binding)
            spec=self.approval_store.lookup(source,binding['frame_size'])
            if spec!=binding['source_approval_snapshot']or spec.get('provider_upload_approved')is not True:raise ValueError('Source approval changed before dispatch')
            if ordinal<0 or ordinal>2 or c.execute('SELECT count(*) FROM calls WHERE source=?',(source,)).fetchone()[0]!=ordinal:raise ValueError('Exact next stage required')
            if ordinal>0 and c.execute('SELECT count(*) FROM calls WHERE source=? AND state=?',(source,'completed')).fetchone()[0]!=ordinal:raise ValueError('Previous stage incomplete')
            if decode_image(source_raw,'image/png').digest!=source or hashlib.sha256(source_raw).hexdigest()!=binding['canonical_png_sha256']:raise ValueError('Source changed before dispatch')
            if ordinal==0:
                expected=build_sam_image_request(source_raw,'image/png','person');expected['store']=False
            else:
                person=binding['persons'][ordinal-1]
                with Image.open(io.BytesIO(source_raw))as im:
                    crop=im.crop(person['box_half_open']);buffer=io.BytesIO();crop.save(buffer,'PNG')
                expected=canonical_body(buffer.getvalue())
            if body!=expected:raise ValueError('Exact canonical request required before dispatch')
            self.carry()
            c.execute('INSERT INTO calls VALUES(?,?,?,?,?,?,?)',(source,ordinal,body['model'],'attempted_uncertain',digest(body),None,'0'));c.commit()
        finally:c.close()
        #No automatic retries. Preserve exact request before dispatch.
        self.save_private(self.path.parent/('fresh-'+source+'-'+str(ordinal)+'-request.json'),json.dumps(body,sort_keys=True,separators=(',',':')).encode())
        reply=self.transport(body)
        if not isinstance(reply,bytes)or len(reply)>4_000_000:raise ValueError('Bounded provider bytes required')
        path=self.path.parent/('fresh-'+source+'-'+str(ordinal)+'-reply.bin');fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb')as f:f.write(reply);f.flush();os.fsync(f.fileno())
        c=self.connect()
        try:c.execute('UPDATE calls SET state=?,response_sha=? WHERE source=? AND ordinal=?',('received_unparsed',hashlib.sha256(reply).hexdigest(),source,ordinal));c.commit()
        finally:c.close()
        return reply
    def record_cost(self,source,ordinal,cost):
        c=self.connect()
        try:
            c.execute('BEGIN IMMEDIATE');c.execute('UPDATE calls SET state=?,cost=? WHERE source=? AND ordinal=?',('completed',str(cost),source,ordinal))
            total=sum(D(r[0])for r in c.execute('SELECT cost FROM calls WHERE source=?',(source,)))
            c.execute('UPDATE jobs SET cost=? WHERE source=?',(str(total),source));c.commit()
        finally:c.close()
    async def run(self,raw,mime,zones):
        frame,png,sam,binding=self.prepare(raw,mime,zones);source=frame.digest
        existing=self.read(source)
        if existing:return existing
        if self.transport is disabled_transport:raise LiveTransportDisabled('Fresh pipeline dispatch disabled; no claim created')
        if not self.claim(binding):return self.read(source)
        try:
            from .ppe import wire_completed
            self.save_private(self.path.parent/('fresh-'+source+'-source.png'),png)
            reply=self.dispatch(source,0,sam);response=wire_completed(reply)
            if response.get('model')!='sam-3.1'or not response.get('id')or response.get('usage',{}).get('images_processed')!=1:raise ValueError('Unique expected SAM completion required')
            self.record_cost(source,0,D('.0025'))
            text=''.join(c['text']for item in response.get('output',[])for c in item.get('content',[])if c.get('type')=='output_text')
            parsed=await parse_sam_image_text(text,Frame(frame.width,frame.height,source),wire_completed=True)
            objects=parsed['objects']
            if not 1<=len(objects)<=2:raise ValueError('Zero/more-than-two persons requires whole-job review, not partial success')
            ids=[str(o['object_id'])for o in objects]
            if len(set(ids))!=len(ids):raise ValueError('Duplicate person ID')
            for obj in objects:encode_mask(obj['mask'],list(obj['box_half_open']),[frame.width,frame.height])
            #Any other person's foreground in a person's crop blocks all crop calls.
            for a in objects:
                for b in objects:
                    if a is b:continue
                    ax,ay,ar,ab=a['box_half_open'];bx,by,br,bb=b['box_half_open'];l,t,r,bottom=max(ax,bx),max(ay,by),min(ar,br),min(ab,bb)
                    if l<r and t<bottom and b['mask'].crop((l-bx,t-by,r-bx,bottom-by)).getbbox():raise ValueError('Cross-person crop ambiguity')
            binding['persons']=[{'id':str(o['object_id']),'box_half_open':list(o['box_half_open']),'mask':encode_mask(o['mask'],list(o['box_half_open']),[frame.width,frame.height])}for o in objects]
            c=self.connect()
            try:c.execute('UPDATE jobs SET binding=? WHERE source=?',(json.dumps(binding),source));c.commit()
            finally:c.close()
            persons=[]
            gates=_single_upload_eligibility(objects)
            with Image.open(io.BytesIO(png))as im:
                for index,obj in enumerate(objects,1):
                    box=list(obj['box_half_open']);mask=encode_mask(obj['mask'],box,[frame.width,frame.height]);crop=im.crop(box);buffer=io.BytesIO();crop.save(buffer,'PNG');crop_bytes=buffer.getvalue();body=canonical_body(crop_bytes)
                    reply=self.dispatch(source,index,body);ppe=parse_reply(reply);self.record_cost(source,index,D(ppe['listed_cost_usd']))
                    persons.append({'id':str(obj['object_id']),'box_half_open':box,'mask':mask,'crop_png_sha256':hashlib.sha256(crop_bytes).hexdigest(),'ppe_request_sha256':digest(body),'ppe_response_id':ppe['response_id'],'helmet':ppe['observation']['helmet'],'vest':ppe['observation']['vest'],'ppe_assessed':True,'provider_observation':ppe,'crop_eligibility':gates[str(obj['object_id'])],'contact_status':'not_checked','compliance_status':'not_evaluated'})
            result={'source':'fresh_upload_provider_review','image':{'pixel_digest':source,'width':frame.width,'height':frame.height},'persons':persons,'zones':[],'zone_status':'not_checked','compliance_status':'not_evaluated','findings':None,'review_status':'needs_human_review','sam_response_id':response['id'],'sam_request_sha256':binding['sam_request_sha256'],'privacy_review_status':'not_validated','evidence_export_allowed':False,'provider_proof':'local_request_response_consistency_not_provider_signature'}
            self.carry();c=self.connect()
            try:c.execute('UPDATE jobs SET state=?,result=?,result_sha=? WHERE source=? AND state=?',('completed',json.dumps(result),digest(result),source,'running_uncertain'));c.commit()
            finally:c.close()
        except Exception:
            #No raw exception/provider/user content surfaced. Job remains held, no retry or partial observations.
            return {**self.read(source),'provider_calls_this_request':None,'notice':'Attempt uncertain; call/debit count needs reconciliation, full reservation retained. No partial result or automatic retry.'}
        return {**self.read(source),'provider_calls_this_request':len(persons)+1}
