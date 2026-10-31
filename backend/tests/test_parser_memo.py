import asyncio
import pytest
import sam_parser as m
from pipeline import Frame
from core import AuditError
from test_sam_parser import TEXT
from test_fresh_upload_routes import material

def test_exact_parse_memo_copies_masks_and_checks_completion(monkeypatch):
 m._PARSE_MEMO.clear()
 f=Frame(320,334,'memo')
 original=asyncio.run(m.parse_sam_image_text(TEXT,f,wire_completed=True))
 pixels=original['objects'][0]['mask'].tobytes()
 original['objects'][0]['mask'].paste(0,(0,0,original['objects'][0]['mask'].width,original['objects'][0]['mask'].height))
 original['objects'].clear()
 def invalid(*args,**kwargs):raise AssertionError('Exact successful parse should be memoized')
 monkeypatch.setattr(m,'_parse_sam_image_text',invalid)
 retained=asyncio.run(m.parse_sam_image_text(TEXT,f,wire_completed=True))
 assert retained['objects'][0]['mask'].tobytes()==pixels
 with pytest.raises(AssertionError):asyncio.run(m.parse_sam_image_text(TEXT,f,wire_completed=False))
 with pytest.raises(AssertionError):asyncio.run(m.parse_sam_image_text(TEXT+'changed',f,wire_completed=True))
 with pytest.raises(AssertionError):asyncio.run(m.parse_sam_image_text(TEXT,Frame(320,334,'different'),wire_completed=True))

def test_memo_bound():
 m._PARSE_MEMO.clear()
 for i in range(7):asyncio.run(m.parse_sam_image_text('',Frame(320,334,str(i)),wire_completed=True))
 assert len(m._PARSE_MEMO)==4

def test_warm_parse_never_skips_current_private_reply_tamper(material):
 p,raw,frame,calls,c,job=material
 p.read(frame.digest)
 reply=p.path.parent/('fresh-'+frame.digest+'-0-reply.bin')
 original=reply.read_bytes();reply.write_bytes(original+b'changed')
 with pytest.raises(ValueError):p.read(frame.digest)
 assert len(calls)==2
