// @vitest-environment happy-dom
// Repro for qualification finding 1 (stuck-busy race). NOT part of the reviewed diff.
// Drop into app/vigilens/components/__tests__/ on the wired tree and run:
//   npx vitest --run app/vigilens/components/__tests__/faceAid-stuck-busy-race-repro.spec.tsx
// Expected on the reviewed wiring: FAILS - the aid's button is stuck on
// "Checking for faces…" (disabled) after prepare supersedes an in-flight face check.
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { createElement } from "react";
import { PreviewCeremony } from "../PreviewCeremony";
import type { Audit } from "../../types";

const SOURCE = "a".repeat(64);
const H = (c: string) => c.repeat(64);

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

async function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(createElement(PreviewCeremony, { audit: audit(), file: new File([new Uint8Array([1])], "scene.png", { type: "image/png" }), onAcknowledged: () => {}, onInvalidate: () => {} }));
  });
}

async function clickButton(text: string) {
  const button = [...container.querySelectorAll("button")].find((b) => b.textContent?.trim() === text);
  expect(button, `button "${text}"`).toBeTruthy();
  await act(async () => { button!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
}

afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.unstubAllGlobals(); });

describe("race repro", () => {
  it("prepare during an in-flight face check leaves the aid stuck busy", async () => {
    let resolveFaces: (r: Response) => void = () => {};
    const facesBody = {
      source_pixel_digest: SOURCE, frame: [1280, 720], detector: "YuNet2023mar", threshold: 0.6,
      proposals: [], status: "needs_manual_review", coverage: "unverified",
      zero_detections_means_safe: false, privacy_review_status: "not_validated",
      reason: "no_faces_detected_still_requires_review", automatic_treatment_applied: false, provider_calls_this_request: 0,
    };
    const session = { session_id: "sess-12345678", source_digest: SOURCE, output_sha256: H("b"), regions_digest: H("c"), width: 1280, height: 720 };
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (String(url).includes("face-proposals")) {
        return new Promise<Response>((res) => { resolveFaces = res; });
      }
      return Promise.resolve(new Response(JSON.stringify(session), { status: 200, headers: { "content-type": "application/json" } }));
    });
    vi.stubGlobal("fetch", fetchMock);
    await render();
    // The aid auto-runs on mount, so the face check is ALREADY in flight here
    // (its fetch is pending on resolveFaces); no click is needed to start it.
    await clickButton("Add a mask region"); // zero proposals: a real operator region is required (no fake box)
    await clickButton("Prepare a treated preview"); // enabled while the face check is in flight
    await act(async () => { resolveFaces(new Response(JSON.stringify(facesBody), { status: 200, headers: { "content-type": "application/json" } })); });
    expect(container.textContent).toContain("Confirm what you checked"); // prepared branch rendered
    await clickButton("Discard and prepare again");
    const checkBtn = [...container.querySelectorAll("button")].find((b) => b.textContent?.includes("face"));
    // Reviewed wiring: "Checking for faces…", disabled=true (stuck until a source change).
    expect(checkBtn?.textContent?.trim()).toBe("Check for unmarked faces (review aid)");
    expect(checkBtn?.disabled).toBe(false);
  });
});
