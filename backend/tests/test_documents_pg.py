"""Pinned documents on Postgres: carry/approvals durability on ephemeral hosts.
Pin semantics identical to the 0600 files; recording serialized by the row lock
inside the install fencing transaction."""
import hashlib
import json
import threading

import pytest

from fresh_review.documents import PinnedPGDocument, put_document
from fresh_review.approvals import ApprovalStore
from fresh_review.demo_approvals import SeamlessDemoApprovalStore
from fresh_review.db import open_store


@pytest.fixture()
def pg_uri(tmp_path):
    pgserver = pytest.importorskip('pgserver')
    srv = pgserver.get_server(str(tmp_path / 'pg'))
    yield srv.get_uri()
    srv.cleanup()


def _seed(pg_uri, name, doc):
    raw = (json.dumps(doc, sort_keys=True) + '\n').encode()
    put_document(pg_uri, name, raw)
    return hashlib.sha256(raw).hexdigest()


def _approval_spec():
    return {'size': [80, 80], 'rights_reference': 'reviewed-ref', 'provider_upload_approved': True,
            'provenance': {'owner_instruction_reference': 'o', 'rights_review_reference': 'r',
                           'reviewed_at': '2026-11-01T00:00:00+00:00', 'reviewer': 'test',
                           'scope': 'synthetic_local_qualification'}}


def test_pinned_document_read_tamper_absent(pg_uri):
    sha = _seed(pg_uri, 'carry', {'version': 1, 'blocked_source_digests': []})
    doc = PinnedPGDocument(pg_uri, 'carry', sha)
    assert json.loads(doc.read())['version'] == 1
    # Tamper externally: the pin refuses it.
    c = open_store(pg_uri)
    c.execute("UPDATE documents SET raw=? WHERE name='carry'", (b'{"version":2}',))
    c.commit()
    c.close()
    with pytest.raises(ValueError, match='integrity changed'):
        doc.read()
    with pytest.raises(ValueError, match='required'):
        PinnedPGDocument(pg_uri, 'missing', sha).read()


def test_approval_store_pg_lookup(pg_uri):
    sha = _seed(pg_uri, 'approvals', {'version': 1, 'approvals': {'a' * 64: _approval_spec()}})
    store = ApprovalStore.pg(pg_uri, 'approvals', sha)
    spec = store.lookup('a' * 64, [80, 80])
    assert spec['provider_upload_approved'] is True
    with pytest.raises(ValueError):
        store.lookup('b' * 64, [80, 80])


def test_seamless_store_pg_records_and_adopts(pg_uri):
    sha = _seed(pg_uri, 'approvals', {'version': 1, 'approvals': {}})
    store = SeamlessDemoApprovalStore.pg(pg_uri, 'approvals', sha)
    spec = store.lookup('c' * 64, [80, 80])  # auto-records
    assert spec['provider_upload_approved'] is True
    again = store.lookup('c' * 64, [80, 80])
    assert again == spec  # recorded once, stable
    # A second instance booted with the ORIGINAL (stale) pin adopts the peer's
    # committed recording instead of failing closed.
    store2 = SeamlessDemoApprovalStore.pg(pg_uri, 'approvals', sha)
    assert store2.lookup('c' * 64, [80, 80]) == spec
    # Never overwrites an existing record.
    store3 = SeamlessDemoApprovalStore.pg(pg_uri, 'approvals', store.sha)
    assert store3.lookup('c' * 64, [80, 80]) == spec


def test_seamless_store_pg_concurrent_recorders(pg_uri):
    sha = _seed(pg_uri, 'approvals', {'version': 1, 'approvals': {}})
    barrier = threading.Barrier(6)
    errors = []
    def worker(i):
        try:
            store = SeamlessDemoApprovalStore.pg(pg_uri, 'approvals', sha)
            barrier.wait(timeout=10)
            store.lookup('d' * 63 + str(i), [80, 80])
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in threads: t.start()
    for t in threads: t.join(30)
    assert not errors, f'concurrent recording failures: {errors!r}'
    final = SeamlessDemoApprovalStore.pg(pg_uri, 'approvals', sha)
    for i in range(6):
        assert final.lookup('d' * 63 + str(i), [80, 80])['provider_upload_approved'] is True


def test_pipeline_carry_document_pg(pg_uri, tmp_path, monkeypatch):
    from test_seamless_demo import _img
    from test_fresh_pipeline_pg import _store, _pg_pipeline
    carry_doc = {'blocked_source_digests': [], 'provider_calls_total': 0,
                 'conservative_booked_usd': '0', 'aggregate_cap_usd': '5',
                 'provenance': 'generated-test-only-not-real-budget'}
    sha = _seed(pg_uri, 'carry', carry_doc)
    from fresh_review.documents import PinnedPGDocument
    from fresh_review.pipeline import FreshPipeline
    p = _pg_pipeline(pg_uri, tmp_path, monkeypatch, lambda body: b'')
    p2 = FreshPipeline(pg_uri, carry_path=None, carry_sha=sha,
                       carry_document=PinnedPGDocument(pg_uri, 'carry', sha),
                       execution_scope='synthetic_local_qualification',
                       approval_store=p.approval_store, transport=p.transport)
    assert p2.carry()['provider_calls_total'] == 0
    c = open_store(pg_uri)
    c.execute("UPDATE documents SET raw=? WHERE name='carry'", (b'{}',))
    c.commit()
    c.close()
    with pytest.raises(ValueError):
        p2.carry()
