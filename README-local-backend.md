# Vigilens local backend, review draft

Local implementation dated 2026-10-27. Not committed, deployed, signed off, or connected to real models. No keys required, no outbound API calls. This replaces the unsafe sample-stub approach, not the team's agreed contract.

## Run and test

Python 3.10 or later:

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
```

`GET /health` reports fixture-only mode. Without an explicitly configured paired fixture, `POST /audit` returns 503 FIXTURE_NOT_CONFIGURED. This is intentional. It never invents results for an arbitrary upload.

HTTP request: multipart `image` file and `zones` JSON text, plus `Idempotency-Key` header (ASCII, 1-128 characters). Let the browser set the multipart Content-Type boundary. Dev origins: localhost:5173 and 127.0.0.1:5173. Do not expose the local server publicly.

## Implemented and locally tested

- Actual image decode/verify, declared vs decoded format checks, still-image-only checks, file bytes, dimensions and decoded pixel caps.
- Strict zone types, IDs, bounds, boolean rejection, nonfinite rejection, repeated/zero-area/self-intersecting polygon rejection.
- Boundary-inclusive foot-point membership, all containing zones and deterministic display-zone order. Unknown contact is explicitly unknown, not outside.
- Fixture accepts only the same decoded RGB raster and normalized ordered zone list as the configured manifest. Changed pixels or zones reject. Metadata-only image changes with identical decoded RGB pixels may match by design.
- Always `source=fixture`, evidence unavailable/null, export disallowed, illustrative trace provenance. Real audit timestamp is null; fixture_loaded_at is load time, not model time.
- Explicit unavailable evidence endpoint, consistent error envelopes for supported application/validation errors, bounded local repeated-request cache.
- Separate draft rules module covers proposed hazard/restricted/outside matrix, uncertainty findings and aggregation. It is NOT wired to real model output or enabled in the fixture API. The policy needs builder approval.

## Compatibility changes requiring frontend review

This is `schema_version=0.2-local-draft`, not a drop-in claim of frozen v0.2 compatibility. Adds Idempotency-Key, `zone_membership_status`, `zone_ids`, `evidence_export_allowed`, `fixture_loaded_at`, explicit evidence_status=unavailable and nullable created_at. API caps are proposed settings; rule policy is draft-unapproved. Zone arrays preserve order for exact fixture matching.

EXIF orientation other than 1 is rejected until frontend upright-preview behavior is confirmed. Core decode computes upright raster/dimensions, but silently rotating after zones were drawn would corrupt coordinates. Normalize the image before drawing and uploading.

## Pairing a fixture

Set `VIGILENS_FIXTURE_MANIFEST` to a trusted local JSON file containing `image_digest` (from core.decode_image), `zones` and `audit` with its manually authored persons/findings. It is local configuration, not an upload field. No production/sample photo is bundled: the original sample is missing and Raakin's synthetic scene has not been received/visually verified. Tests create simple in-memory images strictly for automated contract checks, not a visual PPE demo. A real fixture must be reviewed for image/zone/annotation consistency before inclusion. Do not reuse original canned detections on a new image.

## Limits and remaining work

- No real SAM/Muse adapters, privacy masking, calibrated confidence, retry execution, deployment, auth, paid-use guard, real evidence or real latency measurement.
- Idempotency cache is per process, max256 entries, one-hour TTL. It is suitable only for local no-cost fixture tests, not a durable paid-inference duplicate-charge guarantee. It does not survive restart or coordinate workers.
- Application file reading is bounded, but multipart parsing occurs earlier. Deployment requires ingress request/body limits, resource limits, access controls and a durable request ledger before any paid adapter is enabled. No deployment is authorized here.
- No full frontend/browser integration was run. Pillow format/decode checks reduce malformed-input risk; they are not a security audit.
- Tests currently emit a dependency deprecation warning for FastAPI TestClient using httpx; no test failure. Runtime dependencies are pinned to the tested environment; requirements-lock.txt records installed local dependency versions; inherited Pillow/httpx are pinned in requirements.txt.
- Face privacy via a SAM face concept remains unvalidated. Zero matches must not establish no-faces clearance. Keep evidence/export blocked pending a reviewed privacy approach.

## Sources for later adapter work, not entitlement or live-call proof

https://dev.meta.ai/docs/sam/overview
https://dev.meta.ai/docs/sam/segmenting
https://dev.meta.ai/docs/sam/client-libraries
https://dev.meta.ai/docs/sam/reading-segmentation
https://dev.meta.ai/docs/sdks

Only official pages were fetched for these notes. No model request has been sent.
