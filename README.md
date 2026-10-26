# Vigilens — Zero-Shot PPE & Site-Safety Auditing

> **Meta Global AI Developer Hackathon — Indie track — "Build for Your World"**
> Build window: 26 October – 4 November 2026 · Project submission due: 4 November 2026, 9:00 PM ET (5 November 2026, 7:30 AM IST)

## What this is

Vigilens is an automated site-safety and PPE auditing agent for construction and
manufacturing sites. A safety officer uploads a site image or short video clip
and draws the restricted zones for that camera once. The system then produces
an exportable audit report showing who was in which zone and which required
PPE was missing — with visual evidence.

The problem it solves: the standard route to PPE detection is a custom-trained
detector (e.g. a YOLO-style model), which needs a labelled training dataset
for every new site, PPE type, and camera angle. That cost is why small and
mid-size sites still rely on a supervisor walking around with a register.
Vigilens removes the per-site training step.

## How it works — an agent loop, not a one-shot classifier

1. **Upload + zones.** The operator uploads an image or short clip and draws
   restricted / hazard zones for that camera once. Zones are operator-drawn —
   the system does not infer them.
2. **Zero-shot segmentation (SAM 3.1).** SAM 3.1 segments, from plain-text
   prompts such as `person`, `hard hat`, and `high-visibility jacket`, with no
   custom-trained model. Adding a new PPE type is a new prompt, not a new
   dataset.
3. **Spatial reasoning (Muse).** Muse receives the segmented regions and
   reasons spatially: is this person inside a restricted zone, and which
   required PPE is missing for that zone?
4. **Deterministic severity.** Severity comes from a deterministic matrix
   (e.g. no helmet inside a hazard zone = Critical; no hi-vis outside a
   hazard zone = Medium). Muse explains the classification in plain language
   on the report — the classification is rule-anchored, not free-form
   LLM judgement.
5. **Re-check, then escalate.** Low-confidence or ambiguous regions are
   cropped, re-segmented, and re-checked. Anything still uncertain is
   escalated to a human reviewer rather than guessed.
6. **Evidence you can trust.** The audit report's evidence is the *original*
   image with deterministic polygon overlays drawn from SAM's coordinates.
   Evidence is never generatively edited. Worker faces are masked in reports
   by default.

## MVP scope (10-day build discipline)

- Audits of **uploads / short clips** — not live CCTV integration.
- Core checks: **person + hard hat + high-visibility vest + restricted-zone
  intrusion** (large, reliable objects).
- **Stretch goals only:** goggles and safety boots (small, often occluded —
  SAM's weakest case).
- Muse Image is used **only** to generate synthetic test scenes (site scenes
  with staged violations) for validating the pipeline when real footage is
  scarce. It is never used to generate audit evidence.

## Meta AI tooling used

- **SAM 3.1** via the Meta Model API — zero-shot segmentation, polygon /
  mask coordinates.
- **Muse** (Spark / Wonder) via the Meta Model API — spatial reasoning over
  segmented regions and plain-language severity explanations.
- **Muse Image** — synthetic test scenes only (see above).
- **Muse Code** — development assistance during the build.
- Open-weight models (Muse Spark Open / Glimmer) are used as a reasoning
  fallback for low-confidence re-checks, via partner inference where
  available.

## Repository status

**Hackathon project in progress.** This repository was created for the
Meta Global AI Developer Hackathon, and all project code in it was developed
during the hackathon build window (26 October – 4 November 2026). The
implementation, demo video, and run instructions are being added during
build week — see the sections below as they land.

### Planned layout

```
Vigilens/
├── README.md            # this file
├── backend/             # SAM 3.1 segmentation + Muse reasoning pipeline
├── frontend/            # React dashboard: overlays, hazard log, zone drawing, PDF export
└── docs/                # demo notes, test-set notes, severity matrix
```

### Quick start

_To be added as the implementation lands: prerequisites, environment
variables (Meta Model API key), install steps, and how to run the audit
pipeline and dashboard._

## Team

- **Representative:** _to be confirmed_
- **Aadi Prabhu** ([@AadiSPrabs](https://github.com/AadiSPrabs))
- **Teammate** — _to be added: name and GitHub handle of the second accepted
  participant before submission. Only accepted hackathon participants are
  listed as team members._

## Hackathon

- Event: [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon) (Cerebral Valley × Meta)
- Track: Indie Developer (teams of up to 4)
- Theme: Build for Your World / Real-World Physical Systems
- Judging (project): Impact 30% · Use of Meta AI Tooling 25% · Demo 25% ·
  Technical Depth & Execution 20%
- Demo: a 3-minute demo video, submitted with this repository via the
  Cerebral Valley portal by 4 November 2026, 9:00 PM ET.

## Data & licences

- Test images are used for validation and demo ground truth only, not for
  training a custom detector. Dataset licences will be checked before any
  frame is used in the demo video.
- This project does not claim ownership of third-party site footage or
  datasets. Anything shared in the submission is original work developed
  during the hackathon, or used under its licence.
