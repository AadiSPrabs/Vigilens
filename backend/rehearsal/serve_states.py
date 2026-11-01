import os
OUT=os.environ.get('REHEARSAL_OUT','.');os.makedirs(OUT,exist_ok=True)  # set REHEARSAL_UI_DIST to the built bundle (built with VITE_API_BASE_URL=http://localhost:8000)
"""OFFLINE rehearsal stub backend (test harness only): serves synthetic results through the REAL to_frontend_audit mapper so the real UI
can be inspected on clean-crop present/present, partial, and zero-person states. Image colour selects the state. No provider, no storage."""
import os,sys,io,pathlib,secrets,threading,time
sys.path[:0]=[str(pathlib.Path(__file__).parent.parent),str(pathlib.Path(__file__).parent.parent/'tests')]
TOKEN=secrets.token_urlsafe(40)
import httpx,uvicorn
from fastapi import FastAPI,Request,HTTPException
from PIL import Image
from fresh_review.frontend_audit import to_frontend_audit
from local_ui_proxy import create_proxy
def person(pid,box,eligible):
    return {'id':pid,'box_half_open':list(box),'helmet':'present','vest':'present','ppe_assessed':True,'provider_observation':{'observation':{'helmet':'present','vest':'present','helmet_evidence':'x','vest_evidence':'y'}},'crop_eligibility':{'eligible_for_selected_crop_call':eligible,'review_reasons':[]if eligible else['crop_too_small']}}
app=FastAPI()
@app.post('/fresh-review-audit')
async def a(request:Request):
    if request.headers.get('x-vigilens-local-access')!=TOKEN:raise HTTPException(403)
    from starlette.datastructures import UploadFile
    form=await request.form();im=Image.open(io.BytesIO(await form['image'].read())).convert('RGB');c=im.getpixel((0,0))
    W,H=im.size;wide=None;state='completed'
    if c[1]>150 and c[0]<80:ps=[person('0',(5,5,30,60),True),person('1',(40,5,70,60),True)]          # green: all clean-crop present/present
    elif c[0]>150 and c[1]>150:ps=[person('0',(5,5,30,60),True),person('1',(40,5,70,60),False)];state='partial_completed';wide={'coverage':'partial_example','ppe_withheld_unverified_geometry':True}  # yellow: partial
    elif c[2]>150 and c[0]<80:ps=[]                                                              # blue: zero people
    else:raise HTTPException(409)
    try:return to_frontend_audit({'image':{'width':W,'height':H,'pixel_digest':secrets.token_hex(32)},'persons':ps,**({'wide_scene':wide}if wide else{})},audit_id='fresh:rehearsal',job_state=state)
    except ValueError:raise HTTPException(409)
NONCE='rehearsal-launch-nonce-'+'x'*30
threading.Thread(target=lambda:uvicorn.run(app,host='127.0.0.1',port=8001,log_level='warning'),daemon=True).start();time.sleep(1.5)
uvicorn.run(create_proxy(httpx.AsyncClient(base_url='http://127.0.0.1:8001',timeout=30),TOKEN,launch_nonce=NONCE,ui_dir=os.environ['REHEARSAL_UI_DIST'],port=8000),host='127.0.0.1',port=8000,log_level='warning')
