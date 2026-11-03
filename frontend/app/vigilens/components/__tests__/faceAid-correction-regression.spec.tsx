// @vitest-environment happy-dom
// Regression supplement for the face-aid correction: covers the low findings the
// two reviewer repros do not - reason-aware zero-proposal wording and the strict
// helmet_overlap_unchecked === true requirement (caveat may never disappear).
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { createElement } from "react";
import { PreviewCeremony } from "../PreviewCeremony";
import type { Audit } from "../../types";

const SOURCE = "a".repeat(64);

function audit(): Audit {
  return {
    audit_id: "fresh:abc:def", schema_version: "0.2-local-draft", source: "backend", created_at: null,
    image: { id: "0123456789abcdef", pixel_digest: SOURCE, width: 1280, height: 720 },
    source_digest: SOURCE, zones: [], evidence_image: null, evidence_status: "unavailable",
    evidence_export_allowed: false, persons: [], readings_origin: "synthetic",
    readings_status: "unvalidated_provider_observations", zones_applied: false,
  } as unknown as Audit;
}

function body(over: Record<string, unknown>) {
  return {
    source_pixel_digest: SOURCE, frame: [1280, 720], detector: "YuNet2023mar", threshold: 0.6,
    proposals: [], status: "needs_manual_review", coverage: "unverified",
    zero_detections_means_safe: false, privacy_review_status: "not_validated",
    reason: "no_faces_detected_still_requires_review", automatic_treatment_applied: false,
    provider_calls_this_request: 0, ...over,
  };
}

let container: HTMLDivElement;
let root: Root;

// The face-check aid auto-runs once when the ceremony mounts (proposal-driven
// masking is the default starting point), so setup only renders and flushes;
// no button click is needed. The mock returns a FRESH Response per call because
// a re-check must never hit an already-consumed body.
async function setup(b: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(b), { status: 200, headers: { "content-type": "application/json" } }))));
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(createElement(PreviewCeremony, { audit: audit(), file: new File([new Uint8Array([1])], "scene.png", { type: "image/png" }), onAcknowledged: () => {}, onInvalidate: () => {} }));
  });
  await act(async () => {}); // flush the auto-run check's promise continuations
}

afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.unstubAllGlobals(); });

describe("correction regression", () => {
  it("genuine no-face pass keeps the found-no-faces wording", async () => {
    await setup(body({}));
    expect(container.textContent).toContain("The face check found no faces. That does not mean the frame is safe - check it yourself.");
    expect(container.textContent).not.toContain("could not run");
  });
  it("detector unavailability is worded as could-not-run, never as no faces", async () => {
    await setup(body({ reason: "model_unavailable" }));
    expect(container.textContent).toContain("The face check could not run (the detector model file is unavailable).");
    expect(container.textContent).not.toContain("found no faces");
  });
  it("model digest mismatch is worded distinctly from a genuine no-face pass", async () => {
    await setup(body({ reason: "model_digest_mismatch" }));
    expect(container.textContent).toContain("does not match its pinned digest");
    expect(container.textContent).not.toContain("found no faces");
  });
  it("a proposal without helmet_overlap_unchecked === true is refused, caveat never dropped", async () => {
    await setup(body({
      reason: "proposals_require_face_and_helmet_review",
      proposals: [{ box: [10, 10, 40, 50], review_region: [7, 3, 43, 58], confidence: 0.91, pass_scale: 1, helmet_overlap_unchecked: false }],
    }));
    expect(container.textContent).not.toContain("flagged 1 possible face");
    expect(container.textContent).toContain("not a usable face-check result");
  });
  it("a rendered proposal always carries the helmet/overlap caveat", async () => {
    await setup(body({
      reason: "proposals_require_face_and_helmet_review",
      proposals: [{ box: [10, 10, 40, 50], review_region: [7, 3, 43, 58], confidence: 0.91, pass_scale: 1, helmet_overlap_unchecked: true }],
    }));
    expect(container.textContent).toContain("flagged 1 possible face");
    expect(container.textContent).toContain("helmets and overlaps not checked");
  });
});
