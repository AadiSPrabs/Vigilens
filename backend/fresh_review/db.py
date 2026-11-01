"""Dual-backend store driver: sqlite (default, byte-unchanged legacy path) or Postgres.

The stores were written against the sqlite3 DB-API surface. This module provides
open_store() which returns a raw sqlite3 connection for a file path (legacy,
untouched) or a PGConn wrapper for a 'postgres...' DSN. PGConn mimics the exact
surface the stores use - execute(sql, params) with ? paramstyle, BEGIN IMMEDIATE,
INSERT OR IGNORE, sqlite_master probes, INTEGER PRIMARY KEY rowid + lastrowid,
REAL columns - by translating SQL and adapting cursors, so store code reads the
same on both backends. Translation is SQL-literal-aware: '?' inside single-quoted
strings is never rewritten.

Fencing: sqlite's BEGIN IMMEDIATE takes the file write lock eagerly, serializing
concurrent writers process-wide. On Postgres the equivalent guarantee for the
spend journal is a transaction-scoped advisory lock keyed per install
(ADVISORY_KEY): every translated BEGIN IMMEDIATE acquires pg_advisory_xact_lock
on the SAME connection before any statement runs. Two backend instances sharing
one database therefore serialize exactly; a crashed transaction releases its
lock automatically. This is an atomic PG primitive, not an application-level
check-then-set.
"""
import re
import sqlite3
import time

try:
    import psycopg
except ImportError:  # sqlite-only environments still import this module
    psycopg = None


def validate_dsn_policy(dsn):
    # Connection-string boundary: local sockets / loopback are the internal
    # network (platform-managed ACL). Anything else is EXTERNAL and must pin
    # TLS verification explicitly - a plaintext remote DSN is refused here,
    # never negotiated down silently.
    from urllib.parse import urlparse, parse_qs
    u = urlparse(dsn)
    q = parse_qs(u.query)
    host = q.get('host', [u.hostname or ''])[0] or ''
    if host.startswith('/') or host in ('localhost', '127.0.0.1', '::1'):
        return
    sslmode = q.get('sslmode', [''])[0]
    if sslmode not in ('require', 'verify-ca', 'verify-full'):
        raise ValueError('External Postgres DSNs require explicit TLS (sslmode=require, verify-ca or verify-full)')


def _map_error(exc):
    # Adapt psycopg failures to the sqlite3 exception surface the stores and the
    # API layer already catch (sqlite3.Error subclasses -> governed 409, never an
    # unhandled 500). psycopg errors carry a SQLSTATE; map the classes the stores
    # can actually hit and fall back to OperationalError for the rest.
    state = getattr(exc, 'sqlstate', None)
    diag = getattr(exc, 'diag', None)
    msg = getattr(diag, 'message_primary', None) or str(exc).strip()
    if state == '23505':
        return sqlite3.IntegrityError(msg)
    if state == '55P03':  # lock_not_available: lock_timeout fired
        return sqlite3.OperationalError('database is locked')
    if state == '42P01':  # undefined_table
        table = getattr(diag, 'table_name', None) or ''
        return sqlite3.OperationalError('no such table: ' + table)
    if state == '25P02':  # in_failed_sql_transaction
        return sqlite3.OperationalError('current transaction is aborted: ' + msg)
    return sqlite3.OperationalError(msg)

ADVISORY_KEY = 0x5649474C4553  # 'VIGLES' - stable per install database; fencing scope is the database

_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def is_pg_dsn(value) -> bool:
    return isinstance(value, str) and value.startswith(('postgres://', 'postgresql://'))


def translate_sql(sql: str) -> str:
    """sqlite-flavoured SQL -> Postgres SQL. Literal-aware paramstyle rewrite plus
    the fixed idiom translations the stores use. Raises on anything unexpected so
    an untranslatable statement fails loudly in tests, never silently in prod."""
    out = []
    i = 0
    in_str = False
    while i < len(sql):
        ch = sql[i]
        if in_str:
            out.append(ch)
            if ch == "'":
                if i + 1 < len(sql) and sql[i + 1] == "'":
                    out.append("'")
                    i += 1
                else:
                    in_str = False
        elif ch == "'":
            out.append(ch)
            in_str = True
        elif ch == '?':
            out.append('%s')
        else:
            out.append(ch)
        i += 1
    if in_str:
        raise ValueError('Unterminated SQL string literal')
    s = ''.join(out)
    up = s.upper()
    if 'BEGIN IMMEDIATE' in up:
        s = re.sub(r'(?i)\bBEGIN IMMEDIATE\b', 'BEGIN', s)
    if 'INSERT OR IGNORE INTO' in up:
        m = re.match(r"(?is)^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+(\w+)\s*(.*)$", s.strip())
        if not m:
            raise ValueError('Unparseable INSERT OR IGNORE')
        body = m.group(2).rstrip().rstrip(';')
        s = f"INSERT INTO {m.group(1)} {body} ON CONFLICT DO NOTHING"
    if 'SQLITE_MASTER' in up:
        m = re.match(r"(?is)^\s*SELECT\s+1\s+FROM\s+sqlite_master\s+WHERE\s+name\s*=\s*(('[^']*')|%s)\s*$", s.strip())
        if m:
            s = f"SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = {m.group(1)}"
        else:
            m = re.match(r"(?is)^\s*SELECT\s+name\s+FROM\s+sqlite_master\s+WHERE\s+type\s*=\s*'table'\s*$", s.strip())
            if not m:
                raise ValueError('Unparseable sqlite_master probe')
            s = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    return s


def translate_ddl(sql: str) -> str:
    """CREATE TABLE translation: type mapping only (REAL -> DOUBLE PRECISION so
    epoch floats keep full precision; INTEGER PRIMARY KEY rowid tables get an
    IDENTITY column). Table/column names pass through unchanged."""
    s = re.sub(r'(?i)\bREAL\b', 'DOUBLE PRECISION', sql)
    s = re.sub(r'(?i)\bINTEGER\s+PRIMARY\s+KEY\b', 'BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY', s)
    return s


class PGCursor:
    """Minimal cursor facade matching how the stores use sqlite3 cursors:
    execute() returns self; fetchone/fetchall return plain tuples; lastrowid is
    filled by an appended RETURNING id only for tables registered as rowid-style
    (sqlite exposes a rowid on every table; Postgres has no implicit rowid, so
    the RETURNING applies only where the schema has an IDENTITY column)."""
    def __init__(self, cur, rowid_tables):
        self._cur = cur
        self._rowid_tables = rowid_tables
        self.lastrowid = None

    def execute(self, sql, params=()):
        sql = translate_sql(sql)
        upper = sql.upper()
        returning = False
        if upper.startswith('INSERT INTO') and 'ON CONFLICT DO NOTHING' not in upper and 'RETURNING' not in upper:
            m = re.match(r'(?is)^\s*INSERT\s+INTO\s+(\w+)', sql)
            if m and m.group(1) in self._rowid_tables:
                # sqlite rowid behaviour: expose the new row's id like lastrowid.
                sql = sql.rstrip().rstrip(';') + ' RETURNING id'
                returning = True
        try:
            self._cur.execute(sql, params)
        except psycopg.Error as exc:
            raise _map_error(exc) from exc
        self.lastrowid = None
        if returning:
            row = self._cur.fetchone()
            self.lastrowid = row[0] if row else None
        return self

    def __iter__(self):
        # sqlite cursors are iterable; the stores rely on it.
        return iter(self._cur)

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def rowcount(self):
        return self._cur.rowcount


class PGConn:
    """sqlite3.Connection facade over one psycopg connection. The fencing
    advisory lock is taken on THIS connection inside each translated BEGIN
    IMMEDIATE transaction, so all journal writes through this connection
    serialize against any other instance sharing the database.

    lock_timeout is set on the session at connect so the advisory lock wait is
    BOUNDED (pg_advisory_xact_lock otherwise waits forever; sqlite's equivalent
    is busy_timeout=10s). A timed-out wait surfaces as sqlite3.OperationalError
    'database is locked', exactly the sqlite contention signal the stores and
    the API layer already map to a governed 409 refusal."""
    def __init__(self, dsn, lock_timeout_ms=10000, read_only=False):
        if psycopg is None:
            raise RuntimeError('psycopg is required for Postgres stores')
        validate_dsn_policy(dsn)
        self._dsn = dsn
        try:
            self._c = psycopg.connect(dsn)
        except psycopg.Error:
            # Never surface the DSN through errors - and do NOT chain: a chained
            # traceback prints the original message with host detail. Logs and
            # reports get the generic message only.
            raise RuntimeError('Postgres connection failed') from None
        cur = self._c.cursor()
        cur.execute(f'SET lock_timeout = {int(lock_timeout_ms)}')  # SET takes no binds; value is a coerced int (ms)
        if read_only:
            # sqlite mode=ro parity: reads are enforced, not just conventional.
            cur.execute('SET default_transaction_read_only = on')
        self._c.commit()  # persist the session settings outside any later tx
        self._rowid_tables = set()
        self._cur = PGCursor(self._c.cursor(), self._rowid_tables)
        self._in_tx = False

    def _exec_ddl(self, sql, params):
        # Refused inside an explicit journal transaction: committing or rolling
        # back there would silently commit or discard preserved journal writes.
        if self._in_tx:
            raise sqlite3.OperationalError('DDL inside an explicit journal transaction is refused')
        # Each DDL statement commits on its own. Cold-start race: two instances
        # opening a FRESH database concurrently can both attempt the same
        # CREATE; Postgres can raise duplicate errors even with IF NOT EXISTS.
        # The retry rolls back ONLY the failed statement's own transaction, so
        # earlier statements of the batch stay committed (a batch-level retry
        # would silently lose them). Journal/write statements never take this
        # path - no hidden retries on preserved data.
        for attempt in range(20):
            try:
                self._cur._cur.execute(translate_ddl(sql), params)
                self._c.commit()
                return
            except psycopg.Error as exc:
                self._c.rollback()  # discards only this statement's tx
                if attempt == 19:
                    raise _map_error(exc) from exc
                time.sleep(0.05 * (attempt + 1))

    def execute(self, sql, params=()):
        m = re.match(r'(?is)^\s*CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(\w+)', sql)
        if m:
            # Registration is codified per connection on EVERY DDL pass: the
            # stores run their CREATE IF NOT EXISTS statements on every
            # connect(), so reopening an existing database re-registers its
            # rowid tables from the statement text itself.
            if re.search(r'(?i)\bINTEGER\s+PRIMARY\s+KEY\b', sql):
                self._rowid_tables.add(m.group(1))
            self._exec_ddl(sql, params)
            return self._cur
        upper = sql.strip().upper()
        if upper.startswith('BEGIN'):
            self._cur.execute(sql, params)
            self._in_tx = True
            if 'IMMEDIATE' in upper:
                # Transaction-scoped fencing lock: same connection, atomic,
                # auto-released on COMMIT/ROLLBACK/crash. Bounded by the
                # session lock_timeout; a contender gets 'database is locked'.
                self._cur.execute('SELECT pg_advisory_xact_lock(%s)', (ADVISORY_KEY,))
            return self._cur
        return self._cur.execute(sql, params)

    def commit(self):
        try:
            self._c.commit()
        except psycopg.Error as exc:
            raise _map_error(exc) from exc
        finally:
            self._in_tx = False

    def rollback(self):
        try:
            self._c.rollback()
        except psycopg.Error as exc:
            raise _map_error(exc) from exc
        finally:
            self._in_tx = False

    def close(self):
        self._c.close()


def open_store(path_or_dsn, *, lock_timeout_ms=10000, read_only=False):
    """Return a store connection: raw sqlite3 for a file path (legacy path,
    byte-unchanged), PGConn for a Postgres DSN. lock_timeout_ms bounds the PG
    fencing wait (sqlite parity: busy_timeout=10s); tests may shorten it.
    read_only enforces a read-only PG session (sqlite mode=ro parity)."""
    if is_pg_dsn(path_or_dsn):
        return PGConn(path_or_dsn, lock_timeout_ms=lock_timeout_ms, read_only=read_only)
    return sqlite3.connect(path_or_dsn, timeout=10)
