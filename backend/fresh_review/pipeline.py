"""Reusable fresh-upload backend preparation. Default transport disabled, no public-upload grant."""
import hashlib,io,json,sqlite3,time,os,asyncio,concurrent.futures
from decimal import Decimal as D
from pathlib import Path
from PIL import Image
from core import AuditError,decode_image,pixel_only_png
from private_sqlite import require_private_file
from .db import is_pg_dsn,open_store
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

def _transport_scope_ok(transport,execution_scope):
    """Pairing invariant, checked at construction and on every checkpoint read (covers attribute
    mutation after construction): the shipped live provider transport - MetaTransport or any
    subclass of it, since a subclass retains the live network __call__ - never runs under the
    synthetic scope, where a synthetic approval would otherwise pass the scope check and
    dispatch a real call. isinstance against the lazily imported class binds the actual type
    (a module-level import would be circular: transport.py imports this module); the getattr
    use keeps duck-typed facades (ArchiveExplanation borrows carry()) working.
    Limit: an injected transport that reimplements live network behavior WITHOUT subclassing
    MetaTransport cannot be identified by any type check; such custom code is trusted local
    code, and the spend boundary for it stays the pinned cap, the approval store and the
    owner-approved numeric limit, not this invariant."""
    if execution_scope=='private_provider_processing':return
    if transport is None:return
    from .transport import MetaTransport,MetaRequestTransport
    if isinstance(transport,(MetaTransport,MetaRequestTransport)):raise ValueError('Live provider transport requires the private_provider_processing scope')

def aggregate_cap(carry_doc):
    """Validated explicit per-install aggregate cap (USD listed) from the pinned carry checkpoint.
    The cap lives only in the sha-pinned checkpoint: it is fixed when the checkpoint is created,
    never silently changed by configuration, and every consumer fails closed on mismatch.
    Default for existing checkpoints remains '5'; this validates the value, it does not set it."""
    raw=carry_doc.get('aggregate_cap_usd')
    if not isinstance(raw,str):
        raise ValueError('Explicit aggregate accounting required')
    try:cap=D(raw)
    except Exception:raise ValueError('Explicit aggregate accounting required')
    if not cap.is_finite()or not D('0')<=cap<=D('1000000'):raise ValueError('Aggregate cap outside explicit bound')
    return cap

def _single_upload_eligibility(objects):
    """Record the ACTUAL crop-evidence checks for new single-upload crops (runtime delta seq18 proposal).
    Same function and default limits as the wide-scene gate: verified mask, no other person's foreground
    in the crop, minimum crop size. Never a blanket 'clean': ineligible crops are recorded as ineligible
    and then count as unresolved partial evidence. Older stored results are untouched (no record = legacy).
    Eligible here is the retained crop rule only; person association is not proven."""
    from .wide_scene import eligibility,WideLimits
    limits=WideLimits();gates=eligibility(objects,limits)
    return {k:{**g,'recorded_by':'single_upload_same_eligibility_function','limits_applied':{'min_crop_width':limits.min_crop_width,'min_crop_height':limits.min_crop_height,'source':'WideLimits defaults; technical threshold, not accuracy validation'}}for k,g in gates.items()}


class _ArtifactReader:
    # Minimal .read() shim so verification code consumes preserved bytes the
    # same way regardless of the backing store.
    def __init__(self,service,name):self._s=service;self._n=name
    def read(self):return self._s._read_artifact(self._n)

class FreshPipeline:
    def __init__(self,database,*,approval_store=None,transport=None,execution_scope='private_provider_processing',carry_path=CARRY_PATH,carry_sha=None,cap_enforcement=True,carry_document=None):
        self._dsn=str(database)if is_pg_dsn(database)else None;self.path=Path(database)if self._dsn is None else None
        self._carry_doc=carry_document
        self.approval_store=approval_store or ApprovalStore();self.transport=transport or disabled_transport;self.cap_enforcement=cap_enforcement
        self.carry_path=Path(carry_path)if carry_path is not None else None;self.carry_sha=carry_sha
        self.execution_scope=execution_scope
        if execution_scope not in ('private_provider_processing','synthetic_local_qualification'):raise ValueError('Explicit execution scope required')
        _transport_scope_ok(self.transport,self.execution_scope)
    def carry(self):
        _transport_scope_ok(getattr(self,'transport',None),getattr(self,'execution_scope',None))
        if getattr(self,'_carry_doc',None) is not None:
            raw=self._carry_doc.read()
            if not isinstance(self.carry_sha,str)or len(self.carry_sha)!=64 or self._carry_doc.sha!=self.carry_sha:raise ValueError('Trusted private accounting checkpoint required')
        else:
            if self.carry_path is None or not isinstance(self.carry_sha,str)or len(self.carry_sha)!=64:raise ValueError('Trusted private accounting checkpoint required')
            raw=self.private_bytes(self.carry_path)
            if hashlib.sha256(raw).hexdigest()!=self.carry_sha:raise ValueError('Accounting changed; reconcile before dispatch')
        c=json.loads(raw)
        cap=aggregate_cap(c)
        if type(c.get('provider_calls_total'))is not int or c['provider_calls_total']<0:raise ValueError('Explicit aggregate accounting required')
        blocked=c.get('blocked_source_digests')
        if not isinstance(blocked,list)or any(not isinstance(v,str)or len(v)!=64 or any(x not in '0123456789abcdef'for x in v)for v in blocked):raise ValueError('Reconciled prior source tombstones required')
        booked=D(c['conservative_booked_usd'])
        if not booked.is_finite()or not 0<=booked<=cap:raise ValueError('Valid conservative prior booking required')
        return c
    _JOBS_DDL="CREATE TABLE IF NOT EXISTS jobs(owner TEXT NOT NULL DEFAULT '',source TEXT NOT NULL,state TEXT,reserved TEXT,cost TEXT,binding TEXT,result TEXT,result_sha TEXT,started REAL,key_fp TEXT,PRIMARY KEY(owner,source))"
    _CALLS_DDL="CREATE TABLE IF NOT EXISTS calls(owner TEXT NOT NULL DEFAULT '',source TEXT NOT NULL,ordinal INTEGER,model TEXT,state TEXT,request_sha TEXT,response_sha TEXT,cost TEXT,PRIMARY KEY(owner,source,ordinal))"
    @staticmethod
    def _art(owner,source,suffix):
        # Per-account artifact namespace: request/reply (and source) sidecars of one
        # visitor's job never collide with another account's job over identical bytes.
        # Owner '' is the operator/legacy internal namespace (pre-ownership rows).
        return 'fresh-'+owner+'-'+source+'-'+suffix if owner else 'fresh-'+source+'-'+suffix
    def _ensure_schema(self,c):
        # Composite (owner, source) journal identity. Existing data is never dropped:
        # a legacy source-only table is rebuilt IN PLACE with every row preserved
        # under owner '' (operator/internal namespace), then the old copy removed.
        if self._dsn is not None:
            rows=c.execute("SELECT kcu.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name AND tc.table_name=kcu.table_name WHERE tc.table_name='jobs' AND tc.constraint_type='PRIMARY KEY' ORDER BY kcu.ordinal_position").fetchall()
            if [r[0] for r in rows]==['owner','source']:
                c.execute(self._JOBS_DDL);c.execute(self._CALLS_DDL);return
        else:
            row=c.execute("SELECT sql FROM sqlite_master WHERE name='jobs' AND type='table'").fetchone()
            if row and 'PRIMARYKEY(owner,source)' in row[0].replace(' ',''):
                c.execute(self._JOBS_DDL);c.execute(self._CALLS_DDL);return
        try:c.execute('ALTER TABLE jobs RENAME TO jobs_prev')
        except sqlite3.Error:c.execute(self._JOBS_DDL);c.execute(self._CALLS_DDL);return
        c.execute(self._JOBS_DDL)
        try:oldcols=[d[0] for d in c.execute('SELECT * FROM jobs_prev LIMIT 0').description]
        except sqlite3.Error:oldcols=[]
        has_owner='owner' in oldcols
        src_owner="COALESCE(owner,'')"if has_owner else"''"
        c.execute("INSERT INTO jobs(owner,source,state,reserved,cost,binding,result,result_sha,started,key_fp) SELECT "+src_owner+",source,state,reserved,cost,binding,result,result_sha,started,"+("key_fp"if"key_fp"in oldcols else"NULL")+" FROM jobs_prev")
        c.execute('DROP TABLE jobs_prev')
        try:c.execute('ALTER TABLE calls RENAME TO calls_prev')
        except sqlite3.Error:c.execute(self._CALLS_DDL);return
        c.execute(self._CALLS_DDL)
        c.execute("INSERT INTO calls(owner,source,ordinal,model,state,request_sha,response_sha,cost) SELECT '',source,ordinal,model,state,request_sha,response_sha,cost FROM calls_prev")
        c.execute('DROP TABLE calls_prev')
    def connect(self):
        if self._dsn is not None:
            c=open_store(self._dsn)
            self._ensure_schema(c)
            c.execute('CREATE TABLE IF NOT EXISTS fresh_files(name TEXT PRIMARY KEY,data BYTEA)')
            return c
        require_private_file(self.path);c=sqlite3.connect(self.path,timeout=10)
        self._ensure_schema(c)
        return c
    def _connect_ro(self):
        # Read-only reader. sqlite uses a mode=ro URI; Postgres readers issue plain
        # SELECTs (writes are neither attempted nor permitted by the store paths).
        if self._dsn is not None:return open_store(self._dsn,read_only=True)
        return sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)
    def _read_artifact(self,name):
        # Durable private artifact bytes (source PNG, request/reply sidecars). sqlite:
        # 0600 file + privacy checks; Postgres: BYTEA row in fresh_files (DB ACL is
        # the privacy boundary). Both raise the same error when absent.
        if self._dsn is not None:
            c=self.connect()
            try:r=c.execute('SELECT data FROM fresh_files WHERE name=?',(name,)).fetchone()
            finally:c.close()
            if not r:raise ValueError('Private preserved artifact required')
            return bytes(r[0])
        return self.private_bytes(self.path.parent/name)
    def _write_artifact(self,name,raw):
        # save_private semantics: exclusive create, fsync'd; overwrite is refused.
        if self._dsn is not None:
            # Plain committed INSERT, NOT the fencing transaction: sqlite
            # artifacts are files written OUTSIDE the journal transaction, and
            # satellite executors hold the fencing lock while writing theirs -
            # a fenced write here would self-deadlock against the caller's own
            # lock (found by the PG recheck exercise: lock_timeout under
            # BEGIN IMMEDIATE on a second connection). Exclusive-create
            # semantics come from the primary key: an existing name maps to
            # sqlite3.IntegrityError and is refused. Durability ordering vs the
            # journal row matches the sqlite file flow exactly.
            c=open_store(self._dsn)
            try:
                c.execute('INSERT INTO fresh_files VALUES(?,?)',(name,raw))
                c.commit()
            except sqlite3.Error:
                try:c.rollback()
                except Exception:pass
                raise ValueError('Private artifact write refused: exists or store unavailable')
            finally:c.close()
            return
        self.save_private(self.path.parent/name,raw)
    def _has_artifact(self,name):
        if self._dsn is not None:
            c=self.connect()
            try:return c.execute('SELECT 1 FROM fresh_files WHERE name=?',(name,)).fetchone() is not None
            finally:c.close()
        from .platform_private import path_private as _pp
        p=self.path.parent/name
        return p.is_file() and _pp(p,follow=False)
    def read(self,source,owner=None):
        # owner None is the INTERNAL/operator any-account view (journal inspection,
        # status route, tests): it never crosses an HTTP visitor boundary - visitor
        # routes always pass their account hash explicitly. An explicit owner
        # (including '' for operator-namespace rows) reads only that account's row.
        if self._dsn is not None:
            c=self._connect_ro()
        else:
            if self._dsn is None and not self.path.is_file():return None
            from .platform_private import path_private
            if not path_private(self.path,follow=False):raise ValueError('Private journal required')
            c=self._connect_ro()
        q='SELECT state,reserved,cost,binding,result,result_sha,owner,key_fp FROM jobs WHERE source=?'
        if owner is not None:q+=' AND owner=?'
        try:r=(c.execute(q+' ORDER BY owner',(source,))if owner is None else c.execute(q,(source,owner))).fetchone()
        except sqlite3.OperationalError as e:
            # Postgres parity with a missing sqlite file: a database whose
            # schema has not been created yet holds no stored result.
            if 'no such table' in str(e):return None
            raise
        finally:c.close()
        if not r:return None
        binding=json.loads(r[3])
        if binding.get('source_digest')!=source:raise ValueError('Job source binding changed')
        self.validate_binding(binding)
        result=json.loads(r[4])if r[4]else None
        if result is not None:
            if digest(result)!=r[5]:raise ValueError('Stored fresh result changed')
            if result['image']['pixel_digest']!=source or[result['image']['width'],result['image']['height']]!=binding['frame_size']:raise ValueError('Stored source frame changed')
            self.verify_artifacts(source,result,binding,r[6])
            total=self.call_cost(source,r[6])
            if D(r[2])!=total or total>RESERVE or D(r[1])!=RESERVE or r[0]!='completed':raise ValueError('Job accounting changed')
        if r[0]not in ('completed','running_uncertain')or D(r[1])!=RESERVE or binding.get('carry_sha256')!=self.carry_sha:raise ValueError('Job hold or state changed')
        self.carry()
        from .stopped_source import verify
        c=self._connect_ro()
        try:settlement=verify(self,c,source,r[6])
        finally:c.close()
        out_owner=r[6];out_key_fp=r[7]
        return {'owner':out_owner,'key_fp':out_key_fp,'accounting_settlement':settlement,'requires_operator_reconciliation':r[0]!='completed','execution_status':'completed_provider_observations'if r[0]=='completed'else'attempt_uncertain_terminal_no_retry','state':r[0],'reservation_usd':r[1],'known_listed_usd':r[2],'binding':json.loads(r[3]),'result':result,'retry_allowed':False,'provider_calls_this_request':0,'attempted_provider_calls_total':self.attempted_count(source,r[6]),'provider_call_count_status':'attempts_recorded_debit_unchecked'if r[0]=='completed'else'uncertain_requires_reconciliation','actual_debit':'unchecked','evidence_export_allowed':False}
    def validate_binding(self,binding):
        if binding['source_digest']in self.carry()['blocked_source_digests']:raise ValueError('Previously paid source blocked throughout lifecycle')
        spec=self.approval_store.lookup(binding['source_digest'],binding['frame_size'])
        if spec['provenance']['scope']!=self.execution_scope:raise ValueError('Approval scope differs from execution scope')
        expected={'sam_model':'sam-3.1','ppe_model':'muse-spark-1.3','ppe_max_output_tokens':512,'max_people':2,'carry_sha256':self.carry_sha,'zones':[],'zone_policy':'not_applied','export_allowed':False,'source_approval_snapshot':spec,'source_approval_reference':spec['rights_reference']}
        if any(type(binding.get(k))is not type(v)or binding[k]!=v for k,v in expected.items()):raise ValueError('Source approval/configuration changed')
    def verify_artifacts(self,source,result,binding,owner=''):
        expected={'source':'fresh_upload_provider_review','zones':[],'zone_status':'not_checked','compliance_status':'not_evaluated','findings':None,'review_status':'needs_human_review','privacy_review_status':'not_validated','evidence_export_allowed':False,'provider_proof':'local_request_response_consistency_not_provider_signature'}
        if any(type(result.get(k))is not type(v)or result[k]!=v for k,v in expected.items()):raise ValueError('Top-level private result policy changed')
        if any(p.get('ppe_assessed')is not True or p.get('contact_status')!='not_checked'or p.get('compliance_status')!='not_evaluated'for p in result['persons']):raise ValueError('Person policy fields changed')
        source_raw=self._read_artifact(self._art(owner,source,'source.png'))
        source_frame=decode_image(source_raw,'image/png')
        if source_frame.digest!=source or hashlib.sha256(source_raw).hexdigest()!=binding['canonical_png_sha256']or binding['carry_sha256']!=self.carry_sha:raise ValueError('Preserved source changed')
        c=self._connect_ro()
        try:rows=c.execute('SELECT ordinal,model,state,request_sha,response_sha,cost FROM calls WHERE owner=? AND source=? ORDER BY ordinal',(owner,source)).fetchall()
        finally:c.close()
        if len(rows)!=len(result['persons'])+1 or rows[0][0]!=0:raise ValueError('Call association incomplete')
        if [r[0]for r in rows]!=list(range(len(rows))):raise ValueError('Call ordering changed')
        for ordinal,model,state,request_sha,response_sha,cost in rows:
            request_raw=self._read_artifact(self._art(owner,source,str(ordinal)+'-request.json'))
            body=json.loads(request_raw)
            if digest(body)!=request_sha or body.get('model')!=model:raise ValueError('Request artifact changed')
            if not self._has_artifact(self._art(owner,source,str(ordinal)+'-reply.bin'))or hashlib.sha256(self._read_artifact(self._art(owner,source,str(ordinal)+'-reply.bin'))).hexdigest()!=response_sha:raise ValueError('Private response artifact changed')
            path=_ArtifactReader(self,self._art(owner,source,str(ordinal)+'-reply.bin'))
            if state!='completed':raise ValueError('Incomplete provider stage')
            if ordinal==0:
                from .ppe import wire_completed
                sam=wire_completed(path.read())
                expected=build_sam_image_request(source_raw,'image/png','person');expected['store']=False
                text=''.join(c['text']for item in sam.get('output',[])for c in item.get('content',[])if c.get('type')=='output_text')
                def reparse():return asyncio.run(parse_sam_image_text(text,Frame(source_frame.width,source_frame.height,source),wire_completed=True))
                with concurrent.futures.ThreadPoolExecutor(max_workers=1)as pool:parsed=pool.submit(reparse).result()
                geometry=[{'id':str(o['object_id']),'box_half_open':list(o['box_half_open']),'mask':encode_mask(o['mask'],list(o['box_half_open']),[source_frame.width,source_frame.height])}for o in parsed['objects']]
                if geometry!=binding['persons']or geometry!=[{k:p[k]for k in ('id','box_half_open','mask')}for p in result['persons']]:raise ValueError('Original SAM geometry association changed')
                if body!=expected or model!='sam-3.1'or D(cost)!=D('.0025')or sam.get('id')!=result['sam_response_id']or request_sha!=result['sam_request_sha256']:raise ValueError('SAM response association changed')
            else:
                person=result['persons'][ordinal-1];ppe=parse_reply(path.read());decode_mask(person['mask'])
                with Image.open(io.BytesIO(source_raw))as im:
                    crop=im.crop(person['box_half_open']);out=io.BytesIO();crop.save(out,'PNG');crop_raw=out.getvalue()
                if hashlib.sha256(crop_raw).hexdigest()!=person['crop_png_sha256']or body!=canonical_body(crop_raw)or model!='muse-spark-1.3'or D(cost)!=D(ppe['listed_cost_usd']):raise ValueError('Original crop/request/cost association changed')
                if person['mask']['box_half_open_pixels']!=person['box_half_open']or person['mask']['source_frame_size']!=[result['image']['width'],result['image']['height']]:raise ValueError('Mask source placement changed')
                if ppe!=person['provider_observation']or request_sha!=person['ppe_request_sha256']or ppe['response_id']!=person['ppe_response_id']or(person['helmet'],person['vest'])!=(ppe['observation']['helmet'],ppe['observation']['vest']):raise ValueError('PPE response association changed')
        self.carry()

    @staticmethod
    def private_bytes(path):
        from .platform_private import path_private as _pp
        if not path.is_file()or not _pp(path,follow=False):raise ValueError('Private preserved artifact required')
        return path.read_bytes()
    @staticmethod
    def save_private(path,raw):
        from .platform_private import open_private as _op
        fd=_op(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
        with os.fdopen(fd,'wb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
    def register_derivative(self,png,source):
        pixel=decode_image(png,'image/png').digest
        c=self.connect()
        try:
            c.execute('CREATE TABLE IF NOT EXISTS display_derivatives(pixel_digest TEXT PRIMARY KEY,source_digest TEXT NOT NULL)')
            c.execute('INSERT OR IGNORE INTO display_derivatives VALUES(?,?)',(pixel,source));c.commit()
        finally:c.close()
    def reject_derivative(self,pixel):
        if self._dsn is None and not self.path.is_file():return
        c=self._connect_ro()
        try:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='display_derivatives'").fetchone()and c.execute('SELECT 1 FROM display_derivatives WHERE pixel_digest=?',(pixel,)).fetchone():raise ValueError('Display derivative cannot be provider source')
        finally:c.close()
    def prepare(self,raw,mime,zones):
        if zones!=[]:raise ValueError('Fresh preparation supports no-zone policy only')
        frame=decode_image(raw,mime)
        self.reject_derivative(frame.digest)
        if frame.orientation!=1:raise AuditError(422,'IMAGE_ORIENTATION_UNSUPPORTED','Normalize EXIF orientation before uploading (rotate the photo upright first); no claim or call was created.')
        spec=self.approval_store.lookup(frame.digest,[frame.width,frame.height])
        if spec['provenance']['scope']!=self.execution_scope:raise ValueError('Approval scope differs from execution scope')
        carry=self.carry()
        if frame.digest in carry['blocked_source_digests']:raise ValueError('Previously paid source blocked throughout lifecycle')

        png=pixel_only_png(raw,mime);sam=build_sam_image_request(png,'image/png','person');sam['store']=False
        binding={'source_digest':frame.digest,'frame_size':[frame.width,frame.height],'canonical_png_sha256':hashlib.sha256(png).hexdigest(),'sam_request_sha256':digest(sam),'sam_model':'sam-3.1','ppe_model':'muse-spark-1.3','ppe_max_output_tokens':512,'max_people':2,'source_approval_reference':spec['rights_reference'],'source_approval_snapshot':json.loads(json.dumps(spec)),'carry_sha256':self.carry_sha,'zones':[],'zone_policy':'not_applied','export_allowed':False}
        return frame,png,sam,binding
    def claim(self,binding,owner='',key_fp=None):
        # Returns True (claimed), False (this owner already has a row), or
        # 'uncertain' (ANY account holds this digest as running_uncertain: the
        # journal-GLOBAL no-retry hold - nothing is served, nothing dispatched).
        carry=self.carry();source=binding['source_digest'];self.validate_binding(binding);c=self.connect()
        try:
            c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT state FROM jobs WHERE owner=? AND source=?',(owner,source)).fetchone()
            if r:return False
            if c.execute("SELECT 1 FROM jobs WHERE source=? AND state='running_uncertain'",(source,)).fetchone():return 'uncertain'
            if c.execute('SELECT count(*) FROM jobs').fetchone()[0]>=64:raise ValueError('Journal bound reached; retain tombstones')
            rows=c.execute('SELECT owner,source,state,reserved,cost FROM jobs').fetchall()
            for oldowner,oldsource,state,reserved,cost in rows:
                self.read(oldsource,oldowner) #Verify persisted completed cost/artifacts and all retained holds before new spend.
            from .recheck_journal import reservation_total
            from .recheck_execution import verify_retained_rechecks
            verify_retained_rechecks(self,c)
            from .ppe_segmentation import total as mask_total,verify_retained
            verify_retained(self,c)
            from .explanation_execution import total as explanation_total,verify_retained as verify_explanations
            verify_explanations(self,c)
            from .stopped_source import original_total
            booked=D(carry['conservative_booked_usd'])+original_total(self,c)+reservation_total(c)+mask_total(c)+explanation_total(c)
            if self.cap_enforcement and booked+RESERVE>aggregate_cap(carry):raise ValueError('Same aggregate cap unavailable; held reservations count in full')
            # cap_enforcement=False (explicit install config, owner demo direction): booking above continues
            # unchanged - every reservation and cost is still recorded in full; only the refusal is skipped. The
            # spending stop is then the provider-side key limit, not this app-level gate.
            c.execute('INSERT INTO jobs(owner,source,state,reserved,cost,binding,result,result_sha,started,key_fp) VALUES(?,?,?,?,?,?,?,?,?,?)',(owner,source,'running_uncertain',str(RESERVE),'0',json.dumps(binding),None,None,time.time(),key_fp));c.commit();return True
        finally:c.close()
    def attempted_count(self,source,owner=''):
        c=self._connect_ro()
        try:return c.execute('SELECT count(*) FROM calls WHERE owner=? AND source=?',(owner,source)).fetchone()[0]
        finally:c.close()
    def call_cost(self,source,owner=''):
        c=self._connect_ro()
        try:return sum((D(r[0])for r in c.execute('SELECT cost FROM calls WHERE owner=? AND source=?',(owner,source))),D('0'))
        finally:c.close()
    def dispatch(self,source,ordinal,body,owner=''):
        source_raw=self._read_artifact(self._art(owner,source,'source.png'))
        c=self.connect()
        try:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT state,binding FROM jobs WHERE owner=? AND source=?',(owner,source)).fetchone()
            if not row or row[0]!='running_uncertain':raise ValueError('Active paid claim required')
            from .stopped_source import retained
            if retained(c,source)is not None:raise ValueError('Settled stopped source is terminal; no dispatch')
            binding=json.loads(row[1])
            self.validate_binding(binding)
            spec=self.approval_store.lookup(source,binding['frame_size'])
            if spec!=binding['source_approval_snapshot']or spec.get('provider_upload_approved')is not True:raise ValueError('Source approval changed before dispatch')
            if ordinal<0 or ordinal>2 or c.execute('SELECT count(*) FROM calls WHERE owner=? AND source=?',(owner,source)).fetchone()[0]!=ordinal:raise ValueError('Exact next stage required')
            if ordinal>0 and c.execute('SELECT count(*) FROM calls WHERE owner=? AND source=? AND state=?',(owner,source,'completed')).fetchone()[0]!=ordinal:raise ValueError('Previous stage incomplete')
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
            c.execute('INSERT INTO calls VALUES(?,?,?,?,?,?,?,?)',(owner,source,ordinal,body['model'],'attempted_uncertain',digest(body),None,'0'));c.commit()
        finally:c.close()
        #No automatic retries. Preserve exact request before dispatch.
        self._write_artifact(self._art(owner,source,str(ordinal)+'-request.json'),json.dumps(body,sort_keys=True,separators=(',',':')).encode())
        reply=self.transport(body)
        if not isinstance(reply,bytes)or len(reply)>4_000_000:raise ValueError('Bounded provider bytes required')
        self._write_artifact(self._art(owner,source,str(ordinal)+'-reply.bin'),reply)
        c=self.connect()
        try:c.execute('UPDATE calls SET state=?,response_sha=? WHERE owner=? AND source=? AND ordinal=?',('received_unparsed',hashlib.sha256(reply).hexdigest(),owner,source,ordinal));c.commit()
        finally:c.close()
        return reply
    def record_cost(self,source,ordinal,cost,owner=''):
        c=self.connect()
        try:
            c.execute('BEGIN IMMEDIATE');c.execute('UPDATE calls SET state=?,cost=? WHERE owner=? AND source=? AND ordinal=?',('completed',str(cost),owner,source,ordinal))
            total=sum(D(r[0])for r in c.execute('SELECT cost FROM calls WHERE owner=? AND source=?',(owner,source)))
            c.execute('UPDATE jobs SET cost=? WHERE owner=? AND source=?',(str(total),owner,source));c.commit()
        finally:c.close()
    def held_uncertain(self,source):
        # Journal-GLOBAL no-retry hold view: if ANY account holds this digest as
        # running_uncertain, every account re-presenting the same bytes sees the
        # hold. No result is served and no dispatch happens, so no charge or
        # observation crosses accounts; the view carries no per-account data.
        if self._dsn is None and not self.path.is_file():return None
        c=self._connect_ro()
        try:r=c.execute("SELECT owner FROM jobs WHERE source=? AND state='running_uncertain'",(source,)).fetchone()
        except sqlite3.OperationalError as e:
            if 'no such table' in str(e):return None
            raise
        finally:c.close()
        return self.read(source,r[0])if r else None

    async def run(self,raw,mime,zones,owner=''):
        frame,png,sam,binding=self.prepare(raw,mime,zones);source=frame.digest
        owner=owner or ''
        existing=self.read(source,owner)
        if existing:return existing
        held=self.held_uncertain(source)
        if held:return held
        if self.transport is disabled_transport:raise LiveTransportDisabled('Fresh pipeline dispatch disabled; no claim created')
        from .transport import current_key_fingerprint
        claimed=self.claim(binding,owner=owner,key_fp=current_key_fingerprint())
        if claimed=='uncertain':
            return self.held_uncertain(source)
        if not claimed:
            existing=self.read(source,owner)
            if existing:return existing
            raise ValueError('Fresh journal claim lost; no automatic retry')
        try:
            from .ppe import wire_completed
            self._write_artifact(self._art(owner,source,'source.png'),png)
            reply=self.dispatch(source,0,sam,owner);response=wire_completed(reply)
            if response.get('model')!='sam-3.1'or not response.get('id')or response.get('usage',{}).get('images_processed')!=1:raise ValueError('Unique expected SAM completion required')
            self.record_cost(source,0,D('.0025'),owner)
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
            try:c.execute('UPDATE jobs SET binding=? WHERE owner=? AND source=?',(json.dumps(binding),owner,source));c.commit()
            finally:c.close()
            persons=[]
            gates=_single_upload_eligibility(objects)
            with Image.open(io.BytesIO(png))as im:
                for index,obj in enumerate(objects,1):
                    box=list(obj['box_half_open']);mask=encode_mask(obj['mask'],box,[frame.width,frame.height]);crop=im.crop(box);buffer=io.BytesIO();crop.save(buffer,'PNG');crop_bytes=buffer.getvalue();body=canonical_body(crop_bytes)
                    reply=self.dispatch(source,index,body,owner);ppe=parse_reply(reply);self.record_cost(source,index,D(ppe['listed_cost_usd']),owner)
                    persons.append({'id':str(obj['object_id']),'box_half_open':box,'mask':mask,'crop_png_sha256':hashlib.sha256(crop_bytes).hexdigest(),'ppe_request_sha256':digest(body),'ppe_response_id':ppe['response_id'],'helmet':ppe['observation']['helmet'],'vest':ppe['observation']['vest'],'ppe_assessed':True,'provider_observation':ppe,'crop_eligibility':gates[str(obj['object_id'])],'contact_status':'not_checked','compliance_status':'not_evaluated'})
            result={'source':'fresh_upload_provider_review','image':{'pixel_digest':source,'width':frame.width,'height':frame.height},'persons':persons,'zones':[],'zone_status':'not_checked','compliance_status':'not_evaluated','findings':None,'review_status':'needs_human_review','sam_response_id':response['id'],'sam_request_sha256':binding['sam_request_sha256'],'privacy_review_status':'not_validated','evidence_export_allowed':False,'provider_proof':'local_request_response_consistency_not_provider_signature'}
            self.carry();c=self.connect()
            try:c.execute('UPDATE jobs SET state=?,result=?,result_sha=? WHERE owner=? AND source=? AND state=?',('completed',json.dumps(result),digest(result),owner,source,'running_uncertain'));c.commit()
            finally:c.close()
        except Exception:
            #No raw exception/provider/user content surfaced. Job remains held, no retry or partial observations.
            return {**self.read(source,owner),'provider_calls_this_request':None,'notice':'Attempt uncertain; call/debit count needs reconciliation, full reservation retained. No partial result or automatic retry.'}
        return {**self.read(source,owner),'provider_calls_this_request':len(persons)+1}
