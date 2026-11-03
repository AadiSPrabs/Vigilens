from test_fresh_upload_routes import material,prepare,acknowledge,report
from test_private_report_document import payload
from test_rule_report_integration import rules
from test_fresh_zones import submit,contact
from test_spatial_explanation import setup_explanation

def test_reservation_needs_rules_and_exact_grant_then_dispatch(material):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x)
 route='/fresh-private-report/'+x['session_id']+'/explanation-reservation'
 # No executor configured: refused, nothing reserved.
 assert c.post(route,json=payload(x,job)).status_code==409
 submit(c,frame,job);contact(c,frame);rules(c,frame,job)
 e,plan,identity=setup_explanation(p,raw,job,c,x)  # executor with exact grant for this plan
 # Configured rules + exact grant, not yet installed on the service: still refused.
 assert c.post(route,json=payload(x,job)).status_code==409
 p.explanation_executor=e
 doc=report(c,x,job).json();se=doc['spatial_explanations']
 assert se['exact_plan_sha256'] and se['reservation_route']==route
 out=c.post(route,json=payload(x,job));assert out.status_code==200,out.text
 j=out.json();assert j['state']=='reserved_not_dispatched'and j['provider_calls_this_request']==0 and j['grant_created_here']is False
 assert len(calls)==2  # reservation made no provider call

def test_reservation_refused_when_grant_does_not_cover_plan(material):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x);submit(c,frame,job);contact(c,frame);rules(c,frame,job)
 e,plan,identity=setup_explanation(p,raw,job,c,x)
 import json
 e.path.write_bytes(json.dumps({'format':'x'}).encode())
 p.explanation_executor=e
 assert c.post('/fresh-private-report/'+x['session_id']+'/explanation-reservation',json=payload(x,job)).status_code==409
 assert len(calls)==2
