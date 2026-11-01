# Local durable fixture-job API, 2026-10-27 review draft

This module is independent of any frontend. New code is local only, not pushed, deployed or merged. Real adapters remain absent. Uses the previously reviewed backend as a base, plus ledger.py, runner.py and job_api.py.

## Tested routes

`job_api.create_job_app(database_path, manifest=None)` creates the FastAPI application. Default absent manifest deliberately returns 503 on job submission, same fail-closed fixture behavior as the original local API. Tests supply their own clearly labelled manually authored in-memory fixtures, not real detections or accepted team assets.

- POST /local/jobs: multipart image + zones, Idempotency-Key. Validates exact fixture pairing, registers one durable request, executes only local fixture work, returns job metadata and fixture result. 201 first terminal result, 200 repeated terminal result, 202 if already queued/running. No background worker or paid transport exists.
- GET /local/jobs/{job_id}: durable state/result retrieval, survives creating a new app with the same SQLite path.
- POST /local/jobs/{job_id}/cancel: true only if execution was still queued. Completed/running work is not described as stopped or unbilled.
- Existing /audit remains unchanged and retains its explicitly documented in-memory cache. New routes are opt-in, not a silent frontend contract switch.

No public authentication yet. Routes have a constant local scope and must stay bound to loopback for local testing only. A random job ID is not an authorization policy. Do not expose these routes publicly or put a database under version control. Results may be private. Add access control, retention/deletion and quotas before any shared service.

## Design review notes incorporated

- Record intent before future external calls; current running state means claimed local execution, NOT evidence a provider was contacted. external_started is a separate marker. No provider is contacted by this package.
- Atomic claim, no expired lease stealing, stale owner fencing, explicit needs_review on expiry. No ambiguous retry.
- Status codes including 400/401/403/404 do not prove zero cost. Cost defaults unknown, not zero. A separate zero_local_only value is used only after explicit reconciliation of a captured local fixture/mock result; no monetary amount or vendor billing is inferred. Real tri-state billing reconciliation remains unimplemented.
- Explicit local late-result reconciliation adds a journal transition and refuses external-started/live outputs. It doesn't re-execute work. There is deliberately no general paid-outcome resolution route.
- SQLite WAL and synchronous=FULL; state/result and journal transitions are transactional. Basic migration adds unknown cost to the earlier local schema.

## Verification

Run `python -m pytest -q` after requirements.txt installation. TEST-RESULTS.txt contains actual result. This combined suite includes the published 41 tests, 23 ledger tests, HTTP restart/result/status/cancel/conflict tests, and extra cost/late-result/migration tests. Linux process-contention test uses fork with a joined pool; no child process is left running. One TestClient/httpx deprecation warning remains.

No long-running worker, heartbeat scheduler, vendor usage reconciliation, durable spending guard, real mask/model behavior or frontend browser integration is claimed. Wall-clock jumps/network filesystems/distributed deployments remain untested. SQLite persistence is not a guarantee against duplicate vendor charges. The synthetic image task remains a separate handoff, not a backend blocker.

## Local scope/retention hardening

Trusted local_scope is supplied only when the application is created, never from an HTTP header/body. Status and cancellation are checked against it; another local application scope sharing the database gets 404, not another scope's result. This is a tested isolation primitive, NOT a substitute for public authentication.

Explicit expire_completed_results(cutoff) drops old completed payloads while retaining state, key fingerprint and journal tombstones. Repeated requests return completed with result_expired=1, not a fresh execution. Uncertain/running jobs are untouched. No automatic cleanup schedule is created. SQLite payload removal is logical removal, not guaranteed forensic erasure from WAL/backups/storage; a full retention/security policy remains open.

The combined suite now has 82 passing tests. This supersedes the earlier 76-test local review archive for local development, but nothing here has been pushed or adopted by the frontend. The published 41-test branch remains unchanged.

## Caller-semantics review revision

Caller output now includes boolean result_available/result_expired, retryable_with_same_key=false (no re-execution; same-key retrieval remains supported), a status_reason, cancellation_kind, null result_expires_at/dedup_expires_at and an explicit manual-cleanup/no-dedup-expiry policy label. No retention duration was invented. Queued cancellation is labelled before_local_execution; running cancellation is rejected, not portrayed as provider cancellation or no charge.

Completed fixture/mock execution with no external-start marker records zero_local_only, never a vendor amount. All unproven cases remain unknown. Cleanup now refuses even completed payloads with unknown cost, preserving them for reconciliation. It only removes known-local completed payloads while keeping dedup history; expiry preserves the existing cost classification. Public tri-state vendor-cost amounts and reconciliation are still not implemented.

86 tests pass after this review revision. Scope remains trusted local configuration, not authenticated identity. There is no list endpoint, no public-auth claim, no automatic cleanup, no dedup expiry and no uncertain-work expiry. This is local code, not a new repo push.
