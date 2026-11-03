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


# ---- Render boot configuration of the loop (env), fail closed
def _boot(service, monkeypatch, e, loop):
    import run_render
    monkeypatch.setenv('VIGILENS_STAGE_EXECUTORS', 'on')
    monkeypatch.delenv('VIGILENS_EXPLANATION_GRANT_JSON', raising=False)
    if e is not None:
        monkeypatch.setenv('VIGILENS_RECHECK_GRANT_JSON', e.approval_path.read_text())
    else:
        monkeypatch.delenv('VIGILENS_RECHECK_GRANT_JSON', raising=False)
    if loop is None:
        monkeypatch.delenv('VIGILENS_REVIEW_LOOP_ATTEMPTS_JSON', raising=False)
    else:
        monkeypatch.setenv('VIGILENS_REVIEW_LOOP_ATTEMPTS_JSON', json.dumps(loop))
    if hasattr(service, 'review_loop_attempts'):
        del service.review_loop_attempts
    run_render._wire_stage_executors(service)
    run_render._wire_review_loop(service)


def test_pg_boot_loop_unset_shows_blocked_plan_not_missing_feature(pg_material, monkeypatch, tmp_path):
    from test_fresh_upload_routes import prepare, acknowledge, report
    service, raw, frame, calls, c, job = pg_material
    _boot(service, monkeypatch, None, None)
    assert not hasattr(service, 'review_loop_attempts')
    x = prepare(c, raw, frame); acknowledge(c, x)
    doc = report(c, x, job).json()
    b = doc['bounded_review_loop']
    assert b['status'] == 'blocked_no_configured_attempts' and b['route'] is None and b['creates_grant_or_reservation'] is False
    assert 'owner approves a specific recheck plan' in b['blocked_until'] and len(calls) == 2


@pytest.mark.parametrize('case', ['no_executor', 'bad_source', 'unknown_attempt', 'wrong_source', 'too_many', 'not_json_object'])
def test_pg_boot_loop_bad_config_stays_unconfigured_no_call(pg_material, monkeypatch, tmp_path, capsys, case):
    service, raw, frame, calls, c, job = pg_material
    e, a = make(service, frame, monkeypatch, tmp_path)
    aid = a['attempt_id']
    loops = {'no_executor': {frame.digest: [aid]}, 'bad_source': {'zz': [aid]}, 'unknown_attempt': {frame.digest: ['0' * 64]},
             'wrong_source': {'1' * 64: [aid]}, 'too_many': {frame.digest: [aid, aid, aid]}, 'not_json_object': [aid]}
    _boot(service, monkeypatch, None if case == 'no_executor' else e, loops[case])
    assert not hasattr(service, 'review_loop_attempts')
    assert 'review loop NOT configured' in capsys.readouterr().out and len(calls) == 2


def test_pg_boot_loop_valid_config_runs_exact_attempt_over_http_once(pg_material, monkeypatch, tmp_path):
    from test_fresh_upload_routes import prepare, acknowledge, report
    service, raw, frame, calls, c, job = pg_material
    e, a = make(service, frame, monkeypatch, tmp_path)
    _boot(service, monkeypatch, e, {frame.digest: [a['attempt_id']]})
    assert service.review_loop_attempts == {frame.digest: [a['attempt_id']]}
    x = prepare(c, raw, frame); acknowledge(c, x)
    b = report(c, x, job).json()['bounded_review_loop']
    assert b['status'] == 'configured_exact_attempts' and b['attempt_count'] == 1 and b['creates_grant_or_reservation'] is False
    route = '/fresh-review/' + frame.digest + '/bounded-review-loop'
    body = {'source_digest': frame.digest, 'result_sha256': digest(job['result'])}
    out = c.post(route, json=body); assert out.status_code == 200 and out.json()['attempts'][0]['state'] == 'completed' and len(calls) == 4
    assert c.post(route, json=body).status_code == 200 and len(calls) == 4          # repeat: no new call
    assert c.post(route, json=body, headers={'X-Vigilens-Display-Session': 'cd' * 32}).status_code in (403, 409) and len(calls) == 4


def test_pg_boot_loop_wrong_grant_leaves_loop_unconfigured(pg_material, monkeypatch, tmp_path, capsys):
    service, raw, frame, calls, c, job = pg_material
    e, a = make(service, frame, monkeypatch, tmp_path)
    e.approval_path.write_text(json.dumps({'format': 'vigilens.exact-recheck-approval.v1'}))   # not the exact grant
    _boot(service, monkeypatch, e, {frame.digest: [a['attempt_id']]})
    assert not hasattr(service, 'review_loop_attempts') and 'NOT configured' in capsys.readouterr().out and len(calls) == 2


# ---- recheck plan + reservation routes (Render path): visible plan, grant checked before any booking
def _recheck_ready(pg_material, monkeypatch):
    from test_fresh_upload_routes import prepare, acknowledge
    import run_render
    service, raw, frame, calls, c, job = pg_material
    x = prepare(c, raw, frame); acknowledge(c, x)
    monkeypatch.setenv('VIGILENS_STAGE_EXECUTORS', 'on')
    for k in ('VIGILENS_EXPLANATION_GRANT_JSON', 'VIGILENS_RECHECK_GRANT_JSON', 'VIGILENS_REVIEW_LOOP_ATTEMPTS_JSON'):
        monkeypatch.delenv(k, raising=False)
    run_render._wire_stage_executors(service)
    return service, raw, frame, calls, c, job, run_render


def _grant_for(service, plan_view):
    return {'format': 'vigilens.exact-recheck-approval.v1', 'execution_scope': service.execution_scope, 'source_digest': plan_view['source_digest'],
            'result_sha256': plan_view['result_sha256'], 'person_id': plan_view['person_id'], 'plan_sha256': plan_view['plan_sha256'],
            'authority_reference': 'synthetic-test-only', 'request_sha256': plan_view['request_sha256'], 'max_reserved_usd': plan_view['max_reserved_usd']}


def test_pg_recheck_plan_is_visible_without_grant_and_books_nothing(pg_material, monkeypatch):
    service, raw, frame, calls, c, job, run_render = _recheck_ready(pg_material, monkeypatch)
    db = service.connect(); before = reservation_total(db); db.close()
    r = c.post('/fresh-review/' + frame.digest + '/recheck-plan', json={'person_id': '0'}); assert r.status_code == 200, r.text
    v = r.json()
    assert v['status'] == 'planned_requires_exact_grant' and v['reserved_nothing'] is True and v['configured_grant_matches_this_plan'] is False
    assert len(v['plan_sha256']) == 64 and len(v['request_sha256']) == 2 and v['max_reserved_usd'] == str(RECHECK_RESERVE)
    assert 'data:image' not in r.text and '"request"' not in r.text            # original crop pixels never returned
    db = service.connect(); assert reservation_total(db) == before; db.close()
    assert c.post('/fresh-review/' + frame.digest + '/recheck-reservation', json={'person_id': '0'}).status_code == 409
    db = service.connect(); assert reservation_total(db) == before; db.close()
    assert len(calls) == 2


def test_pg_recheck_reservation_with_exact_grant_holds_without_call_then_executes_and_loops(pg_material, monkeypatch):
    service, raw, frame, calls, c, job, run_render = _recheck_ready(pg_material, monkeypatch)
    import fresh_review.recheck_execution as module

    async def parse(*a, **k):
        return {'objects': [{'object_id': '0', 'box_half_open': [0, 0, 20, 60], 'mask': Image.new('L', (20, 60), 255)}]}
    monkeypatch.setattr(module, 'parse_sam_image_text', parse)
    v = c.post('/fresh-review/' + frame.digest + '/recheck-plan', json={'person_id': '0'}).json()
    monkeypatch.setenv('VIGILENS_RECHECK_GRANT_JSON', json.dumps(_grant_for(service, v)))
    run_render._wire_stage_executors(service)
    assert c.post('/fresh-review/' + frame.digest + '/recheck-plan', json={'person_id': '0'}).json()['configured_grant_matches_this_plan'] is True
    res = c.post('/fresh-review/' + frame.digest + '/recheck-reservation', json={'person_id': '0'}); assert res.status_code == 200, res.text
    j = res.json()
    assert j['state'] == 'reserved_not_dispatched' and j['new_reservation'] is True and j['provider_calls_this_request'] == 0 and j['grant_created_here'] is False
    assert j['held_usd'] == str(RECHECK_RESERVE) and len(calls) == 2
    db = service.connect(); assert reservation_total(db) == RECHECK_RESERVE; db.close()
    again = c.post('/fresh-review/' + frame.digest + '/recheck-reservation', json={'person_id': '0'}).json()
    assert again['attempt_id'] == j['attempt_id'] and again['new_reservation'] is False       # dedupes, no second hold
    other = {'X-Vigilens-Display-Session': 'cd' * 32}
    assert c.post('/fresh-review/' + frame.digest + '/recheck-reservation', json={'person_id': '0'}, headers=other).status_code == 409
    # Execute through the existing route, then the loop config (restart-style) uses that exact attempt id.
    ex = c.post('/fresh-review/' + frame.digest + '/recheck/' + j['attempt_id'], json={'source_digest': frame.digest, 'result_sha256': digest(job['result'])})
    assert ex.status_code == 200 and ex.json()['state'] == 'completed' and len(calls) == 4
    monkeypatch.setenv('VIGILENS_REVIEW_LOOP_ATTEMPTS_JSON', json.dumps({frame.digest: [j['attempt_id']]}))
    run_render._wire_review_loop(service)
    assert service.review_loop_attempts == {frame.digest: [j['attempt_id']]}


def test_pg_recheck_reservation_refuses_a_grant_for_another_plan(pg_material, monkeypatch):
    service, raw, frame, calls, c, job, run_render = _recheck_ready(pg_material, monkeypatch)
    v = c.post('/fresh-review/' + frame.digest + '/recheck-plan', json={'person_id': '0'}).json()
    bad = _grant_for(service, {**v, 'plan_sha256': '0' * 64})
    monkeypatch.setenv('VIGILENS_RECHECK_GRANT_JSON', json.dumps(bad)); run_render._wire_stage_executors(service)
    assert c.post('/fresh-review/' + frame.digest + '/recheck-reservation', json={'person_id': '0'}).status_code == 409
    db = service.connect(); assert reservation_total(db) == 0; db.close()
    assert c.post('/fresh-review/' + frame.digest + '/recheck-plan', json={'person_id': 'nobody'}).status_code == 409 and len(calls) == 2


def test_recheck_grant_builder_output_is_accepted_by_executor_for_exact_plan(pg_material, monkeypatch, capsys):
    import io
    import make_recheck_grant as mk
    service, raw, frame, calls, c, job, run_render = _recheck_ready(pg_material, monkeypatch)
    v = c.post('/fresh-review/' + frame.digest + '/recheck-plan', json={'person_id': '0'}).json()
    assert mk.main(['--authority-reference', 'owner-approval-ref'], stdin=io.StringIO(json.dumps(v))) == 0
    grant = json.loads(capsys.readouterr().out)
    monkeypatch.setenv('VIGILENS_RECHECK_GRANT_JSON', json.dumps(grant)); run_render._wire_stage_executors(service)
    assert c.post('/fresh-review/' + frame.digest + '/recheck-plan', json={'person_id': '0'}).json()['configured_grant_matches_this_plan'] is True
    for bad in ({**v, 'status': 'not_needed'}, {**v, 'plan_sha256': 'x'}, {**v, 'max_reserved_usd': '9'}, {**v, 'request_sha256': v['request_sha256'][:1]}):
        assert mk.main(['--authority-reference', 'r'], stdin=io.StringIO(json.dumps(bad))) == 2
    assert len(calls) == 2
