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
def test_decisive_readings_are_observations_separate_from_the_unvalidated_notice():
 pp=view(person(eligible=True,helmet='absent',vest='present'))['persons'][0]
 by_rule={f['rule_id']:f for f in pp['findings']}
 # decisive provider readings render as observations (auto), not as uncertainty escalation
 obs=by_rule['helmet_reading']
 assert obs['kind']=='observation' and obs['severity'] is None and obs['review_state']=='auto'
 assert 'absent' in obs['message'] and 'unvalidated' in obs['message'] and 'not a verified safety judgment' in obs['message']
 # a present reading adds no per-item finding at all
 assert 'vest_reading' not in by_rule
 # the separate human-review notice always remains, as uncertainty
 notice=by_rule['provider_reading_unvalidated']
 assert notice['kind']=='uncertainty' and notice['review_state']=='needs_human_review'
 # genuinely unknown readings still escalate as uncertainty needing human review
 pp2=view(person(eligible=True,helmet='unknown',vest='unknown'))['persons'][0]
 for f in pp2['findings']:
  if f['rule_id'] in ('helmet_reading','vest_reading'):
   assert f['kind']=='uncertainty' and f['review_state']=='needs_human_review' and 'not determined' in f['message']
 # synthetic absent readings are observations too, labelled as generated test data
 import json as _json
 r=result(person(eligible=True,helmet='absent',vest='absent'));r['sam_response_id']='synthetic-sam-1'
 r['persons'][0]['ppe']={'ppe_response_id':'synthetic-ppe-1'}
 sv=to_frontend_audit(r,audit_id='fresh:x',job_state='completed',source_digest='ab'*32)
 sf=[f for f in sv['persons'][0]['findings'] if f['rule_id'] in ('helmet_reading','vest_reading')]
 assert sf and all(f['kind']=='observation' and f['review_state']=='auto' and 'Synthetic transport' in f['message'] for f in sf)
 assert any(f['rule_id']=='provider_reading_unvalidated' and f['kind']=='uncertainty' for f in sv['persons'][0]['findings'])

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
def test_route_validates_echoes_zones_and_applies_draft_matrix_on_stored_masks(material):
 p,raw,frame,calls,c,job=material;n0=len(calls)
 x=c.post('/fresh-review-audit',files={'image':('x.png',raw,'image/png')},data={'zones':ZN},headers=H).json()
 assert [z['id'] for z in x['zones']]==['z1'] and len(calls)==n0
 # the material fixture's synthetic masks touch the top frame edge -> contact not_determinable under the
 # conservative all-frame-edge rule, so membership stays unknown and the matrix does not run
 assert x['zones_applied'] is False and 'not determinable for every person' in x['zones_applied_meaning']
 for q in x['persons']:
  assert q['zone_membership_status']=='unknown' and q['ground_contact']['validity']=='not_determinable'
  assert 'mask_touches_frame_edge_top' in q['ground_contact']['reasons']
  assert any(f['rule_id']=='zone_membership_z1' and f['kind']=='uncertainty' for f in q['findings'])
  # material readings are unknown (crop-ineligible fixture): only escalation findings, never a violation/severity
  assert not any(f['kind']=='violation' for f in q['findings']) and not any(f['severity'] for f in q['findings']) and q['worst_severity'] is None
def test_membership_candidates_validity_and_boundary_rules():
 from PIL import Image
 from fresh_review.masks import encode_mask
 def masked(pid,box,bottom_rows,run_from=None,run_to=None):
  m=Image.new('L',(box[2]-box[0],box[3]-box[1]),0)
  rf,rt=(m.size[0]//3,2*m.size[0]//3) if run_from is None else (run_from,run_to)
  for y in range(bottom_rows,m.size[1]):
   for x in range(rf,rt):m.putpixel((x,y),255)
  return person(pid,box=box,helmet='absent',vest='present',eligible=True,mask=encode_mask(m,list(box),[100,100]))
 zn=[{'id':'z1','name':'Edge','hazard':True,'points':[{'x':0.1,'y':0.5},{'x':0.9,'y':0.5},{'x':0.9,'y':0.95},{'x':0.1,'y':0.95}]}]
 def view_of(prs,z=zn):return to_frontend_audit(result(prs),audit_id='fresh:x',job_state='completed',source_digest='ab'*32,zones=z)
 # foot stably inside hazard zone -> REVIEW CANDIDATE, never a violation/severity
 x=view_of(masked('0',(10,50,30,90),35));q=x['persons'][0]
 assert q['zone_membership_status']=='known' and q['zone_ids']==['z1'] and q['worst_severity'] is None
 assert q['zone_membership_basis']=='unverified_mask_estimate_limited_scale_relative_probes_only_not_a_guarantee'
 hv=[f for f in q['findings'] if f['rule_id']=='NO_HELMET_IN_HAZARD']
 assert hv and hv[0]['kind']=='uncertainty' and hv[0]['severity'] is None and hv[0]['review_state']=='needs_human_review'
 assert 'deterministic class Critical' in hv[0]['message'] and 'single still image' in hv[0]['message'] and 'Requires human confirmation' in hv[0]['message']
 assert 'unvalidated provider PPE readings' in hv[0]['message']
 assert not any(f['kind']=='violation' for f in q['findings'])
 assert q['ground_contact']['validity']=='plausible_estimate'
 assert x['zones_applied'] is True and 'review candidates only' in x['zones_applied_meaning'] and x['ruleset_version']=='draft-unapproved'
 # foot stably outside -> outside-zone candidate with class Low
 q2=view_of(masked('0',(10,10,30,40),25))['persons'][0]
 assert q2['zone_membership_status']=='known' and q2['zone_ids']==[]
 ov=[f for f in q2['findings'] if f['rule_id']=='NO_HELMET_OUTSIDE']
 assert ov and ov[0]['kind']=='uncertainty' and 'deterministic class Low' in ov[0]['message']
 # foot within the probe radius (2x2px on this 100px frame) of the zone edge -> boundary_uncertain: NOT determined, matrix not run, zones not applied
 zb=[{'id':'z1','name':'Edge','hazard':True,'points':[{'x':0.1,'y':0.5},{'x':0.9,'y':0.5},{'x':0.9,'y':0.89},{'x':0.1,'y':0.89}]}]
 xb=view_of(masked('0',(10,50,30,90),35),z=zb);qb=xb['persons'][0]
 assert qb['zone_membership_status']=='boundary_uncertain' and qb['zone_ids']==[] and qb['worst_severity'] is None
 assert any(f['rule_id']=='zone_membership_boundary_z1' and f['kind']=='uncertainty' and '2x2px' in f['message'] for f in qb['findings'])
 assert qb['zone_membership_basis']=='estimate_within_scale_relative_probe_radius_of_a_zone_boundary'
 assert not any(f['rule_id'].startswith('NO_') for f in qb['findings']) and xb['zones_applied'] is False
 # person cropped at the frame bottom -> contact not determinable -> legacy unknown path
 xc=view_of(masked('0',(10,60,30,100),35));qc=xc['persons'][0]
 assert qc['zone_membership_status']=='unknown' and qc['ground_contact']['validity']=='not_determinable'
 assert 'mask_touches_frame_edge_bottom' in qc['ground_contact']['reasons']
 assert any(f['rule_id']=='zone_membership_z1' for f in qc['findings']) and not any(f['rule_id'].startswith('NO_') for f in qc['findings'])
 assert xc['zones_applied'] is False
 # sparse bottom row (<3px) -> not_determinable
 xs=view_of(masked('0',(10,50,30,90),35,run_from=9,run_to=11))['persons'][0]
 assert xs['zone_membership_status']=='unknown' and 'contact_row_sparse_lt_3px' in xs['ground_contact']['reasons']
 # no mask recorded (legacy) -> membership unknown, no candidates, zones not applied
 x3=view_of(person(eligible=True,helmet='absent'));q3=x3['persons'][0]
 assert q3['zone_membership_status']=='unknown' and q3['ground_contact']['basis']=='not_recorded'
 assert not any(f['rule_id'].startswith('NO_') for f in q3['findings']) and x3['zones_applied'] is False
 assert any(f['rule_id']=='zone_membership_z1' and f['kind']=='uncertainty' for f in q3['findings'])
 # tampered mask refuses the whole view
 bad=masked('0',(10,50,30,90),35);bad['mask']['counts'][0]+=1
 import pytest as _pt
 with _pt.raises(ValueError):view_of(bad)
 # no zones posted -> no membership work at all
 x4=to_frontend_audit(result(masked('0',(10,50,30,90),35)),audit_id='fresh:x',job_state='completed',source_digest='ab'*32)
 assert x4['zones_applied'] is False and 'No zones posted' in x4['zones_applied_meaning']

def test_boundary_probe_coverage_and_documented_limits():
 from PIL import Image
 from fresh_review.masks import encode_mask
 def masked(pid,box,bottom_rows):
  m=Image.new('L',(box[2]-box[0],box[3]-box[1]),0)
  for y in range(bottom_rows,m.size[1]):
   for x in range(m.size[0]//3,2*m.size[0]//3):m.putpixel((x,y),255)
  return person(pid,box=box,helmet='absent',vest='present',eligible=True,mask=encode_mask(m,list(box),[100,100]))
 prs=masked('0',(10,50,30,90),35)  # foot (0.195, 0.89)
 def view_of(z):return to_frontend_audit(result(prs),audit_id='fresh:x',job_state='completed',source_digest='ab'*32,zones=z)
 # diagonal edge y=-x+1.055: foot is 0.03 (x+y units) inside - stable under AXIS-only probes, but the
 # (-2px,-2px) diagonal probe crosses the edge. The 8-probe set catches what axis-only probes miss.
 zd=[{'id':'zd','name':'Diag','hazard':True,'points':[{'x':0.105,'y':0.95},{'x':0.95,'y':0.95},{'x':0.95,'y':0.105}]}]
 qd=view_of(zd)['persons'][0]
 assert qd['zone_membership_status']=='boundary_uncertain' and not any(f['rule_id'].startswith('NO_') for f in qd['findings'])
 assert any(f['rule_id']=='zone_membership_boundary_zd' for f in qd['findings'])
 # DOCUMENTED LIMITATION: a sub-probe-scale sliver near the estimate contains neither the estimate nor any
 # probe, so membership reads 'known'/outside. The basis string must carry the limited-check language:
 # finite probes over a point estimate cannot see sub-probe geometry; 'known' is never verified membership.
 zs=[{'id':'zs','name':'Sliver','hazard':True,'points':[{'x':0.194,'y':0.8922},{'x':0.196,'y':0.8922},{'x':0.195,'y':0.8932}]}]
 qs=view_of(zs)['persons'][0]
 assert qs['zone_membership_status']=='known' and qs['zone_ids']==[]
 assert qs['zone_membership_basis']=='unverified_mask_estimate_limited_scale_relative_probes_only_not_a_guarantee'
 # every 'known' membership anywhere in the view carries that basis language
 x=view_of([{'id':'z1','name':'R','hazard':True,'points':[{'x':0.1,'y':0.5},{'x':0.9,'y':0.5},{'x':0.9,'y':0.95},{'x':0.1,'y':0.95}]}])
 assert all(q['zone_membership_basis'].startswith('unverified_mask_estimate_limited') for q in x['persons'])

def test_route_rejects_invalid_zones_before_any_lookup(material):
 p,raw,frame,calls,c,job=material;n0=len(calls)
 for bad in ('[{"id":"z"}]','NaN','[{"id":"a","name":"n","hazard":true,"points":[{"x":0,"y":0},{"x":1,"y":1}]}]'):
  r=c.post('/fresh-review-audit',files={'image':('x.png',raw,'image/png')},data={'zones':bad},headers=H)
  assert r.status_code==400 and r.json()['error']['code'].startswith('INVALID_')
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
 assert c.get(path,headers={'X-Vigilens-Display-Session':'b2'*32}).status_code==409   # another session cannot read it by digest
 assert len(calls)==n and x['provider_calls_this_request']==0 and x['evidence_image'] is None and x['evidence_export_allowed'] is False and x['compliance_status']=='not_evaluated'
 assert x['source_digest']==frame.digest and x['audit_id'].startswith('fresh:'+frame.digest+':')
 for per in x['persons']:
  assert per['findings'] and all(f['severity'] is None and f['kind'] in ('uncertainty','observation') for f in per['findings'])
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
 return p,raw,frame,calls,TestClient(create_app(fresh_service=p),headers={'X-Vigilens-Local-Access':'','X-Vigilens-Display-Session':'07'*32})
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
 assert c.get('/fresh-review/'+frame.digest+'/frontend-audit',headers={'X-Vigilens-Display-Session':'b2'*32}).status_code==409
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
 c=TestClient(create_app(fresh_service=p),headers=hdr('07'*32))
 r=c.post(GOV,files=files(),data={'zones':'[]'})
 assert r.status_code==409 and r.json()['detail']['code']=='ATTEMPT_UNCERTAIN' and r.json()['detail']['provider_calls_this_request'] is None
 assert 'no call' not in r.text.lower() and len(calls)==timeout
 before=p.read(frame.digest)
 for sess in ('29'*32,'3a'*32):
  for _ in range(2):
   r=TestClient(create_app(fresh_service=p),headers=hdr(sess)).post(GOV,files=files(),data={'zones':'[]'})
   assert r.status_code==409 and r.json()['detail']['code']=='ATTEMPT_UNCERTAIN'
 assert len(calls)==timeout
 # restart: a brand new pipeline object over the same private journal, with a transport that would succeed
 p2,_,_,calls2=setup(tmp_path,monkeypatch,people=2)
 r=TestClient(create_app(fresh_service=p2),headers=hdr('18'*32)).post(GOV,files=files(),data={'zones':'[]'})
 assert r.status_code==409 and r.json()['detail']['code']=='ATTEMPT_UNCERTAIN' and calls2==[]
 assert p.read(frame.digest)==before and before['state']=='running_uncertain' and before['result'] is None
 # the stored-only and frontend-audit view never present a result for it
 assert c.get('/fresh-review/'+frame.digest+'/frontend-audit').status_code==409
 assert TestClient(create_app(fresh_service=p),headers=hdr('07'*32)).post('/fresh-review-audit',files=files(),data={'zones':'[]'}).status_code==409

def test_readings_origin_labels_synthetic_live_and_unknown_from_recorded_ids():
 from fresh_review.frontend_audit import to_frontend_audit
 base={'image':{'width':100,'height':100,'pixel_digest':'ab'*32},'persons':[person()]}
 cases=(('synthetic-sam-1','synthetic'),('meta-resp-abc','live_provider'),(None,'unknown'))
 for rid,label in cases:
  r=json.loads(json.dumps(base))
  if rid is not None:r['sam_response_id']=rid
  # person ppe ids must agree for a clean synthetic/live label
  if rid is not None:r['persons'][0]['ppe']={'ppe_response_id':'synthetic-ppe-1' if rid.startswith('synthetic') else 'meta-resp-ppe'}
  v=to_frontend_audit(r,audit_id='fresh:x',job_state='completed',source_digest='ab'*32)
  assert v['readings_origin']==label,(rid,v['readings_origin'])
 mixed=json.loads(json.dumps(base));mixed['sam_response_id']='synthetic-sam-1';mixed['persons'][0]['ppe']={'ppe_response_id':'meta-resp-ppe'}
 assert to_frontend_audit(mixed,audit_id='fresh:x',job_state='completed',source_digest='ab'*32)['readings_origin']=='unknown'

def test_scale_relative_probe_radius_on_high_res_frame():
 # Probe radius is max(2px, 0.5% of the frame dimension) per axis: on a 4000x3000
 # photo that is 20x15px, and both the finding text and the basis strings must say
 # scale-relative, never a fixed 2px.
 from PIL import Image
 from fresh_review.masks import encode_mask
 def hrmasked(box,bottom_rows):
  m=Image.new('L',(box[2]-box[0],box[3]-box[1]),0)
  for y in range(bottom_rows,m.size[1]):
   for x in range(m.size[0]//3,2*m.size[0]//3):m.putpixel((x,y),255)
  return person('0',box=box,helmet='absent',vest='present',eligible=True,mask=encode_mask(m,list(box),[4000,3000]))
 def view_of(prs,z):
  r={'image':{'width':4000,'height':3000,'pixel_digest':'ab'*32},'persons':[prs]}
  return to_frontend_audit(r,audit_id='fresh:x',job_state='completed',source_digest='ab'*32,zones=z)
 zedge=[{'id':'z1','name':'Edge','hazard':True,'points':[{'x':0.1,'y':0.5},{'x':0.9,'y':0.5},{'x':0.9,'y':0.9},{'x':0.1,'y':0.9}]}]
 qb=view_of(hrmasked((1000,1500,1200,2700),1190),zedge)['persons'][0]
 assert qb['zone_membership_status']=='boundary_uncertain'
 assert qb['zone_membership_basis']=='estimate_within_scale_relative_probe_radius_of_a_zone_boundary'
 assert any('20x15px' in f['message'] for f in qb['findings'] if f['rule_id']=='zone_membership_boundary_z1')
 zin=[{'id':'z1','name':'Pit','hazard':True,'points':[{'x':0.1,'y':0.5},{'x':0.9,'y':0.5},{'x':0.9,'y':0.95},{'x':0.1,'y':0.95}]}]
 q=view_of(hrmasked((1000,1500,1200,2700),1190),zin)['persons'][0]
 assert q['zone_membership_status']=='known' and q['zone_ids']==['z1']
 assert q['zone_membership_basis']=='unverified_mask_estimate_limited_scale_relative_probes_only_not_a_guarantee'

def test_unknown_ppe_keeps_location_only_intrusion_candidate_in_restricted_zone():
 # Unknown PPE suppresses exactly the PPE-absent candidates. It must NOT suppress the
 # PPE-independent location-only intrusion signal in a non-hazard entry-forbidden zone:
 # that candidate carries no PPE verdict and stays a review candidate like the rest.
 from PIL import Image
 from fresh_review.masks import encode_mask
 m=Image.new('L',(20,40),0)
 for y in range(35,40):
  for x in range(6,13):m.putpixel((x,y),255)
 prs=person('0',box=(40,50,60,90),helmet='unknown',vest='unknown',eligible=True,mask=encode_mask(m,[40,50,60,90],[100,100]))
 rz=[{'id':'rz','name':'Restricted','hazard':False,'points':[{'x':0.1,'y':0.5},{'x':0.9,'y':0.5},{'x':0.9,'y':0.95},{'x':0.1,'y':0.95}]}]
 x=to_frontend_audit(result(prs),audit_id='fresh:x',job_state='completed',source_digest='ab'*32,zones=rz);q=x['persons'][0]
 assert q['zone_membership_status']=='known' and q['zone_ids']==['rz']
 intr=[f for f in q['findings'] if f['rule_id']=='INTRUSION_RESTRICTED']
 assert intr and intr[0]['kind']=='uncertainty' and intr[0]['severity'] is None and intr[0]['review_state']=='needs_human_review'
 assert 'deterministic class Medium' in intr[0]['message'] and 'Person in an operator-defined entry-forbidden zone' in intr[0]['message']
 assert 'no PPE reading is used by this rule' in intr[0]['message'] and 'PPE readings' not in intr[0]['message']
 assert not any(f['rule_id'].startswith('NO_') for f in q['findings']) and q['worst_severity'] is None
