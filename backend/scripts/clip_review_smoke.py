"""Generated MP4 + synthetic model transport only. No external model requests.
Uses existing tested orchestration to produce a two-sample reviewed private PDF.
"""
import sys,tempfile,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from pytest import MonkeyPatch
from test_fresh_upload_pipeline import setup
from test_clip_audit import clip_parser,approve_frames
from test_clip_preparation import LIMITS
from test_clip_review import reviewed_clip
from fresh_review.pipeline import digest
from fastapi.testclient import TestClient
from app import create_app
from test_fresh_upload_routes import OWNER
import asyncio

def run(destination):
 destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory()as directory,MonkeyPatch.context()as patch:
  root=Path(directory);p,raw,frame,calls=setup(root,patch)
  job=asyncio.run(p.run(raw,'image/png',[]))
  client=TestClient(create_app(fresh_service=p,fresh_token='generated_clip_private_token_123456789012345'),headers={'X-Vigilens-Display-Session':OWNER,'X-Vigilens-Local-Access':'generated_clip_private_token_123456789012345'})
  file=root/'generated.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=64x48:r=5:d=2','-c:v','mpeg4','-y',str(file)],check=True,timeout=5)
  material=(p,raw,frame,calls,client,job)
  p,c,calls,summary,payload,x=reviewed_clip(material,file.read_bytes(),patch)
  path='/fresh-private-clip-report/'+summary['private_clip_review_id']
  report=c.post(path,json=payload);pdf=c.post(path+'/pdf-preview',json=payload)
  assert report.status_code==pdf.status_code==200
  (destination/'sampled-clip-preview.pdf').write_bytes(pdf.content)
  (destination/'sampled-clip-report.json').write_text(json.dumps(report.json(),indent=2))
  proof={'input':'generated_MP4','models':'synthetic_replies','external_provider_calls':0,'sample_count':2,'repeated_pixels_one_image_job':True,'new_simulated_calls_for_clip':2,'report':200,'pdf':200,'export':False,'tracking':False,'exact_presentation_timestamps':False}
  (destination/'proof.json').write_text(json.dumps(proof,indent=2));print(json.dumps(proof,indent=2))
if __name__=='__main__':run(sys.argv[1])
