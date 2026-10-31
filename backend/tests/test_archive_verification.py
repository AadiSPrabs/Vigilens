import copy,io
from PIL import Image
from fastapi.testclient import TestClient
from app import create_app
from fresh_review.archive_verification import ArchiveVerification
from fresh_review.masks import encode_mask
from fresh_review.pipeline import digest
from core import decode_image
from test_fresh_upload_routes import prepare,acknowledge,OWNER

def test_archive_existing_http_report_never_fakes_fresh_job(tmp_path):
 b=io.BytesIO();Image.new('RGB',(80,80),'blue').save(b,'PNG');raw=b.getvalue();frame=decode_image(raw,'image/png')
 result={'image':{'pixel_digest':frame.digest,'width':80,'height':80},'persons':[{'id':'0','box_half_open':[0,0,20,60],'mask':encode_mask(Image.new('L',(20,60),255),[0,0,20,60],[80,80]),'helmet':'unknown','vest':'absent','provider_observation':{'observation':{'helmet_evidence':'generated test','vest_evidence':'generated test'}}}]}
 record={'result':result,'archive_provenance':{'kind':'generated_test_of_archive_contract','original_fresh_job_restored':False,'provider_calls_this_run':0}}
 service=ArchiveVerification(tmp_path/'operator.sqlite',lambda:copy.deepcopy(record));c=TestClient(create_app(fresh_service=service),headers={'X-Vigilens-Display-Session':OWNER})
 assert c.post('/fresh-review-upload',files={'image':('x.png',raw,'image/png')},data={'zones':'[]'}).status_code==503
 status=c.get('/fresh-review/'+frame.digest);assert status.json()['state']=='archived_verified'
 contract=c.get('/fresh-review/'+frame.digest+'/integration-contract').json();assert contract['assessment_id'].startswith('archive-review:')
 x=prepare(c,raw,frame);acknowledge(c,x)
 body={'assessment_id':contract['assessment_id'],'source_digest':frame.digest,'output_sha256':x['output_sha256'],'regions_digest':x['regions_digest'],'persons':{'0':{'exact_source_confirmed':True,'face_coverage_checked':True,'head_evidence_visible':True,'torso_evidence_visible':True}}}
 out=c.post('/fresh-private-report/'+x['session_id'],json=body);assert out.status_code==200 and out.json()['archive_provenance']==record['archive_provenance']
 assert out.json()['assessment_source']=='verified_archive_provider_review'
 assert c.post('/fresh-private-report/'+x['session_id']+'/pdf-preview',json=body).status_code==200
 conn=service.connect();assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='jobs'").fetchone();conn.close()
 record['archive_provenance']['original_fresh_job_restored']=True
 assert c.get(x['preview_url']).status_code==409
