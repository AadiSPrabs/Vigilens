"""Executable examples of the review/preview/report/zone endpoint contract on SYNTHETIC data (stub transport, no network).
Run with WRITE_CONTRACT_SAMPLES=1 to rewrite frontend-contract-samples/workflow_contract.json."""
import json,os,hashlib,pathlib
from test_fresh_upload_routes import material,prepare,acknowledge,report,OWNER
from test_fresh_zones import submit,contact,ZONE
from fresh_review.pipeline import digest
OTHER='other_browser_nonce_123456789012345'
def step(log,name,r,note=''):
    ct=r.headers.get('content-type','')
    body=r.json() if ct.startswith('application/json') else {'_non_json':ct,'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest()[:16],'pdf':r.content[:5]==b'%PDF-','x-vigilens-export-allowed':r.headers.get('x-vigilens-export-allowed')}
    log.append({'step':name,'status':r.status_code,'note':note,'body_keys':sorted(body)if isinstance(body,dict)else None,'error_or_detail':(body.get('detail')if isinstance(body,dict)else None)})
    return r
def test_workflow_contract(material):
    p,raw,frame,calls,c,job=material;n=len(calls);log=[];H={'X-Vigilens-Display-Session':OWNER};O={'X-Vigilens-Display-Session':OTHER}
    # preview preparation (opaque redaction of declared regions; no source bytes retained, derivative only)
    x=prepare(c,raw,frame);step(log,'POST /fresh-review/{source}/private-display',type('R',(),{'status_code':200,'headers':{'content-type':'application/json'},'json':lambda s:x,'content':b''})(),'owner-session bound; returns session_id, source_digest, output_sha256, regions_digest, frame_size')
    sid=x['session_id']
    img=step(log,'GET /private-display/{sid}/image',c.get('/private-display/'+sid+'/image',headers=H));assert img.status_code==200
    assert step(log,'GET image, another session',c.get('/private-display/'+sid+'/image',headers=O)).status_code in(403,404,409)
    bad={'source_digest':x['source_digest'],'output_sha256':x['output_sha256'],'regions_digest':x['regions_digest'],'frame_size':[80,80],'foreground_checked':True,'background_checked':True,'reflections_checked':True,'derivative_checked':False}
    assert step(log,'POST /private-display/{sid}/review, one check false',c.post('/private-display/'+sid+'/review',json=bad,headers=H)).status_code==409
    assert step(log,'POST /fresh-private-report/{sid} before acknowledgement',report(c,x,job)).status_code==409
    ack={**bad,'derivative_checked':True};assert step(log,'POST /private-display/{sid}/review, all checks',c.post('/private-display/'+sid+'/review',json=ack,headers=H)).status_code==200
    # per-person human review, report
    assert step(log,'POST /fresh-review/{source}/contact (point inside frame)',contact(c,frame)).status_code==200
    for name,pt in (('point outside frame',[1.5,.5]),('non-numeric point',['a','b'])):
        r=c.post('/fresh-review/'+frame.digest+'/contact',json={'person_id':'0','point':pt,'exact_source_confirmed':True,'boots_ground_visible':True,'reviewer_label':'synthetic operator'});step(log,'POST contact, '+name,r);assert r.status_code in(409,422)
    r=step(log,'POST /fresh-private-report/{sid}',report(c,x,job));assert r.status_code==200 and r.json().get('evidence_export_allowed') is False
    ident='fresh:'+x['source_digest']+':'+digest(job['result'])
    wrong={'assessment_id':ident,'source_digest':'0'*64,'output_sha256':x['output_sha256'],'regions_digest':x['regions_digest'],'persons':{'0':{'exact_source_confirmed':True,'face_coverage_checked':True,'head_evidence_visible':True,'torso_evidence_visible':True}}}
    assert step(log,'POST report, wrong source digest',c.post('/fresh-private-report/'+sid,json=wrong,headers=H)).status_code==409
    assert step(log,'POST report, another session',c.post('/fresh-private-report/'+sid,json={**wrong,'source_digest':x['source_digest']},headers=O)).status_code in(403,404,409)
    pl={**wrong,'source_digest':x['source_digest']}
    pdf=step(log,'POST /fresh-private-report/{sid}/pdf-preview',c.post('/fresh-private-report/'+sid+'/pdf-preview',json=pl,headers=H));assert pdf.status_code==200 and pdf.content[:5]==b'%PDF-' and pdf.headers['x-vigilens-export-allowed']=='false'
    dl=step(log,'POST /fresh-private-report/{sid}/private-download',c.post('/fresh-private-report/'+sid+'/private-download',json=pl,headers=H),'export remains disabled unless a separate explicit mode is configured')
    # zones: separate, result-hash bound
    z=step(log,'POST /fresh-review/{source}/zone-review (polygon)',submit(c,frame,job));assert z.status_code==200
    step(log,'GET zone-review',c.get('/fresh-review/'+frame.digest+'/zone-review'))
    bads={'out of bounds':[{**ZONE,'points':[{'x':-.1,'y':.2},{'x':.4,'y':.2},{'x':.4,'y':.9}]}],'two points':[{**ZONE,'points':[{'x':.1,'y':.2},{'x':.4,'y':.2}]}],'self-intersecting':[{**ZONE,'points':[{'x':.1,'y':.1},{'x':.9,'y':.9},{'x':.9,'y':.1},{'x':.1,'y':.9}]}]}
    for name,zs in bads.items():
        r=submit(c,frame,job,zs);step(log,'POST zone-review, '+name,r);assert r.status_code in(409,422)
    r=c.post('/fresh-review/'+frame.digest+'/zone-review',json={'source_digest':frame.digest,'result_sha256':'0'*64,'zones':[ZONE],'reviewer_label':'synthetic reviewer'});step(log,'POST zone-review, stale result hash',r);assert r.status_code==409
    step(log,'GET zone-review, another session',c.get('/fresh-review/'+frame.digest+'/zone-review',headers=O))
    assert step(log,'DELETE /private-display/{sid}',c.delete('/private-display/'+sid,headers=H)).status_code==200
    assert step(log,'GET image after delete',c.get('/private-display/'+sid+'/image',headers=H)).status_code in(403,404,409)
    assert len(calls)==n   # nothing in this workflow calls the provider
    if os.environ.get('WRITE_CONTRACT_SAMPLES')=='1':
        pathlib.Path(__file__).parent.parent.joinpath('frontend-contract-samples','workflow_contract.json').write_text(json.dumps({'synthetic':True,'provider_calls':0,'steps':log},indent=1,sort_keys=True))
    print(json.dumps(log,indent=0)[:6000])
