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
"""
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
    service, token, _loopback_only = load_service(config_path)
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
