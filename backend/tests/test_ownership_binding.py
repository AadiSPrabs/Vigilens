"""Per-account ownership binding with BYOK key provenance.

Account identity is the server-derived X-Vigilens-Display-Session hash (stable
per authenticated account across browsers and key TTL; see vigilens-proxy.ts).
The visitor key fingerprint is charging provenance recorded on the job: rotating
a key never strands the account's stored results, and two accounts sharing one
key still get isolated jobs. Held-uncertain stays journal-GLOBAL (no-retry).
Same expectations on sqlite and Postgres. All keys below are synthetic
stand-ins, never real provider keys.
"""
import hashlib

import pytest
from fastapi.testclient import TestClient

from app import create_app
from test_fresh_upload_pipeline import setup as _setup

A = 'aa' * 32  # display-session VALUES stand in for proxy-derived hashes (64-hex)
B = 'bb' * 32
KEY1 = 'visitor-key-one-' + 'k' * 48
KEY2 = 'visitor-key-two-' + 'k' * 48
GOV = '/fresh-review-audit-governed'


def _owner(who):
    return hashlib.sha256(who.encode()).hexdigest()


def _key_fp(key):
    return hashlib.sha256(b'vigilens-visitor-key:' + key.encode()).hexdigest()


def _client(p):
    return TestClient(create_app(fresh_service=p))


def _upload(c, raw, who, key=None):
    from fresh_review.transport import CURRENT_VISITOR_KEY
    tok = CURRENT_VISITOR_KEY.set(key) if key else None
    try:
        return c.post(GOV, files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
                      headers={'X-Vigilens-Display-Session': who})
    finally:
        if tok is not None:
            CURRENT_VISITOR_KEY.reset(tok)


def _run_both_backends(request, tmp_path, monkeypatch, backend):
    p, raw, frame, calls = _setup(tmp_path, monkeypatch)
    if backend == 'pg':
        pgserver = pytest.importorskip('pgserver')
        srv = pgserver.get_server(str(tmp_path / 'pg'))
        from fresh_review.pipeline import FreshPipeline
        p = FreshPipeline(srv.get_uri(), carry_path=p.carry_path, carry_sha=p.carry_sha,
                          execution_scope='synthetic_local_qualification',
                          approval_store=p.approval_store, transport=p.transport)
        request.addfinalizer(srv.cleanup)
    return p, raw, frame, calls


@pytest.mark.parametrize('backend', ['sqlite', 'pg'])
def test_completed_result_is_account_bound(request, tmp_path, monkeypatch, backend):
    p, raw, frame, calls = _run_both_backends(request, tmp_path, monkeypatch, backend)
    c = _client(p)
    r = _upload(c, raw, A)
    assert r.status_code == 200, r.text
    n = len(calls)
    # Same account (second browser = same derived session value): reuse, zero dispatch.
    assert _upload(c, raw, A).status_code == 200
    assert len(calls) == n
    # Different account, same bytes: never served A's result - own analysis under its own key.
    r2 = _upload(c, raw, B)
    assert r2.status_code == 200, r2.text
    assert len(calls) > n
    job_a = p.read(frame.digest, _owner(A))
    job_b = p.read(frame.digest, _owner(B))
    assert job_a['owner'] == _owner(A) and job_b['owner'] == _owner(B)
    assert job_a['result'] == job_b['result']  # same deterministic synthetic analysis


@pytest.mark.parametrize('backend', ['sqlite', 'pg'])
def test_two_accounts_sharing_one_key_stay_isolated(request, tmp_path, monkeypatch, backend):
    p, raw, frame, calls = _run_both_backends(request, tmp_path, monkeypatch, backend)
    c = _client(p)
    assert _upload(c, raw, A, key=KEY1).status_code == 200
    n = len(calls)
    # Same key, different account: still a separate namespaced job, separate dispatch.
    assert _upload(c, raw, B, key=KEY1).status_code == 200
    assert len(calls) > n
    job_a = p.read(frame.digest, _owner(A))
    job_b = p.read(frame.digest, _owner(B))
    assert job_a['key_fp'] == job_b['key_fp'] == _key_fp(KEY1)
    assert job_a['owner'] != job_b['owner']


@pytest.mark.parametrize('backend', ['sqlite', 'pg'])
def test_same_account_key_rotation_keeps_access(request, tmp_path, monkeypatch, backend):
    p, raw, frame, calls = _run_both_backends(request, tmp_path, monkeypatch, backend)
    c = _client(p)
    assert _upload(c, raw, A, key=KEY1).status_code == 200
    n = len(calls)
    # The account forgot/rotated its key: its stored results stay accessible, no redispatch.
    assert _upload(c, raw, A, key=KEY2).status_code == 200
    assert len(calls) == n
    job = p.read(frame.digest, _owner(A))
    assert job['owner'] == _owner(A)
    assert job['key_fp'] == _key_fp(KEY1)  # original charging provenance retained


@pytest.mark.parametrize('backend', ['sqlite', 'pg'])
def test_uncertain_hold_is_journal_global_across_accounts(request, tmp_path, monkeypatch, backend):
    p, raw, frame, calls = _run_both_backends(request, tmp_path, monkeypatch, backend)
    orig = p.transport

    def boom(body):
        raise IOError('synthetic mid-dispatch failure')

    p.transport = boom
    c = _client(p)
    r = _upload(c, raw, A)
    assert r.status_code == 409 and r.json()['detail']['code'] == 'ATTEMPT_UNCERTAIN'
    p.transport = orig
    # Any account re-presenting the held bytes sees the hold; no retry, no new dispatch.
    for who in (A, B):
        r = _upload(c, raw, who)
        assert r.status_code == 409 and r.json()['detail']['code'] == 'ATTEMPT_UNCERTAIN', (who, r.text)
    assert len(calls) == 0  # synthetic driver records only successful transports; boom added none


@pytest.mark.parametrize('backend', ['sqlite', 'pg'])
def test_raw_key_never_stored_in_journal(request, tmp_path, monkeypatch, backend):
    p, raw, frame, calls = _run_both_backends(request, tmp_path, monkeypatch, backend)
    c = _client(p)
    assert _upload(c, raw, A, key=KEY1).status_code == 200
    job = p.read(frame.digest, _owner(A))
    assert job['key_fp'] == _key_fp(KEY1)
    db = p.connect()
    try:
        for table in ('jobs', 'calls'):
            for row in db.execute(f'SELECT * FROM {table}').fetchall():
                assert all(KEY1 not in str(v) for v in row)
    finally:
        db.close()
