# Offline pipeline and cooperative worker milestone

Local review code, 2026-10-27. Supersedes the previous local 86-test package for development only. No repository push, deployment, API keys, paid calls or accepted frontend contract change.

## Implemented

`pipeline.py` defines upright named source frames, explicit local observations, completed segmentation batches, cropped-pixel-to-normalized geometry conversion and a bounded mock recheck policy. OfflinePipeline connects validated observations to the draft deterministic rules. Unknown PPE survives a failed recheck. Missing/partial segmentation cannot become a successful empty-person report. Duplicate identities, live source labels and changed recheck identity/geometry are rejected or kept uncertain. Traces describe callbacks actually invoked, never invented provider confidence or execution. Cancellation checkpoints withhold results.

`privacy.py` is synthetic redaction plumbing only. It accepts explicitly authored boxes on a matching synthetic image/frame and opaque-fills those regions on a copy. Incomplete/uncertain coverage, wrong frames, zero regions and real/live sources fail closed. Returned metadata ALWAYS keeps evidence unavailable/export false. Neither passed tests nor a synthetic coverage flag validates a real face detector. There is no no_faces or masked clearance, no real photo export, and no assumption that SAM face prompts are accurate.

`worker.py` adds a bounded single-slot local worker with a shutdown flag, owner lease renewal and cooperative checkpoints. Shutdown/timeout/interruption goes needs_review, no automatic retry. Before-claim shutdown leaves queued work alone. Multiple workers still rely on SQLite atomic claims. This worker is a callable library, not a background process manager or new HTTP route. It is not enabled for live transport.

## Limits to preserve

- Cooperative timeout cannot kill a blocked callback or stop an upstream request; uncooperative code may continue until it returns. Completion is checked again before result persistence. No active model/upstream client exists.
- No automatic queue scheduling, fleet orchestration, public authentication, real billing guarantee, face detection, segmentation decoder or model request transport is claimed.
- Model IDs/wire schema were researched previously but adapters remain disabled; this package uses mock observations, not realistic vendor responses.
- Person polygons in tests are manually authored geometry, not SAM masks or verified safety observations. Matrix/recheck limits remain conservative local test choices needing owner/builder policy acceptance.
- Pipeline, synthetic redaction and worker are tested library interfaces; the existing /audit route is unchanged. Local job API remains opt-in as JOB-API.md explains. No frontend adoption is implied.
- Runtime secret handling, protected real evidence storage, ingress/concurrency quotas and deployed operational controls remain future work.

## Verify

From this directory after requirements.txt install:

```sh
python -m pytest -q
```

Actual combined result is in TEST-RESULTS.txt. It includes prior 86 tests plus pipeline geometry, unknown/failed rechecks, privacy guards and cooperative worker lifecycle tests. A single existing TestClient/httpx deprecation warning remains. Test output is not proof of product policy, real accuracy, account access or billing behavior.

## Reviewed hardening after Ayre's semantics checklist

- Known PPE changing to its opposite during a mock recheck becomes unknown with an explicit contradiction trace; it cannot silently take the favourable answer. Contact certainty cannot be changed by the PPE callback. Frame/input dimensions, identity lengths, batch cardinality and boolean statuses are bounded/strict.
- Explicit local late-result reconciliation remains supported as a manual job-state operation; it now forcibly clears evidence image/status/export even if a caller supplies a claimed masked result. This is different from automatic late overwriting or privacy approval. No real evidence is released.
- `limits.py` bounds admitted full ASGI request bodies before multipart parsing, including chunked requests, and restricts concurrent HTTP requests. `run_local.py` is an explicit loopback-only wrapper with access logs off and a 32-active-job local queue cap. Test limits are engineering defaults, not approved user spend/retention/security policy.
- Whole-body buffering is capped, but it adds bounded memory overhead and does not enforce a read timeout. A stalled sender occupies a slot until disconnect. For non-loopback use, ingress timeouts, byte limits, authenticated principals, rate limits, total memory stress tests and more remain required. Do not deploy this wrapper as production protection.
- Queue capacity only counts queued/running rows, not retained history. Storage growth is still unbounded; no automatic deletion or invented retention duration was added.
- Direct app.py or job_api.py factory use bypasses the optional admission wrapper. The local runner in the HTTP fixture API remains synchronous; the new cooperative worker library is independently tested, not silently wired into the API.

## Local run

```sh
python -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
.venv/bin/python -m pytest -q
.venv/bin/python run_local.py --database /tmp/vigilens-local-review.sqlite
```

No manifest means health succeeds but fixture submission fails closed. For a known paired local manifest add `--manifest /path/to/manifest.json`. There is no public bind flag, and no model client is constructed. `--port` can select an unprivileged loopback port. Existing `/audit` behavior and opt-in job routes remain explicit.

## Second independent slice

`adapters.py` builds an offline SAM 3.1 image request from validated upright raster bytes using input_text plus input_image.image_url data URL. It restricts local application prompts to one of person/helmet/vest/face. A face request is merely a concept request, not validated privacy. The send method always raises: no credentials, client, sockets or account access are implemented.

The SAM stream boundary validates SDK event envelopes and bounded text accumulation/completion. Empty successful output is labelled none_detected and never clearance; incomplete/error streams release no partial geometry. This is NOT the official token/mask decoder, NOT a Muse adapter, and NOT a production SSE implementation. Nonempty output is raw data awaiting the official parser, never a list of invented polygons. It makes no transport/billing/retry guarantee.

Request and output conventions were rechecked against these official pages on 2026-10-27:
- https://dev.meta.ai/docs/sam/segmenting
- https://dev.meta.ai/docs/sam/reading-segmentation
- https://dev.meta.ai/docs/sam/overview

`geometry.py` adds strict explicit crop/resize transforms, nearest-neighbour decoded binary TEST-mask placement and inclusive source-box conversion including the last row/column. It rejects ambiguous raster dimensions, nonbinary values and rotated frames. No SAM encoded payload parsing or contour extraction exists.

`explanations.py` emits deterministic rule-linked explanations and verifies exact structured finding/status/severity claims. It rejects conflicting, missing, duplicate or arbitrary prose claims. It does not pretend a schema validator understands natural-language truth. Pipeline results carry deterministic explanations plus original and returned recheck observations, including BOTH values when a contradiction is collapsed to unknown for assessment. No raw provider error text is published.

Journal migrations record schema user_version=1, preserve older unknown-cost results, are idempotently tested, and reject future schema versions rather than downgrade. Restart recovery keeps interrupted jobs needs_review and same-key dedup intact. A local pipeline->worker->scoped journal integration test verifies the assembled path without implying HTTP worker integration.

`scripts/check.sh` is a local compile/test command. `.github/workflows/backend-local-tests.yml` is a draft CI configuration only. It was not pushed, activated or run on GitHub; it assumes this source is placed at the repository root and needs adjustment if installed under a subdirectory. The local shell command was exercised.

A second description-only review highlighted provenance and export ordering. Both conflicting observations are retained. Reconciliation may only clear export, never enable it. All current paths keep evidence unavailable, so there is no release endpoint or export audit log yet. A flag cannot recall copies already sent; future real-evidence release needs independently authorized review, ordering and logging. No product release/human-review policy is adopted here.

## Offline usage reservation model

`usage.py` is a separate durable, atomic local test-unit budget model, not enabled dispatch/billing control. Integer units have no claimed currency or Meta price. It reserves an explicit maximum, blocks concurrent oversubscription, preserves uncertain reservations across restart, keeps same-key dedup, checks scope and settles only on explicit local reconciliation. Exceeding the reservation cap is blocked for review, not silently charged or released. Transition logs use fixed safe reasons, not caller-provided private prose. A released key stays terminal and cannot create a second reservation.

This model is NOT connected to any provider client, HTTP request, wallet, user spending grant or billing feed. Passing a budget number to this local class is not user authority to spend. The pre-dispatch release method must never be called after dispatch; uncertain outcomes hold their reservation. Vendor reconciliation, authenticated budget ownership, per-period policy and measured charges remain unimplemented. No live spend is enabled.

Additional mutation guard: pipeline inputs and callback observations are deep-copied so a mock callback cannot silently mutate the original person geometry or caller data. Such changes cause recheck failure and preserve uncertainty.

## Third slice: opt-in HTTP lifecycle and bounded synthetic storage

Latest change supersedes the earlier worker/HTTP separation in the first two slices: `create_job_app(..., cooperative_worker=True)` now opts into the cooperative LocalWorker and startup expired-lease recovery. The explicit run_local.py entrypoint enables that mode; the default factory preserves the prior local runner. Work executes in a threadpool, not on the HTTP event loop. An occupied worker leaves a newly registered job queued; an explicit same-key request can claim that still-unstarted job later, not rerun uncertain work. Queued jobs can be cancelled. Shutdown sets the cooperative stop flag. Tests include actual overlapping HTTP fixture requests, queued cancellation, repeat keys, startup recovery and before-claim shutdown. There is no background scheduler; queued work needs another explicit request, and uncooperative callback code still cannot be killed.

The admission wrapper now adds a total 15-second request-body read deadline, including chunked bodies. Stalled requests return a safe408 and free their slot, before execution. The wrapper still is optional and direct app factory use bypasses it; this is not public network hardening certification. The inbound server may itself already hold a large chunk before this layer rejects it.

`evidence.py` is bounded private on-disk storage for synthetic local assets only, with immutable audit/frame/pixel identity, scoped access, pixel-only PNG re-encoding, private file mode, symlink refusal, record/byte limits and deletion tombstones. Local test reads and deletes are logged. Real-source storage is rejected. It has no HTTP retrieval route, URL, release operation, identity provider or encryption. Scope is trusted local configuration, not authentication. Filesystem mode is a local precaution, not verified hostile-host isolation; deletion removes logical payloads with SQLite secure_delete but does not certify filesystem/backups/SSD erasure. Metadata tombstones remain. Real-evidence storage, retention, public access and export audit/order remain unimplemented.

Review follow-through:
- Both original (attempt0/source) and returned recheck (attempt/source) values are visible in provenance; derived contradiction stays unknown.
- Identical usage reconciliation is now idempotent with no second accounting event/release. Changing an already-settled amount conflicts. Cap failures never evict held uncertain reservations; held is not charged and released is not a verified refund.
- Local job reconciliation explicitly sets privacy_review_status=not_validated, separate from completed job state. No operator authority or verified-provider-evidence policy is implemented or adopted by the test-only API.

## Fourth slice: actual official parser integration, offline only

`sam_parser.py` now uses pinned `meta-sam-parser==0.0.6` to parse completed saved image output and decode its real mask payload. This supersedes the earlier 'official parser unimplemented' limitation for this offline saved-text path only. The Python package exposes parse_responses_stream plus image_segmentation_format, not the parse_image_stream convenience name suggested by broad documentation. The integration uses the installed package's actual public signatures.

A complete encoded mask from the official reading-segmentation example is parsed and decoded in tests: source320x334, object box [211,228,271,255) after the official parser converts inclusive wire upper coordinates to half-open, decoded60x27 binary mask. The example is a saved documentation record, NOT a model call, person observation, PPE result or labelled accuracy set. Confidence is None when absent, never invented as zero or calibrated safety confidence.

The caller must explicitly supply wire_completed=True. Conservative text/frame/mask-area/count preflight runs before the official parser, whose decoder has no built-in quota ceiling. Any official diagnostic, incomplete output, malformed payload, source mismatch or unsupported record blocks the entire local result, never partial geometry. The wrapper finalizes one saved text lane, including empty text; this is reconstruction for offline parsing, not fabricated proof that an upstream call completed. For live use, real event completion must be verified before invoking it. No transport, account access, paid call, parser-to-PPE pipeline, face-validation or evidence release is implemented.

Sources checked2026-10-27:
- https://dev.meta.ai/docs/sam/client-libraries
- https://dev.meta.ai/docs/sam/reading-segmentation

The installed official parser and the full211-test previous slice were verified in a newly created Python3.10 environment. The current full suite is in TEST-RESULTS.txt; no GitHub CI execution is claimed.

## Fifth slice: response schemas and optional local gate

Local job/status/cancel responses now have typed OpenAPI models with validation of availability/expiry/state/cancellation invariants and error-envelope documentation. Because a same-key POST may start previously queued-but-unclaimed work in opt-in worker mode, a new `same_key_behavior` field distinguishes `may_start_queued_local_work` from `retrieve_only_no_new_execution`. `retryable_with_same_key=false` still forbids re-executing interrupted/completed/failed work; it does not mean a queued request can never start. This is an additive local contract change, not an accepted frontend contract update.

`access.py` provides an OPTIONAL local bearer gate, checking a preconfigured token before consuming the body. Duplicate/missing/wrong authorization headers fail401. run_local.py uses it only when VIGILENS_LOCAL_ACCESS_TOKEN is supplied from the environment. No real secret is generated, collected, stored, committed or printed by this package. Tests use an obviously synthetic token. Length/ASCII validation does not establish entropy or safe secret provisioning; the deployer must provide a properly random secret through approved secret handling. Default remains loopback-only without the gate; this is not public authentication, per-user principals, authorization roles, token rotation/revocation or rate limiting. Direct factories can bypass the optional gate. No public identity provider or access policy has been selected.

## Sixth slice: disabled Muse Spark1.3 request/proposal adapter

`muse_adapter.py` constructs an offline Muse Spark1.3 Responses request with upright single-person crop bytes and an exact finite PPE proposal schema. Responses uses `text.format` (type json_schema, name, schema, strict), NOT Chat Completions response_format. The model identifier and format were checked against current official docs, not inferred from old examples. send() always raises; no SDK client, request dispatch, credentials, provider storage decision, live entitlement or billing exists.

Parsing requires explicit successful response completion, bounded JSON, no duplicate keys, exact person identity, exact fields/enums, no extra severity/confidence/export claims. Uncertain crop quality forces PPE unknown. A structurally valid response stays source=unvalidated_model_proposal, requires_human_review=true and export=false. It is NOT converted into the mock OfflinePipeline Observation type or automatically used for rules: structural validity cannot establish visual correctness, person association or calibrated confidence. No real crop was sent. No parser accuracy, model quality or billing claim is made.

Sources checked2026-10-27:
- https://dev.meta.ai/docs/image-understanding
- https://dev.meta.ai/docs/structured-output
- https://dev.meta.ai/docs/models
- https://dev.meta.ai/docs/protocols/responses

Current source is local review work only. Published branch remains the earlier separately verified framework until a new push is expressly authorized. Authentication remains unfinished despite the optional local gate; real evidence release/privacy/billing/deployment remain gated.

## Correctness audit: request metadata boundary

An audit found the offline request builders base64-encoded original file bytes, which could carry metadata even though nothing was transmitted. Both now validate and re-encode pixel-only upright PNG before constructing data URLs. A regression test embeds synthetic private-location metadata, verifies it is absent from the request bytes and verifies the normalized pixel digest is unchanged. No metadata was sent anywhere because send remains disabled. This is a fixed latent privacy defect, not a real external leak. The future builder cannot mutate shared schema state through an earlier returned request. Muse uncertain-quality normalization also preserves the original proposal fields for human review alongside derived unknowns.

## Operational and integration audit follow-through

- Ledger schema migrations are now serialized inside an immediate transaction. A concurrent legacy-schema migration test caught the previously untested check-then-ALTER race risk; twelve simultaneous initializers now preserve exactly one copy of each new column.
- Optional journal record bound prevents unbounded new-job growth without deleting uncertainty or dedup tombstones. The explicit local entrypoint uses1024 test records; factory default remains explicit/unbounded unless configured. Full event-history/disk-byte limits remain open, so this is not a total storage guarantee.
- `operations.py` adds bounded in-process request-window admission and safe aggregate timing/status counters with no path/identity/header/error-text dimensions. Local entrypoint enables120requests/60seconds as a review safeguard, not user rate/spend policy, public protection or distributed enforcement. No metrics HTTP endpoint exposes data. Direct factory use bypasses it.
- Bounded multiprocess tests prove active-job and usage reservation caps across separate processes. Cancel-vs-claim and synthetic read/delete races are tested. An already-returned read may survive later deletion; no copy-recall claim. Five consecutive full local suites passed in the reviewed environment; this is a regression run, not realistic production load/soak/memory certification.
- Muse adapter now parses a bounded saved nonstreaming Responses envelope: exact expected model, completed assistant message, one output_text lane, rejection of refusal/multiple/incomplete outputs; reasoning isn't used or returned. It still emits only unvalidated proposals, not assessed observations or released evidence. Source: https://dev.meta.ai/docs/protocols/responses . No live response/account was used.

## Integration demo and source binding

`crops.py` prepares a metadata-free raster with its decoded pixel digest as frame identity, selects one parsed object by ID and cuts its exact half-open source box. Wrong-frame pixels (even at identical dimensions), tampered prepared identity, duplicate/missing objects and mask-shape mismatch are rejected. The test chains actual official saved-mask parse -> selected source crop -> disabled Muse request builder. The crop is explicitly not a verified person/isolated crop, and parsed output is still supplied by trusted local code: matching dimensions/digest labels do not cryptographically prove a provider analysed that raster. No blank source image is falsely presented as the source of the official doc mask; the mixed test is labelled plumbing only.

`demo_offline.py` now runs a self-contained synthetic HTTP fixture demo and a separate mock observation->rules->worker->journal path. It generates pixels and manifests, uses only temporary SQLite, asserts same-key duplicate behavior and no export, preserves unknown PPE and prints a labelled summary. No user files/accounts, API network, credentials, production writes or provider results are used. The demo was actually run and its output recorded in DEMO-RESULTS.txt. It is not a real-scene safety demo.

## Final boundary audit

Rate admission now runs before whole-body buffering in the local entrypoint; a rate-rejected request cannot consume the buffering path. Durable result payloads have an explicit local encoded-byte cap on both completion and late reconciliation, preserving previous state on oversize failure. This bounds payload storage after encoding, not total serialization-time memory or event history.

A late-worker race was found in review: after lease expiry plus explicit operator reconciliation, the callback's final heartbeat could raise LeaseLost and its interruption handler then try to alter an already-settled row. The worker now recovers only still-expired running work and returns the existing terminal row without overwriting the reviewed result. Separate tests exercise both late return and concurrent shutdown after manual reconciliation. No duplicate work or evidence release is created.

`scripts/socket_smoke.py` additionally exercises a real Uvicorn loopback HTTP subprocess rather than only TestClient: generated synthetic paired fixture, health200, first job201, same-key200 with identical persisted result, GET status, fixture label/exportfalse. SOCKET-SMOKE-RESULTS.txt records the actual run. The process is always terminated afterward; this is not graceful-shutdown certification or deployment. It uses a fixed local test port and can be rerun with another port through its Python smoke(port) function if occupied.

## Journal file privacy audit

A local file-permission audit found report/job and usage SQLite creation previously depended on the process umask. Both now pre-create regular files with mode0600, refuse file symlinks and refuse existing group/world-readable journals rather than silently chmod them. WAL/SHM permissions are checked while open in regression tests. This is a local safeguard, not encryption, authenticated principals or protection against a hostile filesystem/parent-directory replacement. A trusted private parent directory remains required. Existing broad-permission databases now fail startup with a clear error; back up and restrict them explicitly before reopening. No real existing user database was changed during this work; tests use temporary synthetic files.

## Typed offline report boundary

`reports.py` now validates pipeline output as a strict mock-only report with evidence unavailable/exportfalse/privacy not_validated constants. It recomputes deterministic rule results and explanations, checks zone memberships, unknown/review/severity coherence, IDs, frame bounds, recheck counts/actions and provenance order/source. Tampered favourable severity, missing uncertainty, wrong membership, invented trace or real/masked/export labels fail validation. This is a local report contract, not an accepted frontend or real-model schema.

Local journal completion also strips any supplied fixture/mock evidence-release claims, not only late reconciliation. Supplying a label is not permission to serve evidence. SQLite secure_delete is enabled for explicit local report payload cleanup; logical deletion still cannot certify erasure from backups, journals, SSDs or returned copies.


## Review branch publication preparation

The draft workflow has been moved to ci-drafts/backend-local-tests.yml.disabled, outside all .github/workflows paths. It remains inactive pending repository-path review. Backend code is under backend/; run commands from that directory. Publication is a review handoff only, not deployment, merge, live API authority or validation of real scenes.
