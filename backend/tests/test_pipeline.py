import pytest
from dataclasses import replace
from PIL import Image
from core import AuditError
from pipeline import Frame,Observation,SegmentationBatch,OfflinePipeline,RecheckPolicy,pixel_polygon_to_normalized
from privacy import PrivacyReview,redact_synthetic
from test_backend import Z,PERSON
F=Frame(1280,720,'synthetic-test')
def obs(helmet='present',vest='present',known=True):return Observation('p',tuple(PERSON),helmet,vest,known)
def batch(*xs):return SegmentationBatch(F,tuple(xs),True)

def test_pipeline_unknown_preserved():
 x=OfflinePipeline().run(batch(obs(vest='unknown')),Z)
 assert x['persons'][0]['assessment_status']=='needs_human_review' and not x['evidence_export_allowed']

def test_incomplete_cannot_be_no_people():
 with pytest.raises(AuditError):OfflinePipeline().run(replace(batch(),completed=False),Z)
def test_empty_people_no_clearance():
 x=OfflinePipeline().run(batch(),Z);assert x['person_detection_status']=='no_people_detected' and 'not real' in x['assessment_notice']
def test_live_source_rejected():
 with pytest.raises(AuditError):OfflinePipeline().run(replace(batch(obs()),source='backend'),Z)
def test_duplicate_person_rejected():
 with pytest.raises(AuditError):OfflinePipeline().run(batch(obs(),obs()),Z)
def test_recheck_bounded_and_truthful():
 calls=[]
 def re(o,f):calls.append(1);return o
 x=OfflinePipeline(RecheckPolicy(2,1)).run(batch(obs(vest='unknown')),Z,recheck=re)
 assert len(calls)==x['recheck_attempts']==1 and x['recheck_trace'][0]['action']=='local_mock_recheck'
def test_no_recheck_trace_without_call():assert OfflinePipeline().run(batch(obs()),Z)['recheck_trace']==[]
def test_recheck_failure_keeps_unknown_no_error_leak():
 def re(o,f):raise ValueError('sensitive contents')
 x=OfflinePipeline().run(batch(obs(vest='unknown')),Z,recheck=re)
 assert x['persons'][0]['vest']=='unknown' and x['recheck_trace'][0]['outcome']=='failed' and 'sensitive' not in str(x)
def test_recheck_identity_change_rejected_as_failure():
 x=OfflinePipeline().run(batch(obs(vest='unknown')),Z,recheck=lambda o,f:replace(o,person_id='other',vest='present'))
 assert x['persons'][0]['vest']=='unknown'
def test_cancel_withholds_result():
 with pytest.raises(AuditError):OfflinePipeline().run(batch(obs()),Z,cancelled=lambda:True)
def test_unknown_zone_no_outside_violation():
 x=OfflinePipeline().run(batch(obs(helmet='absent',known=False)),Z)
 assert x['persons'][0]['zone_membership_status']=='unknown' and not any(f['severity']=='Low' for f in x['persons'][0]['findings'])
def test_crop_coordinate_conversion():
 p=pixel_polygon_to_normalized([(0,0),(100,0),(100,100),(0,100)],Frame(1000,500,'f'),crop=(200,100,100,100))
 assert p[0]=={'x':.2,'y':.2} and p[2]=={'x':.3,'y':.4}
def test_wrong_crop_rejects():
 with pytest.raises(AuditError):pixel_polygon_to_normalized([(0,0),(3,0),(3,3)],F,crop=(1200,0,1000,1))
def test_boolean_pixel_rejects():
 with pytest.raises(AuditError):pixel_polygon_to_normalized([(True,0),(3,0),(3,3)],F)

def review(**kw):return PrivacyReview(kw.get('identity',F.identity),F.width,F.height,kw.get('completed',True),kw.get('known',True))
def image():return Image.new('RGB',(F.width,F.height),'white')
def test_redaction_synthetic_not_export_clearance():
 original=image();out,status=redact_synthetic(original,F,[(20,20,40,40)],review())
 assert out.getpixel((30,30))==(0,0,0) and original.getpixel((30,30))==(255,255,255)
 assert status['evidence_status']=='unavailable' and not status['evidence_export_allowed']
@pytest.mark.parametrize('r',[review(completed=False),review(known=False),review(identity='other')])
def test_privacy_incomplete_or_wrong_frame_rejects(r):
 with pytest.raises(AuditError):redact_synthetic(image(),F,[(20,20,40,40)],r)
def test_zero_faces_never_clearance():
 with pytest.raises(AuditError):redact_synthetic(image(),F,[],review())
def test_real_privacy_source_disabled():
 with pytest.raises(AuditError):redact_synthetic(image(),F,[(20,20,40,40)],replace(review(),source='backend'))
def test_privacy_invalid_region():
 with pytest.raises(AuditError):redact_synthetic(image(),F,[(-1,0,30,40)],review())

def test_known_ppe_contradiction_requires_review():
 x=OfflinePipeline().run(batch(obs(helmet='absent',vest='unknown')),Z,recheck=lambda o,f:replace(o,helmet='present',vest='present'))
 p=x['persons'][0]
 assert p['helmet']=='unknown' and p['assessment_status']=='needs_human_review'
 assert p['contradictions']==['helmet'] and p['recheck_trace'][0]['outcome']=='contradiction'
 assert not x['evidence_export_allowed']
def test_recheck_cannot_change_contact_certainty():
 x=OfflinePipeline().run(batch(obs(vest='unknown',known=False)),Z,recheck=lambda o,f:replace(o,vest='present',contact_known=True))
 assert x['persons'][0]['zone_membership_status']=='unknown' and x['persons'][0]['vest']=='unknown'
@pytest.mark.parametrize('bad',[1,'yes',None])
def test_batch_completion_not_truthiness(bad):
 with pytest.raises(AuditError):OfflinePipeline().run(replace(batch(),completed=bad),Z)
@pytest.mark.parametrize('f',[Frame(5000,2,'f'),Frame(2,2,True),Frame(2,2,'f',True)])
def test_frame_bounded_and_strict(f):
 with pytest.raises(AuditError):OfflinePipeline().run(replace(batch(),frame=f),Z)
def test_observation_limit():
 with pytest.raises(AuditError):OfflinePipeline().run(batch(*[obs()]*257),Z)
def test_privacy_nonboolean_coverage_fails():
 with pytest.raises(AuditError):redact_synthetic(image(),F,[(20,20,40,40)],replace(review(),coverage_known='yes'))

def test_both_conflicting_observations_preserved():
 x=OfflinePipeline().run(batch(obs(helmet='absent',vest='unknown')),Z,recheck=lambda o,f:replace(o,helmet='present',vest='present'))
 p=x['persons'][0]
 assert p['original_observations']['helmet']=='absent'
 assert p['recheck_observations']==[{'attempt':1,'source':'mock','helmet':'present','vest':'present','contact_known':True}]
 assert p['helmet']=='unknown'

def test_callback_cannot_mutate_original_geometry():
 original=obs(vest='unknown');before=[dict(p) for p in original.polygon]
 def re(o,f):
  o.polygon[0]['x']=.99
  return replace(o,vest='present')
 x=OfflinePipeline().run(batch(original),Z,recheck=re)
 assert list(original.polygon)==before and x['persons'][0]['polygon']==before
 assert x['persons'][0]['vest']=='unknown' and x['recheck_trace'][0]['outcome']=='failed'

def test_provenance_order_and_source_visible():
 x=OfflinePipeline().run(batch(obs(helmet='absent',vest='unknown')),Z,recheck=lambda o,f:replace(o,helmet='present',vest='present'))
 p=x['persons'][0]
 assert p['original_observations']['attempt']==0 and p['original_observations']['source']=='mock'
 assert p['recheck_observations'][0]['attempt']==1 and p['recheck_observations'][0]['source']=='mock'
 assert x['privacy_review_status']=='not_validated'
