# Current local backend review

2026-10-27. This package is unpushed local work. It extends an earlier published fixture framework, but is not itself deployed or connected to any model account. No paid calls, credentials, push/merge or account changes were made.

## Run and verify

Python3.10 is the tested interpreter. Use a private working directory and a new environment:

```sh
python -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
PATH="$PWD/.venv/bin:$PATH" sh scripts/check.sh
.venv/bin/python demo_offline.py
.venv/bin/python scripts/socket_smoke.py
```

The check script compiles the source and runs the test suite. The demo generates only synthetic pixels and temporary journals. The socket smoke starts an actual127.0.0.1 server with a generated paired fixture, verifies health/POST/repeat/GET and terminates it. It requires local port18476 free. Process termination is not graceful-shutdown proof. TestClient/httpx emits one known deprecation warning. Draft GitHub CI is kept in ci-drafts/backend-local-tests.yml.disabled. It is inactive and must be path-reviewed before activation.

Start the explicit bounded local app:

```sh
.venv/bin/python run_local.py --database /tmp/vigilens-review.sqlite
```

Without a manifest, health works but analysis fails FIXTURE_NOT_CONFIGURED. A manifest must match exact normalized image pixels and exact zones. Arbitrary photos never receive static fixture findings. Use `--manifest` only for a known paired local fixture. It binds loopback; no public bind flag. Existing broad-readable journals fail startup until backed up/restricted explicitly. Parent directory must be private. All persisted data here is test/local data, not production evidence.

## Connected local paths

| Path | What really runs | What does not run |
| --- | --- | --- |
| /audit | Validated exact paired local fixture response, no evidence | Real model analysis or dynamic rules on an arbitrary photo |
| /local/jobs | Opt-in durable fixture jobs, typed states/results, same-key identity, cancellation before claim | Public-authenticated jobs or provider dispatch |
| run_local.py | Cooperative worker in threadpool, startup expired recovery, local body/time/concurrency/rate/record bounds | Background scheduler, killing blocked callbacks or distributed limits |
| OfflinePipeline | Explicit mock/fixture observations -> draft rules -> typed report, bounded mock rechecks and deterministic explanation | Automatic promotion of unvalidated real-model proposals |
| SAM saved-text path | Actual pinned official parser/mask decoder with quotas and frame checks | Live call, actual media provenance/accuracy proof or contour/person association |
| Muse saved-response path | Disabled request builder, strict saved envelope/PPE proposal parser | Validated model accuracy or automatic assessed observation |
| Synthetic storage | Private bounded synthetic assets, scope/frame/pixel binding, test reads/deletes/logs | Real evidence release, public URL or authenticated retrieval |
| Usage ledger | Integer test-unit reservation/cap/uncertainty/reconciliation model | Money grant, provider invoice/charge/refund verification or enabled billing control |

## Caller behavior

An identical key binds the original scope/input/schema/rules. Conflicting identity returns409. Completed, expired, failed, cancelled or needs_review work never silently reruns. Existing queued/unclaimed work MAY start on another same-key POST when capacity frees. Responses say this in same_key_behavior. No background worker scans the queue. Queued cancellation is before-local-execution only; running cancel does not imply upstream stop or no charge. Interrupted/expired work stays needs_review until explicit local-only reconciliation, never automatic retry.

Local reconciliation can settle execution state but always clears evidence and sets privacy not_validated. Unknown-cost completed/uncertain rows are retained; manual result cleanup only affects known local-zero completed payloads and keeps dedup tombstones. No retention/dedup duration was invented.

## Safety/privacy boundaries

Every current evidence path is unavailable/exportfalse. Synthetic redaction and official doc masks are plumbing tests, not privacy accuracy certification. No detected faces means none_detected, not verified face-free. A model JSON schema cannot prove visual truth. Opposite known PPE observations preserve both ordered/source-labelled values and derive unknown/review. Real originals, bystanders, human review/release operators, retention and public-demo policy remain owner decisions. No released-copy recall is promised.

Request builders strip metadata by re-encoding upright RGB pixels to PNG before offline data URLs. send methods always raise; there is no live SDK/network client. Local bearer gating, if explicitly supplied through VIGILENS_LOCAL_ACCESS_TOKEN, is optional and not public/per-user authentication. No secret is generated or printed. Direct app factories bypass optional wrappers unless the caller composes them.

SQLite uses private0600 files, rejects file symlinks/broad-readable existing files and preserves uncertain state. This is not encryption, protection from hostile parent-directory replacement or certified backup/SSD erasure. Journal record/result caps are not total memory/event-history/disk limits. Public auth, deployed security and operational load/soak testing remain unfinished.

## Source map

- app.py/core.py/manifest.py/rules.py: fixture foundation, validation and draft rules.
- ledger.py/runner.py/worker.py/job_api.py/schemas.py: durable local jobs and lifecycle.
- limits.py/access.py/operations.py/run_local.py: optional local admission/operational wrappers.
- pipeline.py/reports.py/explanations.py: typed offline rules/report path and provenance.
- adapters.py/sam_parser.py/geometry.py/crops.py/muse_adapter.py: disabled requests and offline parsing/geometry.
- privacy.py/evidence.py/private_sqlite.py/usage.py: synthetic privacy/storage and local reservation primitives.
- tests/: synthetic tests, complete official documentation-mask record, integration/races.
- STATUS.md: done-vs-open backlog.
- OFFLINE-PIPELINE.md: chronological implementation evidence and caveats. Later sections explicitly supersede earlier limits.
- JOB-API.md and earlier README sections: historical local slices, not the latest state.
- TEST-RESULTS.txt, DEMO-RESULTS.txt, SOCKET-SMOKE-RESULTS.txt: actual local run outputs, not real-model validation.

Official sources used for current adapter boundaries are listed in OFFLINE-PIPELINE.md. Account entitlement, price, latency, accuracy and final provider behavior remain unverified without separately authorized live work.
