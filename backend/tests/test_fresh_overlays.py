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
 assert c.get(path,headers={'X-Vigilens-Display-Session':'wrong_browser_nonce_123456789012345'}).status_code==404
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
 assert after.getpixel((2,2))==before.getpixel((2,2))==(0,0,0)
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
