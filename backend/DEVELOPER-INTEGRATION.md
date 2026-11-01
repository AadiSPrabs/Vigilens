# Developer integration mode - connect a frontend and test it

This mode lets a frontend developer (for example Raakin) run the Vigilens backend on his own
machine, add an API key to his own install, and exercise the real API contract end to end.
Two transports are selectable at server start:

- **synthetic (default)**: fully offline. Provider replies are deterministic synthetic values
  computed from the request bytes: zero network, zero provider cost, no owner data. Use this
  to build and test the frontend against the real routes.
- **meta**: the real provider transport, reading a developer-owned key from a local 0600
  file. This makes real provider calls that spend that key's budget. Every governed control
  (per-image approval with the live scope, the install's own aggregate cap, ledger
  reservation, no-retry rules) still decides each dispatch. Use this only when live provider
  testing is intended and the owner has approved the limit (see below).

The HTTP surface, approval check, ledger reservation, journal, official-parser geometry
path, error shapes and auth gate are the same real code in both modes.

## What this is / is not
- IS: a per-install developer setup for frontend integration testing against the real routes.
- IS NOT: a deployment (loopback-only bind, by design and not caller-selectable), multi-user
  authentication (the key is a local bearer gate), or any use of the project owner's
  credentials, approvals, journals or ledger state. Nothing in a developer install settles,
  replaces or reopens any earlier usage, accounting or blocked-source state from other
  installs or the owner's runtime; each install's journal is its own.

## Setup (Python 3.10, Linux/macOS; Windows not qualified)
    python3.10 -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python dev_install.py setup --state-dir ./dev-state \
        --image ./my-test-photo.png --origin http://localhost:5173
    .venv/bin/python run_dev.py --config ./dev-state/dev-config.json --port 8001

`setup` creates `dev-state/` (mode 0700) with the journal location, the accounting carry
checkpoint, source approvals for the images you passed, `dev-config.json`, and
`access-token.txt` (mode 0600), your install's API key. Read it locally
(`cat dev-state/access-token.txt`); never commit or share it. To approve another test image
later, stop the server and run `dev_install.py approve --state-dir ./dev-state --image
./another.png` (add `--scope private_provider_processing` when the image is for live
provider testing), then restart.

`setup --cap <usd>` sets this install's aggregate accounting cap (default `5`; a decimal USD string, 0..1000000; `--cap 0` refuses every governed run, synthetic included). The value is
written once into the install's sha-pinned carry checkpoint and validated there on every
run: the backend never silently raises it, and every consumer fails closed if the checkpoint
does not match. The cap is a per-install configuration bound, not an inherent limit of the
provider API, and setting it is not spend authority: for live use, set only a numeric limit
the account owner has explicitly approved for you. Until such a limit is agreed, run the
default synthetic mode, which cannot spend anything.

To start over with a fresh synthetic install, stop the server, delete `dev-state/`, and run
setup again. This reset applies to synthetic developer installs only: it discards that
install's local journal and approvals. It never clears, migrates or rewrites live or
uncertain history anywhere else (the owner's journal is separate and is not touched), and it
must not be used to work around a held/uncertain attempt that needs reconciliation: in the
same install, an uncertain attempt stays held and is never auto-retried.

## Live provider testing (meta transport)
Prerequisites, all outside this document's authority to grant:
1. The account owner gives you a provider key directly (never through chat, tickets or the
   repo). Store it as the only line of a local file with mode 0600, e.g.
   `~/vigilens-dev-key.txt`. Never commit or share it. The backend reads it via
   `--key-file`; it is never logged or sent anywhere except the provider Authorization
   header.
2. Agree with the owner the numeric aggregate limit for your testing, then set it at setup
   (`dev_install.py setup ... --cap <limit>`). With no agreed number, do not run live.
3. Approve each test image with the live scope:
   `dev_install.py approve --state-dir ./dev-state --image ./photo.png --scope private_provider_processing`.
   Approvals written with the default synthetic scope do not authorize live provider calls.

Start live mode:
    .venv/bin/python run_dev.py --config ./dev-state/dev-config.json --port 8001 \
        --transport meta --key-file ~/vigilens-dev-key.txt

Real runs book actual listed costs against your install's cap; failed/uncertain attempts
hold the full reservation and are never retried automatically. When you are done, delete the
key file and ask the owner to rotate the key.

Note on proxies: the live transport uses Python's urllib with default proxy handling, so
`HTTP(S)_PROXY`/`ALL_PROXY` environment variables, if set, apply to provider requests, and a
malformed proxy value will fail the request. This is deliberate (no custom proxy bypass is
implemented); on a machine with a corporate proxy, confirm with its administrator that the
provider endpoint is reachable through it and that sending the key through that proxy is
acceptable before running live. The synthetic mode does no network I/O and is unaffected.

## Calling the API from the frontend
Base URL `http://127.0.0.1:8001`. Send on every API call:
- `X-Vigilens-Local-Access: <your install API key>` - missing/wrong key: 403.
- `X-Vigilens-Display-Session: <any 32-128 char value [A-Za-z0-9_-] your app generates per
  session>` - format-checked bearer value, NOT an identity or account.

CORS: only the origins listed in `dev-state/dev-config.json` (`--origin` at setup) are
allowed; others get no allow header. OpenAPI: `GET /openapi.json` and `GET /docs` with the key.

Main flow for an adjusted frontend:
1. `POST /fresh-review-audit-governed` (multipart `image`, form field `zones` JSON array).
   New approved image: runs the governed flow and returns the frontend v0.2 audit JSON with
   `provider_calls_this_request: null` and `provider_calls_note` (the call count lives only
   in the backend ledger). Same image again: the stored result, no new calls. Unapproved
   image: 409, no call. Failed attempt: 409 `ATTEMPT_UNCERTAIN`, held, never retried
   automatically.
2. `GET /fresh-review/{source}/frontend-audit` re-reads the v0.2 view; `source` is the image
   pixel digest. Readable only by the session that presented that exact image (possession
   binding, in memory).
3. `GET /fresh-review/{source}` returns the full stored job, `GET
   /fresh-review/{source}/integration-contract` the proposed review shape.
The fixture `POST /audit` (multipart `image`, `zones`, header `Idempotency-Key`) and
`GET /health` stay open without a key; the fixture serves only its exact paired sample.

Error contract (verified against the routes; statuses are exact):
- 403 missing/wrong key: `{"detail":"Private local access required"}`.
- 400 missing multipart fields: `{"error":{"code":"INVALID_REQUEST",...}}` (shared handler; its
  message mentions Idempotency-Key, which this route does not use - ignore that field name).
- 409 held attempt: distinguishable body `{"detail":{"code":"ATTEMPT_UNCERTAIN","state":...,
  "provider_calls_this_request":null,"message":...}}`. Branch on `detail.code`; the attempt is
  held, never retried, and reconciled only via the backend ledger.
- 409 everything else (unapproved image, oversize upload over 15 MB, invalid zones JSON,
  zero-person result, changed or tombstoned source): one fixed generic message with no
  per-cause signal in the response; never auto-retry.
- 503 provider execution disabled (the meta transport is not configured or live dispatch is
  disabled): `{"detail":"Fresh provider execution disabled; no claim or call created"}`.
413 and 422 do not occur on these routes. Never auto-retry on 400/409/503.

## Semantics the UI must keep (unchanged from FRONTEND-CONTRACT.md)
`job_state: completed` (with `partial_result: false`) is execution state, not assessment completeness. A green/positive tag
means a reading was attempted, never "safe". `provider_observation` values are UNVALIDATED
readings (and in synthetic mode additionally synthetic); show them as such. Zones are
validated and echoed only; `zones_applied` is false and no zone membership is determined.
Zero-person results are refused. `evidence_export_allowed` is always false; no masks are
sent to the frontend-audit view.

## What is synthetic vs real in this mode
Real in both modes: route surface, auth gate, approval requirement per image, ledger
reservation and accounting (in your install's own fresh journal), request/response shapes,
idempotency and no-retry rules, official-parser geometry handling. Synthetic mode only: the
provider replies (deterministic, labelled `synthetic-*`, derived from request bytes). In
meta mode the replies are real provider responses.

## Limits: code constants of this candidate (not inherent API limits)
Max 2 people per image; per-install aggregate accounting cap (default $5 listed, set at
setup and sha-pinned; held reservations count in full; completed synthetic runs book about
$0.0035 each, so normal frontend testing fits comfortably); 15 MB image cap; loopback bind;
single local user. Live new-image analysis additionally needs owner-approved source
approvals with the live scope, an owner-approved numeric limit, and a developer-owned key,
all decided with the account owner outside this mode.
