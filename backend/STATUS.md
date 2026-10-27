# Frontend-independent backlog status

Local continuation2026-10-27. Not pushed, deployed or live-model tested. Read OFFLINE-PIPELINE.md for precise limits and all sources. Tests are mostly synthetic/local fixtures plus one complete official saved mask record. No test count implies production readiness.

| Area | Implemented locally | Still open |
| --- | --- | --- |
| Foundation | Run entrypoint, dependency lock, versioned migration check, durable journal, worker checkpoints, optional HTTP lifecycle, body deadline/byte/concurrency and active-job bounds | Total event-history/disk growth beyond record cap, broader stress/memory tests, background queue scheduler, stronger multi-process lifecycle |
| API | Typed local job/status/cancel and offline mock report models, invariants, error docs, explicit queued same-key behavior, compatibility path | Typed real-audit contract and frontend acceptance; direct factories bypass optional wrapper |
| SAM | Offline request builder, bounded stream envelope, actual official saved-text parser/mask decode, crop/resize/inclusive box tests | Live event/transport integration, detection association/contours, actual API/accuracy/cost validation |
| Muse | Disabled image request builder and strict bounded PPE proposal parser | Verified crop/person association, accuracy, adapter-to-real-rules path |
| Rules | Deterministic draft matrix, overlap/unknown handling, bounded mock rechecks and preserved contradictory observations, deterministic explanations | User/builder acceptance of policy matrix, real observation validation and any calibrated thresholds |
| Privacy | Synthetic opaque-redaction guards, zero-match/unknown block, explicit not_validated/export false, no real-photo path | Real detector/masking validation, bystander handling, review operator/policy, real release checks and export auditing |
| Storage | Durable local reports/jobs; bounded synthetic-only assets, scope/pixel/frame binding, metadata stripping, local read/delete logs, no resurrection | Authenticated protected evidence HTTP endpoints, real originals, approved retention/access/deletion/backup policy |
| Auth | Optional pre-body local bearer gate only | Public authentication, per-user verified principals, roles, token rotation/revocation, protected tenancy |
| Usage | Atomic durable test-unit reservations, cap, uncertainty holds, scoped/idempotent explicit settlement | Real prices/periods/provider evidence and billing feed, authorized budget ownership, dispatch coupling |
| Operations | Safe aggregate local timing/status counters, local rate window, fixed journal errors, disabled access log, local check script/demo runbook, inactive CI draft (ci-drafts/*.disabled) | Distributed per-user rate limits and metrics export, redaction review, deployment ingress, hosted CI, load/soak tests |

## Unchanged authority boundaries

No money, keys, account changes, push/merge, deployment or live requests. Local scope labels and test parameters are not owner authorization. No product retention/privacy/severity policy has been adopted. No real scene is represented as analysed or safe. Aadi can decide any eventual policy at the point it is needed; these remaining decisions do not invalidate completed local interfaces/tests.
