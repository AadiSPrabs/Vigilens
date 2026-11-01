"""Scope transition (synthetic -> live BYOK): retained journal rows verify under
their own recorded scope during pre-spend hold checks, while serving old results
and approving new spend stay bound to the CURRENT execution scope. Tampered or
unknown recorded scopes fail closed. No network: canned transports only."""
import asyncio, hashlib, json

import pytest
from PIL import Image

import fresh_review.pipeline as m
from fresh_review.pipeline import FreshPipeline
from fresh_review.transport import MetaRequestTransport, CURRENT_VISITOR_KEY
from fresh_test_helpers import response
from test_seamless_demo import _img, _empty_store, _carry
from test_byok_visitor_key import FakeOpener


def _parse(monkeypatch):
    async def parse(*a, **k):
        return {'objects': [{'object_id': '0', 'box_half_open': [0, 0, 20, 60], 'mask': Image.new('L', (20, 60), 255)}]}
    monkeypatch.setattr(m, 'parse_sam_image_text', parse)


def _synthetic_pipeline(tmp_path, monkeypatch, cap='5'):
    _parse(monkeypatch)
    calls = []

    def transport(body):
        calls.append(body)
        if body['model'] == 'sam-3.1':
            return b'data: {"type":"response.completed","response":{"model":"sam-3.1","id":"synthetic-sam","status":"completed","usage":{"images_processed":1},"output":[]}}\n\n'
        return response('unknown', 'absent')

    store = _empty_store(tmp_path, scope='synthetic_local_qualification')
    p = FreshPipeline(tmp_path / 'fresh.sqlite', **_carry(tmp_path, cap), execution_scope='synthetic_local_qualification',
                      approval_store=store, transport=transport)
    return p, calls


def _live_pipeline(tmp_path, monkeypatch, cap='5'):
    _parse(monkeypatch)
    approvals = tmp_path / 'approvals.json'
    from fresh_review.demo_approvals import SeamlessDemoApprovalStore
    store = SeamlessDemoApprovalStore(approvals, hashlib.sha256(approvals.read_bytes()).hexdigest(),
                                        scope='private_provider_processing')
    return FreshPipeline(tmp_path / 'fresh.sqlite', **_carry(tmp_path, cap), execution_scope='private_provider_processing',
                         approval_store=store, transport=MetaRequestTransport(opener=FakeOpener()))


def test_retained_synthetic_rows_do_not_block_live_claims_after_scope_switch(tmp_path, monkeypatch):
    synth, _ = _synthetic_pipeline(tmp_path, monkeypatch)
    raw1, frame1 = _img(color='blue')
    r1 = asyncio.run(synth.run(raw1, 'image/png', [], owner='acct-a'))
    assert r1['state'] == 'completed'

    live = _live_pipeline(tmp_path, monkeypatch)
    # Serving the retained synthetic result under the live scope stays refused.
    with pytest.raises(ValueError):
        live.read(frame1.digest, 'acct-a')
    # A new claim by a DIFFERENT account proceeds: retained rows verify under
    # their own recorded scope during the pre-spend hold check only.
    raw2, frame2 = _img(color='green')
    tok = CURRENT_VISITOR_KEY.set('test-visitor-key-not-real')
    try:
        r2 = asyncio.run(live.run(raw2, 'image/png', [], owner='acct-b'))
    finally:
        CURRENT_VISITOR_KEY.reset(tok)
    assert r2['state'] == 'completed', r2.get('notice')
    # The old row is still served-refused; the new result is present and owned.
    with pytest.raises(ValueError):
        live.read(frame1.digest, 'acct-a')
    assert live.read(frame2.digest, 'acct-b')['state'] == 'completed'


def test_tampered_or_unknown_recorded_scope_fails_closed(tmp_path, monkeypatch):
    synth, _ = _synthetic_pipeline(tmp_path, monkeypatch)
    raw1, frame1 = _img(color='blue')
    asyncio.run(synth.run(raw1, 'image/png', [], owner='acct-a'))
    live = _live_pipeline(tmp_path, monkeypatch)

    real_lookup = live.approval_store.lookup

    def bogus_lookup(source, size):
        spec = real_lookup(source, size)
        if source == frame1.digest:
            spec = dict(spec)
            spec['provenance'] = dict(spec['provenance'], scope='unknown-tampered-scope')
        return spec

    monkeypatch.setattr(live.approval_store, 'lookup', bogus_lookup)
    with pytest.raises(ValueError):
        live.read(frame1.digest, 'acct-a', retained_hold_verification=True)
    raw3, _ = _img(color='red')
    tok = CURRENT_VISITOR_KEY.set('test-visitor-key-not-real')
    try:
        with pytest.raises(ValueError):
            asyncio.run(live.run(raw3, 'image/png', [], owner='acct-c'))
    finally:
        CURRENT_VISITOR_KEY.reset(tok)


def _make_aux_rows(p, tmp_path, digest1, raw1, owner):
    """Create one retained row of each aux type (reserved_not_dispatched) under
    the pipeline's current scope. Returns expected reserved totals."""
    import hashlib as _hl
    from fresh_review.pipeline import digest as _dg
    from fresh_review.recheck_journal import RecheckJournal
    from fresh_review.ppe_segmentation import PpeSegmentation, BATCH_RESERVE
    from fresh_review.explanation_execution import ExplanationExecutor
    from fresh_review.spatial_explanation import build_spatial_request
    from fresh_review.ppe import MAX_COST

    job = p.read(digest1, owner)
    rsha = _dg(job['result'])
    # recheck attempt, reserved not dispatched
    rj = RecheckJournal(p)
    rj.reserve(digest1, '0', max_attempts=1, authority_reference='synthetic-only', owner=owner)
    # PPE mask batch, reserved not dispatched (exact pinned grant)
    h = PpeSegmentation(p)
    plan = h.plan(digest1, owner)
    grant = {'format': 'vigilens.exact-ppe-mask-grant.v1', 'execution_scope': p.execution_scope,
             'source_digest': digest1, 'result_sha256': plan['result_sha256'], 'plan_sha256': _dg(plan),
             'max_reserved_usd': str(BATCH_RESERVE), 'authority_reference': 'synthetic-only'}
    gpath = tmp_path / 'synthetic-mask-grant.json'
    enc = json.dumps(grant).encode(); gpath.write_bytes(enc); gpath.chmod(0o600)
    h2 = PpeSegmentation(p, approval_path=gpath, approval_sha256=_hl.sha256(enc).hexdigest())
    h2.reserve(digest1, owner)
    # explanation attempt, reserved not dispatched (exact pinned grant)
    zone_view = {'source_digest': digest1, 'result_sha256': rsha}
    rule_review = {'source_digest': digest1, 'result_sha256': rsha,
                   'status': 'private_operator_rules_evaluated_not_safety_clearance',
                   'persons': [], 'policy_sha256': '0' * 64, 'report_visible_observations': []}
    xplan = build_spatial_request(raw1, job['result'], zone_view, rule_review, [])
    xgrant = {'format': 'vigilens.exact-explanation-grant.v1', 'execution_scope': p.execution_scope,
              'plan_sha256': _dg(xplan), 'maximum_reserved_usd': str(MAX_COST),
              'authority_reference': 'synthetic-only'}
    xpath = tmp_path / 'synthetic-explanation-grant.json'
    xenc = json.dumps(xgrant).encode(); xpath.write_bytes(xenc); xpath.chmod(0o600)
    xe = ExplanationExecutor(p, approval_path=xpath, approval_sha256=_hl.sha256(xenc).hexdigest())
    xe.reserve(xplan, owner)


def test_aux_rows_reserved_not_dispatched_do_not_block_live_claims(tmp_path, monkeypatch):
    synth, _ = _synthetic_pipeline(tmp_path, monkeypatch, cap='20')
    raw1, frame1 = _img(color='blue')
    r1 = asyncio.run(synth.run(raw1, 'image/png', [], owner='acct-a'))
    assert r1['state'] == 'completed'
    _make_aux_rows(synth, tmp_path, frame1.digest, raw1, 'acct-a')

    live = _live_pipeline(tmp_path, monkeypatch, cap='20')
    # accounting on the live service still counts every retained reservation
    from fresh_review.recheck_journal import reservation_total
    from fresh_review.ppe_segmentation import total as mask_total, BATCH_RESERVE
    from fresh_review.explanation_execution import total as explanation_total
    from fresh_review.ppe import MAX_COST
    from decimal import Decimal
    c = live.connect()
    try:
        assert Decimal(reservation_total(c)) > 0
        assert Decimal(mask_total(c)) == BATCH_RESERVE
        assert Decimal(explanation_total(c)) == MAX_COST
    finally:
        c.close()
    raw2, frame2 = _img(color='green')
    tok = CURRENT_VISITOR_KEY.set('test-visitor-key-not-real')
    try:
        r2 = asyncio.run(live.run(raw2, 'image/png', [], owner='acct-b'))
    finally:
        CURRENT_VISITOR_KEY.reset(tok)
    assert r2['state'] == 'completed', r2.get('notice')
    # strict serve of the retained synthetic source stays refused
    with pytest.raises(ValueError):
        live.read(frame1.digest, 'acct-a')
    # tamper with one aux row -> fail closed on the next new claim
    c = live.connect()
    try:
        c.execute("UPDATE recheck_attempts SET reserved='0'")
        c.commit()
    finally:
        c.close()
    raw3, _ = _img(color='red')
    tok = CURRENT_VISITOR_KEY.set('test-visitor-key-not-real')
    try:
        with pytest.raises(ValueError):
            asyncio.run(live.run(raw3, 'image/png', [], owner='acct-c'))
    finally:
        CURRENT_VISITOR_KEY.reset(tok)


def test_uncertain_aux_row_verifies_and_counts_in_full_after_switch(tmp_path, monkeypatch):
    synth, _ = _synthetic_pipeline(tmp_path, monkeypatch, cap='20')
    raw1, frame1 = _img(color='blue')
    assert asyncio.run(synth.run(raw1, 'image/png', [], owner='acct-a'))['state'] == 'completed'
    _make_aux_rows(synth, tmp_path, frame1.digest, raw1, 'acct-a')
    c = synth.connect()
    try:
        c.execute("UPDATE recheck_attempts SET state='attempted_uncertain'")
        c.commit()
    finally:
        c.close()
    live = _live_pipeline(tmp_path, monkeypatch, cap='20')
    raw2, _ = _img(color='green')
    tok = CURRENT_VISITOR_KEY.set('test-visitor-key-not-real')
    try:
        r2 = asyncio.run(live.run(raw2, 'image/png', [], owner='acct-b'))
    finally:
        CURRENT_VISITOR_KEY.reset(tok)
    assert r2['state'] == 'completed', r2.get('notice')
    # the uncertain aux reservation still counts in full in booked accounting
    from fresh_review.recheck_journal import reservation_total, RECHECK_RESERVE
    from decimal import Decimal
    c = live.connect()
    try:
        assert Decimal(reservation_total(c)) == RECHECK_RESERVE
    finally:
        c.close()


def test_aux_reserve_on_live_job_with_retained_synthetic_rows(tmp_path, monkeypatch):
    """Retained synthetic rows (jobs + all 3 aux types) must not block NEW aux
    reservations on a LIVE job: reserve accounting re-verifies retained rows
    under their own recorded scope, while the new row's own grant/plan/dispatch
    stay bound to the current scope. A synthetic-scoped grant on a live job is
    refused; serving a synthetic aux row under the live scope stays refused."""
    import hashlib as _hl
    from fresh_review.pipeline import digest as _dg
    from fresh_review.recheck_journal import RecheckJournal
    from fresh_review.ppe_segmentation import PpeSegmentation, BATCH_RESERVE
    from fresh_review.explanation_execution import ExplanationExecutor
    from fresh_review.spatial_explanation import build_spatial_request
    from fresh_review.ppe import MAX_COST

    synth, _ = _synthetic_pipeline(tmp_path, monkeypatch, cap='20')
    raw1, frame1 = _img(color='blue')
    assert asyncio.run(synth.run(raw1, 'image/png', [], owner='acct-a'))['state'] == 'completed'
    _make_aux_rows(synth, tmp_path, frame1.digest, raw1, 'acct-a')
    synthetic_batch = PpeSegmentation(synth).plan(frame1.digest, 'acct-a')  # for refusal check below

    live = _live_pipeline(tmp_path, monkeypatch, cap='20')
    raw2, frame2 = _img(color='green')
    tok = CURRENT_VISITOR_KEY.set('test-visitor-key-not-real')
    try:
        assert asyncio.run(live.run(raw2, 'image/png', [], owner='acct-b'))['state'] == 'completed'
    finally:
        CURRENT_VISITOR_KEY.reset(tok)
    job2 = live.read(frame2.digest, 'acct-b')

    # 1. recheck reserve on the live job succeeds despite retained synthetic rows
    r = RecheckJournal(live).reserve(frame2.digest, '0', max_attempts=1,
                                     authority_reference='live-test', owner='acct-b')
    assert r['state'] == 'reserved_not_dispatched'

    # 2. PPE batch reserve on the live job with a valid LIVE-scope grant succeeds
    h = PpeSegmentation(live)
    plan = h.plan(frame2.digest, 'acct-b')
    grant = {'format': 'vigilens.exact-ppe-mask-grant.v1', 'execution_scope': 'private_provider_processing',
             'source_digest': frame2.digest, 'result_sha256': plan['result_sha256'],
             'plan_sha256': _dg(plan), 'max_reserved_usd': str(BATCH_RESERVE),
             'authority_reference': 'live-test'}
    gpath = tmp_path / 'live-mask-grant.json'
    enc = json.dumps(grant).encode(); gpath.write_bytes(enc); gpath.chmod(0o600)
    h2 = PpeSegmentation(live, approval_path=gpath, approval_sha256=_hl.sha256(enc).hexdigest())
    live_batch = h2.reserve(frame2.digest, 'acct-b')
    assert PpeSegmentation(live).read(live_batch)['state'] == 'reserved_not_dispatched'

    # 3. explanation reserve on the live job with a valid LIVE-scope grant succeeds
    rsha2 = _dg(job2['result'])
    zone_view = {'source_digest': frame2.digest, 'result_sha256': rsha2}
    rule_review = {'source_digest': frame2.digest, 'result_sha256': rsha2,
                   'status': 'private_operator_rules_evaluated_not_safety_clearance',
                   'persons': [], 'policy_sha256': '0' * 64, 'report_visible_observations': []}
    xplan = build_spatial_request(raw2, job2['result'], zone_view, rule_review, [])
    xgrant = {'format': 'vigilens.exact-explanation-grant.v1', 'execution_scope': 'private_provider_processing',
              'plan_sha256': _dg(xplan), 'maximum_reserved_usd': str(MAX_COST),
              'authority_reference': 'live-test'}
    xpath = tmp_path / 'live-explanation-grant.json'
    xenc = json.dumps(xgrant).encode(); xpath.write_bytes(xenc); xpath.chmod(0o600)
    xe = ExplanationExecutor(live, approval_path=xpath, approval_sha256=_hl.sha256(xenc).hexdigest())
    assert xe.reserve(xplan, 'acct-b')

    # 4. a SYNTHETIC-scoped grant approving spend on the live job is refused
    bad = dict(grant, execution_scope='synthetic_local_qualification')
    bpath = tmp_path / 'bad-grant.json'
    benc = json.dumps(bad).encode(); bpath.write_bytes(benc); bpath.chmod(0o600)
    hb = PpeSegmentation(live, approval_path=bpath, approval_sha256=_hl.sha256(benc).hexdigest())
    with pytest.raises(ValueError):
        hb.reserve(frame2.digest, 'acct-b')

    # 5. serving the retained synthetic batch under the live scope stays refused
    syn_id = _dg({'owner': 'acct-a', 'source': frame1.digest,
                  'result_sha': synthetic_batch['result_sha256'], 'plan_sha': _dg(synthetic_batch)})
    with pytest.raises(ValueError):
        PpeSegmentation(live).read(syn_id)
