"""Recheck execution on real Postgres (pgserver): synthetic transport and a synthetic exact grant only.
Never live permission. Covers normal, repeat, uncertain, ambiguous crop, grant pin/scope, restart no-repeat, owner boundary."""
import asyncio, hashlib, json
import pytest
from PIL import Image
from test_render_stage_executors_pg import pg_material, OWNER  # noqa: F401
from fresh_review.recheck_journal import RecheckJournal, RECHECK_RESERVE, reservation_total
from fresh_review.recheck_execution import RecheckExecutor
from fresh_review.pipeline import digest


def make(service, frame, monkeypatch, tmp_path, *, objects=1, owner=None):
    import fresh_review.recheck_execution as module

    async def parse(*a, **k):
        return {'objects': [{'object_id': str(i), 'box_half_open': [0, 0, 20, 60], 'mask': Image.new('L', (20, 60), 255)} for i in range(objects)]}
    monkeypatch.setattr(module, 'parse_sam_image_text', parse)
    attempt = RecheckJournal(service).reserve(frame.digest, '0', max_attempts=1, authority_reference='synthetic-exact-request-authority', owner=owner)
    plan = attempt['plan']
    grant = {'format': 'vigilens.exact-recheck-approval.v1', 'execution_scope': service.execution_scope, 'source_digest': frame.digest,
             'result_sha256': plan['result_sha256'], 'person_id': '0', 'plan_sha256': digest(plan),
             'authority_reference': 'synthetic-exact-request-authority', 'request_sha256': [s['request_sha256'] for s in plan['steps']],
             'max_reserved_usd': str(RECHECK_RESERVE)}
    d = tmp_path / 'g'; d.mkdir(mode=0o700, exist_ok=True)
    path = d / 'recheck-grant.json'; raw = json.dumps(grant).encode(); path.write_bytes(raw); path.chmod(0o600)
    return RecheckExecutor(service, approval_path=path, approval_sha256=hashlib.sha256(raw).hexdigest()), attempt


def test_pg_recheck_normal_repeat_and_original_unchanged(pg_material, monkeypatch, tmp_path):
    service, raw, frame, calls, c, job = pg_material
    e, a = make(service, frame, monkeypatch, tmp_path)
    r = asyncio.run(e.run(a['attempt_id']))
    assert r['state'] == 'completed' and len(calls) == 4 and r['provider_calls_this_request'] == 2
    assert r['result']['original_overwrite_allowed'] is False
    assert service.read(frame.digest)['result'] == job['result']
    db = service.connect(); assert reservation_total(db) < RECHECK_RESERVE; db.close()
    again = asyncio.run(e.run(a['attempt_id']))
    assert again['provider_calls_this_request'] == 0 and len(calls) == 4


def test_pg_recheck_uncertain_keeps_full_hold_no_retry_and_survives_restart(pg_material, monkeypatch, tmp_path):
    service, raw, frame, calls, c, job = pg_material
    e, a = make(service, frame, monkeypatch, tmp_path)

    def uncertain(body):
        calls.append(body); raise TimeoutError()
    service.transport = uncertain
    r = asyncio.run(e.run(a['attempt_id']))
    assert r['state'] == 'attempted_uncertain' and r['result'] is None and r['provider_calls_this_request'] is None and len(calls) == 3
    assert asyncio.run(e.run(a['attempt_id']))['provider_calls_this_request'] == 0 and len(calls) == 3
    db = service.connect(); assert reservation_total(db) == RECHECK_RESERVE; db.close()
    # Restart: a fresh executor over the same Postgres never repeats the call and keeps the hold.
    e2 = RecheckExecutor(service, approval_path=e.approval_path, approval_sha256=e.approval_sha256)
    assert asyncio.run(e2.run(a['attempt_id']))['provider_calls_this_request'] == 0 and len(calls) == 3
    db = service.connect(); assert reservation_total(db) == RECHECK_RESERVE; db.close()
    assert service.read(frame.digest)['result'] == job['result']


@pytest.mark.parametrize('objects', [0, 2])
def test_pg_recheck_ambiguous_crop_stops_before_ppe(pg_material, monkeypatch, tmp_path, objects):
    service, raw, frame, calls, c, job = pg_material
    e, a = make(service, frame, monkeypatch, tmp_path, objects=objects)
    r = asyncio.run(e.run(a['attempt_id']))
    assert r['state'] == 'attempted_uncertain' and len(calls) == 3 and r['result'] is None


def test_pg_recheck_wrong_grant_makes_no_call(pg_material, monkeypatch, tmp_path):
    service, raw, frame, calls, c, job = pg_material
    e, a = make(service, frame, monkeypatch, tmp_path)
    e.approval_path.write_text('{}')
    with pytest.raises(ValueError):
        asyncio.run(e.run(a['attempt_id']))
    assert len(calls) == 2 and e.read(a['attempt_id'])['state'] == 'reserved_not_dispatched'


def test_pg_recheck_other_account_cannot_reserve_this_job(pg_material, monkeypatch, tmp_path):
    service, raw, frame, calls, c, job = pg_material
    with pytest.raises((ValueError, KeyError)):
        RecheckJournal(service).reserve(frame.digest, '0', max_attempts=1, authority_reference='synthetic', owner='cd' * 32)
    assert len(calls) == 2


# ---- bounded review loop on Postgres (server-configured attempts only; no grant or reservation created by the loop)
from fresh_review.agent_loop import run_review_loop
ACCOUNT = hashlib.sha256(OWNER.encode()).hexdigest()


def test_pg_loop_executes_preapproved_attempt_once_then_escalates(pg_material, monkeypatch, tmp_path):
    service, raw, frame, calls, c, job = pg_material
    e, a = make(service, frame, monkeypatch, tmp_path); service.recheck_executor = e
    out = asyncio.run(run_review_loop(service, frame.digest, attempt_ids=[a['attempt_id']], owner=ACCOUNT))
    assert out['status'] == 'human_review_required' and out['attempts'][0]['state'] == 'completed' and not out['automatic_candidate_adoption']
    assert service.read(frame.digest)['result'] == job['result'] and len(calls) == 4
    asyncio.run(run_review_loop(service, frame.digest, attempt_ids=[a['attempt_id']], owner=ACCOUNT))
    assert len(calls) == 4


def test_pg_loop_without_grant_never_dispatches_or_reserves(pg_material):
    service, raw, frame, calls, c, job = pg_material
    out = asyncio.run(run_review_loop(service, frame.digest, attempt_ids=[], owner=ACCOUNT))
    assert out['unattempted_unknown_person_ids'] == ['0'] and len(calls) == 2
    with pytest.raises(ValueError):
        asyncio.run(run_review_loop(service, frame.digest, attempt_ids=['new'], owner=ACCOUNT))
    assert len(calls) == 2


def test_pg_loop_uncertain_hold_escalates_without_retry(pg_material, monkeypatch, tmp_path):
    service, raw, frame, calls, c, job = pg_material
    e, a = make(service, frame, monkeypatch, tmp_path); service.recheck_executor = e

    def boom(body):
        calls.append(body); raise TimeoutError()
    service.transport = boom
    out = asyncio.run(run_review_loop(service, frame.digest, attempt_ids=[a['attempt_id']], owner=ACCOUNT))
    assert out['attempts'][0]['state'] == 'attempted_uncertain' and out['status'] == 'human_review_required' and len(calls) == 3
    asyncio.run(run_review_loop(service, frame.digest, attempt_ids=[a['attempt_id']], owner=ACCOUNT))
    assert len(calls) == 3 and service.read(frame.digest)['result'] == job['result']


def test_pg_loop_http_needs_server_config_acked_preview_and_exact_result(pg_material, monkeypatch, tmp_path):
    from test_fresh_upload_routes import prepare, acknowledge
    service, raw, frame, calls, c, job = pg_material
    e, a = make(service, frame, monkeypatch, tmp_path); service.recheck_executor = e
    route = '/fresh-review/' + frame.digest + '/bounded-review-loop'
    body = {'source_digest': frame.digest, 'result_sha256': digest(job['result'])}
    assert c.post(route, json=body).status_code == 409                      # no acknowledged preview
    x = prepare(c, raw, frame); acknowledge(c, x)
    assert c.post(route, json=body).status_code == 409                      # no server-side loop configuration
    service.review_loop_attempts = {frame.digest: [a['attempt_id']]}
    assert c.post(route, json={**body, 'attempts': [a['attempt_id']]}).status_code == 409   # client cannot supply attempts
    other = {'X-Vigilens-Display-Session': 'cd' * 32}
    assert c.post(route, json=body, headers=other).status_code in (403, 409) and len(calls) == 2
    out = c.post(route, json=body); assert out.status_code == 200 and out.json()['attempts'][0]['state'] == 'completed'
    assert c.post(route, json=body).status_code == 200 and len(calls) == 4
