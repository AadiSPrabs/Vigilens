import io,hashlib
from PIL import Image
from test_fresh_upload_routes import material,prepare,acknowledge,OWNER
from test_fresh_zones import submit
from fresh_review.overlays import render_overlay

def test_private_overlay_requires_review_owner_and_exact_session(material):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);path='/fresh-private-report/'+x['session_id']+'/overlay'
 assert c.get(path).status_code==409
 acknowledge(c,x);assert submit(c,frame,job).status_code==200
 r=c.get(path);assert r.status_code==200 and r.headers['x-vigilens-export-allowed']=='false'
 assert hashlib.sha256(r.content).hexdigest()==r.headers['x-vigilens-overlay-sha256']
 im=Image.open(io.BytesIO(r.content));assert im.size==(80,80)and not im.info
 assert im.getpixel((2,2))==(0,0,0) # redaction never undone
 assert c.get(path,headers={'X-Vigilens-Display-Session':'56'*32}).status_code==404
 assert c.get(path,headers={'X-Vigilens-Local-Access':'wrong'}).status_code==403
 assert c.get(path).content==r.content and len(calls)==2
 c.app.state.fresh_display.SESSIONS.clear()
 assert c.get(path).status_code==404

def test_overlay_preserves_non_boundary_pixels_and_mask_frame(material):
 import copy,pytest
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame)
 png=c.get(x['preview_url']).content
 out,sha=render_overlay(png,job['result'],[])
 before=Image.open(io.BytesIO(png));after=Image.open(io.BytesIO(out))
 assert after.size==before.size and after.getpixel((79,79))==before.getpixel((79,79))
 assert after.getpixel((79,2))==before.getpixel((79,2))
 changed=copy.deepcopy(job['result']);changed['image']['width']=81
 with pytest.raises(ValueError):render_overlay(png,changed,[])

def test_overlay_cannot_paint_over_privacy_regions(material):
 p,raw,frame,calls,c,job=material
 from fresh_review.masks import encode_mask
 mask=Image.new('L',(8,8),255)
 result={'image':{'width':80,'height':80},'persons':[{'id':'p','box_half_open':[1,1,9,9],'mask':encode_mask(mask,[1,1,9,9],[80,80])}]}
 treated=Image.new('RGB',(80,80),'blue');buf=io.BytesIO();treated.save(buf,'PNG')
 out,_=render_overlay(buf.getvalue(),result,[],[{'box':[0,0,10,10]}])
 im=Image.open(io.BytesIO(out))
 assert im.crop((0,0,10,10)).tobytes()==treated.crop((0,0,10,10)).tobytes()

def test_overlay_result_tamper_invalidates_session(material):
 import sqlite3
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x)
 db=sqlite3.connect(p.path);db.execute("UPDATE jobs SET result_sha='changed'");db.commit();db.close()
 assert c.get('/fresh-private-report/'+x['session_id']+'/overlay').status_code==409
 assert x['session_id']not in c.app.state.fresh_display.SESSIONS


def test_overlay_pixels_are_persistent_derivative_tombstone(material):
 import pytest
 from core import decode_image
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x)
 out=c.get('/fresh-private-report/'+x['session_id']+'/overlay')
 pixel=decode_image(out.content,'image/png').digest
 with pytest.raises(ValueError):p.reject_derivative(pixel)
 assert len(calls)==2

def test_person_display_labels_match_stage_rule_and_tag_overlay():
 from fresh_review.overlays import person_display_labels
 from fresh_review.masks import encode_mask
 def person(pid,box):
  return {'id':pid,'box_half_open':box,'mask':encode_mask(Image.new('L',(box[2]-box[0],box[3]-box[1]),255),box,[80,80])}
 result={'image':{'width':80,'height':80},'persons':[person('7',[10,20,20,40]),person('3',[40,20,50,40]),person('3',[60,20,70,40]),{'id':'9','box_half_open':[0,0,0,5],'mask':None}]}
 labels=person_display_labels(result)
 assert labels['7']=={'mapped':True,'label':'Person 1','text':'Person 1 (backend id 7)'}
 assert labels['3']['mapped'] is False and labels['3']['text']=='Unmapped person (backend id 3)'
 assert labels['9']['mapped'] is False
 treated=Image.new('RGB',(80,80),'blue');buf=io.BytesIO();treated.save(buf,'PNG')
 out,_=render_overlay(buf.getvalue(),{'image':result['image'],'persons':result['persons'][:1]},[])
 im=Image.open(io.BytesIO(out)).convert('RGB')
 assert any(im.getpixel((x,y))==(20,20,20) for x in range(10,40) for y in range(0,20)),'tag drawn above mapped person'

def test_person_tag_stays_off_the_head_even_at_the_frame_top():
 from fresh_review.masks import encode_mask
 box=[10,0,40,50];mask=Image.new('L',(30,50),255)
 result={'image':{'width':80,'height':80},'persons':[{'id':'p','box_half_open':box,'mask':encode_mask(mask,box,[80,80])}]}
 treated=Image.new('RGB',(80,80),'blue');buf=io.BytesIO();treated.save(buf,'PNG')
 out,_=render_overlay(buf.getvalue(),result,[])
 im=Image.open(io.BytesIO(out)).convert('RGB')
 # No room above the box: the dark tag goes below the feet (rows >= 51), never inside the box rows near the head.
 assert not any(im.getpixel((x,y))==(20,20,20) for x in range(10,40) for y in range(0,50))
 assert any(im.getpixel((x,y))==(20,20,20) for x in range(10,60) for y in range(51,80))
