"""Dual-backend driver: SQL translation correctness + live Postgres roundtrip.

pgserver boots a real local Postgres; no sqlite behavior is changed by db.py
(the sqlite branch returns a raw sqlite3 connection untouched).
"""
import sqlite3

import pytest

from fresh_review.db import is_pg_dsn, translate_sql, translate_ddl, open_store, PGConn


def test_translate_paramstyle_skips_literals():
    assert translate_sql('SELECT * FROM jobs WHERE source=? AND state=?') == \
        'SELECT * FROM jobs WHERE source=%s AND state=%s'
    # '?' inside single quotes is data, not a parameter
    assert translate_sql("SELECT * FROM jobs WHERE note='what?' AND source=?") == \
        "SELECT * FROM jobs WHERE note='what?' AND source=%s"
    # escaped quote inside a literal keeps the scanner inside the string
    assert translate_sql("SELECT * FROM jobs WHERE note='it''s ?' AND source=?") == \
        "SELECT * FROM jobs WHERE note='it''s ?' AND source=%s"
    with pytest.raises(ValueError):
        translate_sql("SELECT * FROM jobs WHERE note='unterminated ?")


def test_translate_begin_immediate():
    assert translate_sql('BEGIN IMMEDIATE') == 'BEGIN'


def test_translate_insert_or_ignore():
    assert translate_sql('INSERT OR IGNORE INTO display_derivatives VALUES(?,?)') == \
        'INSERT INTO display_derivatives VALUES(%s,%s) ON CONFLICT DO NOTHING'


def test_translate_sqlite_master_probe():
    assert translate_sql("SELECT 1 FROM sqlite_master WHERE name='jobs'") == \
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'jobs'"
    with pytest.raises(ValueError):
        translate_sql("SELECT count(*) FROM sqlite_master")  # unknown probe shape fails loud


def test_translate_ddl_types():
    ddl = translate_ddl('CREATE TABLE IF NOT EXISTS zone_events(id INTEGER PRIMARY KEY,at REAL)')
    assert 'BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY' in ddl
    assert 'DOUBLE PRECISION' in ddl and 'REAL' not in ddl.replace('DOUBLE PRECISION', '')


def test_sqlite_branch_is_raw_sqlite(tmp_path):
    c = open_store(tmp_path / 'x.sqlite')
    assert type(c) is sqlite3.Connection
    c.close()


@pytest.fixture()
def pg_dsn(tmp_path):
    pgserver = pytest.importorskip('pgserver')
    srv = pgserver.get_server(str(tmp_path / 'pg'))
    yield srv.get_uri()
    srv.cleanup()


def test_pg_roundtrip_schema_insert_select(pg_dsn):
    c = open_store(pg_dsn)
    assert isinstance(c, PGConn)
    c.execute('CREATE TABLE IF NOT EXISTS jobs(source TEXT PRIMARY KEY,state TEXT,reserved TEXT,cost TEXT,binding TEXT,result TEXT,result_sha TEXT,started REAL)')
    c.execute('BEGIN IMMEDIATE')
    c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)', ('a' * 64, 'completed', '0.01', '0.01', '{}', None, None, 1.5))
    c.commit()
    r = c.execute('SELECT state,started FROM jobs WHERE source=?', ('a' * 64,)).fetchone()
    assert r[0] == 'completed' and abs(r[1] - 1.5) < 1e-9
    # insert-or-ignore idempotence
    c.execute('INSERT OR IGNORE INTO jobs VALUES(?,?,?,?,?,?,?,?)', ('a' * 64, 'X', '9', '9', '{}', None, None, 2.5))
    c.commit()
    assert c.execute('SELECT state FROM jobs WHERE source=?', ('a' * 64,)).fetchone()[0] == 'completed'
    c.close()


def test_pg_rowid_lastrowid_and_master_probe(pg_dsn):
    c = open_store(pg_dsn)
    c.execute('CREATE TABLE IF NOT EXISTS zone_events(id INTEGER PRIMARY KEY,source TEXT,at REAL)')
    cur = c.execute('INSERT INTO zone_events(source,at) VALUES(?,?)', ('s1', 1.0))
    assert cur.lastrowid == 1
    cur = c.execute('INSERT INTO zone_events(source,at) VALUES(?,?)', ('s2', 2.0))
    assert cur.lastrowid == 2
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name='zone_events'").fetchone()
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name='nope'").fetchone() is None
    c.close()


def test_pg_advisory_fencing_serializes_writers(pg_dsn):
    import threading, time
    c1 = open_store(pg_dsn)
    c2 = open_store(pg_dsn)
    c1.execute('CREATE TABLE IF NOT EXISTS jobs(source TEXT PRIMARY KEY,state TEXT)')
    c1.commit()
    order = []
    c1.execute('BEGIN IMMEDIATE')
    c1.execute('INSERT INTO jobs VALUES(?,?)', ('first', 'c1'))

    def writer():
        c2.execute('BEGIN IMMEDIATE')  # blocks on the advisory lock until c1 commits
        c2.execute('INSERT INTO jobs VALUES(?,?)', ('second', 'c2'))
        c2.commit()
        order.append('c2')

    t = threading.Thread(target=writer)
    t.start()
    time.sleep(0.5)
    order.append('c1')
    c1.commit()
    t.join(timeout=15)
    assert order == ['c1', 'c2']  # c2 waited for c1's transaction, no deadlock
    assert c2.execute('SELECT count(*) FROM jobs').fetchone()[0] == 2
    c1.close(); c2.close()


def test_pg_rollback_semantics(pg_dsn):
    c = open_store(pg_dsn)
    c.execute('CREATE TABLE IF NOT EXISTS jobs(source TEXT PRIMARY KEY,state TEXT)')
    c.commit()
    c.execute('BEGIN IMMEDIATE')
    c.execute('INSERT INTO jobs VALUES(?,?)', ('x', 's'))
    c.rollback()
    assert c.execute('SELECT count(*) FROM jobs').fetchone()[0] == 0
    c.close()


def test_pg_error_mapping_to_sqlite_classes(pg_dsn):
    # Gate 1: psycopg failures surface as the sqlite3 classes the stores and API
    # layer already catch; nothing psycopg-specific escapes the driver.
    import sqlite3 as s3
    c = open_store(pg_dsn)
    c.execute('CREATE TABLE IF NOT EXISTS dup(id TEXT PRIMARY KEY)')
    c.execute("INSERT INTO dup VALUES('a')")
    try:
        c.execute("INSERT INTO dup VALUES('a')")
        raise AssertionError('unique violation must raise')
    except s3.IntegrityError:
        pass
    c.rollback()
    try:
        c.execute('SELECT 1 FROM missing_table')
        raise AssertionError('undefined table must raise')
    except s3.OperationalError as e:
        assert 'no such table' in str(e)
    c.rollback()
    c.close()


def test_pg_aborted_transaction_requires_rollback(pg_dsn):
    # Gate 2: unlike sqlite, a failed statement aborts the PG transaction;
    # subsequent statements fail until rollback. The stores' except paths roll
    # back before continuing - verify the driver preserves that contract.
    import sqlite3 as s3
    c = open_store(pg_dsn)
    c.execute('CREATE TABLE IF NOT EXISTS t2(id TEXT PRIMARY KEY)')
    c.commit()
    c.execute('BEGIN')
    c.execute("INSERT INTO t2 VALUES('x')")
    try:
        c.execute('SELECT bad syntax here')
        raise AssertionError('bad statement must raise')
    except s3.OperationalError:
        pass
    try:
        c.execute("INSERT INTO t2 VALUES('y')")
        raise AssertionError('aborted tx must refuse further statements')
    except s3.OperationalError as e:
        assert 'aborted' in str(e)
    c.rollback()
    c.execute('BEGIN')
    c.execute("INSERT INTO t2 VALUES('z')")
    c.commit()
    got = {r[0] for r in c.execute('SELECT id FROM t2').fetchall()}
    assert got == {'z'}  # the aborted insert never landed
    c.close()


def test_pg_cold_start_ddl_race(pg_dsn):
    # Gate 3: the exact store pattern - CREATE IF NOT EXISTS then BEGIN with no
    # commit in between - executed by many instances against a FRESH database at
    # once must converge, never fail the cold start.
    import threading
    DDL = [
        'CREATE TABLE IF NOT EXISTS jobs(source TEXT PRIMARY KEY,state TEXT,reserved TEXT,cost TEXT,binding TEXT,result TEXT,result_sha TEXT,started REAL)',
        'CREATE TABLE IF NOT EXISTS calls(source TEXT,ordinal INTEGER,model TEXT,state TEXT,request_sha TEXT,response_sha TEXT,cost TEXT,PRIMARY KEY(source,ordinal))',
        'CREATE TABLE IF NOT EXISTS fresh_files(name TEXT PRIMARY KEY,data BYTEA)',
    ]
    barrier = threading.Barrier(8)
    errors = []
    def worker(i):
        try:
            c = open_store(pg_dsn)
            barrier.wait(timeout=10)
            for stmt in DDL:
                c.execute(stmt)
            # The real store pattern: BEGIN IMMEDIATE right after uncommitted
            # DDL, then the first journal write commits both together.
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT INTO fresh_files VALUES(?,?)', (f'probe-{i}', b'x'))
            c.commit()
            c.close()
        except Exception as e:  # noqa: BLE001 - collect, assert below
            errors.append(e)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join(30)
    assert not errors, f'cold-start race failures: {errors!r}'
    c = open_store(pg_dsn)
    for table in ('jobs', 'calls', 'fresh_files'):
        assert c.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone(), table
    assert c.execute('SELECT count(*) FROM fresh_files').fetchone()[0] == 8
    c.close()


def test_pg_contention_refusal_is_bounded(pg_dsn):
    # Gate 4: the fencing wait is bounded by lock_timeout (sqlite busy_timeout
    # parity). A contender gets sqlite3.OperationalError 'database is locked' -
    # the exact signal the governed routes map to a 409 refusal, never a hang.
    import sqlite3 as s3
    import time
    holder = open_store(pg_dsn)
    holder.execute('BEGIN IMMEDIATE')  # holds the advisory fence
    try:
        contender = open_store(pg_dsn, lock_timeout_ms=300)
        start = time.monotonic()
        try:
            contender.execute('BEGIN IMMEDIATE')
            raise AssertionError('contender must be refused')
        except s3.OperationalError as e:
            assert 'database is locked' in str(e)
        elapsed = time.monotonic() - start
        assert elapsed < 5, f'fencing wait was not bounded: {elapsed:.1f}s'
        contender.close()
    finally:
        holder.rollback()
        holder.close()


def test_pg_ddl_refused_inside_journal_transaction(pg_dsn):
    # Hardening: DDL inside an explicit journal transaction is refused outright -
    # the retry machinery must never commit or roll back preserved journal writes.
    import sqlite3 as s3
    c = open_store(pg_dsn)
    c.execute('CREATE TABLE IF NOT EXISTS j1(id TEXT PRIMARY KEY)')
    c.execute('BEGIN IMMEDIATE')
    c.execute("INSERT INTO j1 VALUES('kept')")
    try:
        c.execute('CREATE TABLE IF NOT EXISTS nope(id TEXT PRIMARY KEY)')
        raise AssertionError('DDL inside a journal tx must be refused')
    except s3.OperationalError as e:
        assert 'refused' in str(e)
    c.commit()  # journal write intact, tx usable
    assert c.execute('SELECT id FROM j1').fetchone()[0] == 'kept'
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name='nope'").fetchone() is None
    c.close()


def test_pg_ddl_retry_preserves_earlier_batch_statements(pg_dsn):
    # Hardening: each DDL statement commits independently, so a raced (retried)
    # statement can never discard earlier statements of the same batch.
    c = open_store(pg_dsn)
    c.execute('CREATE TABLE IF NOT EXISTS b1(id TEXT PRIMARY KEY)')
    c.execute('CREATE TABLE IF NOT EXISTS b2(id TEXT PRIMARY KEY)')
    c.execute('CREATE TABLE IF NOT EXISTS b3(id TEXT PRIMARY KEY)')
    for table in ('b1', 'b2', 'b3'):
        assert c.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone(), table
    c.close()


def test_pg_read_only_session_enforced(pg_dsn):
    # Hardening: sqlite mode=ro parity - a read connection is ENFORCED read-only,
    # not merely conventional.
    import sqlite3 as s3
    w = open_store(pg_dsn)
    w.execute('CREATE TABLE IF NOT EXISTS ro1(id TEXT PRIMARY KEY)')
    w.execute("INSERT INTO ro1 VALUES('v')")
    w.commit()
    w.close()
    r = open_store(pg_dsn, read_only=True)
    assert r.execute('SELECT id FROM ro1').fetchone()[0] == 'v'
    try:
        r.execute("INSERT INTO ro1 VALUES('x')")
        raise AssertionError('read-only session must refuse writes')
    except s3.OperationalError:
        pass
    r.close()


def test_pg_dsn_policy():
    # Hardening: external DSNs must pin TLS verification; internal (socket /
    # loopback) DSNs pass; the guard runs before any connection attempt.
    from fresh_review.db import validate_dsn_policy
    validate_dsn_policy('postgresql://postgres:@/postgres?host=/run/postgresql')
    validate_dsn_policy('postgresql://u:p@localhost/db')
    validate_dsn_policy('postgresql://u:p@127.0.0.1/db')
    validate_dsn_policy('postgresql://u:p@db.internal.example/db?sslmode=verify-full')
    for bad in ('postgresql://u:p@db.internal.example/db',
                'postgresql://u:p@db.internal.example/db?sslmode=prefer',
                'postgresql://u:p@db.internal.example/db?sslmode=disable'):
        try:
            validate_dsn_policy(bad)
            raise AssertionError(f'external DSN without TLS verification must be refused: {bad}')
        except ValueError as e:
            assert 'TLS' in str(e)


def test_pg_connect_failure_hides_dsn():
    # Hardening: connection failures never surface DSN detail (credentials/host).
    from fresh_review.db import open_store as _open
    try:
        _open('postgresql://secret_user:secret_pass@127.0.0.1:1/nope')
        raise AssertionError('unreachable server must fail')
    except RuntimeError as e:
        assert 'secret' not in str(e) and '127.0.0.1' not in str(e)
        assert e.__cause__ is None and e.__suppress_context__  # no chained traceback leaking host detail


def test_translate_sqlite_master_name_listing():
    # The recheck store's table-listing idiom maps to information_schema.
    from fresh_review.db import translate_sql
    assert translate_sql("SELECT name FROM sqlite_master WHERE type='table'") == \
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"


def test_pg_sqlite_master_name_listing_roundtrip(pg_dsn):
    c = open_store(pg_dsn)
    c.execute('CREATE TABLE IF NOT EXISTS listed1(id TEXT PRIMARY KEY)')
    c.execute('CREATE TABLE IF NOT EXISTS listed2(id TEXT PRIMARY KEY)')
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'listed1', 'listed2'} <= names
    c.close()
