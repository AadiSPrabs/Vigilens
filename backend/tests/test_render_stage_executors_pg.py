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
    assert c.post(route, json=payload(x, job)).status_code in (200, 409)  # existing reservation or refusal; never a call
    assert len(calls) == 2
