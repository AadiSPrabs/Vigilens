# Vigilens - PPE and site-safety review assistant (prototype)

> Meta Global AI Developer Hackathon, Indie track, "Build for Your World".
> Build window 26 October - 4 November 2026. Submission due 4 November 2026, 9:00 PM ET (5 November 2026, 7:30 AM IST).

This branch is a hackathon submission candidate. It is a prototype. It has not been verified as a release: see "Status" below before relying on anything here.

## What this is

Vigilens helps a human reviewer check a site image for PPE (hard hat, high-visibility vest) and restricted-zone entry. The operator uploads an image, draws zones for that camera, and the system produces a private review report with the model's observations and the operator's own confirmations. Every model observation is shown as unvalidated and needs a human decision. Vigilens does not clear anyone as safe and makes no compliance decision.

The idea behind it: try prompt-based PPE review through the Meta Model API instead of training a custom detector per site. Whether this works well enough on real footage is not established here.

## How it works

1. **Upload and zones.** The operator uploads an image and draws zones. Zones are operator-drawn; the system does not infer them. Saved zones are bound to the exact image and result.
2. **Segmentation (SAM 3.1).** One SAM 3.1 call segments people from the image through the Meta Model API. Results are parsed offline with the official `meta-sam-parser`.
3. **PPE observation (Muse Spark 1.3).** Each person crop is sent for a strict, schema-limited helmet/vest observation. The result is recorded as an unvalidated model observation.
4. **Human review.** The operator confirms or rejects what is shown. Ground-contact and zone membership checks use the operator's reviewed geometry. Re-checks of a person run only under an exact, separately granted plan, and camera-scene reuse needs operator confirmation each time.
5. **Operator-entered rules and optional explanation.** The operator enters their own rules (nothing is prefilled). An optional Muse Spark explanation of the exact reviewed plan can be reserved (a reservation makes no model call). Running one needs an exact server-side grant that this app does not create. Explanation text is unvalidated commentary, never a rule or a safety decision.
6. **Private report.** The report is a reviewer-prepared private preview. Offline face detection proposes regions for human review. The operator reviews and applies report-only masking; the live upload review is unmasked. A stored reopen deliberately displays a treated copy, not the unmasked live source. Masking can miss faces and is human-reviewed redaction, not verified anonymity. If a face cannot be checked, the operator can withhold the image from the report. Download and export are gated off by default.

Severity and rule evaluation are deterministic and operator-configured. They are not model judgement.

## Meta AI tooling

- **SAM 3.1** and **Muse Spark 1.3** through the Meta Model API (`https://api.meta.ai/v1/responses`): requests set `store: false`, send no tools, and the transport makes one attempt with no automatic retry. The default transport is disabled; no API key or live approval ships in this repository.
- **Muse Code**: development assistance during the build.

The tests and sample data in this repository use a synthetic transport and make no provider calls. Separate hosted checks used generated imagery and a supplied public-domain NIOSH photo with real Meta Model API calls (SAM 3.1 and Muse Spark 1.3). The current review video shows the NIOSH photo attempt, its browser timeout and stored-result recovery. These runs are not repository tests, and their results are unvalidated model observations.

## Status (read this)

- Local synthetic qualification on the current code: 977 non-Postgres backend tests passed in two disjoint file batches, 45 separate Postgres tests, and 222 frontend tests across 43 files. These are separate runs, not one aggregate suite. A focused current-code run on 4 November passed 79 camera, clip, recheck, loop and face-boot tests. No provider calls are made by these tests.
- The focused clip tests include bounded local FFmpeg/ffprobe decoding of a generated MP4, sampled-frame identity and limits. Camera reuse is bound to an explicitly confirmed fixed scene and does not transfer contact decisions or rules. Synthetic recheck/loop tests cover exact grants, immutable original results, owner isolation and no automatic retry after uncertainty.
- Earlier synthetic browser checks covered upload, masking/withholding, camera reuse and a bounded review loop. Current hosted checks on 3-4 November covered stored reopen, offline face-proposal requests, manual region masking, whole-frame review, contact review, operator-entered test rules and a private two-page PDF. Those hosted checks used a generated image, not real-site footage.
- On 4 November, one exact, previously reserved Muse Spark explanation completed on the hosted prototype. Both people retained deterministic position-unknown/manual-contact-review results. Its two commentary rows are unvalidated and did not change the deterministic findings. This does not qualify live recheck execution: no eligible unknown-PPE recheck candidate was available in that review.
- The hosted prototype is https://vigilens-frontend.onrender.com/ on `render-trial-candidate`. On 4 November, the operator confirmed both Render services Live at application code commit `7b914f2`. The same application code is on `hackathon-submission-candidate`; `main` remains older. This submission branch is the intended source for review, not a claim of a verified release. Deployment confirmation is separate from functional qualification; this README is not proof of current dispatch configuration.
- One supplied public-domain NIOSH photo also completed SAM and two person-PPE calls on 4 November. The browser stopped waiting at 60 seconds; an account-bound stored-result read recovered the completed result without another model call. These remain unvalidated observations, not accuracy measurements.
- Private PDF labels now distinguish report-display values from preserved unvalidated provider readings. Missing evidence-review/visibility support can withhold a report-display value without changing the provider reading. No provider readings are printed when the image is withheld. This labeling fix is included in deployed application code `7b914f2`; its updated hosted PDF output has not yet been verified.
- Application code `7b914f2` adds exact-upload, account-bound read-only status recovery and explicit pending UI with no automatic paid retry. It also extends the bounded image request wait to cover sequential calls. The operator confirmed deployment, but the new status-recovery route is not yet qualified on the host. Explanation reservation uncertainty is checked through the existing gated report without creating a second reservation.
- Local production build was not verified after a 2 GB out-of-memory failure. Render Live confirmation is separate deployment evidence, not a clean local production-build result.
- Raw-upload omission from report traffic has not been verified end to end. Face proposals and manual masking are not verified anonymity or all-face coverage. Download and evidence export remain gated off; a private preview is not released evidence.
- Application code `7b914f2` also fixes missing request-key binding on the clip upload route. Five regressions and a six-path local HTTP proxy test pass; the operator confirmed deployment, but this fix has not been verified on the host. Real-footage accuracy, current hosted short-clip execution and current hosted camera reuse have not been qualified. Nothing here is a safety, privacy or compliance guarantee.
- Latest post-deploy checks on 4 November were blocked: stored-result reopen returned HTTP 429, and exact-upload status recovery returned HTML rather than the expected JSON. Checks stopped without retrying analysis. The cause is unresolved; frontend/backend log review is awaited. This does not establish loss of the previously recovered photo result. Updated hosted status recovery and PDF verification remain incomplete.

## Repository layout

```
backend/    Python pipeline, review/report/rules services, tests
frontend/   React dashboard: zone drawing, review, private report, rule entry
RENDER-RUNBOOK.md, render.yaml   deployment notes (used for the hosted prototype on `render-trial-candidate`)
```

Older notes inside `backend/` (for example `RUNNING.md`, `STATUS.md`) predate later work and may be out of date. `backend/FRESH-REVIEW.md` describes the review pipeline.

## What was built during the hackathon

The concept was first written down on 26 October 2026. The frontend dashboard (upload, zone drawing, results UI) began on 27 October with teammate commits visible in this repository's history. The backend and the later review, report, rule and explanation work were developed from 27 October through 4 November with AI-agent assistance (Instinct and Muse) and are added here as a source package. Dates for the backend come from working records; the repository history alone does not show them because the backend was added in a single commit on 1 November.

## Hackathon

- Event: [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon) (Cerebral Valley x Meta)
- Track: Indie Developer
- Demo: the latest private review cut is v14, about 164.5 seconds, with redesigned presentation cards and the same narration. It shows the public-domain NIOSH photo attempt and stored recovery. The source app recording still clips some findings text. Final approval, an accessible submission video link and portal submission are not confirmed. The video is a separate artifact, not committed to this repository.

## Data and licences

- Repository test and bundled sample images are synthetic. No real-site footage or private hosted results are included in this repository. The separately delivered review video uses a public-domain NIOSH still: [Construction workers not wearing fall protection equipment](https://commons.wikimedia.org/wiki/File:Construction_workers_not_wearing_fall_protection_equipment.jpg).
- No licence has been chosen for this repository. Third-party components keep their own licences.
