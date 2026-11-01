# Private fresh-upload backend

The actual `app.create_app` factory supports a separate private fresh-review service by explicit server configuration. The existing `/audit` fixture contract and `/local/jobs` remain unchanged. This is backend integration, not UI wiring or a release.

## Default state

- Default factory transport stays disabled. Explicit MetaTransport and run_private.py support a private live configuration; no API key or live approval is shipped.
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

`POST /fresh-private-report/{session}` joins exact result, preview acknowledgment and independent head/torso visibility review. Unknown stays unknown. Contact is an operator claim. Current operator zones and explicit PPE/access rule findings join the report when configured. Missing contact/priority remains unknown/unrated. No safety clearance or compliance certification is made; privacy is not validated and export is always false.

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

## Explicit live startup

    python run_private.py --config /absolute/private/runtime.json --port 8001

This entry binds127.0.0.1 only,disables access logging,and validates private files before serving. Config is0600with exact keys `version:1`, `journal`, `carry_path`, `carry_sha256`, `approval_path`, `approval_sha256`, `key_file`, `access_token_file`, `execution_scope:"private_provider_processing"`. All paths absolute, journal parent0700existing, referenced secret/carry/approval files0600. Never commit this file or its referenced data. Startup does not dispatch or create a job. Runtime examples must not reset actual spending: carry must reconcile every previous paid source/reservation.

MetaTransport posts only to https://api.meta.ai/v1/responses, blocks redirects, uses a90second timeout and bounded response bytes, makes exactly one attempt and never retries HTTP/network failures. Key is read from privatefile at dispatch,never returned through API. Requests are canonicalized by FreshPipeline before transport; Standard muse-spark-1.3/SAM3.1,storefalse,no tools/background. Current pricing/model checks: https://dev.meta.ai/docs/pricing-rate-limits , https://dev.meta.ai/docs/models , https://dev.meta.ai/docs/sam/segmenting , https://dev.meta.ai/docs/protocols/responses . Before future use recheck rates/model limits;512outputcap includes reasoning,conservative reservation unchanged.

### Private real-provider qualification (2026-10-28)

The explicit `run_private.py` path was qualified on loopback HTTP with one separately approved private test image: one SAM call and one person PPE call completed. A same-source repeated upload and a new-process status read each dispatched zero calls. Request/response, crop, mask and cost associations were checked from the retained private journal. Exact-source face-only display treatment and head/torso evidence checks produced a private report. Boots were not visible, so contact remained unconfirmed. Export remained disabled and privacy/accuracy remained not validated. This is a single development qualification, not a production or accuracy benchmark. Source permissions, keys, image, raw replies, journal, accounting identifiers and access token are deliberately absent from this repository.

The full local suite passed 376 checks (12 deprecation warnings). Network timeout/oversize/status failure and uncertain-reservation/restart behavior use controlled synthetic tests, not additional paid failure calls.


### Local integration draft: capability discovery and cleanup

`GET /health` keeps its historical `/audit` fields (`mode:fixture_only`,
`real_analysis_enabled:false`) and adds
`capabilities.fresh_review_routes_mounted`. This boolean reports only that the
factory mounted the private routes. It is NOT transport readiness, approval,
accounting readiness, authentication success or production readiness. A disabled
pipeline can report mounted routes; the default fixture app reports false.

Fresh-enabled apps permit DELETE preflight from the same two approved localhost
origins for private-display cleanup. Actual cleanup still requires both the
configured local-access token and the owning browser nonce. Default fixture-only
apps do not add DELETE. CORS never replaces these access checks.

### Unpublished zone-review geometry slice

The private completed-source flow adds POST/GET
`/fresh-review/{source}/zone-review`. POST requires exact `source_digest`,
`result_sha256`, `zones` (the existing id/name/hazard/points schema), and a
bounded `reviewer_label`. Both access token and current source/result-bound
browser preview nonce are required. Zones are operator geometry only: the
legacy hazard boolean is preserved data, NOT an applied safety policy.

Snapshots append to the SAME private journal, source/result/browser-bound,
with a canonical zone digest and bounded history. Identical updates reuse the
prior event. Empty zones explicitly clear the active geometry, not history.
GET joins the latest snapshot with current unexpired manual contacts. A point
exactly on a polygon edge abstains as boundary_needs_review. Overlap returns
all containing zones; display selection is smallest area then ID, not safety
priority. Missing/expired contacts stay unknown; no-zone is not_configured,
not confirmed outside. This is operator-claimed placement, not automatic feet
localization or verified human identity. Private reports carry this separate
geometry view, still no compliance decision, no privacy validation and no export.

Inference identity and prior paid results remain unchanged by zone edits.
These routes make zero provider calls. Restart requires recreating the private
preview before access to retained journal snapshots. The GET integration-contract
continues its original no-zone provider-observation proposal; the separate zone
contract is a new local proposal, not an agreed frontend API. Camera-wide zone
reuse, severity, policy decisions, clip processing and real-browser UI wiring
are not completed by this slice. Current geometry is verified with generated
pixels/synthetic provider replies, not a new real-photo qualification.

`GET /fresh-private-report/{session}/overlay` adds a private inspection image
on the exact already-treated preview, after whole-frame acknowledgment. Person
boundaries come from erosion of the verified lossless SAM raster, not invented
boxes or generated imagery; operator zone edges are overlaid with source-frame
mapping. Every treated privacy region is copied back after drawing so overlays
cannot repaint it. This image has no new PPE labels or safety verdicts. It is
inline/no-store, same token/nonce/expiry/source-binding checks, and explicitly
export=false. It is NOT released evidence, a privacy certificate, a polygon API,
or a completed shareable report. The treatment preserves private uncertainty.
Synthetic raster visual checks and actual loopback access passed; real-photo
coverage and UI overlay usability remain unvalidated.

### Other unpublished preparation, not completed features

`fresh_review/policy.py` validates a new explicit policy configuration proposal:
immutable id/version/hash/camera/scope references, independent access modes
(allowed/authorised_only/no_entry_all), explicit helmet/vest/access rules and
configured priority order. Missing priority remains unrated. This is structure
only, not owner approval, legal advice, a default severity matrix or a mounted
policy-approval endpoint. No policy evaluation is enabled yet. Legacy hazard
booleans are not silently mapped to no-entry semantics.

`fresh_review/clips.py` prepares bounded still frames locally with ffmpeg and
ffprobe. Limits and offsets must be explicit; file/pipe protocols only, no shell,
bounded subprocess duration/output, upright single-stream video only, temporary
source deleted, metadata-stripped PNGs with clip hash/sample index/pixel identity.
Offsets are requested decode offsets, NOT guaranteed exact presentation times.
No cross-frame identity, complete temporal coverage, model dispatch, HTTP clip
upload, source/provider permission, report aggregation or export is claimed.
Current tests require ffmpeg and ffprobe installed; Python requirements alone
do not install them. This is clip preparation, not finished clip analysis.

The policy module additionally has a pure configured-rule evaluator, NOT an
approved/mounted safety service. It requires exact camera and immutable policy
hash, explicit position per zone and separate authorisation claims. Unknown
position/PPE/permission and unrated violations stay review-required. No-entry
presence is not asserted to be a temporal crossing. Outside rules apply only
when explicitly configured. All findings are retained alongside the highest
configured priority; summary is never safe/compliant. Illustrative synthetic
policies in tests are not site policy or owner approval.

`fresh_review/rechecks.py` constructs source/result/person/crop-bound plans for
SAM crop re-segmentation then original-crop PPE reassessment, with explicit
0–2 attempt bounds and escalation at the bound. It has no dispatch/API/approval
or accounting mutation. A candidate comparison preserves original observations
and forces contradictory known observations to unknown for review. Execution
still requires reviewed crop-person association, canonical parser/cost/reserved
request integration and the SAME authorized aggregate journal. These helper
plans are not a completed real recheck loop or partner-model fallback.

`RecheckJournal` now implements a disabled-dispatch reservation scaffold in the
SAME aggregate SQLite journal. Its deliberate attempt is bound to original
source/result/person/crop/plan hashes, deduplicates repeated reservation, and
retains the full reviewed current model bound. Original FreshPipeline claims
now include recheck reservations in aggregate capacity checks. Invalid prior
plan/accounting bindings fail closed. A textual authority reference is a record,
not evidence of permission. No HTTP reserve endpoint or release/reset shortcut
is provided. This is not live recheck execution: parser, response/cost association,
provider dispatch, uncertain outcomes and independent review are still required.


### Camera draw-once geometry proposal (unpublished)

POST `/fresh-review/{source}/camera-zones/save` and `/apply` require current exact
source/result preview, browser nonce, reviewer label and `fixed_scene_confirmed`
strict true. `camera_binding` has exact `camera_id`, immutable `scene_revision`,
`width`, `height`, `coordinate_space=normalized_upright_source_v1`, and
`transform=identity`. Save pins current operator geometry as bounded immutable
same-browser template; apply requires explicit `template_id` and exact matching
binding on an independently approved target source. Changed scene, raster or
transform is refused, not rescaled. Explicit old templates remain historical even
when source geometry later changes. No policy, manual contact, safety decision,
source approval or provider call transfers. Fixed scene is an operator claim, not
automatic image registration or verified camera identity. No browser UI integration
or real-camera qualification claimed. Existing source-specific zone routes remain.


## Reviewed sampled-clip reports

Trusted-local clip upload returns private_clip_review_id only after sampled image
jobs complete. The immutable manifest binds clip hash, duration, ordered sample
indices/requested offsets, exact frame pixels and result hashes to the browser.
POST /fresh-private-clip-report/{id} with {"frames":[{"sample_index":0,
"session_id":"current-preview","review":{...exact per-frame report review...}}]}
requires every ordered sample, current source/result-bound private preview,
whole-frame acknowledgment and per-person visibility review. No caller supplies
PPE conclusions or rewrites frame identity. Same pixels may reuse one image job
and preview while retaining distinct sample indices/offsets. Distinct-source
previews coexist up to eight active sessions/32MB; replacing one source invalidates
that source's prior preview. Larger clips must be reviewed in bounded sets, not
silently dropped. Manifests survive restart; preview/ack must be recreated.

The matching /pdf-preview route combines at most eight reviewed samples and32pages,
20MB total. Pages show requested decode offsets, not exact presentation timestamps.
No tracking, continuous coverage, temporal crossing or safety clearance is inferred.
Output remains private/no-store/exportfalse. Rechecking every current sample can
be slow; original terminal results must not be polled unnecessarily.

Health mode private_review_configured means routes/service mounted, not authority
or readiness. Capability fields report the1-2person cap, local-only authentication,
exportoff and trusted clip decoder configuration; no secrets/paths are exposed.


## Configured bounded review loop

POST /fresh-review/{source}/bounded-review-loop takes only source_digest and
result_sha256, requires current private preview, and uses server-owned existing
review_loop_attempts. It cannot accept attempt IDs, create grants/reservations or
spend from caller JSON. Only genuinely unknown ORIGINAL observations qualify.
At most one pre-reserved/granted attempt per person (two total) is preflighted
before any dispatch. Uncertain association/provider outcome stops and escalates;
there is no retry. Completed candidate observations remain separate from original
and require human review. Known observations need no uncertainty recheck.

Private runtime config accepts optional trusted_clip_limits (ClipLimits fields),
recheck_grant_path/recheck_grant_sha256 pair, explanation_grant_path/
explanation_grant_sha256 pair, and review_loop_attempts source-to-existing-ID lists.
Private absolute paths/pins and existing exact source attempts/grants are validated
on startup. No new reservation/job/dispatch/approval is created by configuration.
An exact grant file is an integrity record, not source evidence of owner authority.
Real unknown recheck and spatial commentary qualification still remain open.

ArchiveExplanation is an explicitly selected operator qualification harness, not
fresh ingestion: verifies retained authentic archive evidence per access, pins the
original source pixels and already-reconciled whole aggregate carry, and permits
only an exact-granted commentary request through the existing executor. It creates
no jobs table and does not restore a historical fresh job. Upload/run is disabled.
No default runtime or HTTP request installs this harness or grants authority.


## Disabled private-download preparation

The per-image and sampled-clip /private-download routes are disabled unless the
server explicitly sets operator_private_download_enabled=True after owner scope
acceptance. No HTTP payload or default runtime config enables them. After owner acceptance, explicit runtime operator_private_download_enabled:true enables guarded private downloads. They reuse
all current PDF/whole-frame/person/sample guards, return an attachment with
private/not-certified-safe-to-share restriction, no-store and export-allowed false.
Human-reviewed private-only downloads are a local option only; this is not automatic privacy protection or a public release. There
is no public-share route, privacy certification or automatic coverage guarantee.


### Explicit SAM-cardinality stop settlement

Operator-only fresh_review.stopped_source.settle(service,source) adds immutable
verified accounting proof for a completed SAM-only0/>2person stop. It makes no
provider call and never marks the original job complete. Unknown/missing/pending
artifacts retain fullhold. Original result staysNULL/running_uncertain/no-retry.
Review/test this contract before actual use..


### Explicit wide-scene partial-PPE local mode

Optional wide_scene_limits config selects a separate WideScenePipeline. Source
approval must include wide_scene selected_person_ids plus authority_reference.
Capacity defaults16, max32, all detections preserved; PPEselection max3 with full
worstreservation and sameaggregate5. Unselected, tiny and crosspersoncrops stay
unassessedunknown with distinct reasons. This is not full10+PPEcoverage, real
accuracy or automaticcontact. See STATUS.md for the required
sequentialreservation/partialcoverage continuation work. Legacy defaults unchanged.
