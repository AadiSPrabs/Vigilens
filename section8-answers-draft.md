# Vigilens — Section 8 answers (DRAFT for Aadi to send Raakin)

**Status:** DRAFT, not sent. Based on Raakin's CONTRACT v0.1 + Instinct's 14:23 IST research review.
Muse and Instinct agree on the revised positions below, with qualifications noted.
Nothing below is a backend implementation claim — the backend is not built yet — and
nothing is agreed by Raakin until he confirms it. Deadline Raakin asked for: Thu 29 Oct.
Contract freeze: Sat 31 Oct. Scope freeze: Mon 2 Nov. Demo recording: Tue 3 Nov.
Submit: Wed 4 Nov, internal target 10 PM IST, official Thu 5 Nov 7:30 AM IST.

## Acknowledgement (for the reply to Raakin)

Phase 1 looks good: React + Vite in `frontend/` on `feat/frontend-dashboard`,
upload + zone draw/undo/clear/save, 3 sample images with pre-filled zones,
fixture mode standalone, tests + build pass. Next phase by Thu 29 Oct
(overlays, findings list, matched sample results, review buttons + hazard log)
is the right order — overlays and matched results before PDF/polish.

## Section 8 answers

### 1. Real endpoint path and base URL — PROVISIONAL, adopt for dev

- `POST {VITE_API_BASE_URL}/audit`
- Dev base URL: `http://localhost:8000` (local backend, not a deployed URL)
- Request: `multipart/form-data`, two parts exactly as v0.1 §3:
  `image` (file, jpeg/png/webp) + `zones` (text, JSON string, same shape as v0.1)
- Frontend must use FormData and let the browser set `Content-Type` including its boundary.
- Deployed path/base URL for the demo: NOT confirmed yet — backend is local-only for now.
  Do not hardcode a deployed URL until Aadi confirms one.

### 2. evidence_image format — Option B, with fixes from Instinct

- **Choose Option B:** `evidence_image: { "url": "..." }`
- The URL points to a **clean, privacy-masked image** from the backend:
  same coordinate frame, orientation, full-image crop, and preferably exact
  pixel dimensions as the original. Same aspect ratio alone is not enough.
  EXIF rotation: one agreed oriented raster is used for upload preview,
  zone drawing, backend coordinates, and returned evidence.
- **Masking is already applied by the backend before the URL is returned.**
  Frontend draws SVG overlays on top of that masked image only.
  The masked image must NOT have polygons baked in — no double overlays.
- **Remove Option A.** `null` cannot also carry a URL unless a second field is defined.
- **New field (proposed, additive):** `evidence_status`:
  `"masked"` | `"no_faces"` (verified: no faces found, privacy processing complete) |
  `"masking_failed"`. An empty face-detection result alone is not proof of completion
  unless the backend explicitly returns `"no_faces"`.
- **When masked evidence is missing, blocked, expired, or fails to load:**
  show an explicit unavailable/error state and **disable evidence export**.
  Never fall back to the unmasked original as evidence.
  The v0.1 interim default ("original with a note") is withdrawn.
- Local upload preview, if retained, is clearly separate from report evidence
  and must never be exported as evidence.
- For local dev, the backend will serve the masked image from its own origin
  (e.g. under `/evidence/<audit_id>` — exact path to confirm when the backend
  serves its first real audit). For the demo, URLs must be private, short-lived,
  and authorized — not a public image bucket — with retention/deletion rules
  to confirm before demo recording.

### 3. worst_severity per person — YES

- **Yes, the backend will provide it, optional in the response.**
- Type: `string | null` (not just string).
- Value: maximum over that person's **severity-bearing** findings only,
  order Critical > Medium > Low. `null` when there are no severity-bearing
  findings (including uncertainty-only persons).
- `null` is NOT a compliance claim.
- Frontend fallback stays as in v0.1: if absent, do not guess — keep the
  person's outline neutral and label each finding separately.
  This fixes the old `findings[0]` bug; findings are not assumed sorted.

### 4. Full severity list + deterministic matrix — PROPOSED

Only three violation levels: **Critical, Medium, Low**. No "High" or others.
Any other string renders grey with the raw text, never silently remapped.
Low violations must NOT use success-green styling — reserve success styling
for an explicit completed assessment.

Proposed matrix (gradient by zone risk — for Raakin and Aadi to accept):

| Rule | When | Severity |
|---|---|---|
| NO_HELMET_IN_HAZARD | Helmet absent, person in a hazard zone | Critical |
| NO_VEST_IN_HAZARD | Vest absent, person in a hazard zone | Critical |
| NO_HELMET_IN_RESTRICTED | Helmet absent, person in a restricted-only zone | Medium |
| NO_VEST_IN_RESTRICTED | Vest absent, person in a restricted-only zone | Medium |
| INTRUSION_RESTRICTED | Person in a restricted-only zone (entry-forbidden), regardless of PPE | Medium |
| NO_HELMET_OUTSIDE | Helmet absent, person outside all zones | Low |
| NO_VEST_OUTSIDE | Vest absent, person outside all zones | Low |

Notes:
- Hazard zones (`hazard: true`) are PPE-required zones, not entry-forbidden zones.
  A person in a hazard zone gets PPE findings only, not an intrusion finding.
- Restricted-only zones (`hazard: false`) are entry-forbidden zones.
  A person there gets an intrusion finding, plus PPE findings if applicable.
- Unknown PPE is NOT a violation rule — see Q5/uncertainty below.
- This matrix is proposed, not implemented. Backend code will implement exactly
  this table once Aadi confirms it, and the table will be versioned (see below).

### 5. zone_id when zones overlap — evaluate all, display one

- **Zone membership (new, was undefined in v0.1):**
  A person is in a zone if the person's foot point — bottom-centre of the
  person bounding box derived from the returned mask — is inside the zone
  polygon. Polygon boundaries count as inside.
- **Evaluate ALL containing zones, not just one.** A hazard-first /
  smallest-area tie-break may choose a display zone, but must not suppress
  findings from another overlapping applicable zone.
- **Per-finding association (new, additive):** each finding carries its own
  `zone_id` (the zone that finding applies to).
- **Top-level `person.zone_id` = display zone**, chosen deterministically:
  hazard zones first, then smallest area, then zone ID as the final tie-break.
- **Ambiguous contact** (feet occluded, person truncated, mask includes an
  outstretched limb): mark as needing review, do not guess a zone.
- **Invalid polygons** (self-intersecting, zero-area, <3 points, coordinates
  outside 0–1, nonfinite): backend returns 400, frontend shows the message, no retry.
- If the MVP intentionally evaluates only one zone, that loss must be
  documented explicitly — it is not hidden in the tie-break.

### 6. Typical time per image / 60 s timeout — UNMEASURED, keep 60 s provisionally

- **No benchmark exists yet. No paid Meta call has been verified successful.**
  60 s is a provisional UX timeout only, not measured SAM + Wonder latency.
- Keep 60 s for now. Backend will measure the first real SAM + Wonder call
  and report the actual time before the 31 Oct freeze; revisit the timeout
  then if a real call exceeds it.
- Define before implementation: whether upload time is included, and align
  backend/upstream deadlines with the frontend timeout.
- **Stale/late responses:** frontend must abort or supersede old requests and
  discard a late response after the image or zones have changed. Clearing
  state alone does not stop a slow older response repopulating the UI —
  associate every response with its image+zones request snapshot and ignore
  responses that do not match the current snapshot.
- A frontend timeout does NOT mean backend work stopped, so blind Retry can
  duplicate inference and cost. Preferred mechanism (to agree before
  implementing): an idempotent request token / result lookup, or an explicit
  pending/unknown state. Until that mechanism exists, Retry only after an
  explicit error, not on a silent timeout.
- Honor `Retry-After` for 429 rate limiting.

### 7. CORS — YES for dev, exact origins only

- **Yes:** allow `http://localhost:5173` in development.
- Allow `http://127.0.0.1:5173` separately — localhost and 127.0.0.1 are
  distinct origins.
- Allow the deployed frontend origin separately when a demo URL exists;
  do not use `*` for the demo backend.
- Methods/headers: POST + OPTIONS preflight as required, multipart/form-data.
- CORS is NOT authentication or a spending guard. How a public demo prevents
  arbitrary paid backend use is still open — to confirm before demo recording.

### 8. Max image size and dimensions — PROPOSED caps

- File size: **15 MB = 15,000,000 bytes**, matching the frontend limit.
  Multipart overhead is separate; the file part itself must be ≤ 15 MB.
- Dimensions (proposed, to confirm before freeze):
  max 4096 × 4096 pixels, max 16 megapixels decoded, per image.
  "Any dimensions" is withdrawn.
- Other caps (proposed): max 20 zones per request, max 100 points per polygon.
- Backend validates BEFORE any paid inference, and rejects with 400/413/415:
  unsupported file type (415 for unsupported media, with a stable error code),
  image that cannot be decoded, decoded dimensions/pixel count over cap,
  duplicate person/zone/finding IDs, malformed polygons, nonfinite coordinates,
  oversized content. Browser MIME/extension checks are not sufficient —
  backend must validate the actual decoded image.
- Backend may downscale internally for the model, but must return the
  original dimensions in `image.width` / `image.height` so normalised
  polygons still line up.

### 9. Short video clips later — separate endpoint, out of scope

- Agree: out of scope for now. Still-image first, as in the MVP.
- A separate future endpoint for clips/frames is a design preference,
  not a commitment. No clip work before the still-image flow is demo-ready.

## Revised contract changes (v0.1 → proposed v0.2)

Additive fields (backend will add, frontend may ignore or adopt):
- `schema_version`: e.g. `"0.2"` — version the schema before freeze.
- `ruleset_version`: e.g. `"1"` — the severity matrix version above.
- `source`: `"fixture" | "backend"`.
- `created_at`: UTC timestamp of the audit.
- Finding `id`: stable within an audit, stable across re-render/review,
  never randomly regenerated per render.
- Finding `kind`: `"violation" | "uncertainty"` (see below).
- Finding `zone_id`: the zone that finding applies to.
- `evidence_status`: `"masked" | "no_faces" | "masking_failed"`.

Uncertainty schema — CHOSEN OPTION (Instinct flagged two options; this draft picks one):
- An unknown helmet or vest produces a **stable uncertainty finding** for that item:
  `kind: "uncertainty"`, `severity: null`, `review_state: "needs_human_review"`,
  with a plain-text message saying the item could not be confirmed.
- Severity and certainty are separate. Unknown is never a violation, never
  Critical, and never compliant.
- A person with only uncertainty findings has `worst_severity: null` and must
  NOT be labelled compliant. Empty `findings` still means compliant — but only
  when all PPE items are present, not when any item is unknown.
- A manual "Reviewed" click in the UI acknowledges review; it does NOT rewrite
  unknown to present and does NOT change backend severity.
- If Raakin prefers the alternative (a separate assessment/review status
  outside severity, keeping severity always a string), say so before 29 Oct
  and we will switch — do not implement both.

Other fixes:
- `persons: []` must render as **"No people detected; not a safety clearance."**
  Distinct from "detected people have no listed violations" and from a failed
  detector. Failed segmentation is an error, never a successful empty array.
  Non-empty detections do not prove every person was found.
- Empty `zones: []` means zone-based checks were not run, not proof the area is safe.
- Recheck traces: each item from actions actually taken only. Remove the
  illustrative 0.54 / 0.88 numbers from backend examples unless unmistakably
  marked fixture-only. Never convert a model's narrative confidence into a
  measured score. Omit numeric confidence where the component supplies none;
  identify the component when a real score is used. Define a fixed maximum
  recheck count and budget before implementation (unresolved, not permission to spend).
  Human review remains mandatory when uncertainty survives.
- Text rendering only, never HTML injection, for operator labels, model
  messages, and traces. Backend owns deterministic rule/severity assignment;
  a generated explanation must not contradict it.
- Validate enums, IDs, required arrays, finite coordinates, and cross-field
  invariants on both sides. Schema incompatibility is an explicit error, not
  a silent remap.
- Handle non-JSON proxy errors and check `response.ok` — fetch does not reject
  solely for HTTP 4xx/5xx.
- Section 9 clarification: "additive anytime" means optional backward-compatible
  additions only. Meaning/type/required-field changes are breaking, need
  agreement from both, and must land before 31 Oct. After freeze, any change
  needs a quick message first — that is the rule, not an absolute lock.

Fixture acceptance cases (for Raakin's fixture mode, before swap):
unknown PPE, zero people, overlapping zones, no zones, missing/failed masked
evidence, EXIF rotation, late/stale response, timeout/retry, invalid schema.
Each sample stays paired with its matching image and zones, with the
"SAMPLE DATA" banner never removed in fixture mode.

## Two quick things (Raakin's asks)

1. **Collaborator invite — BLOCKED on one missing detail:**
   Aadi cannot invite Raakin yet because Raakin's GitHub username/handle is
   not known to Muse (only his name Raakin/Shaik and Slack member ID are known).
   Ask Raakin for his GitHub handle, then Aadi adds him in GitHub:
   repo Settings → Collaborators → Add people. Muse will not push code for
   Raakin; Raakin pushes his own branch and opens PRs.
2. **Main demo-ready rule — AGREED:**
   Main always stays demo-ready. No direct commits to main, PRs only, for both.
   After 31 Oct, tell the other person before changing any JSON field.
   This matches v0.1 §9 as clarified above.

## What Aadi must confirm before this draft is sent

- [ ] Severity matrix gradient above (hazard Critical / restricted Medium / outside Low)
- [ ] Uncertainty schema choice: severity null + kind uncertainty (vs separate status)
- [ ] Dimension caps: 4096×4096, 16 MP, 20 zones, 100 points/polygon
- [ ] Local evidence serving path (e.g. `/evidence/<audit_id>`) — to confirm on first real audit
- [ ] Raakin's GitHub handle (ask him in the same reply)
- [ ] That the 31 Oct swap date is realistic given the backend is not built yet —
      Raakin's plan swaps on 31 Oct, but earlier guidance was to connect one real
      slice when both sides are ready, not deliberately wait for 31 Oct.
      If a real slice is ready earlier, swap earlier.

## Backend work starting now (Aadi, after answers are sent)

1. Backend skeleton: `POST /audit`, multipart parsing, zones validation,
   CORS for localhost:5173 / 127.0.0.1:5173, error codes as in v0.1 §6 + 415.
2. Severity matrix + zone logic in code: foot-point, all-zones evaluation,
   display-zone tie-break, uncertainty findings, worst_severity aggregate.
3. Evidence masking step: masked image serving + evidence_status.
   Implementation choice for face masking is still open — research before coding it.
4. Fixture-first backend: return a labelled sample audit in the v0.2 shape
   so Raakin can swap the endpoint without paid calls, then one real
   SAM + Wonder call (paid test still needs Aadi's explicit approval — $1 tranche
   is NOT approved yet) and measure actual latency vs the 60 s timeout.
5. Branch: backend work on its own feature branch, PRs only, main demo-ready.
