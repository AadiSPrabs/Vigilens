# Private fresh-upload backend

The actual `app.create_app` factory supports a separate private fresh-review service by explicit server configuration. The existing `/audit` fixture contract and `/local/jobs` remain unchanged. This is backend integration, not UI wiring or a release.

## Default state

- Provider transport is disabled. No API key or network provider adapter is in this change.
- Source approval file is empty. No real image permission is inferred.
- A trusted private accounting checkpoint path/hash is required before a job can reserve credits. No actual ledger, source image, private response or account credential is shipped.
- The default fixture app and `run_local.py` do not mount fresh/display routes. Use `create_app(fresh_service=service,fresh_token=token)` to opt in. The token is captured per app, not reread from global environment on each request.
- All mounted fresh and private-display routes require `X-Vigilens-Local-Access` matching an externally configured token of at least 32 characters. The existing optional outer `Authorization: Bearer` gate from `run_local.py` applies too when configured. This is local access control, not production human authentication.
- Bind only to loopback. No deployment, public hosting, merge to main, release or evidence export is included.

## Flow and routes

`POST /fresh-review-upload` accepts multipart `image` and `zones=[]`. Trusted server configuration supplies exact approved source, accounting and transport. One SAM segmentation, one or two distinct persons, original person crops and strict helmet/vest observations feed the private review. Zero/more-than-two people or cross-person crop ambiguity blocks the whole result. No client model/prompt/budget controls.

`GET /fresh-review/{source}` returns durable state, held reservation, known listed cost, attempted-call total and reconciliation status. A repeated source does not dispatch again. An uncertain attempt retains the full reservation and never retries automatically. Zero calls on a GET means that GET made no calls, not that the underlying job was free.

`GET /fresh-review/{source}/integration-contract` returns lossless binary mask RLE, preserved PPE observations, distinct unknown/not_checked/not_evaluated states, null evidence image and export false. The version is a local proposal, not an agreed frontend API.

`POST /fresh-review/{source}/private-display` takes the exact original plus source-bound manual regions. `GET /private-display/{session}/image` and `POST /private-display/{session}/review` use `X-Vigilens-Display-Session`, a private browser nonce. Whole-frame review acknowledges operator claims only, not reliable face detection.

`POST /fresh-review/{source}/contact` requires that same nonce and a current source-bound preview. A strict manual point must hit the exact person mask. Changes append private SQLite history; latest own-browser claim remains active for 30 minutes, with 128-event cap. History survives restart, but previews need recreation. The nonce is not verified human identity.

`POST /fresh-private-report/{session}` joins exact result, preview acknowledgment and independent head/torso visibility review. Unknown stays unknown. Contact is an operator claim. Compliance is never evaluated, zones are not checked, privacy is not validated and export is always false.

## Trusted configuration

`create_app(fresh_service=FreshPipeline(...),fresh_token=token)` injects a server-owned service. `FreshPipeline` requires one journal for the entire authorized aggregate and exact private carry file/hash. The carry contains `aggregate_cap_usd` (currently exactly `5`), `provider_calls_total`, `conservative_booked_usd`, and `blocked_source_digests` for all already-paid sources. Reconcile prior spend and source tombstones from original records before configuration. Do not create a new journal to bypass earlier attempts or reservations. Uncertain prior costs must remain booked conservatively.

`ApprovalStore(path,sha)` reads an operator-reviewed file containing `version:1` and exact-source `approvals`. Each entry names `size`, `rights_reference`, `provider_upload_approved:true` and `provenance` with `owner_instruction_reference`, `rights_review_reference`, `reviewed_at`, `reviewer`, `scope`. No HTTP endpoint grants approval. Default processing scope is `private_provider_processing`; synthetic test scope cannot enable it. File pins prove only local integrity, not that cited references actually grant rights. Inspect original authority before adding real entries.

Each fresh job reserves at most $2.627012 at the documented current model/rate bounds. A provider or price change requires review before enabling transport. Completed reads reparse saved SAM, rebuild original crops/requests, reparse PPE, validate mask/person/cost and top-level policy. Raw sources, requests, replies and journals must stay outside the repository in a private controlled directory. This is not protection against a malicious host rewriting code and records together.

## Verification

From `backend` with dependencies installed:

    PYTHONPATH=.:tests python -m pytest -q
    PYTHONPATH=. python scripts/socket_smoke.py
    PYTHONPATH=. python scripts/fresh_socket_smoke.py

The fresh smoke starts the actual backend factory over loopback HTTP, uses generated pixels, the real official SAM parser and synthetic SAM/PPE replies. It verifies upload, repeated source, private preview, acknowledgment, contact and report with zero external provider calls. It does not establish real-image accuracy, provider compatibility, face coverage or safe release. Tests generate their own sources/accounting/approvals; no private sample dependency.

Before enabling real sources: verify source rights and processing authority, current model/rate policy, aggregate accounting and transport behavior. Production worker isolation, authentication, privacy/retention, zone/severity policy, frontend agreement and UI are separate work.

Private pipeline and display session state are per application instance. Sharing a browser nonce does not share preview state across instances. The local gate does not change this into a verified human identity system.

## Integration review fixes
Browser-origin preflight permits the exact access/session headers for localhost:5173 and127.0.0.1:5173 only; approved OPTIONS passes CORS without performing work. Actual multipart requests still require the private token. Unapproved origins fail CORS, which is not a substitute for token authentication.

Created derivative pixel identities persist as tombstones in the SAME configured aggregate journal. Any app instance/restart using that journal rejects those pixels before approval or provider dispatch, even if an approval entry mistakenly names them. No global image registry is created. A different independent journal cannot discover those tombstones: one aggregate MUST use one journal, and source approval review must exclude derivatives from other workspaces. Cross-independent-store protection is not claimed.
