"""Developer-install state builder for the OFFLINE synthetic integration mode.

Creates a self-contained per-install state (journal location, accounting carry, source
approvals for the developer's own test images, and a local API key) so a developer can run
the real governed backend flow against the deterministic SyntheticTransport with zero
network, zero provider cost and no owner data. This is a per-install developer setup, not
owner authority: it creates no live provider access, does not touch any owner journal,
ledger, approvals or carry, and the synthetic mode cannot make a real provider call.
"""
import argparse
import os
import hashlib
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from core import decode_image

MODE = 'developer_synthetic_offline'
SCOPES = ('synthetic_local_qualification', 'private_provider_processing')


def carry_doc(cap):
    from fresh_review.pipeline import aggregate_cap
    aggregate_cap({'aggregate_cap_usd': cap})  # same validation the backend applies; fail closed on a bad value
    return {'blocked_source_digests': [], 'provider_calls_total': 0, 'conservative_booked_usd': '0',
            'aggregate_cap_usd': cap, 'provenance': 'developer-install-per-install-budget-not-owner-accounting'}


def _private_write(path, raw):
    fd = path.open('wb')
    fd.write(raw)
    fd.close()
    path.chmod(0o600)


def _approval_spec(width, height, scope):
    if scope not in SCOPES:
        raise ValueError('Exact processing scope required')
    owner_ref = ('developer-self-approval-under-separate-owner-provided-key-not-owner-journal'
                 if scope == 'private_provider_processing' else 'developer-self-approval-not-owner-authority')
    return {'size': [width, height], 'rights_reference': 'developer-install-provided-test-image',
            'provider_upload_approved': True,
            'provenance': {'owner_instruction_reference': owner_ref,
                           'rights_review_reference': 'developer-provided-local-test-image',
                           'reviewed_at': datetime.now(timezone.utc).isoformat(),
                           'reviewer': 'dev_install.py local tool',
                           'scope': scope}}


def _read_approvals(path):
    return json.loads(path.read_bytes())['approvals']


def _atomic_private_write(path, raw):
    """Temp file + fsync + os.replace, 0600: no half-written state is ever visible."""
    tmp = path.with_name(path.name + '.tmp-' + secrets.token_hex(4))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        path.chmod(0o600)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def approve_image(state_dir, image_path, scope='synthetic_local_qualification'):
    """Add or refresh the per-install source approval for one developer test image. Offline.

    Serialized with a running seamless server through the same advisory lockfile
    (fresh_review.demo_approvals._cross_process_lock; fails closed when locking is
    unavailable), so a CLI approval cannot lose a concurrent upload recording or be
    lost by one. The approval file and config pin are written atomically. On a
    seamless install the recorded-sidecar pin is advanced to the merged state, so a
    running seamless server re-syncs on its next lookup instead of failing closed
    until restart. Accounting (carry/journal) is never touched here."""
    from fresh_review.demo_approvals import _cross_process_lock
    state = Path(state_dir)
    approvals_path = state / 'approvals.json'
    config_path = state / 'dev-config.json'
    if not approvals_path.is_file() or not config_path.is_file():
        raise ValueError('Run dev_install.py setup first')
    raw = Path(image_path).read_bytes()
    frame = decode_image(raw, 'image/png') if not str(image_path).lower().endswith(('.jpg', '.jpeg')) else decode_image(raw, 'image/jpeg')
    with _cross_process_lock(approvals_path):
        approvals = _read_approvals(approvals_path)
        approvals[frame.digest] = _approval_spec(frame.width, frame.height, scope)
        new_raw = (json.dumps({'version': 1, 'approvals': approvals}, sort_keys=True) + '\n').encode()
        _atomic_private_write(approvals_path, new_raw)
        new_sha = hashlib.sha256(new_raw).hexdigest()
        config = json.loads(config_path.read_bytes())
        config['approval_sha256'] = new_sha
        _atomic_private_write(config_path, (json.dumps(config, indent=2, sort_keys=True) + '\n').encode())
        if config.get('seamless_upload_approval') is True:
            sidecar = approvals_path.with_name('approvals.recorded-sha256')
            _atomic_private_write(sidecar, (new_sha + '\n').encode())
    return frame.digest


def create_state(state_dir, images=(), cors_origins=(), cap='5', seamless=False):
    state = Path(state_dir)
    if state.exists() and any(state.iterdir()):
        raise ValueError('State directory must be empty or new (choose a fresh directory; do not reuse owner state)')
    state.mkdir(parents=True, mode=0o700, exist_ok=True)
    state.chmod(0o700)
    approvals = {}
    for image in images:
        raw = Path(image).read_bytes()
        mime = 'image/jpeg' if str(image).lower().endswith(('.jpg', '.jpeg')) else 'image/png'
        frame = decode_image(raw, mime)
        approvals[frame.digest] = _approval_spec(frame.width, frame.height, 'synthetic_local_qualification')
    carry_raw = (json.dumps(carry_doc(cap), sort_keys=True) + '\n').encode()
    approvals_raw = (json.dumps({'version': 1, 'approvals': approvals}, sort_keys=True) + '\n').encode()
    token = secrets.token_urlsafe(36)  # 48 chars, A-Za-z0-9_- : passes the strong-token format check
    _private_write(state / 'carry.json', carry_raw)
    _private_write(state / 'approvals.json', approvals_raw)
    _private_write(state / 'access-token.txt', token.encode())
    config = {'version': 1, 'mode': MODE,
              'journal': str((state / 'dev.sqlite').resolve()),
              'carry_path': str((state / 'carry.json').resolve()),
              'carry_sha256': hashlib.sha256(carry_raw).hexdigest(),
              'approval_path': str((state / 'approvals.json').resolve()),
              'approval_sha256': hashlib.sha256(approvals_raw).hexdigest(),
              'access_token_file': str((state / 'access-token.txt').resolve()),
              'cors_origins': list(cors_origins) or ['http://localhost:5173', 'http://127.0.0.1:5173'],
              'seamless_upload_approval': bool(seamless)}
    _private_write(state / 'dev-config.json', (json.dumps(config, indent=2, sort_keys=True) + '\n').encode())
    return config


def load_service(config_path, transport='synthetic', key_file=None):
    """Build the governed fresh pipeline for a developer install.

    transport 'synthetic' (default): offline deterministic transport, no provider calls possible.
    transport 'meta': the real MetaTransport reading a developer-owned 0600 key file (the key the
    account owner gives the developer directly); approvals with private_provider_processing scope,
    the install's own cap and all governed controls still decide every dispatch. No call is made here.
    """
    from fresh_review.approvals import ApprovalStore
    from fresh_review.pipeline import FreshPipeline
    from fresh_review.synthetic_transport import SyntheticTransport
    if transport == 'meta':
        from fresh_review.transport import MetaTransport
        if not key_file:
            raise ValueError('Meta transport needs --key-file: a local 0600 file holding the developer-owned provider key')
        key_path = Path(key_file)
        if not key_path.is_file() or key_path.is_symlink():
            raise ValueError('Provider key file not found (or is a symlink): %s' % key_path)
        from fresh_review.platform_private import path_private, IS_WINDOWS
        if not path_private(key_path, follow=False):
            if IS_WINDOWS:
                raise ValueError('Provider key file grants access beyond owner/SYSTEM/Administrators: restrict its ACLs (icacls %s /inheritance:r /grant:r %%USERNAME%%:F)' % key_path)
            raise ValueError('Provider key file must be private: run chmod 600 %s' % key_path)
        selected = MetaTransport(key_path)
    elif transport == 'synthetic':
        selected = SyntheticTransport()
    else:
        raise ValueError('Exact transport selection required')
    from fresh_review.platform_private import open_private
    def _private_read(path):
        fd = open_private(path, os.O_RDONLY)  # no-follow + privacy-checked, both platforms
        try:
            with os.fdopen(fd, 'rb') as fh:
                return fh.read()
        except BaseException:
            try: os.close(fd)
            except OSError: pass
            raise
    config = json.loads(_private_read(config_path))
    if config.get('version') != 1 or config.get('mode') != MODE:
        raise ValueError('Exact developer-install configuration required')
    token = _private_read(config['access_token_file']).decode().strip()
    if not 32 <= len(token) <= 256 or any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise ValueError('Strong local access token required')
    scope = 'private_provider_processing' if transport == 'meta' else 'synthetic_local_qualification'
    seamless = config.get('seamless_upload_approval') is True
    if seamless:
        # Synthetic and live installs both support the seamless flow; the recorded scope
        # always matches the install's execution scope. Live seamless means the upload
        # action is the recorded approval: an explicit install decision, labelled as such.
        from fresh_review.demo_approvals import SeamlessDemoApprovalStore
        approval_path = Path(config['approval_path'])
        pin = config['approval_sha256']
        sidecar = approval_path.with_name('approvals.recorded-sha256')
        if sidecar.is_file() and approval_path.is_file():
            recorded = sidecar.read_text().strip()
            if hashlib.sha256(approval_path.read_bytes()).hexdigest() == recorded:
                pin = recorded  # restart after seamless recordings: reload the recorded state
        store = SeamlessDemoApprovalStore(approval_path, pin, scope=scope)
    else:
        store = ApprovalStore(Path(config['approval_path']), config['approval_sha256'])
    cap_enforcement = config.get('cap_enforcement', True)
    if type(cap_enforcement) is not bool:
        raise ValueError('Explicit cap_enforcement boolean required when present')
    if cap_enforcement is False and transport == 'meta':
        # Tracking-only mode: the app records all spending but does not enforce a second
        # app-level budget gate; the spending stop is then the provider-side key limit
        # (alert-only for Meta, per the README link - NOT a hard stop). This mode requires an
        # explicit, current owner decision; no such decision is recorded in this package, so
        # leave the default (enforcement on) unless the owner has just said otherwise. The
        # ledger keeps booking every reservation and cost in full; only the refusal is off.
        print('note: cap_enforcement=false - aggregate cap is tracked, not enforced; the provider-side key limit is the spending stop', file=sys.stderr)
    service = FreshPipeline(config['journal'], execution_scope=scope,
                            approval_store=store,
                            carry_path=Path(config['carry_path']), carry_sha=config['carry_sha256'],
                            transport=selected, cap_enforcement=cap_enforcement)
    service.carry()  # validate accounting checkpoint before serving; no journal creation
    origins = config.get('cors_origins')
    if not isinstance(origins, list) or any(not isinstance(o, str) or not o.startswith(('http://localhost:', 'http://127.0.0.1:')) for o in origins):
        raise ValueError('Loopback developer CORS origins required')
    return service, token, origins


def main():
    p = argparse.ArgumentParser(description='Offline developer-install setup for the Vigilens synthetic integration mode')
    p.add_argument('action', choices=('setup', 'approve', 'export-approvals'))
    p.add_argument('--state-dir', required=True)
    p.add_argument('--image', action='append', default=[], help='test image to approve (repeatable); PNG or JPEG')
    p.add_argument('--origin', action='append', default=[], help='allowed loopback frontend origin, e.g. http://localhost:5173 (repeatable)')
    p.add_argument('--seamless', action='store_true', help='setup: seamless demo flow - the upload action is recorded as the approval at upload time (no per-image CLI approval or restart). Synthetic installs record synthetic scope (offline). With --transport meta at serve time the same flag records LIVE scope: upload-as-approval spends the configured key for real - enable only deliberately, exactly as the README documents.')
    p.add_argument('--cap', default='5', help='setup: per-install aggregate budget cap in listed USD, sha-pinned into the install carry checkpoint (default 5; for live use set only an owner-approved limit)')
    p.add_argument('--scope', default='synthetic_local_qualification', choices=SCOPES, help='approve: approval scope; live provider testing needs private_provider_processing')
    a = p.parse_args()
    if a.action == 'setup':
        config = create_state(a.state_dir, images=a.image, cors_origins=a.origin, cap=a.cap, seamless=a.seamless)
        print('Developer install created (OFFLINE synthetic mode; no provider access, no owner data).')
        print('  config:      ' + str(Path(a.state_dir) / 'dev-config.json'))
        print('  API key file:' , config['access_token_file'], '(read it locally; never commit or share it)')
        print('  approved test images:', len(json.loads((Path(a.state_dir) / 'approvals.json').read_bytes())['approvals']))
        print('Next: python3.10 run_dev.py --config', str(Path(a.state_dir) / 'dev-config.json'))
    elif a.action == 'export-approvals':
        # Offline provisioning aid for the hosted (E2) path: print the exact
        # pinned-document env pair for this install's approvals file. Shape is
        # validated first so a malformed store is never exported. The values
        # are provisioning material - never commit them.
        import base64 as _b64
        from fresh_review.approvals_seed import validate_document_shape
        raw = (Path(a.state_dir) / 'approvals.json').read_bytes()
        validate_document_shape(raw)
        print('VIGILENS_APPROVALS_SHA256=' + hashlib.sha256(raw).hexdigest())
        print('VIGILENS_APPROVALS_DOC_JSON=' + _b64.b64encode(raw).decode())
    else:
        if not a.image or len(a.image) != 1:
            p.error('approve needs exactly one --image')
        digest = approve_image(a.state_dir, a.image[0], scope=a.scope)
        print('Approved test image in this developer install only:', digest)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, FileNotFoundError) as e:
        print('error: %s' % e, file=sys.stderr)
        sys.exit(2)
