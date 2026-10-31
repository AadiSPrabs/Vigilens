# memory.md: Vigilens frontend handoff (for another model)

Written Tue 27 Oct 2026. Paste this whole file at the start of a new chat so the next model can continue without re-asking anything.

---

## 0. How to behave with this user

- User is **Raakin**, B.Tech CSE (Cyber Security) student at Dayananda Sagar University, Bangalore. He owns the **frontend only**.
- Style he wants: **casual, happy, detailed, with examples and analogies**, structured replies with **tables and code blocks** over dense prose. Emojis are welcome.
- He builds with **OpenCode** (an AI coding agent). The usual workflow: the assistant writes a prompt, Raakin pastes it into OpenCode in **Build mode**, the agent builds one phase, stops at a gate, Raakin tests and sends screenshots or terminal output, the assistant reviews and writes the next prompt.
- Raakin is on **Windows / PowerShell**. Give PowerShell commands, not bash.
- He does NOT build the backend. Never suggest he does. A teammate does it.
- Be honest: do not claim code works unless output proves it. Do not promise the hackathon will be won. Push back on risky choices.
- Raakin said "$10,000 on the line" (the prize), so quality and correctness matter more than speed.

## 1. The project

**Vigilens**: zero-shot PPE and site-safety auditing. An operator uploads a site photo, draws restricted/hazard zones once, and gets an audit report: who was in which zone and which required PPE (hard hat, high-visibility vest) was missing, with visual evidence.

- Event: **Meta Global AI Developer Hackathon**, Indie track, theme "Build for Your World". Build window 26 Oct to 4 Nov 2026.
- Judging: Impact 30%, Use of Meta AI Tooling 25%, Demo 25%, Technical Depth and Execution 20%.
- Submission: 3-minute demo video + public repo via the Cerebral Valley portal. **Official deadline Wed 4 Nov 2026, 9:00 PM ET = Thu 5 Nov 2026, 7:30 AM IST.** Internal target: Wed 4 Nov, 10:00 PM IST (the plan's own internal target; submit early).
- Repo: https://github.com/AadiSPrabs/Vigilens (public). Raakin is a collaborator (already done). Local path: `C:\Users\admin\Documents\Vigilens`. Frontend lives in `frontend/`.
- Pipeline (backend, not Raakin's job): SAM 3.1 zero-shot segmentation (`person`, `hard hat`, `high-visibility jacket`), Muse spatial reasoning and plain-language explanations, a **deterministic** severity matrix, low-confidence re-check then escalation to a human, evidence = original image + deterministic polygon overlays (never generatively edited), faces masked by default.
- MVP scope: still-image audits only. No live CCTV, no goggles/boots in the first slice, video clips later/out of scope.
- Team: **Raakin = frontend**, **Aadi = backend** (SAM/Muse/severity). The README says the second team member and the representative are still to be confirmed; the representative is **not Aadi** (his correction) and must be settled before 4 Nov. Only accepted hackathon participants may be listed as team members.
- Aadi's side is partly worked by an AI teammate called "Muse" plus a reviewer called "Instinct" in Slack; their messages arrive as pasted text. Treat their notes as the backend's position, not as Raakin's agreement.

**Weekday labels:** the original plan labelled dates with the wrong weekday (off by one). Today is Tue 27 Oct 2026, so 28 Oct = Wed, 31 Oct = Sat, 1 Nov = Sun, 2 Nov = Mon, 3 Nov = Tue, 4 Nov = Wed. Go by **dates**.

## 2. Raakin's frontend plan (settled decisions)

| Decision | Settled as |
|---|---|
| Stack | React + Vite, **JavaScript (not TypeScript)**, plain CSS. Vitest + @testing-library/react as devDependencies only. No UI frameworks, no state libraries. |
| Overlay rendering | SVG polygons over the image, normalised 0 to 1 coordinates, `viewBox="0 0 1 1"`, `preserveAspectRatio="none"` |
| Data in dev | Local **fixtures** (not live API). UI can be built and demoed without the backend. |
| API calls | The UI calls only a backend adapter (`src/api/auditClient.js`) or fixtures. **No Meta keys, no Meta URLs, ever, in the frontend.** |
| PDF export | Browser print-to-PDF with a print stylesheet. **Lowest priority, last, only when the user says so.** |
| Persistence | Browser state + localStorage for zones of user-uploaded images. No database, auth, accounts. |
| Branching | Work on `feat/frontend-dashboard`. No direct commits to `main`. PRs only. `main` stays demo-ready. |
| Fallback | If React proves unfamiliar, vanilla HTML/CSS/JS with the same contract (was due by morning of 28 Oct; React is working, so ignore). |

### Timeline (by date)

| Date | Plan |
|---|---|
| Wed 28 Oct | Skeleton + fixtures + overlays + findings list |
| Thu 29 Oct | Zone editor done; Aadi's answers to open questions due |
| Fri 30 Oct | Findings, hazard log, review decisions |
| Sat 31 Oct | Contract freeze; swap fixtures for the real endpoint **if a safe slice is ready** (can be earlier) |
| Sun 1 Nov | PDF/print + polish, demo images checked |
| Mon 2 Nov | **Scope freeze** (no new features) |
| Tue 3 Nov | Record demo-video shots |
| Wed 4 Nov | Final check and submit before the internal target |

## 3. Repo and git state

- Branch: `feat/frontend-dashboard`. Local `main` was reset to match `origin/main` after Phase 1 was accidentally committed on `main`.
- Pushing the branch: `git push -u origin feat/frontend-dashboard` (suggested several times; confirm it was done with `git status` / `git log`).
- `CONTRACT.md` was meant to be moved into `frontend/CONTRACT.md` and committed; **confirm that happened**. It is still at **v0.1** (outdated, see section 6).
- `frontend/.gitignore` excludes `node_modules` and `dist`. `.env.local` must never be committed.
- npm showed "6 vulnerabilities" after install. Advice given: do **not** run `npm audit fix --force`; check `npm audit --omit=dev`. Not yet confirmed what it printed.

## 4. Frontend structure (as built; verify against the real repo)

```
frontend/
  index.html  package.json  vite.config.js  .gitignore  README.md
  src/
    main.jsx  App.jsx  styles.css
    api/auditClient.js
    components/ UploadZoneEditor AuditImage FindingsList SeverityBadge StatusChip Banner (HazardLog and ReportView NOT built yet)
    lib/ geometry.js canAnalyse.js severity.js storage.js evidence.js
    fixtures/ index.js, sample1-3.json, sample images (synthetic), contract/ (planned)
    tests/
```

App state: `image, zones, audit, selectedId, decisions, filters, sample, runWithoutZones`.
`sample = { id, imageSrc, presetZones } | null`.

## 5. HARD RULES the frontend must keep

1. **Frontend only.** No backend code, no mock servers, no model calls, no severity logic. Do not copy backend code into the repo.
2. **Never scaffold over an existing `frontend/`.** Inspect and extend.
3. Coordinates normalised 0 to 1, origin top-left, relative to the **uploaded (upright) image**.
4. **Overlay alignment**: wrapper `position:relative; display:inline-block; line-height:0`; `<img>` `display:block; max-width:100%; height:auto`; SVG `position:absolute; inset:0; width:100%; height:100%`. No padding, border, margin, object-fit, letterboxing or cropping. Click maths uses the **image's** `getBoundingClientRect()`: `x = (e.clientX - rect.left) / rect.width`, `y = (e.clientY - rect.top) / rect.height`; ignore clicks outside 0 to 1. (A Slack paste once turned `rect.top` into a link; the intended text is plain.)
5. PPE values only `present` / `absent` / `unknown`. **Never turn `unknown` into `absent`.** Show "Unclear - needs human check".
6. **Severity** values are only **Critical (red), Medium (amber), Low (blue-grey, NOT green)**. Any other string = neutral grey plus the raw text. Colour AND text always. The frontend never computes severity.
7. **Outlines are neutral**; tint only by the backend's `worst_severity` when present. **Never use `findings[0]`** (findings are not sorted).
8. **Uncertainty findings** (`kind:"uncertainty"`, `severity:null`, `review_state:"needs_human_review"`) render as a distinct "Uncertain - needs human check" badge: never a violation, never compliant.
9. **Wording:** never say "compliant". Use **"No listed violations"** (tooltip: "Not a safety clearance"). Green only when findings are empty AND helmet and vest are both `present`.
10. **Honesty banners:** when `source === "fixture"` (or `fixture_notice` exists) show a persistent SAMPLE DATA banner (use `fixture_notice` verbatim if present). Backend failures show an explicit error with a manual "Try again" (no auto-retry). Never show a fake success after a failure.
11. **Fixture matching:** a fixture result is shown only for its matching bundled sample. User-uploaded photos in fixture mode get: "Fixture mode only has results for the bundled sample images. Pick a sample, or switch to backend mode."
12. **Stale state:** changing the image, sample or zones clears audit, review decisions, selection and filters. Late responses are discarded using an image+zones snapshot. Abort the previous request.
13. **Evidence integrity:** never generatively edit images. Never export a local preview as evidence. Evidence comes only from `audit.evidence_image.url` (masked by the backend), must load, and its `naturalWidth/Height` must **exactly equal** `audit.image.width/height`. Export enabled only if `evidence_export_allowed === true` AND evidence ok AND `source !== "fixture"`. Never fall back to the original as evidence. Local preview is labelled "Preview only, not evidence".
14. **Accessibility:** each finding is a real `<button>`; overlay polygons focusable (`tabIndex=0`, `role="button"`, `aria-label`), activate on Enter AND Space (preventDefault on Space), visible focus ring; text labels with colours; aria-live for analysis complete/errors.
15. No `console.log`, no `dangerouslySetInnerHTML`, no TODO placeholders, no lorem ipsum, no features beyond spec, no new dependencies without justification.
16. Sample data must be labelled; the report footer must say "Prototype audit for human review - not a compliance certification."
17. Time labels: browser-clock time is "Loaded at HH:MM", never "audit run". If `created_at` is shown it is "Sample timestamp (fixture metadata)" for fixtures; hide it when null.

## 6. Contract status (frontend <-> backend)

`CONTRACT.md` v0.1 was written by the assistant and sent to Aadi; he answered Section 8 in a draft ("section8-answers-draft"). The accepted direction is below. **CONTRACT.md in the repo has not yet been updated to match; offering to do so is a pending item.**

### Request
`POST {VITE_API_BASE_URL}/audit` (dev base `http://127.0.0.1:8000` or `http://localhost:8000`), `multipart/form-data`:

| Part / header | Detail |
|---|---|
| `image` | file; jpeg/png/webp; **File/Blob must carry the correct explicit `type`**; do not re-encode needlessly |
| `zones` | JSON string; each zone has **exactly** `id`, `name`, `hazard` (bool), `points`; points have **exactly** `x`, `y` |
| `Idempotency-Key` | header, ASCII 1 to 128 chars; `crypto.randomUUID()` once per image+zones snapshot; **reuse for "Try again" on the same snapshot**; new key on any change |
| Content-Type | never set manually (browser adds the boundary) |

Zone rules (backend validates; frontend mirrors): max 20 zones, 3 to 100 points per polygon, coords finite numbers 0 to 1, **no booleans, no repeated vertices (including a closing repeat), no zero-area, no self-intersecting or touching edges**, name 1 to 200 chars, id <= 128 chars and unique, zones JSON <= 100,000 characters. Frontend ignores a click within 0.002 of the previous point (double-click guard).

Image limits: 15,000,000 bytes, max 4096 per side, max 16,000,000 decoded pixels, still image only.

**EXIF:** the backend **rejects non-upright EXIF (orientation != 1) with 422** `IMAGE_ORIENTATION_UNSUPPORTED`. So the frontend bakes rotation in before drawing zones (orientation 2 to 8: `createImageBitmap(file,{imageOrientation:"from-image"})` + canvas, lossless PNG, JPEG 0.92 fallback only if over 15,000,000 bytes) and uses that **same File for preview and upload**. Orientation 1 / no EXIF: upload the original bytes.

### Response (schema_version `"0.2"` or `"0.2-local-draft"`; anything else = "Unsupported schema version" error)
Top level: `audit_id`, `schema_version`, `ruleset_version`, `source` (`"fixture"|"backend"`), `created_at` (UTC string or **null**), `image {id,width,height}` (must equal the uploaded file's decoded dimensions, else error), `zones` (echo), `persons`, `evidence_image` (`{url}` or **null**), `evidence_status` (`masked|no_faces|masking_failed|unavailable`), and local-draft extras: `evidence_export_allowed`, `fixture_loaded_at`, `fixture_notice`.

Person: `id`, `polygon`, `helmet`, `vest`, `zone_id` (display zone; may be null), `zone_ids` (all containing zones), `zone_membership_status` (`known|unknown`), `worst_severity` (`Critical|Medium|Low|null`), `findings`, optional `assessment_status`, `trace_provenance`.

Finding: `id` (stable, authored; **required and unique in backend mode**; fixture mode may fall back to `${person.id}:${rule_id}:${index}`), `rule_id`, `kind` (`violation|uncertainty`), `severity` (string or null for uncertainty), `zone_id` (the finding's own zone), `message` (plain text, shown verbatim, never HTML), `review_state` (`auto|needs_human_review`), `recheck_trace` (array of strings). Traces with `trace_provenance:"illustrative_fixture_only"` are labelled "Illustrative (fixture), not a real re-check".

Cross-checks in `validateAudit`: coordinates finite and 0 to 1, polygons >= 3 points, valid enums, duplicate ids rejected, every `zone_id`/`zone_ids` entry is null or an id in `zones`.

### Zone label table
| Backend says | Frontend shows |
|---|---|
| `zone_membership_status: "unknown"` | "Zone unknown: ground contact uncertain, needs review" |
| known, `zone_ids: []`, zones drawn | "Outside all drawn zones" |
| known, `zone_ids: []`, no zones drawn | "No zones were checked" |
| known, `zone_ids: [...]` | the zone names |
| field missing | "No zone shown" |
Each finding shows the name of **its own** `zone_id`.

### Empty states
`persons: []` -> "No people detected; not a safety clearance." `zones: []` -> "No zones were checked; this is not proof the area is safe."

### Proposed severity matrix (backend draft, "draft-unapproved", **not yet signed off**)
| Rule | When | Severity |
|---|---|---|
| NO_HELMET_IN_HAZARD / NO_VEST_IN_HAZARD | PPE absent, person in a hazard zone (`hazard:true`) | Critical |
| NO_HELMET_IN_RESTRICTED / NO_VEST_IN_RESTRICTED | PPE absent, person in a restricted-only zone (`hazard:false`) | Medium |
| INTRUSION_RESTRICTED | person in a restricted-only zone (entry-forbidden) | Medium |
| NO_HELMET_OUTSIDE / NO_VEST_OUTSIDE | PPE absent, person outside all drawn zones | Low |
Zone membership uses the person's **foot point** (bottom-centre of the mask bbox); boundary counts as inside; all containing zones are evaluated; display zone = hazard first, then smallest area, then id. Hazard zones give PPE findings only; restricted-only zones add intrusion. Unknown PPE is an uncertainty finding, not a violation.

### Error envelope and codes
`{ "error": { "code", "message" } }`; show `message` as plain text, never branch on HTTP status alone. Known codes: INVALID_REQUEST (400), INVALID_IDEMPOTENCY_KEY (400), INVALID_ZONES / INVALID_ZONE / INVALID_ZONE_ID / INVALID_POLYGON / INVALID_COORDINATE (400), ZONES_TOO_LARGE (413), IMAGE_TOO_LARGE (413), UNSUPPORTED_MEDIA_TYPE (415), ANIMATED_IMAGE_UNSUPPORTED (415), IMAGE_UNREADABLE (422), IMAGE_DIMENSIONS_TOO_LARGE (422), IMAGE_ORIENTATION_UNSUPPORTED (422), FIXTURE_MISMATCH (422), IDEMPOTENCY_CONFLICT (409), FIXTURE_NOT_CONFIGURED (503), LOCAL_CACHE_FULL (503), EVIDENCE_UNAVAILABLE (404). Check `response.ok`; handle non-JSON bodies; honour `Retry-After` on 429. 60 s UI timeout is **provisional**, not measured. A timeout shows "No response yet; the audit may still be running" with a manual "Try again" (an error does not prove paid work stopped).

### Other agreed points
- `GET /health` -> `{status, mode:"fixture_only", real_analysis_enabled:false, fixture_configured:bool}`. Frontend calls it in backend mode and shows banners (fixture-only; no paired fixture; backend not reachable).
- CORS: backend allows only `http://localhost:5173` and `http://127.0.0.1:5173` in dev.
- Face masking is **not implemented** and unvalidated; evidence/export stays unavailable. A zero-faces result is not proof of privacy.
- Backend's idempotency cache is local and in-memory only (not a paid-call guard).
- Video clips: separate future endpoint, out of scope.
- Additive optional fields are fine anytime; meaning/type/required changes need agreement before the 31 Oct freeze; after it, message first.

## 7. Backend status (Aadi's side, for context only; Raakin does not build it)

- First stub (`app.py` v1) was flawed: attached canned findings to any upload, hard-coded `source:"backend"` and `evidence_status:"masked"`, served a grey 1280x720 placeholder as "evidence", no EXIF handling. **Do not use it.** Its `sample-audit-v0.2.json` is only a contract-test fixture (and its person-4 has an inconsistent `zone_id:null`, treated as a sample defect; `created_at` is in the future).
- Replacement: a **fixture-only local backend** (`app.py`, `core.py`, `rules.py`, `requirements.txt`, tests; Aadi reports 38 pytest tests passing; not run by the assistant or Raakin). Python 3.10+, pins: fastapi==0.162.0, httpx==0.28.1, pillow==12.3.0, pytest==9.1.1, python-multipart==0.0.32, uvicorn==0.54.0 (use `requirements.txt`; `requirements-lock.txt` looks incomplete).
- Behaviour: always `source:"fixture"`, evidence null/unavailable, export disallowed. Without `VIGILENS_FIXTURE_MANIFEST` pointing to a trusted local manifest, `POST /audit` returns **503 FIXTURE_NOT_CONFIGURED**. A manifest pairs **one exact image (decoded RGB pixel digest) with the exact ordered zones**; any pixel or zone change = 422 FIXTURE_MISMATCH. `rules.py` is a draft matrix not wired into the API.
- Not done: SAM/Muse adapters, face masking, real evidence, latency measurement, retry deduplication, deployment, auth/spend guard. No paid model call has been made; a paid test is not approved.
- Aadi confirmed: expect `schema_version="0.2-local-draft"` from the current build (not a promise it stays unchanged; compat changes will be flagged), manifest will contain stable authored finding ids (he is tightening validation), and he needs Raakin's **synthetic contract image + exact ordered zones**.
- Optional for Raakin: run the backend locally **outside the repo** (`C:\Users\admin\Documents\vigilens-backend-local`, venv, `pip install -r requirements.txt`, `pytest -q`, `uvicorn app:app --host 127.0.0.1 --port 8000`), then set `frontend/.env.local` with `VITE_AUDIT_MODE=backend` and `VITE_API_BASE_URL=http://127.0.0.1:8000` (delete it after testing; never commit it).

## 8. Phase log (OpenCode build phases)

| Phase | What | Status |
|---|---|---|
| 0 | Inspect + plan, approved with 6 amendments | Done |
| 1 | Upload + zone drawing + samples with preset zones + `canAnalyse` + geometry tests | Done, committed (7 tests). It was first committed on `main`, then moved to the feature branch. |
| 2 | Matched sample results, `validateAudit`, fixture-mode `auditClient`, AuditImage, FindingsList, Banner, stale clearing | Done (reported 19 tests). Built on the old contract. |
| 2b | Contract v0.2: evidence resolver, severity colours, uncertainty badge, per-finding zone, empty states, stale-response guard, HTTP handling, FormData, pre-checks, updated fixtures | Reported complete. Raakin's verification of screenshots/test count not yet seen. |
| 2c | Integration safety (contract fixture, source labelling, geometry validation, single request in flight, "No zone shown", etc.) | Raakin ran it (order was 2c before 2b). Not separately verified. Partly superseded by 2d. |
| "Loaded at" patch | Rename time labels | Prompt given; not confirmed run. 2d report says "Loaded at" uses `fixture_loaded_at` or browser clock, so likely covered. |
| Evidence aspect patch | 1% aspect check | **Superseded** by 2d's exact `naturalWidth/Height` check. |
| 2d | Adapt to the local fixture backend (Idempotency-Key, strict zones, double-click guard, EXIF bake, preview vs evidence split, `/health`, labels, error codes) | **Complete, committed, 34 tests passing, build passes** (per OpenCode's report). Verification checklist given; Raakin has not yet reported results of the manual tests. |
| 2e | Contract pairing assets (synthetic image + exact zones) | **NEXT. Prompt below.** |
| 3 | Review decisions, hazard log, filters, summary counts, keyboard zone drawing, accessibility pass | Not started. |
| 4 | Backend handoff hardening, `CONTRACT.md` v0.2 file | Not started. |
| 5 | Tests, README, final audit | Not started. |
| 6 | PDF/print report | Optional, last, only on Raakin's say-so. |

## 9. NEXT STEP: Phase 2e prompt (paste into OpenCode, Build mode)

Raakin must first paste the zones JSON into item 2 where marked.

```text
Phase 2e: contract pairing assets for the backend teammate. Build, test, commit on feat/frontend-dashboard, report, STOP. Do not copy any backend code.
1. Create src/fixtures/contract/contract-sample.png: 1280x720, upright (no EXIF orientation), clearly labelled "SYNTHETIC - contract test" in a corner. Draw a simple figure inside each person polygon of src/fixtures/contract/sample-audit-v0_2.json (person-1 x 0.30-0.45 y 0.30-0.70, no helmet, vest on; person-2 x 0.70-0.82 y 0.30-0.70, helmet and vest on; person-3 x 0.15-0.25 y 0.35-0.65, helmet on, vest partly hidden; person-4 x 0.50-0.58 y 0.10-0.40, helmet and vest on). NO polygons, zone outlines or annotations baked into the image. Generate it with a deterministic script (committed under scripts/) so it can be regenerated byte-identically.
2. Create src/fixtures/contract/contract-zones.json containing EXACTLY the two zones below, in that order, with exactly the keys id, name, hazard, points and point keys x, y, and these exact numbers.
[{"id":"zone-1","name":"Crane Zone","hazard":true,"points":[{"x":0.1,"y":0.2},{"x":0.6,"y":0.2},{"x":0.6,"y":0.8},{"x":0.1,"y":0.8}]},{"id":"zone-2","name":"Storage Yard","hazard":false,"points":[{"x":0.65,"y":0.2},{"x":0.95,"y":0.2},{"x":0.95,"y":0.8},{"x":0.65,"y":0.8}]}]
3. Add a selectable entry "Contract test (backend pairing)" to the sample picker ONLY when VITE_AUDIT_MODE=backend. It loads contract-sample.png and presets contract-zones.json (editable, with the existing Reset behaviour). In fixture mode it does not appear. The image is uploaded as its ORIGINAL bytes with type image/png, never re-encoded.
4. In backend mode, validateAudit requires a non-empty unique id on every finding; fixture mode keeps the fallback key. Reject any schema_version other than "0.2" and "0.2-local-draft" with the message "Unsupported schema version".
5. Tests: contract-zones.json passes the zone validator and matches the order and numbers above; the picker entry is hidden in fixture mode; missing or duplicate finding ids are rejected in backend mode; an unknown schema_version is rejected.
6. README note in src/fixtures/contract/: what these files are for, that the image is synthetic, and that it is not model evidence.
```

Then Raakin sends Aadi: `contract-sample.png` (the **original file**, not a screenshot), `contract-zones.json`, and the generator script, noting the image is synthetic, not model evidence, and that Aadi should review image/zone/annotation consistency before putting it in a manifest.

`src/fixtures/contract/sample-audit-v0_2.json` is the backend's sample audit (contract-test fixture only, NOT a selectable demo sample). Its four persons: person-1 Critical NO_HELMET_IN_HAZARD in zone-1; person-2 Medium INTRUSION_RESTRICTED in zone-2; person-3 vest unknown -> uncertainty finding in zone-1; person-4 no findings, `zone_id:null` (sample defect).

## 10. AFTER 2e: Phase 3 spec (write the OpenCode prompt from this)

1. **Review decisions:** per finding, a 3-option radio group in a `<fieldset>` with a visually hidden `<legend>`: Unreviewed / Reviewed / Needs human review. Default = Needs human review if backend `review_state === "needs_human_review"`, else Unreviewed. Shared `decisions` state feeds the summary and hazard log. Keys: finding `id`, else `${person.id}:${rule_id}:${index}`. Reviewing never changes `unknown` to `present` or alters backend severity. Decisions are UI-only and are not sent to the backend.
2. **Summary line:** e.g. "3 findings - 1 Critical - 1 Needs Human Review" (uncertainty findings counted separately, not as violations).
3. **Hazard Log** (`HazardLog.jsx`): table with loaded-at time, person, zone, finding, severity, review state; filters by severity, zone, review state; sortable by severity (Critical first, unknown strings and uncertainty last); row click selects finding + polygon (shared `selectedId`).
4. **Filters** on the findings list: by severity and zone.
5. **Keyboard alternative for zone drawing:** e.g. "Add point at centre" plus arrow-key nudging, with the same validation as mouse clicks.
6. **Accessibility pass:** keyboard-only walkthrough, focus management, aria-live, contrast.
7. Gate: all review/filter/log behaviour in sync from image, list and log; tests for decisions, filters, sorting, keyboard zone drawing; build and tests pass; commit; STOP for screenshot.
Do not build PDF/print in Phase 3.

## 11. What Raakin still owes / open items

- Report results of the **Phase 2d manual verification** (test drive in fixture mode; portrait phone photo EXIF test; optional backend-mode test) and the `npm test` summary / terminal checks.
- Send the assistant **screenshots of sample-2 and sample-3 results** (never received so far).
- Run Phase 2e, then send Aadi the three files.
- Confirm `CONTRACT.md` is in `frontend/` and committed; ask the assistant to **update it to v0.2-local-draft** (offered several times, not yet done).
- Confirm the branch is pushed and `main` untouched.
- The Slack-shared note from Aadi's side asked for "fixture labelling, persistent SAMPLE DATA banner, evidence export disabled" which the frontend already implements.
- Team representative / second participant still unresolved (README); settle before 4 Nov.
- Demo needs **licensed real photos** before recording (the bundled samples are synthetic); the README notes this. Check dataset licences/consent.
- Backend swap: only try backend mode with the matching contract image + exact zones (stub/fixture banners on). Real SAM/Muse integration depends on Aadi; if not ready by 2 Nov the demo runs from fixtures with SAMPLE DATA labelled. The "Use of Meta AI Tooling" criterion is 25%, so keep checking in with Aadi.
- Latency: unmeasured; 60 s timeout is provisional until Aadi measures a real call.

## 12. Reference: message to Aadi about the contract (already sent in spirit)

Raakin accepted: evidence masked URL + `evidence_status` with no original fallback; uncertainty schema; Critical/Medium/Low (Low not green); per-finding `zone_id` with `person.zone_id` as the display zone; caps (15 MB, 4096x4096, 16 MP, 20 zones, 100 points); 60 s provisional timeout; ignore stale responses; retry only after an explicit error with deduplication. Raakin does not need to wait for Aadi to proceed because everything is built against fixtures, and each backend answer only changes one file (`lib/evidence.js`, the endpoint constant in `auditClient.js`, `lib/severity.js`, or `validateAudit`).

## 13. Quick verification commands (PowerShell, from `frontend/`)

```powershell
git branch --show-current       # feat/frontend-dashboard
git status
git log --oneline -6
npm test
npm run build
npm audit --omit=dev
Select-String -Path src\*.js,src\**\*.js,src\**\*.jsx -Pattern "console.log|dangerouslySetInnerHTML|api.meta|API_KEY|VITE_AUDIT_STUB|ompliant"
git push
```
(The last `Select-String` should print nothing; a test that asserts the word "compliant" is gone may legitimately match.)

## 14. Honesty notes for the next model

- Nothing here was run by the assistant. All test counts and "complete" statements come from OpenCode's own reports or Aadi's messages, not from independent verification.
- The backend is a fixture-only local draft; no real analysis, masking or evidence exists yet. Do not let the demo imply otherwise.
- Contract details marked "draft" (severity matrix, ruleset version, caps) are not signed off by both people.
