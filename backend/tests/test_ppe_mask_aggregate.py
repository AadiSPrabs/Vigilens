import asyncio,io
import pytest
from PIL import Image
from test_fresh_upload_routes import material
from test_ppe_segmentation import helper
from test_fresh_upload_pipeline import add_approval
from fresh_review.recheck_journal import RecheckJournal
from core import decode_image

def test_original_new_reservation_revalidates_mask_artifacts(material,monkeypatch):
 p,raw,frame,calls,c,job=material;h,identity=helper(p,frame,monkeypatch)
 assert asyncio.run(h.run(identity))['state']=='completed'
 h.artifact(identity,1,'reply.bin').write_bytes(b'changed')
 out=io.BytesIO();Image.new('RGB',(80,80),'green').save(out,'PNG');f=decode_image(out.getvalue(),'image/png')
 add_approval(p,f.digest,{'size':[80,80],'rights_reference':'synthetic','provider_upload_approved':True})
 _,_,_,binding=p.prepare(out.getvalue(),'image/png',[])
 with pytest.raises(ValueError):p.claim(binding)
 with pytest.raises(ValueError):RecheckJournal(p).reserve(frame.digest,'0',max_attempts=1,authority_reference='synthetic')
 assert len(calls)==4

def test_mask_reservation_and_recheck_use_shared_cap(material,monkeypatch):
 p,raw,frame,calls,c,job=material;h,identity=helper(p,frame,monkeypatch)
 RecheckJournal(p).reserve(frame.digest,'0',max_attempts=1,authority_reference='synthetic')
 # Reserve a new original full hold, then another source cannot be reserved.
 for color in ('green','red'):
  out=io.BytesIO();Image.new('RGB',(80,80),color).save(out,'PNG');f=decode_image(out.getvalue(),'image/png')
  add_approval(p,f.digest,{'size':[80,80],'rights_reference':'synthetic','provider_upload_approved':True})
  _,_,_,binding=p.prepare(out.getvalue(),'image/png',[])
  if color=='green':assert p.claim(binding)
  else:
   with pytest.raises(ValueError,match='aggregate'):p.claim(binding)
 assert len(calls)==2
