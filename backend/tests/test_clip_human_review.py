import json,hashlib,socket,pytest
from pathlib import Path
from PIL import Image
import io as _io
from test_clip_preparation import clip,LIMITS
from test_clip_audit import clip_parser,approve_frames
from test_fresh_upload_routes import material,OWNER
from fresh_review.clip_review import ClipReviewStore
from clip_human_review import *

def prepare(material,clip,monkeypatch):
 p,raw,frame,calls,c,job=material;clip_parser(monkeypatch);frames=approve_frames(p,clip);p.trusted_clip_limits=LIMITS
 out=c.post('/fresh-review-clip-upload',files={'clip':('g.mp4',clip,'video/mp4')},data={'offsets':'[0,0.8]'});assert out.status_code==200
 cid=out.json()['private_clip_review_id'];man=ClipReviewStore(p).read(cid,OWNER)
 pngs={f['pixel_digest']:f['png']for f in frames};return p,c,calls,cid,man,pngs
def script(answers):
 it=iter(answers)
 def inp(q):
  try:return next(it)
  except StopIteration:raise EOFError
 return Console(inp=inp,out=lambda *a:None)
def good(head='y',torso='y',boxes=('0 0 0 40 24',)):
 a=list(boxes)+['']
 a+=['y']*4+['y','y',head,torso]
 return a
OK=lambda path:True
def run(tmp,c,p,cid,man,pngs,answers,viewer=OK,manual=False):
 return run_review(c,p,cid,man,lambda fr:pngs[fr['pixel_digest']],tmp,script(answers),label='tester typed label',viewer=viewer,manual_view=manual)

def test_happy_path_typed_answers_only_pdf_and_record_no_new_calls_no_network(material,clip,monkeypatch,tmp_path):
 p,c,calls,cid,man,pngs=prepare(material,clip,monkeypatch);n=len(calls)
 def deny(*a,**k):raise AssertionError('network used')
 monkeypatch.setattr(socket.socket,'connect',deny)
 rec=run(tmp_path,c,p,cid,man,pngs,good())
 assert rec['complete']and len(calls)==n and (tmp_path/'combined-private-clip-preview.pdf').read_bytes()[:5]==b'%PDF-'
 doc=json.loads((tmp_path/'combined-report.json').read_text());assert doc['evidence_export_allowed']is False and doc['privacy_review_status']=='not_validated' and doc['provider_calls_this_request']==0
 saved=json.loads((tmp_path/'review-record-TYPED-BY-HUMAN.json').read_text());assert saved['frames'][0]['persons']['0']['head_evidence_visible']is True and saved['frames'][1]['same_pixels_as']==0 and saved['evidence_export_allowed']is False

def test_viewer_failure_aborts_and_manual_view_needs_exact_typed_word(material,clip,monkeypatch,tmp_path):
 p,c,calls,cid,man,pngs=prepare(material,clip,monkeypatch)
 with pytest.raises(ReviewAbort,match='viewer'):run(tmp_path/'a',c,p,cid,man,pngs,good(),viewer=lambda x:False)
 assert not (tmp_path/'a'/'combined-private-clip-preview.pdf').exists() and json.loads((tmp_path/'a'/'review-record-TYPED-BY-HUMAN.json').read_text())['complete']is False
 with pytest.raises(ReviewAbort,match='viewing not confirmed'):run(tmp_path/'b',c,p,cid,man,pngs,['nope'],viewer=lambda x:False,manual=True)
 rec=run(tmp_path/'c',c,p,cid,man,pngs,['viewed']+good()[:1]+[''] and ['viewed','0 0 0 40 24','']+['viewed']+['y']*4+['y','y','y','y'],viewer=lambda x:False,manual=True);assert rec['complete']

def test_no_implicit_yes_closed_input_and_bad_answers_abort(material,clip,monkeypatch,tmp_path):
 p,c,calls,cid,man,pngs=prepare(material,clip,monkeypatch)
 io=script(['','yes','Y','maybe','1']);io.out=lambda *a:None
 with pytest.raises(ReviewAbort):io.yn('q')
 full=good()
 for cut in range(len(full)):
  with pytest.raises(ReviewAbort):run(tmp_path/f'e{cut}',c,p,cid,man,pngs,full[:cut])
  assert not (tmp_path/f'e{cut}'/'combined-private-clip-preview.pdf').exists()
 with pytest.raises(ReviewAbort):run(tmp_path/'n',c,p,cid,man,pngs,['0 0 0 40 24','']+['y','y','y','n']*3)
 assert not (tmp_path/'n'/'combined-private-clip-preview.pdf').exists()

def test_zero_boxes_and_bad_boxes_never_accepted(material,clip,monkeypatch,tmp_path):
 p,c,calls,cid,man,pngs=prepare(material,clip,monkeypatch)
 with pytest.raises(ReviewAbort,match='at least one'):run(tmp_path,c,p,cid,man,pngs,[''])
 rec=run(tmp_path/'x',c,p,cid,man,pngs,['0 5 5 1 1','0 -1 0 4 4','0 0 0 9999 9999','0 0 0 40 24','']+['y']*4+['y']*4)
 assert rec['frames'][0]['regions']==[{'person_id':'0','box':[0,0,40,24]}]

def test_changed_frame_result_and_derivative_bindings_rejected(material,clip,monkeypatch,tmp_path):
 p,c,calls,cid,man,pngs=prepare(material,clip,monkeypatch)
 other=_io.BytesIO();Image.new('RGB',(64,48),'red').save(other,'PNG')
 with pytest.raises(ReviewAbort):run_review(c,p,cid,man,lambda fr:other.getvalue(),tmp_path/'f',script(['0 0 0 40 24','']*5),label='t',viewer=OK)
 job=p.read(man['frames'][0]['pixel_digest']);bad=json.loads(json.dumps(job));bad['result']['persons'][0]['helmet']='present'
 with monkeypatch.context() as m:
  m.setattr(p,'read',lambda s:bad)
  with pytest.raises(ReviewAbort,match='saved result changed'):run(tmp_path/'r',c,p,cid,man,pngs,good())
 src=man['frames'][0]['pixel_digest'];png=pngs[src]
 body=json.dumps({'source_digest':src,'frame_size':[64,48],'regions':[{'person_id':'0','box':[0,0,40,24]}],'reviewer_label':'t'})
 x=c.post(f'/fresh-review/{src}/private-display',files={'image':('f.png',png,'image/png')},data={'review':body}).json()
 ack={'source_digest':x['source_digest'],'output_sha256':'0'*64,'regions_digest':x['regions_digest'],'frame_size':[64,48]}|{k:True for k in FRAME_KEYS}
 assert c.post(f"/private-display/{x['session_id']}/review",json=ack).status_code==409

def test_partial_head_torso_stays_honest_unknown_and_boxes_render_exactly(material,clip,monkeypatch,tmp_path):
 p,c,calls,cid,man,pngs=prepare(material,clip,monkeypatch)
 rec=run(tmp_path,c,p,cid,man,pngs,good(head='n',torso='n'))
 doc=json.loads((tmp_path/'combined-report.json').read_text());pr=doc['frames'][0]['report']['persons'][0]
 assert pr['report_display_helmet']=='unknown' and pr['provider_vest_observation']=='absent' and pr['report_display_vest']=='unknown'
 assert pr['report_display_helmet']!='present'
 src=man['frames'][0]['pixel_digest'];prev=Image.open(tmp_path/'preview-frame0.png').convert('RGB');orig=Image.open(_io.BytesIO(pngs[src])).convert('RGB')
 assert all(prev.getpixel((x,y))==(0,0,0)for x in(0,39)for y in(0,23)) and prev.getpixel((40,10))==orig.getpixel((40,10)) and prev.getpixel((10,24))==orig.getpixel((10,24))

def test_guide_image_marks_people_and_grid(tmp_path):
 im=_io.BytesIO();Image.new('RGB',(200,150),'black').save(im,'PNG')
 guide_image(im.getvalue(),[{'id':'0','box_half_open':[10,10,50,60]}],tmp_path/'g.png');g=Image.open(tmp_path/'g.png').convert('RGB')
 assert g.getpixel((10,30))==(0,255,255) and g.getpixel((64,100))==(255,255,0)

def test_setup_workdir_copies_only_and_uses_no_real_key(tmp_path):
 b=tmp_path/'b';(b/'data').mkdir(parents=True);(b/'proof-v4').mkdir()
 (b/'data'/'journal.sqlite').write_bytes(b'j');(b/'proof-v4'/'p').write_bytes(b'p')
 for n in('approvals.json','carry-v4-candidate.json','manifest-v4-candidate.json'):(b/n).write_text('{}')
 h=lambda:{str(f):hashlib.sha256(f.read_bytes()).hexdigest()for f in sorted(b.rglob('*'))if f.is_file()};before=h()
 rt,token=setup_workdir(b,tmp_path/'w');cfg=json.loads(rt.read_text())
 assert h()==before and cfg['journal'].startswith(str(tmp_path/'w')) and Path(cfg['key_file']).read_text()=='REVIEW-ONLY-NO-PROVIDER-CALLS'
 assert all(oct(Path(cfg[k]).stat().st_mode&0o777)=='0o600'for k in('key_file','access_token_file','carry_path','approval_path')) and oct((tmp_path/'w'/'data').stat().st_mode&0o777)=='0o700'
