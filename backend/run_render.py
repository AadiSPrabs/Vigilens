"""Render trial entrypoint (SYNTHETIC transport only in this package).

The other entrypoints bind 127.0.0.1 by deliberate design; this one binds
0.0.0.0 because Render routes external HTTP to the service. It reuses the exact
same create_app + dev_install state and governed routes as run_dev.py - no
route, ledger, approval or transport behavior changes.

Environment:
  PORT                        Render-provided port (default 8000).
  VIGILENS_STATE_DIR          State dir for dev-config.json/dev.sqlite/... (default ./render-state).
                              Render's free filesystem is EPHEMERAL: this state is lost on
                              restart/redeploy. Used only when VIGILENS_DATABASE_URL is unset.
  VIGILENS_DATABASE_URL       Postgres DSN (durable mode). Set this to the database's
                              INTERNAL connection string from the Render dashboard; the boot
                              appends sslmode=require when the internal hostname lacks it
                              (Render supports require internally; verify-ca/full are not
                              supported on the internal hostname). The DSN is never logged
                              and never written to any file. When set, the journal, preserved
                              artifacts and pinned carry/approvals documents all live in the
                              database and survive restarts/redeploys; VIGILENS_STATE_DIR is
                              not used.
  VIGILENS_FRONTEND_ORIGINS   Comma-separated CORS origins (the frontend URL).
  VIGILENS_LOCAL_ACCESS_TOKEN Stable gate token shared with the frontend build. If unset on
                              first boot a random one is generated (fail-closed: nobody can
                              call the governed routes). Never logged.
  VIGILENS_TRANSPORT          'synthetic' (default) or 'meta'. 'meta' wires the per-request
                              visitor-key transport (BYOK); actual provider dispatch is still
                              gated per request by VIGILENS_LIVE_DISPATCH=on (default off),
                              and requires the durable-records path before it may be enabled.
  VIGILENS_LIVE_DISPATCH      'on' permits real provider calls in meta mode. OFF by default;
                              owner-approved, paid, and never set by this package.
  VIGILENS_CAP                Install cap in USD string (default '5').
  VIGILENS_CLIP_LIMITS_JSON   Optional bounded local clip decoding. JSON object with the
                              six ClipLimits fields (max_bytes, max_seconds, max_frames,
                              max_side, max_pixels, subprocess_seconds). Unset keeps the
                              clip route fail-closed (409). Limits bound the local decoder
                              only; they never install source approvals and enable no
                              provider dispatch. Invalid values refuse the boot.
"""
import json
import os
import secrets
import sys
from pathlib import Path

import uvicorn

from app import create_app
from dev_install import create_state, load_service


def _private_write(path: Path, raw: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


def _wire_face_proposals(service):
    # Optional offline face-check review aid: enabled only when the operator
    # provisions the pinned YuNet model file and sets its absolute path. Unset
    # means the proposals endpoint stays unavailable (409) and the operator's
    # manual whole-frame review remains the requirement. The model sha256 pin
    # lives in fresh_review/face_proposals.py; a mismatched file fails closed.
    # The aid never creates regions, never applies treatment, and never spends.
    face_model = os.environ.get('VIGILENS_FACE_MODEL_PATH', '').strip()
    if not face_model:
        # Bundled pinned model (MIT, OpenCV Zoo YuNet 2023mar). The sha256 pin in
        # fresh_review/face_proposals.py still applies; a mismatch fails closed.
        bundled = Path(__file__).resolve().parent / 'models' / 'face_detection_yunet_2023mar.onnx'
        if bundled.is_file():
            face_model = str(bundled)
    if face_model:
        service.face_proposal_model_path = face_model


def _wire_stage_executors(service):
    """Opt-in recheck / explanation executors for the Postgres boot path.

    Off unless VIGILENS_STAGE_EXECUTORS=on (a spend-adjacent feature, so it is never
    switched on by default). When on, an executor object is attached so the report can show
    the exact plan hash; it still cannot reserve or dispatch without an exact, sha-pinned
    grant document. A grant is supplied only through VIGILENS_RECHECK_GRANT_JSON /
    VIGILENS_EXPLANATION_GRANT_JSON (the full grant JSON, written for one exact plan). This
    function never creates a grant. Grant bytes go to a 0700 temp dir as 0600 files and are
    pinned by sha256, exactly like the file-based local runtime."""
    if os.environ.get('VIGILENS_STAGE_EXECUTORS', 'off').strip().lower() != 'on':
        return
    import hashlib
    import tempfile
    from fresh_review.explanation_execution import ExplanationExecutor
    from fresh_review.recheck_execution import RecheckExecutor
    base = Path(tempfile.mkdtemp(prefix='vigilens-grants-'))
    os.chmod(base, 0o700)
    for attr, env, cls, fname in (
            ('recheck_executor', 'VIGILENS_RECHECK_GRANT_JSON', RecheckExecutor, 'recheck-grant.json'),
            ('explanation_executor', 'VIGILENS_EXPLANATION_GRANT_JSON', ExplanationExecutor, 'explanation-grant.json')):
        raw = os.environ.get(env, '').strip()
        path = sha = None
        if raw:
            json.loads(raw)  # must at least be valid JSON; exact-shape checks happen at use
            data = raw.encode('utf-8')
            path = base / fname
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
            sha = hashlib.sha256(data).hexdigest()
        setattr(service, attr, cls(service, approval_path=path, approval_sha256=sha))


def _wire_review_loop(service):
    """Fail-closed Render configuration for the bounded review loop.

    Set VIGILENS_REVIEW_LOOP_ATTEMPTS_JSON to {"<64-hex source>": ["<64-hex attempt id>", ...]} (1-2 ids each).
    Every id must already exist as a reserved recheck attempt for that source and must pass the executor's own
    grant check (pinned, scoped grant). This function never creates a grant, reservation or attempt and makes no
    provider call. Any problem leaves the loop UNCONFIGURED (the report then shows a blocked plan) and prints
    the reason; a bad value never takes the host down and never partially configures."""
    raw = os.environ.get('VIGILENS_REVIEW_LOOP_ATTEMPTS_JSON', '').strip()
    if not raw:
        return
    try:
        cfg = json.loads(raw)
        executor = getattr(service, 'recheck_executor', None)
        if executor is None or getattr(executor, 'approval_path', None) is None:
            raise ValueError('a configured recheck executor with an exact grant is required (VIGILENS_STAGE_EXECUTORS=on and a recheck grant)')
        if not isinstance(cfg, dict) or not cfg:
            raise ValueError('a non-empty JSON object is required')
        for source, ids in cfg.items():
            if not isinstance(source, str) or len(source) != 64 or any(ch not in '0123456789abcdef' for ch in source):
                raise ValueError('each key must be an exact 64-hex source digest')
            if not isinstance(ids, list) or not 1 <= len(ids) <= 2 or any(not isinstance(i, str) or len(i) != 64 for i in ids):
                raise ValueError('each source needs 1-2 exact attempt ids')
            for identity in ids:
                attempt = executor.read(identity)
                if attempt['plan']['source_digest'] != source:
                    raise ValueError('an attempt id does not belong to its source')
                executor.approval(attempt)
        service.review_loop_attempts = cfg
    except Exception as e:  # noqa: BLE001 - fail closed to unconfigured, with the reason on stdout
        print('Vigilens review loop NOT configured: %s' % e, flush=True)


def _wire_clip_limits(service):
    # Optional bounded local clip decoding, mirroring _wire_face_proposals: enabled
    # only when the operator sets VIGILENS_CLIP_LIMITS_JSON (see module docstring).
    # Unset means the clip route stays unavailable (409) and /health keeps reporting
    # trusted_clip_decode_configured=false. The limits bound the local decoder only;
    # the route itself never installs source approvals - every sampled frame still
    # requires its own pre-existing approval. Invalid config refuses the boot loudly
    # rather than silently degrading an operator's explicit intent.
    raw = os.environ.get('VIGILENS_CLIP_LIMITS_JSON', '').strip()
    if not raw:
        return
    from fresh_review.clips import ClipLimits
    try:
        values = json.loads(raw)
        if not isinstance(values, dict):
            raise TypeError('JSON object with the six ClipLimits fields required')
        limits = ClipLimits(**values)
        limits.validate()
    except (ValueError, TypeError, KeyError) as e:
        raise SystemExit('VIGILENS_CLIP_LIMITS_JSON is set but invalid; refusing to boot: ' + str(e))
    # Host binary gate: the decoder needs all three on PATH. DECIDED fail-closed
    # behavior: a configured-but-undecodable limits config refuses the WHOLE boot
    # here (SystemExit), not just the clip route. This is a deliberate impact
    # change from the unconfigured case (route-only 409, health reports
    # trusted_clip_decode_configured=false): an operator who set the limits asked
    # for decoding; serving a half-configured service whose health endpoint
    # reports configured=true while every clip request fails closed would hide a
    # provisioning defect behind a healthy-looking boot. Operators who want the
    # route-only behavior unset VIGILENS_CLIP_LIMITS_JSON. The same SystemExit
    # applies to invalid JSON above.
    import shutil
    missing = [b for b in ('ffmpeg', 'ffprobe', 'prlimit') if shutil.which(b) is None]
    if missing:
        raise SystemExit('VIGILENS_CLIP_LIMITS_JSON requires host binaries on PATH, missing: '
                         + ', '.join(missing) + '; refusing to boot')
    service.trusted_clip_limits = limits

def _seed_approvals_ephemeral(config_path, env):
    """E2 hosted path, ephemeral/file state: merge the operator-pinned approvals
    document (env) into the install approvals file INSERT-only, then re-pin the
    config. Unset env leaves the install untouched. Any divergence or pin
    mismatch refuses the boot (see fresh_review/approvals_seed.py).

    The whole read-merge-write runs under the SAME cross-process lock the
    seamless recorder and the CLI approve tool take (a concurrent upload
    recording can never be silently lost to this write), both files are written
    atomically (temp + fsync + replace, never O_TRUNC), the seamless sidecar is
    advanced when the install is seamless (so a peer server re-syncs instead of
    failing closed on tamper suspicion), and the paired state is verified
    before serving: file sha, config pin and sidecar must all agree."""
    from fresh_review.approvals_seed import env_pinned_document, merge_insert_only, EMPTY_DOC
    seed = env_pinned_document(env)
    if seed is None:
        return
    import hashlib
    from dev_install import _atomic_private_write
    from fresh_review.demo_approvals import _cross_process_lock
    config = json.loads(config_path.read_bytes())
    approvals_path = Path(config['approval_path'])
    seamless = config.get('seamless_upload_approval') is True
    sidecar = approvals_path.with_name('approvals.recorded-sha256')
    with _cross_process_lock(approvals_path):
        existing = approvals_path.read_bytes() if approvals_path.is_file() else EMPTY_DOC
        raw, sha, _inserted = merge_insert_only(existing, seed)
        _atomic_private_write(approvals_path, raw)
        config['approval_sha256'] = sha
        _atomic_private_write(config_path, (json.dumps(config, indent=2, sort_keys=True) + '\n').encode())
        if seamless:
            _atomic_private_write(sidecar, (sha + '\n').encode())
        if hashlib.sha256(approvals_path.read_bytes()).hexdigest() != sha \
                or json.loads(config_path.read_bytes()).get('approval_sha256') != sha \
                or (seamless and sidecar.read_text().strip() != sha):
            raise SystemExit('approvals seed paired-state verification failed; refusing to boot')


def main() -> None:
    state = Path(os.environ.get('VIGILENS_STATE_DIR', 'render-state'))
    port = int(os.environ.get('PORT', '8000'))
    origins = [o.strip() for o in os.environ.get('VIGILENS_FRONTEND_ORIGINS', '').split(',') if o.strip()]
    env_token = os.environ.get('VIGILENS_LOCAL_ACCESS_TOKEN', '').strip()
    config_path = state / 'dev-config.json'
    if not config_path.is_file():
        # Fresh boot on ephemeral storage: initialise the same state dev_install creates.
        if state.exists() and any(state.iterdir()):
            # Partial state is never trusted; fail closed rather than reuse it.
            raise SystemExit('render-state exists but dev-config.json is missing; refusing to reuse partial state')
        # dev_install.load_service enforces loopback-only CORS origins as a guardrail for
        # LOCAL installs. This entrypoint's whole purpose is a public trial origin, given
        # explicitly via env by the operator - so the stored config keeps inert loopback
        # origins (load_service's check is preserved, not weakened) and the real origins go
        # straight to create_app below.
        create_state(state, cap=os.environ.get('VIGILENS_CAP', '5'), seamless=True)
    if env_token:
        # Dashboard env is the single source of truth for the gate token.
        _private_write(state / 'access-token.txt', env_token.encode())
    transport_mode = os.environ.get('VIGILENS_TRANSPORT', 'synthetic')
    dsn = os.environ.get('VIGILENS_DATABASE_URL', '').strip()
    if dsn:
        if transport_mode not in ('synthetic', 'meta'):
            raise SystemExit("VIGILENS_TRANSPORT must be 'synthetic' or 'meta'")
        # Durable mode: the whole install state lives in Postgres (see module docstring).
        from render_boot import boot_pg_service
        from fresh_review.synthetic_transport import SyntheticTransport
        scope = 'private_provider_processing' if transport_mode == 'meta' else 'synthetic_local_qualification'
        service = boot_pg_service(dsn, cap=os.environ.get('VIGILENS_CAP', '5'), scope=scope,
                                  seamless=True, transport=SyntheticTransport())
        _wire_face_proposals(service)
        _wire_clip_limits(service)
        _wire_stage_executors(service)
        _wire_review_loop(service)
        token = env_token or secrets.token_urlsafe(36)  # fail-closed random gate when unset
        origins = origins or ['http://localhost:5173']
        if transport_mode == 'meta':
            from fresh_review.transport import MetaRequestTransport
            service.transport = MetaRequestTransport()
            print('Vigilens Render trial server: meta transport wired (visitor BYOK); live dispatch '
                  + ('ENABLED' if os.environ.get('VIGILENS_LIVE_DISPATCH', 'off') == 'on' else 'DISABLED (VIGILENS_LIVE_DISPATCH!=on)') + '.', flush=True)
        app = create_app(fresh_service=service, fresh_token=token, cors_origins=origins)
        print('Vigilens Render trial server (durable Postgres state; governed routes and cap accounting unchanged).', flush=True)
        uvicorn.run(app, host='0.0.0.0', port=port, access_log=False)
        return
    _seed_approvals_ephemeral(config_path, os.environ)
    service, token, _loopback_only = load_service(config_path)
    _wire_face_proposals(service)
    _wire_clip_limits(service)
    if transport_mode == 'meta':
        # BYOK shape: live-capable transport whose key arrives per request (visitor's own
        # key, request-scoped contextvar, never stored). Actual network dispatch remains
        # gated per request by VIGILENS_LIVE_DISPATCH=on (default off) in the API layer,
        # strictly before any journal write - this flag does NOT enable paid calls.
        from fresh_review.transport import MetaRequestTransport
        service.transport = MetaRequestTransport()
        print('Vigilens Render trial server: meta transport wired (visitor BYOK); live dispatch '
              + ('ENABLED' if os.environ.get('VIGILENS_LIVE_DISPATCH', 'off') == 'on' else 'DISABLED (VIGILENS_LIVE_DISPATCH!=on)') + '.', flush=True)
    elif transport_mode != 'synthetic':
        raise SystemExit("VIGILENS_TRANSPORT must be 'synthetic' or 'meta'")
    app = create_app(fresh_service=service, fresh_token=token, cors_origins=origins or ['http://localhost:5173'])
    print('Vigilens Render trial server (OFFLINE synthetic mode; governed routes and cap accounting unchanged).', flush=True)
    uvicorn.run(app, host='0.0.0.0', port=port, access_log=False)


if __name__ == '__main__':
    main()
