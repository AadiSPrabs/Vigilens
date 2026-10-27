"""Real loopback HTTP subprocess smoke, synthetic fixture only.
No external host, provider API, deployment, user data or paid action.
"""
import io,json,os,subprocess,sys,tempfile,time,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from core import decode_image

def smoke(port=18476):
 b=io.BytesIO();Image.new('RGB',(48,32),'white').save(b,'PNG');data=b.getvalue()
 zones=[];manifest={'image_digest':decode_image(data,'image/png').digest,'zones':zones,'audit':{'persons':[]}}
 with tempfile.TemporaryDirectory(prefix='vigilens-socket-') as d:
  mf=Path(d)/'manifest.json';mf.write_text(json.dumps(manifest))
  # Do not inherit a user's local token, which would make an unauthenticated smoke misleading.
  env=dict(os.environ);env.pop('VIGILENS_LOCAL_ACCESS_TOKEN',None)
  process=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1]/'run_local.py'),'--database',d+'/j.sqlite','--manifest',str(mf),'--port',str(port)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
  base='http://127.0.0.1:'+str(port)
  def get(path):
   with urllib.request.urlopen(base+path,timeout=2) as r:return r.status,json.loads(r.read())
  try:
   for _ in range(50):
    try:status,health=get('/health');break
    except Exception:
     if process.poll() is not None:raise RuntimeError('Smoke server exited before health')
     time.sleep(.1)
   else:raise RuntimeError('Smoke server health timeout')
   assert status==200 and not health['real_analysis_enabled'] and health['fixture_configured']
   boundary='synthetic-local-test-boundary'
   body=(f'--{boundary}\r\nContent-Disposition: form-data; name="zones"\r\n\r\n[]\r\n--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="synthetic.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+data+f'\r\n--{boundary}--\r\n'.encode())
   def post():
    req=urllib.request.Request(base+'/local/jobs',data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary,'Idempotency-Key':'socket-synthetic-key'})
    with urllib.request.urlopen(req,timeout=2) as r:return r.status,json.loads(r.read())['job']
   first,x=post();second,y=post();assert first==201 and second==200 and x==y
   assert x['state']=='completed' and x['result']['source']=='fixture' and not x['result']['evidence_export_allowed']
   assert get('/local/jobs/'+x['job_id'])[1]['job']==x
   return {'health_status':status,'first_status':first,'repeat_status':second,'duplicate_result_equal':True,'source':'fixture','real_analysis_enabled':False,'evidence_export_allowed':False,'notice':'ACTUAL LOOPBACK HTTP / GENERATED SYNTHETIC INPUT ONLY'}
  finally:
   process.terminate()
   try:process.communicate(timeout=5)
   except subprocess.TimeoutExpired:process.kill();process.communicate(timeout=5)
   # Terminated process only; return code -15 does not certify graceful lifespan completion.

if __name__=='__main__':print(json.dumps(smoke(),indent=2))
