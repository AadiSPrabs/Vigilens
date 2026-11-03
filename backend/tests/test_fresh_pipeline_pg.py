"""FreshPipeline on the Postgres backend: full lifecycle, restart durability,
reuse without re-dispatch, and held-uncertain semantics. Real local PG (pgserver);
carry/approvals stay pinned FILES in this slice (their own port is a later slice).
The sqlite legacy path is covered by the unchanged existing suite.
"""
import hashlib

import pytest
from fastapi.testclient import TestClient

from app import create_app
from fresh_review.demo_approvals import SeamlessDemoApprovalStore
from fresh_review.pipeline import FreshPipeline
import fresh_review.pipeline as m
from fresh_test_helpers import response
from test_seamless_demo import _img, _carry


def _store(tmp_path, scope='synthetic_local_qualification'):
    # Open the pinned approval store; create it empty only on first use. A
    # "restart" must see the SAME recorded approvals a prior process wrote.
    path = tmp_path / 'approvals.json'
    if path.exists():
        raw = path.read_bytes()
    else:
        raw = b'{"version":1,"approvals":{}}\n'
        path.write_bytes(raw)
        path.chmod(0o600)
    return SeamlessDemoApprovalStore(path, hashlib.sha256(raw).hexdigest(), scope=scope)

A = 'dd' * 32


@pytest.fixture()
def pg_uri(tmp_path):
    pgserver = pytest.importorskip('pgserver')
    srv = pgserver.get_server(str(tmp_path / 'pg'))
    yield srv.get_uri()
    srv.cleanup()


def _pg_pipeline(pg_uri, tmp_path, monkeypatch, transport):
    from PIL import Image
    async def parse(*a, **k):
        return {'objects': [{'object_id': '0', 'box_half_open': [0, 0, 20, 60], 'mask': Image.new('L', (20, 60), 255)}]}
    monkeypatch.setattr(m, 'parse_sam_image_text', parse)
    store = _store(tmp_path)
    return FreshPipeline(pg_uri, **_carry(tmp_path), execution_scope='synthetic_local_qualification',
                         approval_store=store, transport=transport)


def test_pg_full_lifecycle_restart_and_reuse(pg_uri, tmp_path, monkeypatch):
    calls = []
    def transport(body):
        calls.append(body)
        if body['model'] == 'sam-3.1':
            return b'data: {"type":"response.completed","response":{"model":"sam-3.1","id":"synthetic-sam","status":"completed","usage":{"images_processed":1},"output":[]}}\n\n'
        return response('unknown', 'absent')
    p = _pg_pipeline(pg_uri, tmp_path, monkeypatch, transport)
    c = TestClient(create_app(fresh_service=p))
    raw, f = _img()
    r = c.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
               headers={'X-Vigilens-Display-Session': A})
    assert r.status_code == 200, r.text
    n = len(calls)
    assert n >= 2  # SAM + at least one PPE call recorded

    # RESTART: a brand-new pipeline object over the same database (process death
    # in between is exactly the Render redeploy/spin-down case).
    p2 = _pg_pipeline(pg_uri, tmp_path, monkeypatch, transport)
    c2 = TestClient(create_app(fresh_service=p2))
    job = p2.read(f.digest)
    assert job is not None and job['state'] == 'completed'
    r2 = c2.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
                 headers={'X-Vigilens-Display-Session': A})
    assert r2.status_code == 200, r2.text
    assert len(calls) == n  # reuse from the durable store: ZERO re-dispatch


def test_pg_uncertain_attempt_held_no_retry(pg_uri, tmp_path, monkeypatch):
    calls = []
    def transport(body):
        calls.append(body)
        raise OSError('simulated provider outage mid-dispatch')
    p = _pg_pipeline(pg_uri, tmp_path, monkeypatch, transport)
    c = TestClient(create_app(fresh_service=p))
    raw, f = _img()
    r = c.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
               headers={'X-Vigilens-Display-Session': A})
    assert r.status_code == 409, r.text  # attempted_uncertain: held, not retried
    r2 = c.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
                headers={'X-Vigilens-Display-Session': A})
    assert r2.status_code == 409
    # A restart must NOT clear the hold: uncertain survives process death on PG.
    p2 = _pg_pipeline(pg_uri, tmp_path, monkeypatch, transport)
    c3 = TestClient(create_app(fresh_service=p2))
    r3 = c3.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
                 headers={'X-Vigilens-Display-Session': A})
    assert r3.status_code == 409
    assert len(calls) == 1  # exactly one attempted dispatch, ever


def test_pg_governed_route_contention_maps_to_409(pg_uri, tmp_path, monkeypatch):
    # Gate 1+4 at the route boundary: with the fencing lock held by another
    # instance, the governed route answers a bounded 409 (its standard governed
    # refusal), never an unhandled 500 from a leaked psycopg error.
    from fresh_review.db import open_store
    holder = open_store(pg_uri)
    holder.execute('BEGIN IMMEDIATE')
    try:
        p = _pg_pipeline(pg_uri, tmp_path, monkeypatch, lambda body: b'')
        c = TestClient(create_app(fresh_service=p), raise_server_exceptions=False)
        raw, _f = _img()
        r = c.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
                   headers={'X-Vigilens-Display-Session': A})
        assert r.status_code == 409, r.text
    finally:
        holder.rollback()
        holder.close()


def test_pg_legacy_journal_schema_hard_refuses_preserving_records(pg_uri, tmp_path, monkeypatch):
    # A Postgres journal whose jobs primary key is not (owner, source) carries
    # history this code has not verified: refuse loudly, preserve every record.
    import psycopg
    with psycopg.connect(pg_uri, autocommit=True) as c:
        c.execute("CREATE TABLE jobs(source TEXT PRIMARY KEY,state TEXT,reserved TEXT,cost TEXT,binding TEXT,result TEXT,result_sha TEXT,started DOUBLE PRECISION,key_fp TEXT)")
        c.execute("INSERT INTO jobs VALUES('paid-source','completed','1','0.0025','{}',NULL,NULL,1.0,NULL)")
    p = _pg_pipeline(pg_uri, tmp_path, monkeypatch, lambda body: response('unknown', 'absent'))
    with pytest.raises(ValueError) as e:
        p.connect()
    assert 'Legacy Postgres journal schema' in str(e.value)
    with psycopg.connect(pg_uri) as c:
        assert c.execute("SELECT state FROM jobs WHERE source='paid-source'").fetchone()[0] == 'completed'
