"""Postgres boot wiring for the Render trial entrypoint (durable-state mode).

When VIGILENS_DATABASE_URL is set, run_render boots the SAME governed service
against Postgres instead of ephemeral files: the spend journal, preserved
artifacts, and the pinned carry/approvals documents all live in the install
database, so restarts/redeploys keep every record. Nothing about routes,
ledgers, approvals or transports changes - only where state lives.

The DSN comes from an explicit operator-set environment variable, never from a
blueprint fromDatabase wiring and never logged. Render's internal connection
string carries no sslmode; the platform supports sslmode=require internally
(self-signed; verify-ca/full are not supported on the internal hostname), so
normalize_dsn appends sslmode=require for any non-local host that lacks an
sslmode, and the driver policy enforces the result.
"""
import hashlib
import json
import sqlite3

from dev_install import carry_doc
from fresh_review.approvals import ApprovalStore
from fresh_review.demo_approvals import SeamlessDemoApprovalStore
from fresh_review.db import open_store, validate_dsn_policy
from fresh_review.documents import PinnedPGDocument, create_documents
from fresh_review.pipeline import FreshPipeline

CARRY_DOC = 'carry'
APPROVALS_DOC = 'approvals'


def normalize_dsn(dsn):
    # Local socket/loopback DSNs pass unchanged (the internal network is the
    # boundary). Any other host must end up with TLS pinned; a missing sslmode
    # gets sslmode=require appended, an explicit one is kept and validated.
    from urllib.parse import urlparse, parse_qs
    u = urlparse(dsn)
    q = parse_qs(u.query)
    host = q.get('host', [u.hostname or ''])[0] or ''
    if host.startswith('/') or host in ('localhost', '127.0.0.1', '::1'):
        out = dsn
    elif 'sslmode' not in q:
        out = dsn + ('&' if u.query else '?') + 'sslmode=require'
    else:
        out = dsn
    validate_dsn_policy(out)
    return out


def _seed_document(dsn, name, raw):
    # Idempotent boot seeding. First boot creates the pinned document; later
    # boots adopt the EXISTING row (the database is the durable boundary) and
    # its actual content's sha becomes the enforced pin. Concurrent boots race
    # on the primary key; the loser adopts the winner's row.
    c = open_store(dsn)
    try:
        create_documents(c)
        try:
            c.execute('INSERT INTO documents VALUES(?,?)', (name, raw))
            c.commit()
            return hashlib.sha256(raw).hexdigest()
        except sqlite3.IntegrityError:
            c.rollback()
            row = c.execute('SELECT raw FROM documents WHERE name=?', (name,)).fetchone()
            adopted = bytes(row[0])
            if adopted != raw:
                # One safe line, no content: the operator sees that a changed
                # boot seed (e.g. a new VIGILENS_CAP) was IGNORED in favour of
                # the durable document. Stored records bind the original pin.
                import sys
                print('note: existing %s document adopted from the database; the boot seed value was ignored' % name, file=sys.stderr)
            return hashlib.sha256(adopted).hexdigest()
    finally:
        c.close()


def boot_pg_service(dsn, *, cap, scope, seamless, transport):
    """Build the governed FreshPipeline fully backed by Postgres. Same service
    shape dev_install.load_service returns, with durable state. No provider
    dispatch happens here; the transport decides, and live dispatch stays
    gated per request by VIGILENS_LIVE_DISPATCH=on in the API layer."""
    dsn = normalize_dsn(dsn)
    if scope not in ('synthetic_local_qualification', 'private_provider_processing'):
        raise ValueError('Exact processing scope required')
    carry_raw = (json.dumps(carry_doc(cap), sort_keys=True) + '\n').encode()
    carry_sha = _seed_document(dsn, CARRY_DOC, carry_raw)
    approvals_raw = (json.dumps({'version': 1, 'approvals': {}}, sort_keys=True) + '\n').encode()
    approvals_sha = _seed_document(dsn, APPROVALS_DOC, approvals_raw)
    if seamless:
        store = SeamlessDemoApprovalStore.pg(dsn, APPROVALS_DOC, approvals_sha, scope=scope)
    else:
        store = ApprovalStore.pg(dsn, APPROVALS_DOC, approvals_sha)
    service = FreshPipeline(dsn, execution_scope=scope, approval_store=store,
                            carry_path=None, carry_sha=carry_sha,
                            carry_document=PinnedPGDocument(dsn, CARRY_DOC, carry_sha),
                            transport=transport)
    service.carry()  # validate the accounting checkpoint before serving; creates nothing
    return service
