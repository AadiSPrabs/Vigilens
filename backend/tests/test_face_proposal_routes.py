from test_fresh_upload_routes import material
from fresh_review.face_proposals import MODEL_SHA256

def test_face_proposal_default_refuses_and_unavailable_model_never_safe(material,tmp_path):
 p,raw,frame,calls,c,job=material;path='/fresh-review/'+frame.digest+'/face-proposals'
 assert c.post(path,files={'image':('original.png',raw,'image/png')}).status_code==409
 p.face_proposal_model_path=tmp_path/'missing.onnx'
 r=c.post(path,files={'image':('original.png',raw,'image/png')});assert r.status_code==200
 out=r.json();assert out['reason']=='model_unavailable'and out['coverage']=='unverified'and out['zero_detections_means_safe']is False and out['automatic_treatment_applied']is False and len(calls)==2

def test_face_proposal_source_and_detector_result_not_approval(material,tmp_path,monkeypatch):
 p,raw,frame,calls,c,job=material;p.face_proposal_model_path=tmp_path/'server-controlled.onnx'
 import fresh_review.face_proposals as m
 def propose(data,mime,path):return {'source_pixel_digest':frame.digest,'proposals':[{'box':[1,2,3,4]}],'coverage':'unverified','evidence_export_allowed':False,'privacy_review_status':'not_validated'}
 monkeypatch.setattr(m,'propose_faces',propose)
 out=c.post('/fresh-review/'+frame.digest+'/face-proposals',files={'image':('original.png',raw,'image/png')}).json()
 assert out['automatic_treatment_applied']is False and out['result_sha256']and len(calls)==2
 assert c.post('/fresh-review/'+frame.digest+'/face-proposals',files={'image':('wrong.png',b'wrong','image/png')}).status_code==409
 assert not c.app.state.fresh_display.SESSIONS
