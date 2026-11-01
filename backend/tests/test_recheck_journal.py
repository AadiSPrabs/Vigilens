import sqlite3,pytest
from decimal import Decimal
from test_fresh_upload_routes import material
from fresh_review.recheck_journal import RecheckJournal,reservation_total,RECHECK_RESERVE

def test_same_aggregate_recheck_reservation_dedup_no_dispatch(material):
 p,raw,frame,calls,c,job=material;j=RecheckJournal(p)
 first=j.reserve(frame.digest,'0',max_attempts=1,authority_reference='synthetic-review-authority-not-real')
 second=j.reserve(frame.digest,'0',max_attempts=1,authority_reference='synthetic-review-authority-not-real')
 assert first['new_reservation']and not second['new_reservation']and first['attempt_id']==second['attempt_id']
 assert first['dispatch_enabled']is False and first['state']=='reserved_not_dispatched'and len(calls)==2
 db=p.connect();assert reservation_total(db)==RECHECK_RESERVE;db.close()
 assert p.read(frame.digest)['result']==job['result']
 with pytest.raises(ValueError):j.reserve(frame.digest,'0',max_attempts=1,authority_reference='different')

def test_original_future_claim_includes_recheck_holds(material):
 from test_fresh_upload_pipeline import add_approval
 from core import decode_image
 from fresh_review.recheck_journal import RECHECK_RESERVE
 import io
 from PIL import Image
 p,raw,frame,calls,c,job=material;j=RecheckJournal(p)
 j.reserve(frame.digest,'0',max_attempts=1,authority_reference='synthetic-only')
 # Another valid person-bound reservation is not needed: lower remaining aggregate via synthetic carry.
 carry=p.carry();carry['conservative_booked_usd']='2'
 import json,hashlib
 p.carry_path.write_text(json.dumps(carry));p.carry_sha=hashlib.sha256(p.carry_path.read_bytes()).hexdigest()
 # Updating carry also invalidates prior result bindings, which must fail closed before spend.
 out=io.BytesIO();Image.new('RGB',(80,80),'green').save(out,'PNG');f=decode_image(out.getvalue(),'image/png')
 add_approval(p,f.digest,{'size':[80,80],'rights_reference':'synthetic','provider_upload_approved':True})
 _,_,_,binding=p.prepare(out.getvalue(),'image/png',[])
 with pytest.raises(ValueError):p.claim(binding)
 assert len(calls)==2

def test_reservation_tamper_and_invalid_bound(material):
 p,raw,frame,calls,c,job=material;j=RecheckJournal(p)
 with pytest.raises(ValueError):j.reserve(frame.digest,'0',max_attempts=1,authority_reference='')
 x=j.reserve(frame.digest,'0',max_attempts=1,authority_reference='synthetic-only')
 db=p.connect();db.execute("UPDATE recheck_attempts SET plan_sha='wrong'");db.commit();db.close()
 with pytest.raises(ValueError):j.reserve(frame.digest,'0',max_attempts=1,authority_reference='synthetic-only')


def test_future_original_claim_blocked_by_valid_recheck_hold(material):
 from test_fresh_upload_pipeline import add_approval
 from core import decode_image
 import io
 from PIL import Image
 p,raw,frame,calls,c,job=material
 RecheckJournal(p).reserve(frame.digest,'0',max_attempts=1,authority_reference='synthetic-only')
 # Original full hold (2.627012) + deliberate recheck hold (1.314756) fits,
 # but two new originals do not. First claim creates retained uncertain hold.
 for color in ('green','red'):
  out=io.BytesIO();Image.new('RGB',(80,80),color).save(out,'PNG');f=decode_image(out.getvalue(),'image/png')
  add_approval(p,f.digest,{'size':[80,80],'rights_reference':'synthetic','provider_upload_approved':True})
  _,_,_,binding=p.prepare(out.getvalue(),'image/png',[])
  if color=='green':assert p.claim(binding)
  else:
   with pytest.raises(ValueError,match='aggregate cap'):p.claim(binding)
 assert len(calls)==2
