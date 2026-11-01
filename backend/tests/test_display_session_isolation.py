"""Cross-session (cross-account behind the proxy) isolation for stored results.

The deploy proxy derives one display-session value per authenticated account, so
the backend's possession-binding is what separates two judges' data. These tests
pin that contract: a session can only read a stored result after presenting the
exact image bytes (possession proof), re-presenting known bytes never
re-dispatches, and zone reviews are keyed per session, never per image.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app import create_app
from test_seamless_demo import _img, _empty_store, _pipeline

A = 'f0' * 32
B = 'e1' * 32


def _client(p):
    return TestClient(create_app(fresh_service=p))


def test_unbound_session_cannot_read_stored_result(tmp_path, monkeypatch):
    store = _empty_store(tmp_path)
    p, calls = _pipeline(tmp_path, monkeypatch, store)
    c = _client(p)
    raw, f = _img(color='blue')
    rA = c.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
                headers={'X-Vigilens-Display-Session': A})
    assert rA.status_code == 200, rA.text
    # B never presented the image: the stored result is refused, not served
    rB = c.get('/fresh-review/' + f.digest + '/frontend-audit', headers={'X-Vigilens-Display-Session': B})
    assert rB.status_code == 409
    assert 'persons' not in rB.text and 'audit_id' not in rB.text


def test_same_account_second_browser_reuses_without_redispatch(tmp_path, monkeypatch):
    # The proxy derives the SAME display-session value for one account across
    # browsers, so a second browser presenting known bytes reuses the stored
    # result with zero new provider calls.
    store = _empty_store(tmp_path)
    p, calls = _pipeline(tmp_path, monkeypatch, store)
    c = _client(p)
    raw, f = _img(color='blue')
    assert c.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
                  headers={'X-Vigilens-Display-Session': A}).status_code == 200
    n = len(calls)
    rA2 = c.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
                 headers={'X-Vigilens-Display-Session': A})
    assert rA2.status_code == 200
    assert len(calls) == n, 'known bytes within one account must never re-dispatch'
    assert rA2.json()['source_digest'] == f.digest


def test_second_account_identical_bytes_gets_own_analysis(tmp_path, monkeypatch):
    # A different account presenting identical bytes NEVER sees the first
    # account's stored result: it gets its own analysis, charged to its own
    # visitor key, as its own namespaced job. (Synthetic driver: no real calls.)
    store = _empty_store(tmp_path)
    p, calls = _pipeline(tmp_path, monkeypatch, store)
    c = _client(p)
    raw, f = _img(color='blue')
    assert c.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
                  headers={'X-Vigilens-Display-Session': A}).status_code == 200
    n = len(calls)
    rB = c.post('/fresh-review-audit-governed', files={'image': ('x.png', raw, 'image/png')}, data={'zones': '[]'},
                headers={'X-Vigilens-Display-Session': B})
    assert rB.status_code == 200, rB.text
    assert len(calls) > n, 'a second account analysis dispatches under its own key'
    assert rB.json()['source_digest'] == f.digest
    # Each account reads only its own job row for the same digest.
    import hashlib
    assert p.read(f.digest, hashlib.sha256(A.encode()).hexdigest())['result'] is not None
    assert p.read(f.digest, hashlib.sha256(B.encode()).hexdigest())['result'] is not None
    assert c.get('/fresh-review/' + f.digest + '/frontend-audit',
                 headers={'X-Vigilens-Display-Session': B}).status_code == 200


def test_zone_review_snapshots_are_keyed_per_session(tmp_path, monkeypatch):
    store = _empty_store(tmp_path)
    p, calls = _pipeline(tmp_path, monkeypatch, store)
    raw, f = _img(color='blue')
    import asyncio
    job = asyncio.run(p.run(raw, 'image/png', []))
    from fresh_review.zones import ZoneStore
    from fresh_review.pipeline import digest
    zs = ZoneStore(p)
    sha = digest(job['result'])
    zones = [{'id': 'z1', 'name': 'Edge', 'hazard': True, 'points': [{'x': 0.1, 'y': 0.1}, {'x': 0.5, 'y': 0.1}, {'x': 0.5, 'y': 0.5}]}]
    zs.append(f.digest, sha, A, zones, 'reviewer-a')
    assert zs.latest(f.digest, sha, A) is not None
    assert zs.latest(f.digest, sha, B) is None, 'zone review must never leak across sessions'
