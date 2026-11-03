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
6. **Private report.** The report is a reviewer-prepared private preview. Faces the detector finds are masked in the report only; the live review view is unmasked. Masking can miss faces and is human-reviewed redaction, not verified anonymity. If a face cannot be checked, the operator can withhold the image from the report. Download and export are gated off by default.

Severity and rule evaluation are deterministic and operator-configured. They are not model judgement.

## Meta AI tooling

- **SAM 3.1** and **Muse Spark 1.3** through the Meta Model API (`https://api.meta.ai/v1/responses`): requests set `store: false`, send no tools, and the transport makes one attempt with no automatic retry. The default transport is disabled; no API key or live approval ships in this repository.
- **Muse Code**: development assistance during the build.

Tests and demos in this repository use a synthetic transport and make no provider calls.

## Status (read this)

- Verified locally on synthetic data: frontend 157/157 vitest (happy-dom) and a clean `tsc --noEmit`; the backend suites for the report, explanation, redaction and rule paths pass (383 tests in the last run). A full backend run of 946/946 was recorded on an older baseline, not repeated on this exact tree.
- Browser flows (login, upload, face proposals, masked and withheld PDFs, zone save, camera-template reuse, bounded review loop) were checked in a real browser on **synthetic** data against an **earlier** build. The newest rule-entry and explanation screens have **not** been checked in a browser.
- A clean **production build is not verified** (the build ran out of memory on a 2 GB machine).
- Raw-upload omission from report traffic has not been verified end to end.
- Accuracy on real footage has not been measured. Nothing here is a safety, privacy or compliance guarantee.
- No deployment is triggered by this branch.

## Repository layout

```
backend/    Python pipeline, review/report/rules services, tests
frontend/   React dashboard: zone drawing, review, private report, rule entry
RENDER-RUNBOOK.md, render.yaml   deployment notes (not run for this branch)
```

Older notes inside `backend/` (for example `RUNNING.md`, `STATUS.md`) predate later work and may be out of date. `backend/FRESH-REVIEW.md` describes the review pipeline.

## What was built during the hackathon

The concept was first written down on 26 October 2026. The frontend dashboard (upload, zone drawing, results UI) began on 27 October with teammate commits visible in this repository's history. The backend and the later review, report, rule and explanation work were developed from 27 October through 3 November with AI-agent assistance (Instinct and Muse) and are added here as a source package. Dates for the backend come from working records; the repository history alone does not show them because the backend was added in a single commit on 1 November.

## Hackathon

- Event: [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon) (Cerebral Valley x Meta)
- Track: Indie Developer
- Demo: a narrated screenshot walkthrough using synthetic data, submitted through the Cerebral Valley portal.

## Data and licences

- Test and demo images are synthetic. No real-site footage is included in this repository.
- No licence has been chosen for this repository. Third-party components keep their own licences.
