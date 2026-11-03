"""Auxiliary executor readiness gate (v6.2): recheck / SAM PPE / explanation
executors share FreshPipeline.require_dispatch_ready, checked BEFORE the
reserved_not_dispatched -> attempted_uncertain transition. Under the hosted
BYOK wiring (MetaRequestTransport) with the gate off or no request visitor key,
a run() refuses with ZERO state change: the attempt stays reserved, no call is
attempted, and retry/completed-result semantics are unchanged. Canned opener
only; no network."""
import asyncio, hashlib, json
import pytest
from PIL import Image

import fresh_review.pipeline as m
from fresh_review.pipeline import FreshPipeline, digest
from fresh_review.recheck_journal import RecheckJournal, RECHECK_RESERVE
from fresh_review.recheck_execution import RecheckExecutor
from fresh_review.ppe_segmentation import PpeSegmentation, BATCH_RESERVE
from fresh_review.transport import MetaRequestTransport, CURRENT_VISITOR_KEY
from adapters import LiveTransportDisabled
from test_seamless_demo import _img, _empty_store, _carry
from test_byok_visitor_key import FakeOpener


def _live(tmp_path, monkeypatch):
    async def parse(*a, **k):
        return {'objects': [{'object_id': '0', 'box_half_open': [0, 0, 20, 60], 'mask': Image.new('L', (20, 60), 255)}]}
    monkeypatch.setattr(m, 'parse_sam_image_text', parse)
    import fresh_review.recheck_execution as re_mod
    monkeypatch.setattr(re_mod, 'parse_sam_image_text', parse)
    monkeypatch.setenv('VIGILENS_LIVE_DISPATCH', 'on')
    opener = FakeOpener()
    store = _empty_store(tmp_path, scope='private_provider_processing')
    p = FreshPipeline(tmp_path / 'fresh.sqlite', **_carry(tmp_path, '5'), execution_scope='private_provider_processing',
                      approval_store=store, transport=MetaRequestTransport(opener=opener))
    return p, opener


def _completed_original(p, tmp_path):
    raw, frame = _img(color='blue')
    tok = CURRENT_VISITOR_KEY.set('test-visitor-key-not-real')
    try:
        job = asyncio.run(p.run(raw, 'image/png', [], owner='acct-a'))
    finally:
        CURRENT_VISITOR_KEY.reset(tok)
    assert job['state'] == 'completed', job.get('notice')
    return raw, frame, job


def _recheck(p, frame, tmp_path):
    attempt = RecheckJournal(p).reserve(frame.digest, '0', max_attempts=1, authority_reference='synthetic-exact-request-authority')
    plan = attempt['plan']
    grant = {'format': 'vigilens.exact-recheck-approval.v1', 'execution_scope': p.execution_scope,
             'source_digest': frame.digest, 'result_sha256': plan['result_sha256'], 'person_id': '0',
             'plan_sha256': digest(plan), 'authority_reference': 'synthetic-exact-request-authority',
             'request_sha256': [s['request_sha256'] for s in plan['steps']], 'max_reserved_usd': str(RECHECK_RESERVE)}
    path = tmp_path / 'recheck-grant.json'
    raw = json.dumps(grant).encode(); path.write_bytes(raw); path.chmod(0o600)
    return RecheckExecutor(p, approval_path=path, approval_sha256=hashlib.sha256(raw).hexdigest()), attempt


def _ppe(p, frame, tmp_path):
    h = PpeSegmentation(p)
    plan = h.plan(frame.digest)
    grant = {'format': 'vigilens.exact-ppe-mask-grant.v1', 'execution_scope': p.execution_scope,
             'source_digest': frame.digest, 'result_sha256': plan['result_sha256'],
             'plan_sha256': digest(plan), 'max_reserved_usd': str(BATCH_RESERVE),
             'authority_reference': 'synthetic-only-not-owner-grant'}
    path = tmp_path / 'mask-grant.json'
    raw = json.dumps(grant).encode(); path.write_bytes(raw); path.chmod(0o600)
    h = PpeSegmentation(p, approval_path=path, approval_sha256=hashlib.sha256(raw).hexdigest())
    return h, h.reserve(frame.digest)


class TestRecheckGateIsZeroState:
    def test_gate_off_refuses_before_any_state_change(self, tmp_path, monkeypatch):
        p, opener = _live(tmp_path, monkeypatch)
        raw, frame, job = _completed_original(p, tmp_path)
        executor, attempt = _recheck(p, frame, tmp_path)
        calls_before = len(opener.requests)
        monkeypatch.delenv('VIGILENS_LIVE_DISPATCH')
        tok = CURRENT_VISITOR_KEY.set('test-visitor-key-not-real')  # key alone is not enough
        try:
            with pytest.raises(LiveTransportDisabled):
                asyncio.run(executor.run(attempt['attempt_id']))
        finally:
            CURRENT_VISITOR_KEY.reset(tok)
        assert len(opener.requests) == calls_before                       # no call attempted
        assert executor.read(attempt['attempt_id'])['state'] == 'reserved_not_dispatched'  # no wedge
        # Gate restored: the SAME attempt still runs (refusal destroyed nothing).
        monkeypatch.setenv('VIGILENS_LIVE_DISPATCH', 'on')
        tok = CURRENT_VISITOR_KEY.set('test-visitor-key-not-real')
        try:
            out = asyncio.run(executor.run(attempt['attempt_id']))
        finally:
            CURRENT_VISITOR_KEY.reset(tok)
        assert out['state'] == 'completed'

    def test_keyless_refuses_before_any_state_change(self, tmp_path, monkeypatch):
        p, opener = _live(tmp_path, monkeypatch)
        raw, frame, job = _completed_original(p, tmp_path)
        executor, attempt = _recheck(p, frame, tmp_path)
        calls_before = len(opener.requests)
        # Gate on, but NO request visitor key (exactly the upload/clip route context).
        with pytest.raises(LiveTransportDisabled):
            asyncio.run(executor.run(attempt['attempt_id']))
        assert len(opener.requests) == calls_before
        assert executor.read(attempt['attempt_id'])['state'] == 'reserved_not_dispatched'


class TestPpeGateIsZeroState:
    def test_keyless_refuses_before_any_state_change(self, tmp_path, monkeypatch):
        p, opener = _live(tmp_path, monkeypatch)
        raw, frame, job = _completed_original(p, tmp_path)
        h, identity = _ppe(p, frame, tmp_path)
        calls_before = len(opener.requests)
        with pytest.raises(LiveTransportDisabled):
            asyncio.run(h.run(identity))
        assert len(opener.requests) == calls_before
        assert h.read(identity)['state'] == 'reserved_not_dispatched'
        # Gate fully on: the same batch completes.
        tok = CURRENT_VISITOR_KEY.set('test-visitor-key-not-real')
        try:
            out = asyncio.run(h.run(identity))
        finally:
            CURRENT_VISITOR_KEY.reset(tok)
        assert out['state'] == 'completed'


class TestSyntheticAuxFlowUnchanged:
    def test_disabled_transport_message_preserved(self, tmp_path, monkeypatch):
        """The pre-existing disabled_transport refusal keeps its exact shape
        (route tests match on it): now raised via the shared gate."""
        from fresh_review.pipeline import disabled_transport
        store = _empty_store(tmp_path, scope='synthetic_local_qualification')
        p = FreshPipeline(tmp_path / 'fresh.sqlite', **_carry(tmp_path, '5'), execution_scope='synthetic_local_qualification',
                          approval_store=store, transport=disabled_transport)
        with pytest.raises(LiveTransportDisabled, match='Recheck dispatch not enabled; no claim, state change or call created'):
            p.require_dispatch_ready('Recheck')
