// @vitest-environment happy-dom
// Repro for qualification finding 2 (returned digest never verified). NOT part of the reviewed diff.
// Drop into app/vigilens/components/__tests__/ on the wired tree and run:
//   npx vitest --run app/vigilens/components/__tests__/faceAid-digest-binding-repro.spec.tsx
// Expected on the reviewed wiring: FAILS - a result whose source_pixel_digest does
// NOT match the requested source is rendered as if bound to the current upload.
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { createElement } from "react";
import { PreviewCeremony } from "../PreviewCeremony";
import type { Audit } from "../../types";

const SOURCE = "a".repeat(64);
const OTHER = "b".repeat(64);

function audit(): Audit {
  return {
    audit_id: "fresh:abc:def", schema_version: "0.2-local-draft", source: "backend", created_at: null,
    image: { id: "0123456789abcdef", pixel_digest: SOURCE, width: 1280, height: 720 },
    source_digest: SOURCE, zones: [], evidence_image: null, evidence_status: "unavailable",
    evidence_export_allowed: false, persons: [], readings_origin: "synthetic",
    readings_status: "unvalidated_provider_observations", zones_applied: false,
  } as unknown as Audit;
}

let container: HTMLDivElement;
let root: Root;

afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.unstubAllGlobals(); });

describe("binding repro", () => {
  it("renders proposals whose digest does not match the requested source", async () => {
    const body = {
      source_pixel_digest: OTHER, frame: [1280, 720], detector: "YuNet2023mar", threshold: 0.6,
      proposals: [{ box: [10, 10, 40, 50], review_region: [7, 3, 43, 58], confidence: 0.91, pass_scale: 1, helmet_overlap_unchecked: true }],
      status: "needs_manual_review", coverage: "unverified", zero_detections_means_safe: false,
      privacy_review_status: "not_validated", reason: "proposals_require_face_and_helmet_review",
      automatic_treatment_applied: false, provider_calls_this_request: 0,
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } })));
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(createElement(PreviewCeremony, { audit: audit(), file: new File([new Uint8Array([1])], "scene.png", { type: "image/png" }), onAcknowledged: () => {}, onInvalidate: () => {} }));
    });
    const button = [...container.querySelectorAll("button")].find((b) => b.textContent?.trim() === "Check for unmarked faces (review aid)");
    await act(async () => { button!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    // Reviewed wiring: logs true - the mismatched result is rendered.
    expect(container.textContent).not.toContain("flagged 1 possible face");
  });
});
