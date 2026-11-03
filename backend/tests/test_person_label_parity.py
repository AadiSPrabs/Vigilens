import json,os,pytest
from fresh_review.frontend_audit import to_frontend_audit
from fresh_review.overlays import person_display_labels
from test_frontend_audit_route import person

FIXTURE=os.path.join(os.path.dirname(__file__),'..','..','frontend','app','vigilens','components','__tests__','fixtures','person-label-parity.json')

def real_sized(*ps):
 return {'image':{'width':1600,'height':1000,'pixel_digest':'ab'*32},'persons':list(ps)}

def build():
 r=real_sized(person('7',(300,220,640,900)),person('3',(940,220,1260,920)),person('12',(100,500,260,980)))
 audit=to_frontend_audit(r,audit_id='fresh:x',job_state='completed',source_digest='ab'*32)
 return {'audit_persons':[{'id':p['id'],'polygon':p['polygon']}for p in audit['persons']],'backend_labels':person_display_labels(r)}

def test_frontend_audit_persons_and_backend_labels_agree_and_match_committed_fixture():
 got=build()
 assert [p['id']for p in got['audit_persons']]==['7','3','12'] # same order as the stored result
 assert [got['backend_labels'][i]['label']for i in('7','3','12')]==['Person 1','Person 2','Person 3']
 if os.environ.get('VIGILENS_WRITE_PARITY_FIXTURE'):json.dump(got,open(FIXTURE,'w'),indent=1,sort_keys=True)
 assert json.load(open(FIXTURE))==json.loads(json.dumps(got)),'fixture drifted: frontend personMappings test reads it'

def test_unusable_or_duplicate_people_fail_closed_on_both_sides():
 dup=real_sized(person('3',(10,10,50,90)),person('3',(60,10,90,90)))
 outside=real_sized(person('4',(10,10,50,90)),person('5',(1500,10,1700,90)))
 for r in(dup,outside):
  with pytest.raises(ValueError):to_frontend_audit(r,audit_id='fresh:x',job_state='completed',source_digest='ab'*32)
 assert all(not v['mapped']for v in person_display_labels(dup).values())
 assert person_display_labels(outside)['4']['mapped']is True and person_display_labels(outside)['5']['mapped']is False
