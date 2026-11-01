"""Seamless OFFLINE-demo approval recording (synthetic scope only).

In the seamless local demo the developer's upload action in the UI IS the recorded
approval event: this store writes that approval transactionally at upload time and
rebinds its integrity pin in-process, so a new image needs no CLI step or restart.

Scope discipline (unchanged from the pinned store):
- Synthetic scope only. Nothing is uploaded to a provider in this mode; the
  transport is the deterministic SyntheticTransport and no bytes leave the machine.
  The recorded 'provider_upload_approved' flag is the store schema's dispatch flag,
  and every recorded provenance field states plainly that this is a developer-scope
  synthetic demo recording, not an owner instruction and not a rights review.
- Live (private_provider_processing) use is a separate explicit install decision:
  the seamless flag with the meta transport records live-scope approvals the same
  way (the upload action is the recorded approval), labelled as owner-configured
  demo mode. The pairing invariant still bars a live transport under the synthetic
  scope. Live seamless dispatch spends the configured key's budget; the spending
  boundary is the provider-side key limit and the tracking ledger, which keeps
  booking every reservation and cost in full.
- Never overwrites an existing approval entry; a digest with an invalid or
  mismatched record stays refused.

Failure contract (stated, not hidden):
- Recording is temp-file + fsync + atomic os.replace, then the sidecar pin. A crash
  mid-record leaves the old file+pin pair (clean) or a new file with a stale/absent
  sidecar: a restart then fails closed (lookups refuse, 409) until the state is
  repaired or reset. It never trusts half-written state and never serves a result
  whose approval record is unverifiable.
- Multi-process use of one state directory is serialized by an advisory lockfile.
  This is still a single-install developer mechanism, not a shared database.
"""
import hashlib
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from .approvals import ApprovalStore


@contextmanager
def _cross_process_lock(path):
    """Advisory lock around read-modify-write so two processes sharing one state
    directory (e.g. a server and the CLI approval tool, or a duplicate dev server)
    serialize recordings instead of silently losing one (os.replace is last-writer-
    wins). POSIX flock; Windows msvcrt byte lock. Fail-closed: if no locking mechanism
    exists or the lock cannot be acquired, the recording is refused, never performed unlocked."""
    lock_path = path.with_name('approvals.lock')
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            import fcntl
        except ImportError:
            fcntl = None
        if fcntl is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
            except OSError as e:
                raise ValueError('Cross-process approval lock could not be acquired; refusing rather than recording unlocked') from e
        else:
            try:
                import msvcrt
            except ImportError as e:
                raise ValueError('No cross-process locking mechanism on this platform; failing closed, never recording unlocked') from e
            os.write(fd, b' ' if os.lseek(fd, 0, os.SEEK_END) == 0 else b'')
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            except OSError as e:
                raise ValueError('Cross-process approval lock could not be acquired; refusing rather than recording unlocked') from e
        yield
    finally:
        try:
            os.close(fd)
        except OSError:
            pass

class SeamlessDemoApprovalStore(ApprovalStore):
    def __init__(self, path, sha, scope='synthetic_local_qualification'):
        if scope not in ('synthetic_local_qualification', 'private_provider_processing'):
            raise ValueError('Exact processing scope required')
        super().__init__(path, sha)
        self._scope = scope
        self._record_lock = threading.Lock()

    @classmethod
    def pg(cls, dsn, name, sha, scope='synthetic_local_qualification'):
        from .documents import PinnedPGDocument
        store = cls(None, sha, scope=scope)
        store._doc = PinnedPGDocument(dsn, name, sha)
        return store

    def lookup(self, source, size):
        if self._doc is not None:
            try:
                return super().lookup(source, size)
            except ValueError:
                pass
            with self._record_lock:
                try:
                    return super().lookup(source, size)
                except ValueError:
                    pass
                self._doc.refresh()  # adopt a peer's committed recording, then retry
                try:
                    return super().lookup(source, size)
                except ValueError:
                    return self._record(source, size)
        try:
            return super().lookup(source, size)
        except ValueError:
            pass
        with self._record_lock, _cross_process_lock(self.path):
            # Under the lock, a file that differs from our pin but matches its sidecar is a
            # COMPLETED recording by a peer process (peers write only under this same lock):
            # re-sync our pin to it. A file matching neither pin nor sidecar is a crash or
            # tamper remnant: keep our pin and let lookup fail closed.
            if self.path.is_file():
                raw = self.path.read_bytes()
                actual = hashlib.sha256(raw).hexdigest()
                if actual != self.sha:
                    sidecar = self.path.with_name('approvals.recorded-sha256')
                    if sidecar.is_file() and sidecar.read_text().strip() == actual:
                        self.sha = actual
            try:
                return super().lookup(source, size)
            except ValueError:
                return self._record(source, size)

    def _spec(self, source, size, owner_ref, rights_ref, reviewer):
        return {'size': list(size),
                'rights_reference': 'seamless-upload-recorded-at-upload-no-rights-review',
                'provider_upload_approved': True,
                'provenance': {
                    'owner_instruction_reference': owner_ref,
                    'rights_review_reference': rights_ref,
                    'reviewed_at': datetime.now(timezone.utc).isoformat(),
                    'reviewer': reviewer,
                    'scope': self._scope}}

    def _record_pg(self, source, size):
        # PG recording: the document row serializes concurrent recorders (FOR
        # UPDATE inside the install fencing transaction); a committed peer
        # recording is complete by construction, so pin adoption happens inside
        # PinnedPGDocument.record. Seamless recording still never overwrites.
        if self._scope == 'synthetic_local_qualification':
            owner_ref = 'seamless-demo-upload-action-developer-scope-not-owner-authority'
            rights_ref = 'not-reviewed-synthetic-offline-demo-only-no-provider-upload-occurs'
            reviewer = 'seamless demo upload action (automatic recording, synthetic scope)'
        else:
            owner_ref = 'seamless-upload-action-owner-configured-demo-mode-install'
            rights_ref = 'not-reviewed-upload-action-is-the-recorded-approval-under-owner-configured-seamless-mode'
            reviewer = 'seamless upload action (automatic recording, owner-configured demo mode)'
        spec = self._spec(source, size, owner_ref, rights_ref, reviewer)
        def mutate(doc):
            if set(doc) != {'version', 'approvals'} or doc['version'] != 1:
                raise ValueError('Approval store version required')
            if source in doc['approvals']:
                raise ValueError('Existing approval record invalid; seamless recording never overwrites')
            doc['approvals'][source] = spec
            return doc
        self._doc.record(mutate)
        return spec

    def _record(self, source, size):
        if self._doc is not None:
            return self._record_pg(source, size)
        from .platform_private import path_private
        p = self.path
        if not p.is_file() or not path_private(p, 0o022, follow=False):
            raise ValueError('Server-controlled approval store required')
        raw = p.read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.sha:
            raise ValueError('Approval store integrity pin changed')
        doc = json.loads(raw)
        if set(doc) != {'version', 'approvals'} or doc['version'] != 1:
            raise ValueError('Approval store version required')
        if source in doc['approvals']:
            raise ValueError('Existing approval record invalid; seamless recording never overwrites')
        if self._scope == 'synthetic_local_qualification':
            owner_ref = 'seamless-demo-upload-action-developer-scope-not-owner-authority'
            rights_ref = 'not-reviewed-synthetic-offline-demo-only-no-provider-upload-occurs'
            reviewer = 'seamless demo upload action (automatic recording, synthetic scope)'
        else:
            owner_ref = 'seamless-upload-action-owner-configured-demo-mode-install'
            rights_ref = 'not-reviewed-upload-action-is-the-recorded-approval-under-owner-configured-seamless-mode'
            reviewer = 'seamless upload action (automatic recording, owner-configured demo mode)'
        spec = self._spec(source, size, owner_ref, rights_ref, reviewer)
        doc['approvals'][source] = spec
        blob = (json.dumps(doc, sort_keys=True) + '\n').encode()
        tmp = p.with_name(p.name + '.tmp-' + os.urandom(4).hex())
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(blob)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, p)
            os.chmod(p, 0o600)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self.sha = hashlib.sha256(blob).hexdigest()
        # Sidecar pin so a backend restart reloads the recorded state without a config edit:
        # load_service prefers this pin when the file matches it, else falls back to the
        # config pin (CLI-approved state), else fails closed on lookup.
        pin_path = p.with_name('approvals.recorded-sha256')
        fd = os.open(pin_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(self.sha + '\n')
        os.chmod(pin_path, 0o600)
        return spec
