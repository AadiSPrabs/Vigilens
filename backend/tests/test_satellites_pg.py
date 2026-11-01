"""Actual Postgres exercise of the remaining spend-critical satellites: exact
recheck and spatial explanation. Same fixtures as the sqlite tests, journal
rebuilt over PG; grant files stay operator-pinned files by design."""
import asyncio
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app import create_app
from fresh_review.pipeline import FreshPipeline, digest
from fresh_review.recheck_journal import RecheckJournal, RECHECK_RESERVE, reservation_total
from fresh_review.recheck_execution import RecheckExecutor
from test_fresh_upload_pipeline import setup as _setup


@pytest.fixture()
def pg_uri(tmp_path):
    pgserver = pytest.importorskip('pgserver')
    srv = pgserver.get_server(str(tmp_path / 'pg'))
    yield srv.get_uri()
    srv.cleanup()


def _material_pg(pg_uri, tmp_path, monkeypatch):
    from test_fresh_upload_routes import OWNER
    p0, raw, frame, calls = _setup(tmp_path, monkeypatch)
    p = FreshPipeline(pg_uri, carry_path=p0.carry_path, carry_sha=p0.carry_sha,
                      execution_scope='synthetic_local_qualification',
                      approval_store=p0.approval_store, transport=p0.transport)
    c = TestClient(create_app(fresh_service=p), headers={'X-Vigilens-Display-Session': OWNER})
    out = c.post('/fresh-review-upload', files={'image': ('synthetic.png', raw, 'image/png')}, data={'zones': '[]'})
    assert out.status_code == 200 and out.json()['state'] == 'completed'
    return p, raw, frame, calls, c, out.json()


def _recheck_executor_pg(p, frame, tmp_path, monkeypatch):
    import fresh_review.recheck_execution as module
    from PIL import Image
    async def parse(*args, **kwargs):
        return {'objects': [{'object_id': '0', 'box_half_open': [0, 0, 20, 60], 'mask': Image.new('L', (20, 60), 255)}]}
    monkeypatch.setattr(module, 'parse_sam_image_text', parse)
    attempt = RecheckJournal(p).reserve(frame.digest, '0', max_attempts=1, authority_reference='synthetic-exact-request-authority')
    plan = attempt['plan']
    grant = {'format': 'vigilens.exact-recheck-approval.v1', 'execution_scope': p.execution_scope,
             'source_digest': frame.digest, 'result_sha256': plan['result_sha256'], 'person_id': '0',
             'plan_sha256': digest(plan), 'authority_reference': 'synthetic-exact-request-authority',
             'request_sha256': [s['request_sha256'] for s in plan['steps']], 'max_reserved_usd': str(RECHECK_RESERVE)}
    path = tmp_path / 'synthetic-recheck-grant.json'
    raw = json.dumps(grant).encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return RecheckExecutor(p, approval_path=path, approval_sha256=hashlib.sha256(raw).hexdigest()), attempt


def test_recheck_pg_full_flow_and_restart(pg_uri, tmp_path, monkeypatch):
    p, raw, frame, calls, c, job = _material_pg(pg_uri, tmp_path, monkeypatch)
    e, a = _recheck_executor_pg(p, frame, tmp_path, monkeypatch)
    result = asyncio.run(e.run(a['attempt_id']))
    assert result['state'] == 'completed' and result['provider_calls_this_request'] == 2
    n = len(calls)
    # Repeat: reuse from the durable store, zero new calls.
    assert asyncio.run(e.run(a['attempt_id']))['provider_calls_this_request'] == 0
    assert len(calls) == n
    # Restart: new executor over the same database sees the completed attempt.
    e2, _a2 = _recheck_executor_pg(p, frame, tmp_path, monkeypatch)
    assert e2.read(a['attempt_id'])['state'] == 'completed'
    db = p.connect()
    assert reservation_total(db) < RECHECK_RESERVE
    db.close()


def test_recheck_pg_uncertain_held(pg_uri, tmp_path, monkeypatch):
    p, raw, frame, calls, c, job = _material_pg(pg_uri, tmp_path, monkeypatch)
    e, a = _recheck_executor_pg(p, frame, tmp_path, monkeypatch)
    def uncertain(body):
        calls.append(body)
        raise TimeoutError()
    p.transport = uncertain
    result = asyncio.run(e.run(a['attempt_id']))
    assert result['state'] == 'attempted_uncertain' and result['result'] is None
    result2 = asyncio.run(e.run(a['attempt_id']))
    assert result2['state'] == 'attempted_uncertain'  # held, never retried


def test_explanation_pg_full_flow(pg_uri, tmp_path, monkeypatch):
    from test_fresh_upload_routes import prepare, acknowledge, report
    from test_fresh_zones import submit, contact
    from test_rule_report_integration import rules
    from test_private_report_document import payload
    from fresh_review.spatial_explanation import build_spatial_request
    from fresh_review.explanation_execution import ExplanationExecutor
    from fresh_review.ppe import MAX_COST
    from test_spatial_explanation import response as exp_response

    p, raw, frame, calls, c, job = _material_pg(pg_uri, tmp_path, monkeypatch)
    x = prepare(c, raw, frame)
    acknowledge(c, x)
    submit(c, frame, job)
    contact(c, frame)
    rules(c, frame, job)
    doc = report(c, x, job).json()
    plan = build_spatial_request(raw, job['result'], doc['zone_review'], doc['configured_rule_review'], [])
    grant = {'format': 'vigilens.exact-explanation-grant.v1', 'execution_scope': p.execution_scope,
             'plan_sha256': digest(plan), 'maximum_reserved_usd': str(MAX_COST),
             'authority_reference': 'synthetic-only'}
    path = tmp_path / 'synthetic-explanation-grant.json'
    encoded = json.dumps(grant).encode()
    path.write_bytes(encoded)
    path.chmod(0o600)
    e = ExplanationExecutor(p, approval_path=path, approval_sha256=hashlib.sha256(encoded).hexdigest())
    identity = e.reserve(plan)
    p.transport = lambda body: exp_response(plan)
    out = e.run(identity, plan)
    assert out['state'] == 'completed'
    # Repeat serves the stored explanation without new dispatch.
    out2 = e.run(identity, plan)
    assert out2['state'] == 'completed' and out2['provider_calls_this_request'] == 0


def test_zone_rule_contact_rows_persist_in_pg(pg_uri, tmp_path, monkeypatch):
    # Direct smoke: submitted zone/rule/contact review rows actually land in the
    # PG tables (not only in memory), queryable through the store connection.
    from test_fresh_upload_routes import prepare, acknowledge
    from test_fresh_zones import submit, contact
    from test_rule_report_integration import rules

    p, raw, frame, calls, c, job = _material_pg(pg_uri, tmp_path, monkeypatch)
    x = prepare(c, raw, frame)
    acknowledge(c, x)
    submit(c, frame, job)
    contact(c, frame)
    rules(c, frame, job)
    con = p.connect()
    try:
        for table in ('zone_events', 'contact_events', 'rule_events'):
            n = con.execute('SELECT count(*) FROM ' + table).fetchone()[0]
            assert n >= 1, table + ' has no persisted rows'
    finally:
        con.close()
