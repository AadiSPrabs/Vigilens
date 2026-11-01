# Vigilens - connected demo (integration snapshot 3)

Snapshot 3 is a reviewer repair delta on snapshot 2 (same origins, plus the fixes listed
under "Snapshot 3 delta" below). Snapshots 1-2 remain frozen; this is the candidate.

The frontend-builder UI connected to the governed Vigilens backend, in one working copy.
Built from `feat/frontend-builder` @970e39c (untouched upstream) plus the draft6 backend.
Offline synthetic testing only so far; no paid provider calls were made or are authorized
by this package.

## What works

- Upload a photo -> Analyse -> findings render (persons, PPE chips, review workflow).
- A brand-new image works immediately after the previous one: no CLI approval step,
  no backend restart (seamless mode records the upload action as the approval).
- Bundled samples keep working offline from fixtures, with the SAMPLE DATA banner.
- Spending is tracked in the background ledger. Refusals (403/409/503, ATTEMPT_UNCERTAIN)
  surface as-is; the UI never auto-retries a held attempt.
- Honesty labeling: synthetic results show "SYNTHETIC READINGS - boxes and PPE values are
  generated test data, not detections". The offline transport's person boxes are generated
  from request bytes, not detected from the photo; the UI says so.
- Bad uploads say why: an oversize, EXIF-rotated or unsupported image now returns its exact
  status (413 IMAGE_TOO_LARGE / 415 UNSUPPORTED_MEDIA_TYPE / 422 IMAGE_ORIENTATION_UNSUPPORTED
  or IMAGE_UNREADABLE) with an operator-safe message, instead of a generic "unapproved" 409.
  A rotated phone photo must be rotated upright before upload; nothing was sent anywhere.
- `dev_install.py approve` while the seamless server runs: the CLI takes the same advisory
  lockfile as the server and advances the sidecar pin, so the running server re-syncs on its
  next lookup - no restart, no lost recordings either direction.

## Run it (Linux/macOS dev machine)

Backend (Python 3.10, venv with backend/requirements-lock.txt installed):

    cd backend
    python dev_install.py setup --state-dir ../state --origin http://localhost:5199 --seamless
    python run_dev.py --config ../state/dev-config.json --port 8001
    # note the generated local key: ../state/access-token.txt (never commit or share it)

Frontend (Node, from this directory):

    cd frontend
    printf 'VITE_VIGILENS_LOCAL_ACCESS=<paste local key>\nVITE_API_BASE_URL=http://localhost:8001\n' > .env.local
    chmod 600 .env.local
    npm install
    AUTH_DISABLED=true npx agent-native dev --port 5199

Open http://localhost:5199, upload a photo, Analyse.

## Modes and safety rails (unchanged unless you opt in)

- Default install (`dev_install.py setup` without `--seamless`) keeps the original
  per-image CLI approval. `--seamless` records the upload action as the approval.
- Synthetic mode (default) cannot make real provider calls; the transport/scope pairing
  invariant blocks a live transport under the synthetic scope.
- Live mode (`run_dev.py --transport meta --key-file ...`) spends the configured key's
  budget under the install's approvals. With `--seamless`, live-scope uploads are
  auto-approved at upload time and labelled "owner-configured demo mode" - enable this
  only deliberately.
- IMPORTANT: Meta's dashboard "spend limit" is ALERT-ONLY (email when usage crosses the
  amount; you still pay overage) per https://dev.meta.ai/help/billing/spend-limit-alert.
  It is NOT a hard stop. The app-level aggregate cap stays enforced unless you set
  "cap_enforcement": false in dev-config.json (tracking stays complete either way).

## Tests

    cd backend && python -m pytest tests -q   # 770 passed (Linux, clean shell)

Frontend: the 10 governed-client/adapter tests pass (`npx vitest run
app/vigilens/api/__tests__/backendClient.test.ts` after `npm ci`). The FULL `npm test` is
NOT green as shipped: two untouched builder-template (@970e39c) scaffold spec files fail
(tests/use-navigation-state.spec.ts: 7 failures, spec/API drift `pathForCommand is not a
function`; server/mcp-provider-schemas.spec.ts: generated-registry resolution). Both are
pre-existing template debt off the Vigilens route; no Vigilens test fails.

New coverage for this integration: seamless approval recording (record-on-miss, pin
rebind, no-overwrite, concurrent single-writer, restart via sidecar pin), multi-image
no-restart, repeat-upload zero-calls, tracking-only booking, and the live transport path
over a fake-HTTP boundary (exact frontend multipart request, live-origin labelling,
provider-error hold with no retry).

Snapshot 3 delta coverage (backend/tests/test_review_delta.py, 5 tests): exact 413/415/422
image-error mapping on the governed route (rotated image refused before any approval
recording), lock-unavailable fails closed (nothing recorded unlocked), CLI approve
serializes with the running seamless server and the server re-syncs without restart.

## Snapshot 3 delta (reviewer repairs on frozen snapshot 2)

- dev_install.py `--seamless` help text corrected: it wrongly claimed the flag is "never
  valid with the meta transport". Seamless+meta is supported and records LIVE-scope
  upload-as-approval that spends the configured key; the help now says so.
- Governed/frontend-audit upload routes: image-input AuditErrors keep their exact status
  and code instead of collapsing into a generic 409; the frontend surfaces the message.
- demo_approvals.py cross-process lock: if no locking mechanism exists or the lock cannot
  be acquired, recording is REFUSED (fail closed); it never runs unlocked.
- dev_install.py `approve`: takes the same lockfile, writes approvals/config atomically
  (temp + fsync + replace), and advances the seamless sidecar pin.
- Two pre-existing tests that pinned the old masked statuses were updated to the exact
  statuses with their intent preserved (valid image exercises the dispatch gate; invalid
  zones assert the exact 400 INVALID_* code before any lookup).

## Limits and recovery (read before the demo)

- Journal bound: an install holds at most 64 distinct analysed images; the 65th upload is
  refused (409). This is a hard stop, not an error. Do NOT delete state or create a fresh
  install to keep going: a new install starts with fresh budget while the old spend and
  holds still exist, which would defeat the accounting. Reconcile against the ORIGINAL
  journal/carry (operator step) or stop there for the demo.
- Crash mid-recording: an upload interrupted between file write and pin write fails closed
  afterwards (409s) until repaired. Repair means restoring consistency between
  approvals.json and approvals.recorded-sha256 (both are plain JSON/text; the sidecar must
  name the sha256 of the approvals file). Never delete or reset the journal
  (dev.sqlite), carry.json or any ledger file: they are the only spending record.
- Spending visibility is journal-only: there is no UI or endpoint for cumulative spend.
  To inspect it on the demo machine:
      sqlite3 state/dev.sqlite "SELECT source, state, reserved, cost FROM jobs;"
      sqlite3 state/dev.sqlite "SELECT source, ordinal, model, state, cost FROM calls;"
  (`sqlite3` CLI, or any SQLite browser, read-only.)
- Windows remains UNVERIFIED as shipped: the backend's Win32 privacy/no-follow code has
  never executed on Windows (run windows_preflight.py first and require a PASS), and the
  agent-native frontend toolchain has never been run on Windows (WSL2 escape route above).

## Review aids

`review-aids/` contains diffs against the two origins (draft6 backend, frontend-builder
@970e39c) limited to the files this integration added or changed.

## Windows setup (Aadi's demo machine)

Verified here on Linux; Windows notes below state what is and isn't exercised.

Backend:
- Python 3.10 (3.10 exactly; the pinned requirements and windows_preflight.py target it).
- `py -3.10 -m venv .venv; .venv\Scripts\pip install -r requirements.txt`
- `python windows_preflight.py` first: it validates the platform-privacy layer (ACLs instead
  of chmod), path handling and the suite entry point on Windows. This is the same
  preflight shipped with native draft6; share its output before relying on a Windows run.
- `python dev_install.py setup --state-dir ..\state --origin http://localhost:5199 --seamless`
  then `python run_dev.py --config ..\state\dev-config.json --port 8001`.

Frontend:
- Node: developed and verified on v22.23.4 (LTS line). `npm install` (~888 packages), then
  `set AUTH_DISABLED=true && npx agent-native dev --port 5199` (PowerShell:
  `$env:AUTH_DISABLED="true"; npx agent-native dev --port 5199`).
- The AUTH_DISABLED workaround is required locally: without it the dev server loops on an
  auth reload. Production build additionally demands BETTER_AUTH_SECRET and a managed
  Postgres DATABASE_URL - not needed for the local demo.
- NOT yet exercised: the agent-native toolchain on Windows. If `agent-native dev` misbehaves
  there, the escape hatch is running the frontend on WSL2 or keeping the frontend on any
  Linux/macOS machine pointed at the Windows backend (VITE_API_BASE_URL, loopback CORS rules
  apply - run both on one machine for the demo).

Seamless-store failure contract (short version, full text in demo_approvals.py):
recordings are atomic (temp + fsync + replace) with a sidecar pin; a crash mid-record fails
closed on restart, never half-trusted; concurrent processes on one state dir (two servers,
or a server and the CLI approval tool) serialize through one advisory lockfile; if locking
is unavailable the recording is refused, never performed unlocked; peer recordings and CLI
approvals are re-synced only when file and sidecar match under the lock.
