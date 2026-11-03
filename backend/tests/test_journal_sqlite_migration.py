import asyncio,io,json,sqlite3
import pytest
from PIL import Image
from core import decode_image
from test_fresh_upload_pipeline import carry,approval_store,add_approval
from fresh_review.wide_scene import WideScenePipeline,WideLimits
from fresh_test_helpers import response

# Regression tests for the sqlite journal migration: a legacy source-only-PK
# journal must migrate atomically (all-or-nothing), a half-migrated state left
# by the old implicit-transaction flow must be repaired, and the no-repeat
# record of old paid rows must survive migration, failure and restart.

LEGACY_JOBS="CREATE TABLE jobs(source TEXT PRIMARY KEY,state TEXT,reserved TEXT,cost TEXT,binding TEXT,result TEXT,result_sha TEXT,started REAL,key_fp TEXT)"
LEGACY_CALLS="CREATE TABLE calls(source TEXT,ordinal INTEGER,model TEXT,state TEXT,request_sha TEXT,response_sha TEXT,cost TEXT,PRIMARY KEY(source,ordinal))"

def make(tmp_path,monkeypatch):
 import fresh_review.wide_scene as m
 im=Image.new('RGB',(1000,600),'#223344');b=io.BytesIO();im.save(b,'PNG');raw=b.getvalue();f=decode_image(raw,'image/png')
 objects=[]
 for i in range(12):
  x=20+(i%6)*150;y=20+(i//6)*260;w,h=(10,15)if i==10 else(70,180)
  if i==11:x,y=30,30
  objects.append({'object_id':str(i),'box_half_open':[x,y,x+w,y+h],'mask':Image.new('L',(w,h),255)})
 async def parse(*a,**k):return {'objects':objects}
 monkeypatch.setattr(m,'parse_sam_image_text',parse)
 def transport(body):
  if body['model']=='sam-3.1':return b'data: {"type":"response.completed","response":{"model":"sam-3.1","id":"synthetic-wide-SAM","status":"completed","usage":{"images_processed":1},"output":[]}}\n\n'
  return response('unknown','absent')
 spec={f.digest:{'size':[1000,600],'rights_reference':'generated-wide-scene','provider_upload_approved':True,'wide_scene':{'selected_person_ids':['1','2'],'authority_reference':'synthetic-only'}}}
 p=WideScenePipeline(tmp_path/'wide.sqlite',**carry(tmp_path),execution_scope='synthetic_local_qualification',approval_store=approval_store(tmp_path,spec),transport=transport,wide_limits=WideLimits())
 return p,raw,f

def binding_of(p,raw):
 return p.prepare(raw,'image/png',[])[3]

def leftovers(c):
 return [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE name LIKE '%_prev' OR name LIKE '%_staging'")]

def legacy_db(tmp_path,p,raw,f):
 # A pre-ownership-era journal: one REALLY completed paid job (result, calls and
 # artifact sidecars all present, so retained-hold verification can pass),
 # transplanted into the legacy source-only primary key schema.
 out=asyncio.run(p.run(raw,'image/png',[]));assert out['state']=='completed'
 path=tmp_path/'wide.sqlite';c=sqlite3.connect(path)
 rows_j=c.execute('SELECT source,state,reserved,cost,binding,result,result_sha,started,key_fp FROM jobs').fetchall()
 rows_c=c.execute('SELECT source,ordinal,model,state,request_sha,response_sha,cost FROM calls').fetchall()
 c.close();path.unlink()
 c=sqlite3.connect(path);c.execute(LEGACY_JOBS);c.execute(LEGACY_CALLS)
 c.executemany("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)",rows_j)
 c.executemany("INSERT INTO calls VALUES(?,?,?,?,?,?,?)",rows_c)
 c.commit();c.close();path.chmod(0o600);return path

def test_legacy_journal_migrates_atomically_preserving_paid_no_repeat(tmp_path,monkeypatch):
 p,raw,f=make(tmp_path,monkeypatch);path=legacy_db(tmp_path,p,raw,f)
 # First connect migrates; the paid legacy row's source must never re-claim.
 assert p.claim(binding_of(p,raw)) is False
 c=sqlite3.connect(path)
 got=c.execute("SELECT owner,state FROM jobs WHERE source=?",(f.digest,)).fetchone();assert got==('','completed')
 assert c.execute("SELECT count(*) FROM calls WHERE owner='' AND source=?",(f.digest,)).fetchone()[0]==3
 assert leftovers(c)==[];c.close()
 # A brand-new source claims cleanly on the migrated journal (no nested BEGIN).
 im=Image.new('RGB',(1000,600),'#445566');b=io.BytesIO();im.save(b,'PNG');raw2=b.getvalue();f2=decode_image(raw2,'image/png')
 add_approval(p,f2.digest,{'size':[1000,600],'rights_reference':'generated-wide-scene','provider_upload_approved':True,'wide_scene':{'selected_person_ids':['1','2'],'authority_reference':'synthetic-only'}})
 assert p.claim(binding_of(p,raw2)) is True
 # Restart: a fresh pipeline over the same journal still refuses the old paid source.
 p3,_,_=make(tmp_path,monkeypatch)
 assert p3.claim(binding_of(p3,raw)) is False

def test_half_migrated_stranded_rows_are_repaired(tmp_path,monkeypatch):
 p,raw,f=make(tmp_path,monkeypatch);path=legacy_db(tmp_path,p,raw,f)
 # The exact stranded state the old flow produced: empty composite tables
 # beside legacy rows stuck in jobs_prev/calls_prev.
 c=sqlite3.connect(path)
 c.execute('ALTER TABLE jobs RENAME TO jobs_prev');c.execute('ALTER TABLE calls RENAME TO calls_prev')
 c.execute(WideScenePipeline._JOBS_DDL);c.execute(WideScenePipeline._CALLS_DDL)
 c.commit();c.close()
 assert p.claim(binding_of(p,raw)) is False
 c=sqlite3.connect(path)
 assert c.execute("SELECT count(*) FROM jobs WHERE owner='' AND source=?",(f.digest,)).fetchone()[0]==1
 assert c.execute("SELECT count(*) FROM calls WHERE owner='' AND source=?",(f.digest,)).fetchone()[0]==3
 assert leftovers(c)==[];c.close()

def test_migration_copy_failure_rolls_back_preserving_history(tmp_path,monkeypatch):
 p,raw,f=make(tmp_path,monkeypatch);path=legacy_db(tmp_path,p,raw,f)
 c=sqlite3.connect(path)
 c.execute('ALTER TABLE jobs RENAME TO jobs_prev');c.execute('ALTER TABLE calls RENAME TO calls_prev')
 c.execute(WideScenePipeline._JOBS_DDL);c.execute(WideScenePipeline._CALLS_DDL)
 c.execute("CREATE TRIGGER failcopy BEFORE INSERT ON jobs BEGIN SELECT RAISE(ABORT,'injected copy failure'); END")
 c.commit();c.close()
 with pytest.raises(Exception):p.connect()
 c=sqlite3.connect(path)
 # Nothing lost: stranded rows intact, composite jobs still empty, both tables present.
 assert c.execute("SELECT count(*) FROM jobs_prev").fetchone()[0]==1
 assert c.execute("SELECT count(*) FROM jobs").fetchone()[0]==0
 c.execute('DROP TRIGGER failcopy');c.commit();c.close()
 # After the obstacle clears, the repair completes with every row preserved.
 assert p.claim(binding_of(p,raw)) is False
 c=sqlite3.connect(path)
 assert c.execute("SELECT count(*) FROM jobs WHERE owner=''").fetchone()[0]==1
 assert leftovers(c)==[];c.close()

def stranded_state(tmp_path,p,raw,f):
 # The exact half-migrated state the old flow produced: empty composite tables
 # beside legacy rows stuck in jobs_prev/calls_prev. Returns an OPEN connection
 # for test-specific setup; caller commits and closes.
 path=legacy_db(tmp_path,p,raw,f)
 c=sqlite3.connect(path)
 c.execute('ALTER TABLE jobs RENAME TO jobs_prev');c.execute('ALTER TABLE calls RENAME TO calls_prev')
 c.execute(WideScenePipeline._JOBS_DDL);c.execute(WideScenePipeline._CALLS_DDL)
 return path,c

def test_conflicting_jobs_history_refuses_loudly_preserving_both(tmp_path,monkeypatch):
 p,raw,f=make(tmp_path,monkeypatch);path,c=stranded_state(tmp_path,p,raw,f)
 # Reachable post-stranding: the source was re-claimed and RE-PAID, so the composite
 # table holds a DIFFERENT paid row for the same key. Merging must never pick a winner.
 old=c.execute("SELECT source,state,reserved,cost,binding,result,result_sha,started,key_fp FROM jobs_prev").fetchone()
 c.execute("INSERT INTO jobs VALUES('',?,?,?,?,?,?,?,?,?)",(old[0],old[1],old[2],'9.99',old[4],'"different-result"',old[6],old[7],old[8]))
 c.execute("INSERT INTO calls SELECT '',source,ordinal,model,state,request_sha,response_sha,cost FROM calls_prev")
 c.commit();c.close()
 with pytest.raises(ValueError) as e:p.connect()
 assert 'Conflicting journal history' in str(e.value)
 c=sqlite3.connect(path)
 assert c.execute("SELECT cost,result FROM jobs WHERE owner='' AND source=?",(f.digest,)).fetchone()==('9.99','"different-result"')
 assert c.execute("SELECT cost FROM jobs_prev WHERE source=?",(f.digest,)).fetchone()[0]==old[3]
 names=sorted(r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'"));c.close()
 assert 'jobs' in names and 'jobs_prev' in names and 'calls_prev' in names

def test_conflicting_calls_history_refuses_loudly_preserving_both(tmp_path,monkeypatch):
 p,raw,f=make(tmp_path,monkeypatch);path,c=stranded_state(tmp_path,p,raw,f)
 c.execute("INSERT INTO jobs SELECT '',source,state,reserved,cost,binding,result,result_sha,started,key_fp FROM jobs_prev")
 rows=c.execute("SELECT source,ordinal,model,state,request_sha,response_sha,cost FROM calls_prev").fetchall()
 c.executemany("INSERT INTO calls VALUES('',?,?,?,?,?,?,?)",[(r[0],r[1],r[2],r[3],r[4],'DIFFERENT' if r[1]==0 else r[5],r[6]) for r in rows])
 c.commit();c.close()
 with pytest.raises(ValueError) as e:p.connect()
 assert 'Conflicting journal history' in str(e.value)
 c=sqlite3.connect(path)
 assert c.execute("SELECT count(*) FROM calls_prev").fetchone()[0]==len(rows)
 names=sorted(r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'"));c.close()
 assert 'calls' in names and 'calls_prev' in names and 'jobs_prev' in names

def test_identical_duplicate_history_tolerated(tmp_path,monkeypatch):
 p,raw,f=make(tmp_path,monkeypatch);path,c=stranded_state(tmp_path,p,raw,f)
 c.execute("INSERT INTO jobs SELECT '',source,state,reserved,cost,binding,result,result_sha,started,key_fp FROM jobs_prev")
 c.execute("INSERT INTO calls SELECT '',source,ordinal,model,state,request_sha,response_sha,cost FROM calls_prev")
 c.commit();c.close()
 assert p.claim(binding_of(p,raw)) is False
 c=sqlite3.connect(path)
 assert c.execute("SELECT count(*) FROM jobs WHERE owner='' AND source=?",(f.digest,)).fetchone()[0]==1
 assert c.execute("SELECT count(*) FROM calls WHERE owner='' AND source=?",(f.digest,)).fetchone()[0]==3
 assert leftovers(c)==[];c.close()

def test_staging_table_present_refuses_loudly_preserving_everything(tmp_path,monkeypatch):
 p,raw,f=make(tmp_path,monkeypatch);path=legacy_db(tmp_path,p,raw,f)
 c=sqlite3.connect(path);c.execute(LEGACY_JOBS.replace('jobs','jobs_staging'));c.commit();c.close()
 with pytest.raises(ValueError) as e:p.connect()
 assert 'staging table already present' in str(e.value)
 c=sqlite3.connect(path)
 sql=c.execute("SELECT sql FROM sqlite_master WHERE name='jobs' AND type='table'").fetchone()[0]
 assert 'PRIMARYKEY(owner,source)' not in sql.replace(' ','')
 assert c.execute("SELECT count(*) FROM jobs WHERE source=?",(f.digest,)).fetchone()[0]==1
 assert c.execute("SELECT count(*) FROM jobs_staging").fetchone()[0]==0;c.close()
