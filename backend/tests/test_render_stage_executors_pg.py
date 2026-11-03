"""Opt-in explanation/recheck executors on the Render Postgres boot path (real Postgres via pgserver).
Synthetic transport only. Grants here are synthetic test fixtures, never live permission."""
import hashlib
import io
import json

import pytest
from PIL import Image

OWNER = 'ab' * 32


@pytest.fixture()
def pg_material(tmp_path, monkeypatch):
    pgserver = pytest.importorskip('pgserver')
    srv = pgserver.get_server(str(tmp_path / 'pg'))
    from fastapi.testclient import TestClient
    import fresh_review.pipeline as m
    from app import create_app
    from core import decode_image
    from fresh_test_helpers import response
    from render_boot import boot_pg_service

    im = Image.new('RGB', (80, 80), 'blue')
    out = io.BytesIO()
    im.save(out, 'PNG')
    raw = out.getvalue()
    frame = decode_image(raw, 'image/png')
    calls = []

    async def parse(*a, **k):
        return {'objects': [{'object_id': '0', 'box_half_open': [0, 0, 20, 60], 'mask': Image.new('L', (20, 60), 255)}]}
    monkeypatch.setattr(m, 'parse_sam_image_text', parse)

    def transport(body):
        calls.append(body)
        if body['model'] == 'sam-3.1':
            return b'data: {"type":"response.completed","response":{"model":"sam-3.1","id":"synthetic-sam","status":"completed","usage":{"images_processed":1},"output":[]}}\n\n'
        return response('unknown', 'absent')

    service = boot_pg_service(srv.get_uri(), cap='5', scope='synthetic_local_qualification', seamless=True, transport=transport)
    c = TestClient(create_app(fresh_service=service), headers={'X-Vigilens-Display-Session': OWNER})
    r = c.post('/fresh-review-upload', files={'image': ('synthetic.png', raw, 'image/png')}, data={'zones': '[]'})
    assert r.status_code == 200 and r.json()['state'] == 'completed', r.text
    yield service, raw, frame, calls, c, r.json()
    srv.cleanup()


def test_off_by_default_leaves_not_configured(pg_material, monkeypatch):
    import run_render
    monkeypatch.delenv('VIGILENS_STAGE_EXECUTORS', raising=False)
    service = pg_material[0]
    run_render._wire_stage_executors(service)
    assert not hasattr(service, 'explanation_executor') and not hasattr(service, 'recheck_executor')


def test_pg_explanation_reservation_needs_exact_grant_then_reserves_without_call(pg_material, monkeypatch):
    from test_fresh_upload_routes import prepare, acknowledge, report
    from test_private_report_document import payload
    from test_rule_report_integration import rules
    from test_fresh_zones import submit, contact
    from fresh_review.pipeline import digest
    from fresh_review.ppe import MAX_COST
    from fresh_review.spatial_explanation import build_spatial_request
    import run_render
    service, raw, frame, calls, c, job = pg_material
    x = prepare(c, raw, frame)
    acknowledge(c, x)
    submit(c, frame, job)
    contact(c, frame)
    rules(c, frame, job)
    route = '/fresh-private-report/' + x['session_id'] + '/explanation-reservation'
    monkeypatch.setenv('VIGILENS_STAGE_EXECUTORS', 'on')
    monkeypatch.delenv('VIGILENS_EXPLANATION_GRANT_JSON', raising=False)
    monkeypatch.delenv('VIGILENS_RECHECK_GRANT_JSON', raising=False)
    run_render._wire_stage_executors(service)
    # Executor attached but no grant: the report shows the exact plan, reservation is refused, no call.
    doc = report(c, x, job).json()
    se = doc['spatial_explanations']
    assert se['exact_plan_sha256'] and se['reservation_route'] == route
    assert c.post(route, json=payload(x, job)).status_code == 409
    assert len(calls) == 2
    # Operator supplies an exact (synthetic) grant for that plan hash through the env var, then reboots the wiring.
    plan = build_spatial_request(raw, job['result'], doc['zone_review'], doc['configured_rule_review'], [])
    assert digest(plan) == se['exact_plan_sha256']
    grant = {'format': 'vigilens.exact-explanation-grant.v1', 'execution_scope': service.execution_scope,
             'plan_sha256': digest(plan), 'maximum_reserved_usd': str(MAX_COST), 'authority_reference': 'synthetic-test-only'}
    monkeypatch.setenv('VIGILENS_EXPLANATION_GRANT_JSON', json.dumps(grant))
    run_render._wire_stage_executors(service)
    out = c.post(route, json=payload(x, job))
    assert out.status_code == 200, out.text
    j = out.json()
    assert j['state'] == 'reserved_not_dispatched' and j['provider_calls_this_request'] == 0 and j['grant_created_here'] is False
    assert len(calls) == 2  # reservation made no provider call
    # A grant for a different plan is refused.
    bad = dict(grant, plan_sha256='0' * 64)
    monkeypatch.setenv('VIGILENS_EXPLANATION_GRANT_JSON', json.dumps(bad))
    run_render._wire_stage_executors(service)
    bad_out = c.post(route, json=payload(x, job))
    assert bad_out.status_code == 409 or (bad_out.status_code == 200 and bad_out.json()['plan_sha256'] == digest(plan))  # refusal, or the already-reserved exact plan; never a wrong-plan reservation
    assert len(calls) == 2


def _granted_ready(pg_material, monkeypatch):
    """Boot-wired explanation executor with a synthetic exact grant; returns reserved attempt + helpers."""
    from test_fresh_upload_routes import prepare, acknowledge, report
    from test_private_report_document import payload
    from test_rule_report_integration import rules
    from test_fresh_zones import submit, contact
    from fresh_review.pipeline import digest
    from fresh_review.ppe import MAX_COST
    from fresh_review.spatial_explanation import build_spatial_request
    import run_render
    service, raw, frame, calls, c, job = pg_material
    x = prepare(c, raw, frame); acknowledge(c, x); submit(c, frame, job); contact(c, frame); rules(c, frame, job)
    monkeypatch.setenv('VIGILENS_STAGE_EXECUTORS', 'on')
    monkeypatch.delenv('VIGILENS_RECHECK_GRANT_JSON', raising=False)
    monkeypatch.delenv('VIGILENS_EXPLANATION_GRANT_JSON', raising=False)
    run_render._wire_stage_executors(service)
    doc = report(c, x, job).json()
    plan = build_spatial_request(raw, job['result'], doc['zone_review'], doc['configured_rule_review'], [])
    grant = {'format': 'vigilens.exact-explanation-grant.v1', 'execution_scope': service.execution_scope, 'plan_sha256': digest(plan),
             'maximum_reserved_usd': str(MAX_COST), 'authority_reference': 'synthetic-test-only'}
    monkeypatch.setenv('VIGILENS_EXPLANATION_GRANT_JSON', json.dumps(grant))
    run_render._wire_stage_executors(service)
    res = c.post('/fresh-private-report/' + x['session_id'] + '/explanation-reservation', json=payload(x, job))
    assert res.status_code == 200, res.text
    return service, calls, c, x, job, plan, res.json()['attempt_id'], payload(x, job), run_render


def test_pg_explanation_run_via_boot_wiring_normal_repeat_restart(pg_material, monkeypatch):
    from test_spatial_explanation import response as exp_response
    service, calls, c, x, job, plan, aid, body, run_render = _granted_ready(pg_material, monkeypatch)
    n0 = len(calls)
    service.transport = lambda b: (calls.append(b), exp_response(plan))[1]
    route = '/fresh-private-report/' + x['session_id'] + '/explanation/' + aid
    out = c.post(route, json=body); assert out.status_code == 200, out.text
    assert out.json()['state'] == 'completed' and out.json()['commentary_display'] == 'unvalidated_model_text_never_rule_authority'
    assert len(calls) == n0 + 1
    again = c.post(route, json=body).json(); assert again['provider_calls_this_request'] == 0 and len(calls) == n0 + 1
    run_render._wire_stage_executors(service)   # restart-style rewire: stored attempt is not re-dispatched
    assert c.post(route, json=body).json()['provider_calls_this_request'] == 0 and len(calls) == n0 + 1


def test_pg_explanation_uncertain_is_held_and_never_retried(pg_material, monkeypatch):
    service, calls, c, x, job, plan, aid, body, run_render = _granted_ready(pg_material, monkeypatch)
    n0 = len(calls)

    def boom(b):
        calls.append(b); raise TimeoutError()
    service.transport = boom
    route = '/fresh-private-report/' + x['session_id'] + '/explanation/' + aid
    out = c.post(route, json=body)
    assert out.status_code == 200 and out.json()['state'] == 'attempted_uncertain' and len(calls) == n0 + 1
    c.post(route, json=body); c.post(route, json=body)
    assert len(calls) == n0 + 1      # never retried automatically


def test_pg_explanation_other_account_cannot_run_or_reserve(pg_material, monkeypatch):
    service, calls, c, x, job, plan, aid, body, run_render = _granted_ready(pg_material, monkeypatch)
    n0 = len(calls)
    other = {'X-Vigilens-Display-Session': 'cd' * 32}
    route = '/fresh-private-report/' + x['session_id'] + '/explanation/' + aid
    assert c.post(route, json=body, headers=other).status_code in (403, 404, 409)
    assert c.post('/fresh-private-report/' + x['session_id'] + '/explanation-reservation', json=body, headers=other).status_code in (403, 404, 409)
    assert len(calls) == n0


def test_grant_builder_output_is_accepted_for_exact_plan_only(pg_material, monkeypatch, capsys):
    """The documented operator tool produces a grant the boot wiring accepts for that plan, and refuses bad input."""
    import make_explanation_grant as mk
    from fresh_review.ppe import MAX_COST
    service, calls, c, x, job, plan, aid, body, run_render = _granted_ready(pg_material, monkeypatch)
    from fresh_review.pipeline import digest
    g = mk.build(digest(plan), service.execution_scope, 'owner-approval-ref')
    assert g['maximum_reserved_usd'] == str(MAX_COST) and g['plan_sha256'] == digest(plan)
    with pytest.raises(ValueError):
        mk.build('xyz', service.execution_scope, 'ref')
    with pytest.raises(ValueError):
        mk.build(digest(plan), service.execution_scope, 'ref', maximum_reserved_usd='9')
    assert mk.main(['--plan-sha256', 'bad', '--execution-scope', 's', '--authority-reference', 'r']) == 2
    assert mk.main(['--plan-sha256', digest(plan), '--execution-scope', service.execution_scope, '--authority-reference', 'r']) == 0
    assert json.loads(capsys.readouterr().out)['plan_sha256'] == digest(plan)
