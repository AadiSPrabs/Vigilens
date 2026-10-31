import json,io,pytest
from PIL import Image
from fresh_review.frontend_audit import to_frontend_audit
from test_fresh_upload_routes import material,OWNER
H={'X-Vigilens-Display-Session':OWNER}

def person(pid='0',box=(10,10,30,50),helmet='present',vest='present',eligible=None,reasons=(),assessed=True,**kw):
 p={'id':pid,'box_half_open':list(box),'helmet':helmet,'vest':vest,'ppe_assessed':assessed,**kw}
 if assessed:p['provider_observation']={'observation':{'helmet':helmet,'vest':vest,'helmet_evidence':'x','vest_evidence':'y'}}
 else:p['provider_observation']=None
 if eligible is not None:p['crop_eligibility']={'eligible_for_selected_crop_call':eligible,'review_reasons':list(reasons)}
 return p
def result(*ps,wide=None):
 r={'image':{'width':100,'height':100,'pixel_digest':'ab'*32},'persons':list(ps)}
 if wide:r['wide_scene']=wide
 return r
def view(*ps,state='completed',**kw):return to_frontend_audit(result(*ps,**kw),audit_id='fresh:x',job_state=state,source_digest='ab'*32)

def test_clean_crop_shows_reading_but_never_empty_findings_so_client_cannot_show_fully_equipped():
 x=view(person(eligible=True));pp=x['persons'][0]
 assert (pp['helmet'],pp['vest'])==('present','present') and pp['ppe_basis']['crop_basis']=='clean_crop' and pp['ppe_basis']['resolved'] is True
 assert pp['findings'] and all(f['kind']=='uncertainty' and f['severity'] is None for f in pp['findings'])
 assert any(f['rule_id']=='provider_reading_unvalidated' for f in pp['findings'])
def test_legacy_and_ineligible_and_partial_bases_never_show_present_absent():
 cases=[person(),person(eligible=False,reasons=['other_person_foreground_in_crop']),person(eligible=False,reasons=['crop_too_small']),person(eligible=False,reasons=['overlaps_unverified_geometry_person_box'],helmet='absent',vest='absent')]
 for p in cases:
  pp=view(p)['persons'][0]
  assert (pp['helmet'],pp['vest'])==('unknown','unknown') and pp['ppe_basis']['resolved'] is False and pp['ppe_basis']['target_level_outcome_permitted']=={'helmet':False,'vest':False}
 assert [view(p)['persons'][0]['ppe_basis']['crop_basis'] for p in cases]==['not_recorded_legacy','overlapped_crop','crop_rule_ineligible','overlapped_crop']
def test_unassessed_person_and_forged_basis_are_unknown_or_refused():
 pp=view(person(assessed=False,helmet='unknown',vest='unknown'))['persons'][0];assert (pp['helmet'],pp['vest'])==('unknown','unknown') and pp['ppe_basis']['provider_observation_attempted'] is False
 with pytest.raises(ValueError):view(person(crop_basis='clean_crop'))   # clean_crop without the proving eligibility record
ZN='[{"id":"z1","name":"Edge","hazard":true,"points":[{"x":0.1,"y":0.1},{"x":0.6,"y":0.1},{"x":0.6,"y":0.6}]}]'
def test_route_validates_echoes_zones_and_never_infers_membership(material):
 p,raw,frame,calls,c,job=material;n0=len(calls)
 x=c.post('/fresh-review-audit',files={'image':('x.png',raw,'image/png')},data={'zones':ZN},headers=H).json()
 assert x['zones_applied'] is False and 'unknown for every zone' in x['zones_semantics']
 assert [z['id'] for z in x['zones']]==['z1'] and len(calls)==n0
 for q in x['persons']:
  zf=[f for f in q['findings'] if f.get('zone_id')=='z1']
  assert zf and all(f['kind']=='uncertainty' and f['severity'] is None for f in zf)
 assert x.get('zone_membership_status') in(None,'unknown')
def test_route_rejects_invalid_zones_before_any_lookup(material):
 p,raw,frame,calls,c,job=material;n0=len(calls)
 for bad in ('[{"id":"z"}]','NaN','[{"id":"a","name":"n","hazard":true,"points":[{"x":0,"y":0},{"x":1,"y":1}]}]'):
  assert c.post('/fresh-review-audit',files={'image':('x.png',raw,'image/png')},data={'zones':bad},headers=H).status_code==409
 assert len(calls)==n0

def test_partial_state_coverage_counts_and_full_digests_visible():
 x=view(person(eligible=True),person('1',box=(40,10,60,50)),state='partial_completed',wide={'coverage':'partial_example','ppe_withheld_unverified_geometry':True})
 assert x['partial_result'] is True and x['job_state']=='partial_completed' and x['coverage']=='partial_example' and x['ppe_withheld_unverified_geometry'] is True
 assert x['all_detected_people_target_level_resolved'] is False and x['ppe_basis_counts']['detected_count']==2 and x['execution_state_is_not_assessment_completeness'] is True
 assert x['source_digest']=='ab'*32 and x['image']['pixel_digest']=='ab'*32 and x['image']['id']=='ab'*8
 assert view(person(eligible=True))['partial_result'] is False
def test_malformed_or_out_of_bounds_geometry_and_duplicates_refuse_whole_view():
 for box in [(30,10,10,50),(10,50,30,10),(-1,0,5,5),(0,0,101,5),(0,0,5,101),(5,5,5,9),('a',0,5,5),(0.5,0,5,5),(True,0,5,5),[1,2,3],None]:
  with pytest.raises((ValueError,TypeError)):view(person(box=box))
 with pytest.raises(ValueError):view(person('0'),person('0',box=(40,10,60,50)))
 bad=result(person());bad['image']['width']=0
 with pytest.raises(ValueError):to_frontend_audit(bad,audit_id='x')

def test_routes_gated_owner_scoped_read_only_and_governed(material):
 p,raw,frame,calls,c,job=material;n=len(calls)
 path='/fresh-review/'+frame.digest+'/frontend-audit'
 assert c.get(path,headers={**H,'X-Vigilens-Local-Access':''}).status_code==403
 assert c.get(path,headers={'X-Vigilens-Display-Session':'short'}).status_code==403
 assert c.get(path,headers=H).status_code==409   # not bound: this session has not presented the image
 assert c.post('/fresh-review-audit',files={'image':('x.png',raw,'image/png')},data={'zones':'[]'},headers=H).status_code==200
 r=c.get(path,headers=H);assert r.status_code==200;x=r.json()
 assert c.get(path,headers={'X-Vigilens-Display-Session':'B'*40}).status_code==409   # another session cannot read it by digest
 assert len(calls)==n and x['provider_calls_this_request']==0 and x['evidence_image'] is None and x['evidence_export_allowed'] is False and x['compliance_status']=='not_evaluated'
 assert x['source_digest']==frame.digest and x['audit_id'].startswith('fresh:'+frame.digest+':')
 for per in x['persons']:
  assert per['findings'] and all(f['kind']=='uncertainty' and f['severity'] is None for f in per['findings'])
  assert per['outline_basis']=='bounding_box_display_only_not_segmentation' and len(per['polygon'])==4 and all(0<=q['x']<=1 and 0<=q['y']<=1 for q in per['polygon'])
 assert '"mask"' not in json.dumps(x) and 'violation' not in [f['kind'] for per in x['persons'] for f in per['findings']]
 assert c.get('/fresh-review/'+'0'*64+'/frontend-audit',headers=H).status_code==409
 files={'image':('x.png',raw,'image/png')}
 assert c.post('/fresh-review-audit',files=files,data={'zones':'[]'},headers={**H,'X-Vigilens-Local-Access':''}).status_code==403
 assert c.post('/fresh-review-audit',files=files,data={'zones':'[]'},headers={'X-Vigilens-Display-Session':''}).status_code==403   # no owner session
 r=c.post('/fresh-review-audit',files=files,data={'zones':'[]'},headers=H);assert r.status_code==200 and len(calls)==n and r.json()['zones_applied'] is False
 buf=io.BytesIO();Image.new('RGB',(40,40),(9,8,7)).save(buf,'PNG')
 r=c.post('/fresh-review-audit',files={'image':('n.png',buf.getvalue(),'image/png')},data={'zones':'[]'},headers=H);assert r.status_code==409 and len(calls)==n

def test_default_deny_every_route_needs_token_except_health_and_audit(material):
 import re
 from fresh_review.install import OPEN_PATHS
 p,raw,frame,calls,c,job=material;n=len(calls);seen=0
 assert OPEN_PATHS=={'/health','/audit'}
 assert c.get('/openapi.json',headers={'X-Vigilens-Local-Access':''}).status_code==403   # docs/schema are gated too
 spec=c.get('/openapi.json').json()['paths']   # with the valid token
 for path,methods in spec.items():
  if path in OPEN_PATHS:continue
  concrete=re.sub(r'\{[^}]+\}','x',path)
  for m in methods:
   if m.upper() in('HEAD','OPTIONS'):continue
   resp=c.request(m.upper(),concrete,headers={'X-Vigilens-Local-Access':''});seen+=1
   assert resp.status_code==403,(m,path,resp.status_code)
 assert seen>20 and len(calls)==n
 assert c.get('/health',headers={'X-Vigilens-Local-Access':''}).status_code==200
 # positive authorised path: a valid token and session reaches past the gate on a clip route (409 = refused by binding, not 403)
 assert c.post('/fresh-private-clip-report/x',json={'frames':[]},headers=H).status_code==409


def test_audit_route_is_structurally_stored_only_never_reaches_run(material,monkeypatch):
 p,raw,frame,calls,c,job=material;n=len(calls)
 async def boom(*a,**k):raise AssertionError('SERVICE.run must not be reachable from /fresh-review-audit')
 monkeypatch.setattr(p,'run',boom)
 files={'image':('x.png',raw,'image/png')}
 assert c.post('/fresh-review-audit',files=files,data={'zones':'[]'},headers=H).status_code==200   # stored result, no run
 buf=io.BytesIO();Image.new('RGB',(40,40),(9,8,7)).save(buf,'PNG')
 r=c.post('/fresh-review-audit',files={'image':('n.png',buf.getvalue(),'image/png')},data={'zones':'[]'},headers=H)
 assert r.status_code==409 and len(calls)==n
 import pathlib,re;src=(pathlib.Path(__file__).parent.parent/'fresh_review'/'api.py').read_text();h=src[src.index("@router.post('/fresh-review-audit')"):];h=h[1:];h=h[:h.index("@router.")];h='\n'.join(l for l in h.splitlines() if not l.strip().startswith('#'))
 assert 'SERVICE.run' not in h and 'dispatch' not in h.lower() and 'transport' not in h.lower()   # no dispatch code and no switch in the handler

def test_zero_people_refused_and_missing_fields_never_default_to_verified_or_attempted():
 for r in (result(),{**result(),'persons':None}):
  with pytest.raises(ValueError):to_frontend_audit(r,audit_id='x')
 p=person(eligible=True);p.pop('ppe_assessed');p['provider_observation']=None
 q=view(p)['persons'][0];assert q['geometry_status']=='unknown_not_recorded' and q['ppe_basis']['provider_observation_attempted'] is False
 assert view(person(eligible=True,geometry_status='unverified_box_only'))['persons'][0]['geometry_status']=='unverified_box_only'
 assert view(person(eligible=True,geometry_status='bogus'))['persons'][0]['geometry_status']=='unknown_not_recorded'
 assert view(person(eligible=True))['all_detected_people_target_level_resolved'] in(True,False)
def test_partial_state_is_visible_in_every_persons_findings_because_client_ignores_partial_fields():
 x=view(person(eligible=True),person('1',box=(40,10,60,50)),state='partial_completed',wide={'coverage':'partial_example','ppe_withheld_unverified_geometry':True})
 assert all(any(f['rule_id']=='result_partial'and f['kind']=='uncertainty'and f['severity'] is None for f in q['findings'])for q in x['persons'])
 assert not any(f['rule_id']=='result_partial'for f in view(person(eligible=True))['persons'][0]['findings'])


def _fresh(tmp_path,monkeypatch,**kw):
 from test_fresh_upload_pipeline import setup
 from fastapi.testclient import TestClient
 from app import create_app
 p,raw,frame,calls=setup(tmp_path,monkeypatch,**kw)
 return p,raw,frame,calls,TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Local-Access':'','X-Vigilens-Display-Session':'o'*40})
GOV='/fresh-review-audit-governed'
def test_governed_new_image_callable_runs_only_through_governed_pipeline_and_binds_owner(tmp_path,monkeypatch):
 p,raw,frame,calls,c=_fresh(tmp_path,monkeypatch,people=2)
 files={'image':('x.png',raw,'image/png')}
 assert c.get('/fresh-review/'+frame.digest+'/frontend-audit').status_code==409 and not calls
 r=c.post(GOV,files=files,data={'zones':'[]'});assert r.status_code==200,r.text
 x=r.json();assert len(calls)==3 and x['source_digest']==frame.digest and len(x['persons'])==2 and x['zones_applied'] is False
 assert all(q['findings']for q in x['persons'])
 n=len(calls);assert c.post(GOV,files=files,data={'zones':'[]'}).status_code==200 and len(calls)==n   # repeat: stored, no new call
 assert c.get('/fresh-review/'+frame.digest+'/frontend-audit').status_code==200                      # bound by the governed call
 assert c.get('/fresh-review/'+frame.digest+'/frontend-audit',headers={'X-Vigilens-Display-Session':'B'*40}).status_code==409
def test_governed_refuses_unapproved_image_and_disabled_transport_with_zero_calls(tmp_path,monkeypatch):
 p,raw,frame,calls,c=_fresh(tmp_path,monkeypatch)
 buf=io.BytesIO();Image.new('RGB',(80,80),(9,8,7)).save(buf,'PNG')
 r=c.post(GOV,files={'image':('n.png',buf.getvalue(),'image/png')},data={'zones':'[]'});assert r.status_code==409 and not calls   # no source approval
 import fresh_review.pipeline as pm
 p.transport=pm.disabled_transport
 r=c.post(GOV,files={'image':('x.png',raw,'image/png')},data={'zones':'[]'});assert r.status_code==503 and not calls and not p.path.exists()
def test_governed_route_requires_token_and_session_format(tmp_path,monkeypatch):
 p,raw,frame,calls,c=_fresh(tmp_path,monkeypatch)
 files={'image':('x.png',raw,'image/png')}
 assert c.post(GOV,files=files,data={'zones':'[]'},headers={'X-Vigilens-Display-Session':'short'}).status_code==403 and not calls
 assert c.post(GOV,files=files,data={'zones':'[]'},headers={'X-Vigilens-Local-Access':''}).status_code==403 and not calls


@pytest.mark.parametrize('timeout',[1,2,3])
def test_governed_post_dispatch_failure_is_uncertain_and_never_redispatched(tmp_path,monkeypatch,timeout):
 """Synthetic: the transport fails after calls were consumed. The route reports an explicit uncertain outcome. Retrying with the same session, a new session or a restarted service (new pipeline over the same journal) makes no new call. The journal state is unchanged and nothing is settled."""
 from test_fresh_upload_pipeline import setup
 from fastapi.testclient import TestClient
 from app import create_app
 from fresh_review.pipeline import FreshPipeline
 p,raw,frame,calls=setup(tmp_path,monkeypatch,people=2,timeout=timeout)
 files=lambda:{'image':('x.png',raw,'image/png')}
 hdr=lambda s:{'X-Vigilens-Local-Access':'','X-Vigilens-Display-Session':s}
 c=TestClient(create_app(fresh_service=p),headers=hdr('o'*40))
 r=c.post(GOV,files=files(),data={'zones':'[]'})
 assert r.status_code==409 and r.json()['detail']['code']=='ATTEMPT_UNCERTAIN' and r.json()['detail']['provider_calls_this_request'] is None
 assert 'no call' not in r.text.lower() and len(calls)==timeout
 before=p.read(frame.digest)
 for sess in ('o'*40,'p'*40):
  for _ in range(2):
   r=TestClient(create_app(fresh_service=p),headers=hdr(sess)).post(GOV,files=files(),data={'zones':'[]'})
   assert r.status_code==409 and r.json()['detail']['code']=='ATTEMPT_UNCERTAIN'
 assert len(calls)==timeout
 # restart: a brand new pipeline object over the same private journal, with a transport that would succeed
 p2,_,_,calls2=setup(tmp_path,monkeypatch,people=2)
 r=TestClient(create_app(fresh_service=p2),headers=hdr('q'*40)).post(GOV,files=files(),data={'zones':'[]'})
 assert r.status_code==409 and r.json()['detail']['code']=='ATTEMPT_UNCERTAIN' and calls2==[]
 assert p.read(frame.digest)==before and before['state']=='running_uncertain' and before['result'] is None
 # the stored-only and frontend-audit view never present a result for it
 assert c.get('/fresh-review/'+frame.digest+'/frontend-audit').status_code==409
 assert TestClient(create_app(fresh_service=p),headers=hdr('o'*40)).post('/fresh-review-audit',files=files(),data={'zones':'[]'}).status_code==409
