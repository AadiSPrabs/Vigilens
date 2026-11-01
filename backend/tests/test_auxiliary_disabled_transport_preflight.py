"""Auxiliary executors must not change attempt state or reservations while the transport is disabled."""
import asyncio
import pytest
from adapters import LiveTransportDisabled
from test_fresh_upload_routes import material,prepare,acknowledge
from test_recheck_execution import executor as recheck_executor
from test_ppe_segmentation import helper as mask_helper
from test_spatial_explanation import setup_explanation
from test_fresh_zones import submit
from test_rule_report_integration import rules
from test_private_report_document import payload
from fresh_review.pipeline import disabled_transport,digest
from fresh_review.recheck_journal import RECHECK_RESERVE,reservation_total
from fresh_review.ppe_segmentation import total as mask_total
from fresh_review.explanation_execution import total as explanation_total

def hold(p,fn):
 db=p.connect()
 try:return fn(db)
 finally:db.close()

def test_recheck_disabled_transport_changes_nothing_then_enabled_run_works(material,monkeypatch):
 p,raw,frame,calls,c,job=material;e,a=recheck_executor(p,frame,monkeypatch)
 live=p.transport;before=hold(p,reservation_total);n=len(calls)
 p.transport=disabled_transport
 with pytest.raises(LiveTransportDisabled):asyncio.run(e.run(a['attempt_id']))
 assert e.read(a['attempt_id'])['state']=='reserved_not_dispatched'and len(calls)==n and hold(p,reservation_total)==before
 p.transport=live
 out=asyncio.run(e.run(a['attempt_id']))
 assert out['state']=='completed'and out['provider_calls_this_request']==2

def test_recheck_existing_uncertain_attempt_is_preserved_not_cleared_when_transport_later_disabled(material,monkeypatch):
 p,raw,frame,calls,c,job=material;e,a=recheck_executor(p,frame,monkeypatch)
 def uncertain(body):calls.append(body);raise TimeoutError()
 p.transport=uncertain
 assert asyncio.run(e.run(a['attempt_id']))['state']=='attempted_uncertain'
 held=hold(p,reservation_total);assert held==RECHECK_RESERVE;n=len(calls)
 p.transport=disabled_transport
 again=asyncio.run(e.run(a['attempt_id']))
 assert again['state']=='attempted_uncertain'and again['provider_calls_this_request']==0 and len(calls)==n and hold(p,reservation_total)==held

def test_mask_batch_disabled_transport_changes_nothing_then_enabled_run_works(material,monkeypatch):
 p,raw,frame,calls,c,job=material;h,identity=mask_helper(p,frame,monkeypatch)
 live=p.transport;before=hold(p,mask_total);n=len(calls)
 p.transport=disabled_transport
 with pytest.raises(LiveTransportDisabled):asyncio.run(h.run(identity))
 assert h.read(identity)['state']=='reserved_not_dispatched'and len(calls)==n and hold(p,mask_total)==before
 p.transport=live
 assert asyncio.run(h.run(identity))['state']=='completed'

def test_mask_route_returns_503_and_leaves_batch_reserved_when_disabled(material,monkeypatch):
 p,raw,frame,calls,c,job=material;h,identity=mask_helper(p,frame,monkeypatch)
 x=prepare(c,raw,frame);acknowledge(c,x);body={'source_digest':frame.digest,'result_sha256':digest(job['result'])}
 path='/fresh-review/'+frame.digest+'/ppe-segmentation/'+identity
 p.ppe_segmentation=h;n=len(calls);p.transport=disabled_transport
 assert c.post(path,json=body).status_code==503
 assert h.read(identity)['state']=='reserved_not_dispatched'and len(calls)==n

def test_explanation_disabled_transport_changes_nothing_then_enabled_run_works(material,monkeypatch):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x);submit(c,frame,job);rules(c,frame,job)
 e,plan,identity=setup_explanation(p,raw,job,c,x)
 live=p.transport;before=hold(p,explanation_total);n=len(calls)
 p.transport=disabled_transport
 with pytest.raises(LiveTransportDisabled):e.run(identity,plan)
 assert e.read(identity)['state']=='reserved_not_dispatched'and len(calls)==n and hold(p,explanation_total)==before
