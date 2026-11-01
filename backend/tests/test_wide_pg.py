"""Wide-scene and sequential pipelines on the Postgres backend: full lifecycle
plus restart durability, reusing the exact synthetic fixtures of the sqlite
wide tests. Artifacts (source PNG, request/reply sidecars) round-trip through
fresh_files BYTEA rows; the sqlite legacy path is covered by the untouched
original tests."""
import pytest

from test_wide_scene import wide as _wide_sqlite


@pytest.fixture()
def pg_uri(tmp_path):
    pgserver = pytest.importorskip('pgserver')
    srv = pgserver.get_server(str(tmp_path / 'pg'))
    yield srv.get_uri()
    srv.cleanup()


def _wide_pg(pg_uri, tmp_path, monkeypatch, **kw):
    p, raw, f, calls, objects = _wide_sqlite(tmp_path, monkeypatch, **kw)
    # Rebuild the SAME pipeline over PG: identical fixtures, carry and approval
    # pins; only the journal backend differs.
    from fresh_review.wide_scene import WideScenePipeline, WideLimits
    p2 = WideScenePipeline(pg_uri, carry_path=p.carry_path, carry_sha=p.carry_sha,
                           execution_scope='synthetic_local_qualification',
                           approval_store=p.approval_store, transport=p.transport,
                           wide_limits=WideLimits())
    return p2, raw, f, calls, objects


def test_wide_scene_pg_lifecycle_and_restart(pg_uri, tmp_path, monkeypatch):
    import asyncio
    p, raw, f, calls, _o = _wide_pg(pg_uri, tmp_path, monkeypatch)
    out = asyncio.run(p.run(raw, 'image/png', []))
    assert out['state'] == 'completed' and len(calls) == 3  # SAM + 2 selected crops

    # Restart: new pipeline object over the same database, same pins.
    from fresh_review.wide_scene import WideScenePipeline, WideLimits
    p2 = WideScenePipeline(pg_uri, carry_path=p.carry_path, carry_sha=p.carry_sha,
                           execution_scope='synthetic_local_qualification',
                           approval_store=p.approval_store, transport=p.transport,
                           wide_limits=WideLimits())
    job = p2.read(f.digest)
    assert job is not None and job['state'] == 'completed'
    out2 = asyncio.run(p2.run(raw, 'image/png', []))
    assert out2['state'] == 'completed'
    assert len(calls) == 3  # reuse from the durable store: zero re-dispatch


def test_wide_scene_pg_uncertain_held(pg_uri, tmp_path, monkeypatch):
    import asyncio
    p, raw, f, calls, _o = _wide_pg(pg_uri, tmp_path, monkeypatch, timeout=True)
    out = asyncio.run(p.run(raw, 'image/png', []))
    assert out['state'] == 'running_uncertain' and out['result'] is None
    out2 = asyncio.run(p.run(raw, 'image/png', []))
    assert out2['state'] == 'running_uncertain'
    assert len(calls) == 2  # attempted, held, never retried
