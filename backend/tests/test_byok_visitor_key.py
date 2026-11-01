"""BYOK visitor-key transport: request-scoped keys, pre-journal gating, no persistence.

The visitor's own Meta key arrives on X-Vigilens-Visitor-Key from the deploy proxy,
lives only in a request-scoped contextvar, and is never stored, logged or echoed.
Live dispatch stays gated by VIGILENS_LIVE_DISPATCH=on, strictly before any journal
write. All network here is a fake opener - no real provider contact.
"""
import json,sqlite3

import pytest
from fastapi.testclient import TestClient

from adapters import LiveTransportDisabled
from app import create_app
from fresh_review.pipeline import FreshPipeline
from fresh_review.ppe import canonical_body
from fresh_review.transport import MetaRequestTransport, CURRENT_VISITOR_KEY
from fresh_test_helpers import response
from test_seamless_demo import _img, _empty_store, _carry

import fresh_review.pipeline as m


class FakeResponse:
    def __init__(self, status=200, payload=b'{"ok":true}'):
        self.status = status; self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, n): return self.payload


class FakeOpener:
    """Returns the synthetic SAM/PPE payloads, keyed off the request body's model."""
    def __init__(self):
        self.requests = []
    def open(self, request, timeout=None):
        self.requests.append(request)
        body = json.loads(request.data)
        if body['model'] == 'sam-3.1':
            payload = b'data: {"type":"response.completed","response":{"model":"sam-3.1","id":"synthetic-sam","status":"completed","usage":{"images_processed":1},"output":[]}}\n\n'
        else:
            payload = response('unknown', 'absent')
        return FakeResponse(200, payload)


def _byok_pipeline(tmp_path, monkeypatch, opener):
    async def parse(*a, **k):
        from PIL import Image
        return {'objects': [{'object_id': '0', 'box_half_open': [0, 0, 20, 60], 'mask': Image.new('L', (20, 60), 255)}]}
    monkeypatch.setattr(m, 'parse_sam_image_text', parse)
    store = _empty_store(tmp_path, scope='private_provider_processing')
    p = FreshPipeline(tmp_path / 'fresh.sqlite', **_carry(tmp_path), execution_scope='private_provider_processing',
                      approval_store=store, transport=MetaRequestTransport(opener=opener))
    return p


def _job_count(path):
    c = sqlite3.connect(path)
    try:
        return c.execute('SELECT count(*) FROM jobs').fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        c.close()


def test_transport_uses_request_scoped_key_then_fails_closed():
    opener = FakeOpener()
    t = MetaRequestTransport(opener=opener)
    tok = CURRENT_VISITOR_KEY.set('visitor-key-abc-123')
    try:
        assert t(canonical_body(b'fake-crop')) == response('unknown', 'absent')
        req = opener.requests[0]
        assert req.get_header('Authorization') == 'Bearer visitor-key-abc-123'
    finally:
        CURRENT_VISITOR_KEY.reset(tok)
    with pytest.raises(LiveTransportDisabled):
        t(canonical_body(b'fake-crop'))
    assert len(opener.requests) == 1  # the fail-closed call never touched the network


def test_transport_rejects_malformed_key_before_network():
    opener = FakeOpener()
    t = MetaRequestTransport(opener=opener)
    tok = CURRENT_VISITOR_KEY.set('bad key with spaces')
    try:
        with pytest.raises(ValueError):
            t(canonical_body(b'fake-crop'))
    finally:
        CURRENT_VISITOR_KEY.reset(tok)
    assert len(opener.requests) == 0


def test_scope_invariant_covers_request_transport(tmp_path):
    store = _empty_store(tmp_path, scope='synthetic_local_qualification')
    with pytest.raises(ValueError):
        FreshPipeline(tmp_path / 'f.sqlite', **_carry(tmp_path), execution_scope='synthetic_local_qualification',
                      approval_store=store, transport=MetaRequestTransport(opener=FakeOpener()))


def test_route_refuses_before_journal_when_dispatch_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv('VIGILENS_LIVE_DISPATCH', raising=False)
    opener = FakeOpener()
    p = _byok_pipeline(tmp_path, monkeypatch, opener)
    c = TestClient(create_app(fresh_service=p))
    raw, f = _img()
    r = c.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
               headers={'X-Vigilens-Display-Session': 'a' * 64, 'X-Vigilens-Visitor-Key': 'visitor-secret-key-123'})
    assert r.status_code == 503, r.text
    assert _job_count(tmp_path / 'fresh.sqlite') == 0  # pre-journal: no intent, no reservation
    assert len(opener.requests) == 0
    assert 'visitor-secret-key-123' not in r.text  # never echoed


def test_route_refuses_without_key_when_dispatch_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv('VIGILENS_LIVE_DISPATCH', 'on')
    opener = FakeOpener()
    p = _byok_pipeline(tmp_path, monkeypatch, opener)
    c = TestClient(create_app(fresh_service=p))
    raw, f = _img()
    r = c.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
               headers={'X-Vigilens-Display-Session': 'a' * 64})
    assert r.status_code == 503, r.text
    assert _job_count(tmp_path / 'fresh.sqlite') == 0
    assert len(opener.requests) == 0


def test_route_dispatches_with_visitor_key_over_fake_http_and_result_outlives_key(tmp_path, monkeypatch):
    monkeypatch.setenv('VIGILENS_LIVE_DISPATCH', 'on')
    opener = FakeOpener()
    p = _byok_pipeline(tmp_path, monkeypatch, opener)
    c = TestClient(create_app(fresh_service=p))
    raw, f = _img()
    r = c.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
               headers={'X-Vigilens-Display-Session': 'a' * 64, 'X-Vigilens-Visitor-Key': 'visitor-secret-key-123'})
    assert r.status_code == 200, r.text
    assert _job_count(tmp_path / 'fresh.sqlite') == 1
    assert any(req.get_header('Authorization') == 'Bearer visitor-secret-key-123' for req in opener.requests)
    assert 'visitor-secret-key-123' not in r.text
    # Key forgotten + dispatch disabled again: the STORED result is still served, zero new calls.
    monkeypatch.delenv('VIGILENS_LIVE_DISPATCH')
    n = len(opener.requests)
    r2 = c.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
                headers={'X-Vigilens-Display-Session': 'a' * 64})
    assert r2.status_code == 200, r2.text
    assert len(opener.requests) == n
