"""Actual backend factory over loopback HTTP. Generated pixels, synthetic replies,
real official SAM parser. No provider/network calls except local socket to self.
"""
import io,json,os,secrets,subprocess,sys,tempfile,time,urllib.request,urllib.error,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PIL import Image
from core import decode_image
TEXT="<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|><|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
def generated():
 b=io.BytesIO();Image.new('RGB',(320,334),'#223344').save(b,'PNG');return b.getvalue()
def synthetic_app():
 from app import create_app
 from fresh_review.pipeline import FreshPipeline
 from fresh_review.approvals import ApprovalStore
 d=Path(os.environ['VIGILENS_SYNTHETIC_SMOKE_DIR']);raw=generated();f=decode_image(raw,'image/png')
 spec={f.digest:{'size':[320,334],'rights_reference':'generated-only','provider_upload_approved':True,'provenance':{'owner_instruction_reference':'synthetic-no-owner-grant','rights_review_reference':'generated-only','reviewed_at':'synthetic','reviewer':'smoke-harness','scope':'synthetic_local_qualification'}}}
 approval=json.dumps({'version':1,'approvals':spec}).encode();a=d/'approval.json';a.write_bytes(approval);a.chmod(0o600)
 carry=json.dumps({'blocked_source_digests':[],'provider_calls_total':0,'conservative_booked_usd':'0','aggregate_cap_usd':'5'}).encode();c=d/'carry.json';c.write_bytes(carry);c.chmod(0o600)
 def transport(body):
  if body['model']=='sam-3.1':return ('data: '+json.dumps({'type':'response.completed','response':{'id':'synthetic-sam','model':'sam-3.1','status':'completed','usage':{'images_processed':1},'output':[{'type':'message','content':[{'type':'output_text','text':TEXT}]}]}})+'\n\n').encode()
  return json.dumps({'id':'synthetic-ppe','model':'muse-spark-1.3','status':'completed','usage':{'input_tokens':100,'output_tokens':50},'output':[{'type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':json.dumps({'helmet':'unknown','vest':'unknown','helmet_evidence':'generated pixels','vest_evidence':'generated pixels'})}]}]}).encode()
 service=FreshPipeline(d/'fresh.sqlite',approval_store=ApprovalStore(a,hashlib.sha256(approval).hexdigest()),carry_path=c,carry_sha=hashlib.sha256(carry).hexdigest(),execution_scope='synthetic_local_qualification',transport=transport)
 return create_app(fresh_service=service)
def smoke(port=18477):
 token=secrets.token_urlsafe(36);owner=secrets.token_urlsafe(32);raw=generated();source=decode_image(raw,'image/png').digest
 with tempfile.TemporaryDirectory(prefix='vigilens-fresh-synthetic-')as d:
  env=dict(os.environ,PYTHONPATH=str(ROOT)+os.pathsep+str(Path(__file__).resolve().parent),VIGILENS_LOCAL_ACCESS_TOKEN=token,VIGILENS_SYNTHETIC_SMOKE_DIR=d)
  process=subprocess.Popen([sys.executable,'-m','uvicorn','fresh_socket_smoke:synthetic_app','--factory','--host','127.0.0.1','--port',str(port),'--no-access-log'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  base='http://127.0.0.1:'+str(port)
  def req(path,body=None,content=None,auth=True):
   headers={'X-Vigilens-Display-Session':owner}
   if auth:headers['X-Vigilens-Local-Access']=token
   if content:headers['Content-Type']=content
   try:
    with urllib.request.urlopen(urllib.request.Request(base+path,data=body,headers=headers),timeout=10)as r:return r.status,r.read()
   except urllib.error.HTTPError as e:return e.code,e.read()
  def multipart(fields):
   boundary='generated-smoke-boundary';body=b''
   for key,value in fields.items():body+=f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
   body+=f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="generated.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+raw+f'\r\n--{boundary}--\r\n'.encode()
   return body,'multipart/form-data; boundary='+boundary
  def postjson(path,payload):return req(path,json.dumps(payload).encode(),'application/json')
  try:
   for _ in range(100):
    try:
     if req('/health')[0]==200:break
    except OSError:pass
    if process.poll()is not None:raise RuntimeError('Local smoke process exited')
    time.sleep(.05)
   else:raise RuntimeError('Local smoke startup timeout')
   assert req('/fresh-review/'+source,auth=False)[0]==403
   body,content=multipart({'zones':'[]'});status,value=req('/fresh-review-upload',body,content);job=json.loads(value)
   assert status==200 and job['state']=='completed'and job['provider_calls_this_request']==2
   status,repeat=req('/fresh-review-upload',body,content);assert json.loads(repeat)['provider_calls_this_request']==0
   _,contract=req('/fresh-review/'+source+'/integration-contract');contract=json.loads(contract)
   review={'source_digest':source,'frame_size':[320,334],'regions':[{'person_id':'0','box':[212,229,218,235]}],'reviewer_label':'synthetic operator','redaction_method':'opaque'}
   body,content=multipart({'review':json.dumps(review)});status,value=req('/fresh-review/'+source+'/private-display',body,content);display=json.loads(value);assert status==200
   assert req(display['preview_url'])[0]==200
   ack={k:display[k]for k in ['source_digest','output_sha256','regions_digest']};ack.update(frame_size=[320,334],**{k:True for k in ['foreground_checked','background_checked','reflections_checked','derivative_checked']})
   assert postjson('/private-display/'+display['session_id']+'/review',ack)[0]==200
   from fresh_review.masks import decode_mask
   mask=decode_mask(job['result']['persons'][0]['mask']);box=job['result']['persons'][0]['box_half_open']
   point=next(((x,y)for y in range(mask.height-1,-1,-1)for x in range(mask.width)if mask.getpixel((x,y))))
   contact={'person_id':'0','point':[(box[0]+point[0]+.1)/320,(box[1]+point[1]+.1)/334],'exact_source_confirmed':True,'boots_ground_visible':True,'reviewer_label':'synthetic claim not actual boots'}
   assert postjson('/fresh-review/'+source+'/contact',contact)[0]==200
   payload={'assessment_id':contract['assessment_id'],'source_digest':source,'output_sha256':display['output_sha256'],'regions_digest':display['regions_digest'],'persons':{'0':{'exact_source_confirmed':True,'face_coverage_checked':True,'head_evidence_visible':True,'torso_evidence_visible':False}}}
   status,value=postjson('/fresh-private-report/'+display['session_id'],payload);report=json.loads(value);assert status==200 and report['evidence_export_allowed']is False and report['compliance_decision']is False and report['contact_review_status']=='operator_claims_only'
   return {'actual_backend_factory':'app.create_app','transport':'actual_loopback_HTTP','input':'generated_pixels','parser':'official_meta_sam_parser','inference':'synthetic_replies_not_real_model','external_provider_calls':0,'simulated_dispatches':2,'repeat_dispatches':0,'unauthorized_status':403,'private_report_status':status,'helmet':report['persons'][0]['report_display_helmet'],'vest':report['persons'][0]['report_display_vest'],'export':False}
  finally:
   process.terminate()
   try:process.communicate(timeout=5)
   except subprocess.TimeoutExpired:process.kill();process.communicate(timeout=5)
if __name__=='__main__':print(json.dumps(smoke(),indent=2))
