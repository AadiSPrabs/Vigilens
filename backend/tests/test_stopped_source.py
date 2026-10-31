import asyncio,sqlite3,json
import pytest
from test_fresh_upload_pipeline import setup,add_approval
from fresh_review.stopped_source import settle,original_total
from fresh_review.pipeline import RESERVE
from decimal import Decimal

@pytest.fixture
def stopped(tmp_path,monkeypatch):
 p,raw,f,calls=setup(tmp_path,monkeypatch,people=3)
 import fresh_review.pipeline as pipeline
 import fresh_review.stopped_source as stop
 monkeypatch.setattr(stop,'parse_sam_image_text',pipeline.parse_sam_image_text)
 result=asyncio.run(p.run(raw,'image/png',[]));assert result['state']=='running_uncertain'and len(calls)==1
 return p,raw,f,calls

def test_settle_cardinality_stop_preserves_job_calls_no_result_retry(stopped):
 p,raw,f,calls=stopped;c=p.connect();before=c.execute('SELECT * FROM jobs').fetchall(),c.execute('SELECT * FROM calls').fetchall();assert original_total(p,c)==RESERVE;c.close()
 proof=settle(p,f.digest);assert proof['parsed_person_count']==3 and proof['result_published']is False
 assert settle(p,f.digest)==proof
 c=p.connect();assert original_total(p,c)==Decimal('.0025');after=c.execute('SELECT * FROM jobs').fetchall(),c.execute('SELECT * FROM calls').fetchall();assert before==after;c.close()
 read=p.read(f.digest);assert read['state']=='running_uncertain'and read['result']is None and read['retry_allowed']is False
 assert read['accounting_settlement']==proof
 assert asyncio.run(p.run(raw,'image/png',[]))['state']=='running_uncertain'and len(calls)==1
 with pytest.raises(ValueError):p.dispatch(f.digest,1,{})

@pytest.mark.parametrize('damage',['source','request','reply','row','cost','result','extraartifact','pendingcall','proof'])
def test_settlement_fails_closed_damage(stopped,damage):
 p,raw,f,calls=stopped
 if damage=='proof':settle(p,f.digest)
 c=p.connect()
 if damage in ('source','request','reply'):
  suffix={'source':'source.png','request':'0-request.json','reply':'0-reply.bin'}[damage];(p.path.parent/('fresh-'+f.digest+'-'+suffix)).write_bytes(b'changed')
 elif damage=='row':c.execute('DELETE FROM calls')
 elif damage=='cost':c.execute("UPDATE jobs SET cost='0'")
 elif damage=='result':c.execute("UPDATE jobs SET result='{}'")
 elif damage=='extraartifact':(p.path.parent/('fresh-'+f.digest+'-1-request.json')).write_text('{}')
 elif damage=='pendingcall':c.execute("UPDATE calls SET state='attempted_uncertain'")
 else:c.execute("UPDATE source_stop_settlements SET proof='{}'")
 c.commit();c.close()
 with pytest.raises(Exception):settle(p,f.digest)
 assert len(calls)==1

def test_timeout_not_settleable(tmp_path,monkeypatch):
 p,raw,f,calls=setup(tmp_path,monkeypatch,timeout=1);asyncio.run(p.run(raw,'image/png',[]))
 with pytest.raises(ValueError):settle(p,f.digest)
 assert p.read(f.digest)['accounting_settlement']is None

def test_valid_cardinality_not_settleable(tmp_path,monkeypatch):
 p,raw,f,calls=setup(tmp_path,monkeypatch,people=1);asyncio.run(p.run(raw,'image/png',[]))
 with pytest.raises(ValueError):settle(p,f.digest)

def test_settled_read_tamper_blocks_future_budget(stopped):
 import io
 from PIL import Image
 from core import decode_image
 p,raw,f,calls=stopped;settle(p,f.digest)
 b=io.BytesIO();Image.new('RGB',(80,80),'green').save(b,'PNG');new=b.getvalue();nf=decode_image(new,'image/png');add_approval(p,nf.digest,{'size':[80,80],'rights_reference':'synthetic','provider_upload_approved':True})
 (p.path.parent/('fresh-'+f.digest+'-0-reply.bin')).write_bytes(b'changed')
 _,_,_,binding=p.prepare(new,'image/png',[])
 with pytest.raises(Exception):p.claim(binding)
 assert len(calls)==1

def test_settled_cardinality_releases_only_unused_budget_not_tombstone(stopped):
 import io
 from PIL import Image
 from core import decode_image
 p,raw,f,calls=stopped;settle(p,f.digest)
 b=io.BytesIO();Image.new('RGB',(80,80),'green').save(b,'PNG');new=b.getvalue();nf=decode_image(new,'image/png');add_approval(p,nf.digest,{'size':[80,80],'rights_reference':'synthetic','provider_upload_approved':True})
 _,_,_,binding=p.prepare(new,'image/png',[]);assert p.claim(binding)
 assert p.claim(p.read(f.digest)['binding'])is False
 assert len(calls)==1

def test_official_parser_cardinality_stop_not_injected(tmp_path):
 import io,hashlib
 from PIL import Image
 from core import decode_image
 from fresh_review.pipeline import FreshPipeline
 from test_fresh_upload_pipeline import carry,approval_store
 record="<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|><|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
 text='<0f>'+''.join(str(i)+record for i in range(3));b=io.BytesIO();Image.new('RGB',(320,334),'#334455').save(b,'PNG');raw=b.getvalue();f=decode_image(raw,'image/png');calls=[]
 def transport(body):
  calls.append(body);return ('data: '+json.dumps({'type':'response.completed','response':{'model':'sam-3.1','id':'synthetic-3-doc-records','status':'completed','usage':{'images_processed':1},'output':[{'type':'message','content':[{'type':'output_text','text':text}]}]}})+'\n\n').encode()
 p=FreshPipeline(tmp_path/'fresh.sqlite',**carry(tmp_path),execution_scope='synthetic_local_qualification',approval_store=approval_store(tmp_path,{f.digest:{'size':[320,334],'rights_reference':'generated-doc-geometry','provider_upload_approved':True}}),transport=transport)
 assert asyncio.run(p.run(raw,'image/png',[]))['state']=='running_uncertain'
 assert settle(p,f.digest)['parsed_person_count']==3 and len(calls)==1
 assert p.read(f.digest)['result']is None
