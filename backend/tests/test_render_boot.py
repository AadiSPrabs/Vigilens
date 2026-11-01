"""Render durable boot: DSN normalization, idempotent seeding, restart adoption,
and an end-to-end governed flow on a fully PG-backed booted service."""
import hashlib
import json

import pytest

from render_boot import boot_pg_service, normalize_dsn, _seed_document
from fresh_review.db import open_store


@pytest.fixture()
def pg_uri(tmp_path):
    pgserver = pytest.importorskip('pgserver')
    srv = pgserver.get_server(str(tmp_path / 'pg'))
    yield srv.get_uri()
    srv.cleanup()


def test_normalize_dsn():
    # Local/socket DSNs pass unchanged.
    assert normalize_dsn('postgresql://postgres:@/postgres?host=/run/postgresql') == \
        'postgresql://postgres:@/postgres?host=/run/postgresql'
    assert normalize_dsn('postgresql://u:p@localhost/db') == 'postgresql://u:p@localhost/db'
    # Render-style internal hostname without sslmode gets require appended.
    assert normalize_dsn('postgresql://u:p@dpg-abc-a/db') == \
        'postgresql://u:p@dpg-abc-a/db?sslmode=require'
    assert normalize_dsn('postgresql://u:p@dpg-abc-a/db?application_name=x') == \
        'postgresql://u:p@dpg-abc-a/db?application_name=x&sslmode=require'
    # An explicit verifying mode is kept.
    assert normalize_dsn('postgresql://u:p@db.example.com/db?sslmode=verify-full').endswith('verify-full')
    # A plaintext external mode is refused.
    with pytest.raises(ValueError, match='TLS'):
        normalize_dsn('postgresql://u:p@dpg-abc-a/db?sslmode=disable')


def test_boot_idempotent_and_restart_adopts(pg_uri):
    from fresh_review.synthetic_transport import SyntheticTransport
    kw = dict(cap='5', scope='synthetic_local_qualification', seamless=True,
              transport=SyntheticTransport())
    s1 = boot_pg_service(pg_uri, **kw)
    sha1 = s1.carry_sha
    s2 = boot_pg_service(pg_uri, **kw)  # redeploy: same database
    assert s2.carry_sha == sha1  # same seeded checkpoint, no re-seed drift
    # Boot adoption: a pre-existing document wins over the computed seed.
    raw = (json.dumps({'blocked_source_digests': [], 'provider_calls_total': 3,
                       'conservative_booked_usd': '0.5', 'aggregate_cap_usd': '5',
                       'provenance': 'pre-existing'}, sort_keys=True) + '\n').encode()
    c = open_store(pg_uri)
    c.execute("UPDATE documents SET raw=? WHERE name='carry'", (raw,))
    c.commit()
    c.close()
    s3 = boot_pg_service(pg_uri, **kw)
    assert s3.carry_sha == hashlib.sha256(raw).hexdigest()
    assert s3.carry()['provider_calls_total'] == 3  # adopted, not overwritten


def test_booted_service_full_governed_flow_on_pg(pg_uri, tmp_path, monkeypatch):
    import fresh_review.pipeline as m
    from fastapi.testclient import TestClient
    from PIL import Image
    from app import create_app
    from fresh_review.synthetic_transport import SyntheticTransport
    from test_seamless_demo import _img

    async def parse(*a, **k):
        return {'objects': [{'object_id': '0', 'box_half_open': [0, 0, 20, 60], 'mask': Image.new('L', (20, 60), 255)}]}
    monkeypatch.setattr(m, 'parse_sam_image_text', parse)
    kw = dict(cap='5', scope='synthetic_local_qualification', seamless=True,
              transport=SyntheticTransport())
    service = boot_pg_service(pg_uri, **kw)
    c = TestClient(create_app(fresh_service=service))
    raw, f = _img()
    A = 'cc' * 32
    r = c.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
               headers={'X-Vigilens-Display-Session': A})
    assert r.status_code == 200, r.text
    # REDEPLOY: brand-new boot over the same database - result and approval
    # recording both survived; re-POST reuses with zero re-dispatch.
    service2 = boot_pg_service(pg_uri, **kw)
    c2 = TestClient(create_app(fresh_service=service2))
    job = service2.read(f.digest)
    assert job is not None and job['state'] == 'completed'
    r2 = c2.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
                 headers={'X-Vigilens-Display-Session': A})
    assert r2.status_code == 200, r2.text
