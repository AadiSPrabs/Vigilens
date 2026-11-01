"""Pinned durable documents on Postgres: the PG home for carry.json and
approvals.json, whose file forms are integrity-pinned 0600 files. On an
ephemeral filesystem (Render free tier) a pinned file is lost on restart; the
documents table keeps the same pin semantics durably:

- every read verifies sha256(raw) against the pin, exactly like the file path;
- an absent row behaves like an absent file (fail closed);
- recording paths (seamless approvals) take the row under SELECT ... FOR UPDATE
  inside the install fencing transaction, so concurrent recorders serialize
  exactly like the file cross-process lock, and a committed UPDATE is complete
  by construction - no sidecar needed.
"""
import hashlib

from .db import open_store

DDL = 'CREATE TABLE IF NOT EXISTS documents(name TEXT PRIMARY KEY,raw BYTEA)'


def create_documents(conn):
    conn.execute(DDL)


def put_document(dsn, name, raw: bytes):
    # Boot-time seeding only (dev_install/create_state equivalent). Exclusive
    # create: overwriting a pinned document is never a boot action.
    c = open_store(dsn)
    try:
        create_documents(c)
        c.execute('INSERT INTO documents VALUES(?,?)', (name, raw))
        c.commit()
    finally:
        c.close()


class PinnedPGDocument:
    """Read handle for one pinned document row."""
    def __init__(self, dsn, name, sha):
        if not isinstance(sha, str) or len(sha) != 64:
            raise ValueError('Document integrity pin required')
        self._dsn = dsn
        self._name = name
        self.sha = sha

    def read(self) -> bytes:
        import sqlite3
        c = open_store(self._dsn, read_only=True)
        try:
            row = c.execute('SELECT raw FROM documents WHERE name=?', (self._name,)).fetchone()
        except sqlite3.OperationalError as e:
            if 'no such table' in str(e):
                raise ValueError('Server-controlled pinned document required') from e
            raise
        finally:
            c.close()
        if row is None:
            raise ValueError('Server-controlled pinned document required')
        raw = bytes(row[0])
        if hashlib.sha256(raw).hexdigest() != self.sha:
            raise ValueError('Pinned document integrity changed')
        return raw

    def refresh(self):
        # Adopt a peer's committed recording outside a write: re-read the row
        # and, when it differs from our pin, accept it only if it parses as a
        # JSON object (a committed row is complete by construction). Anything
        # else fails closed. Lets a stale-pinned store see peer recordings
        # without writing.
        import sqlite3
        c = open_store(self._dsn, read_only=True)
        try:
            row = c.execute('SELECT raw FROM documents WHERE name=?', (self._name,)).fetchone()
        except sqlite3.OperationalError as e:
            if 'no such table' in str(e):
                raise ValueError('Server-controlled pinned document required') from e
            raise
        finally:
            c.close()
        if row is None:
            raise ValueError('Server-controlled pinned document required')
        raw = bytes(row[0])
        if hashlib.sha256(raw).hexdigest() != self.sha:
            self._adopt(raw)
        return raw

    @staticmethod
    def _adopt_shape(raw):
        import json
        try:
            doc = json.loads(raw)
        except ValueError:
            raise ValueError('Pinned document integrity changed') from None
        if not isinstance(doc, dict):
            raise ValueError('Pinned document integrity changed')
        return doc

    def _adopt(self, raw):
        self._adopt_shape(raw)
        self.sha = hashlib.sha256(raw).hexdigest()

    def record(self, mutate):
        """Serialized read-modify-write for recording paths (seamless approvals).
        mutate(doc_dict) -> new doc dict. The row is taken FOR UPDATE inside the
        install fencing transaction; a peer's committed recording is adopted
        (complete by construction) when it parses as a valid document, mirroring
        the file sidecar re-sync, and anything else fails closed."""
        import sqlite3
        c = open_store(self._dsn)
        try:
            c.execute('BEGIN IMMEDIATE')
            try:
                row = c.execute('SELECT raw FROM documents WHERE name=? FOR UPDATE', (self._name,)).fetchone()
            except sqlite3.OperationalError as e:
                if 'no such table' in str(e):
                    raise ValueError('Server-controlled pinned document required') from e
                raise
            if row is None:
                raise ValueError('Server-controlled pinned document required')
            raw = bytes(row[0])
            actual = hashlib.sha256(raw).hexdigest()
            if actual != self.sha:
                self._adopt(raw)
            import json
            doc = json.loads(raw)
            new_raw = (json.dumps(mutate(doc), sort_keys=True) + '\n').encode()
            c.execute('UPDATE documents SET raw=? WHERE name=?', (new_raw, self._name))
            c.commit()
            self.sha = hashlib.sha256(new_raw).hexdigest()
            return new_raw
        except BaseException:
            try:
                c.rollback()
            except Exception:
                pass
            raise
        finally:
            c.close()
