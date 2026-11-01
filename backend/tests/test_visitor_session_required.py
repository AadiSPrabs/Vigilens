"""Structural visitor-session requirement (reviewer invariant).

Every visitor route REQUIRES a well-formed X-Vigilens-Display-Session header
(the proxy's displaySessionFor value: 64 lowercase hex chars). A missing or
malformed header is 403 BEFORE any write or dispatch - it must never fall back
into the internal/operator namespace (''). The local-access token gates the
install, not the account; it is never a substitute for the session header.
"""
import pytest
from fastapi.testclient import TestClient

from app import create_app
from test_fresh_upload_pipeline import setup

BAD = [None, '', 'short', 'z' * 64, 'A' * 64, 'a' * 63, 'a' * 65, 'not-a-session-value']


def _jobs(p):
    c = p.connect()
    try:
        return c.execute('SELECT owner,source FROM jobs').fetchall()
    finally:
        c.close()


@pytest.mark.parametrize('bad', BAD)
def test_upload_missing_or_malformed_session_403_no_write_no_dispatch(tmp_path, monkeypatch, bad):
    p, raw, frame, calls = setup(tmp_path, monkeypatch)
    c = TestClient(create_app(fresh_service=p))
    headers = {} if bad is None else {'X-Vigilens-Display-Session': bad}
    out = c.post('/fresh-review-upload', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'}, headers=headers)
    assert out.status_code == 403
    assert _jobs(p) == []            # no internal-namespace row, no account row
    assert calls == []               # no dispatch, no provider call
    out = c.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'}, headers=headers)
    assert out.status_code == 403
    assert _jobs(p) == [] and calls == []


@pytest.mark.parametrize('bad', BAD)
def test_bounded_loop_face_proposals_explanation_require_session(tmp_path, monkeypatch, bad):
    from test_fresh_upload_routes import OWNER
    import hashlib
    p, raw, frame, calls = setup(tmp_path, monkeypatch)
    import asyncio
    account = hashlib.sha256(OWNER.encode()).hexdigest()
    job = asyncio.run(p.run(raw, 'image/png', [], owner=account))
    assert job['state'] == 'completed'
    c = TestClient(create_app(fresh_service=p))
    headers = {} if bad is None else {'X-Vigilens-Display-Session': bad}
    before = len(calls)
    digest = frame.digest
    assert c.post('/fresh-review/' + digest + '/bounded-review-loop', json={'source_digest': digest, 'result_sha256': '0' * 64}, headers=headers).status_code == 403
    assert c.post('/fresh-review/' + digest + '/face-proposals', files={'image': ('x.png', raw, 'image/png')}, headers=headers).status_code == 403
    assert c.post('/fresh-private-report/some-session/explanation/some-attempt', json={}, headers=headers).status_code == 403
    assert c.get('/fresh-review/' + digest + '/frontend-audit', headers=headers).status_code == 403
    assert c.get('/fresh-review/' + digest + '/integration-contract', headers=headers).status_code == 403
    assert c.get('/fresh-review/' + digest + '/zone-review', headers=headers).status_code == 403
    assert len(calls) == before      # nothing dispatched through any of these
    # the account's stored job is untouched and no internal-namespace row appeared
    assert _jobs(p) == [(account, digest)] or set(_jobs(p)) == {(account, digest)}


def test_local_token_is_not_a_session_substitute(tmp_path, monkeypatch):
    # The install gate token plus no session header is still 403: the token
    # authorizes the install, never an account namespace.
    p, raw, frame, calls = setup(tmp_path, monkeypatch)
    c = TestClient(create_app(fresh_service=p))
    out = c.post('/fresh-review-upload', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'})
    assert out.status_code == 403 and _jobs(p) == [] and calls == []


@pytest.mark.parametrize('bad', BAD)
def test_status_route_requires_session(tmp_path, monkeypatch, bad):
    # GET /fresh-review/{source}: missing/malformed header is 403 before any read;
    # the route must never use the internal any-account view.
    from test_fresh_upload_routes import OWNER
    import hashlib, asyncio
    p, raw, frame, calls = setup(tmp_path, monkeypatch)
    account = hashlib.sha256(OWNER.encode()).hexdigest()
    job = asyncio.run(p.run(raw, 'image/png', [], owner=account))
    assert job['state'] == 'completed'
    c = TestClient(create_app(fresh_service=p))
    headers = {} if bad is None else {'X-Vigilens-Display-Session': bad}
    out = c.get('/fresh-review/' + frame.digest, headers=headers)
    assert out.status_code == 403


def test_status_route_account_isolation(tmp_path, monkeypatch):
    # Owner A's stored job is invisible to visitor B: B gets the generic 409,
    # never another account's result.
    import hashlib, asyncio
    p, raw, frame, calls = setup(tmp_path, monkeypatch)
    owner_a = hashlib.sha256(('ab' * 32).encode()).hexdigest()
    job = asyncio.run(p.run(raw, 'image/png', [], owner=owner_a))
    assert job['state'] == 'completed'
    c = TestClient(create_app(fresh_service=p))
    out = c.get('/fresh-review/' + frame.digest, headers={'X-Vigilens-Display-Session': 'bb' * 32})
    assert out.status_code == 409
    out = c.get('/fresh-review/' + frame.digest, headers={'X-Vigilens-Display-Session': 'ab' * 32})
    assert out.status_code == 200
    assert out.json()['state'] == 'completed'
