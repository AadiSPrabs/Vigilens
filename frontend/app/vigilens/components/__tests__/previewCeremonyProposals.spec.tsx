// @vitest-environment happy-dom
// PreviewCeremony face-proposals review aid: proposals render with their
// fail-closed labels, never tick boxes or prepare anything, and a refusal
// surfaces as a manual-review message. Fetch is mocked; no network.
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { createElement } from "react";
import { PreviewCeremony } from "../PreviewCeremony";
import type { Audit } from "../../types";

const SOURCE = "a".repeat(64);

function audit(): Audit {
  return {
    audit_id: "fresh:abc:def",
    schema_version: "0.2-local-draft",
    source: "backend",
    created_at: null,
    image: { id: "0123456789abcdef", pixel_digest: SOURCE, width: 1280, height: 720 },
    source_digest: SOURCE,
    zones: [],
    evidence_image: null,
    evidence_status: "unavailable",
    evidence_export_allowed: false,
    persons: [],
    readings_origin: "synthetic",
    readings_status: "unvalidated_provider_observations",
    zones_applied: false,
  } as unknown as Audit;
}

function proposalsBody() {
  return {
    source_pixel_digest: SOURCE,
    frame: [1280, 720],
    detector: "YuNet2023mar",
    threshold: 0.6,
    proposals: [
      { box: [10, 10, 40, 50], review_region: [7, 3, 43, 58], confidence: 0.91, pass_scale: 1, helmet_overlap_unchecked: true },
    ],
    status: "needs_manual_review",
    coverage: "unverified",
    zero_detections_means_safe: false,
    privacy_review_status: "not_validated",
    reason: "proposals_require_face_and_helmet_review",
    automatic_treatment_applied: false,
    provider_calls_this_request: 0,
  };
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
  await act(async () => {
    button!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

describe("PreviewCeremony face-proposals review aid", () => {
  it("renders proposals with fail-closed labels and prepares nothing", async () => {
    // Fresh Response per call: the aid auto-runs once on mount, and a manual
    // re-check must never read an already-consumed body.
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(proposalsBody()), { status: 200, headers: { "content-type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);
    await render();
    await act(async () => {}); // flush the auto-run check
    const text = container.textContent || "";
    expect(text).toContain("flagged 1 possible face");
    expect(text).toContain("confidence 0.91");
    expect(text).toContain("helmets and overlaps not checked");
    expect(text).toContain("masked by default above; inspect, adjust or remove each mask");
    // The aid auto-ran exactly once on mount; no prepare or acknowledgment call.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]![0])).toContain("/face-proposals");
    // The prepare button is still the next explicit action.
    expect([...container.querySelectorAll("button")].some((b) => b.textContent?.trim() === "Prepare a treated preview")).toBe(true);
    // Before preparation the only checkbox is the explicit, unchecked image-withhold election;
    // nothing is pre-checked and the acknowledgment stays manual.
    const boxes = [...container.querySelectorAll("input[type=checkbox]")] as HTMLInputElement[];
    expect(boxes).toHaveLength(1);
    expect(boxes[0]!.checked).toBe(false);
    expect(boxes[0]!.closest("label")?.textContent).toContain("Withhold the whole image");
  });

  it("shows the zero-detection wording without implying safety", async () => {
    const body = { ...proposalsBody(), proposals: [], reason: "no_faces_detected_still_requires_review" };
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } }))));
    await render();
    await act(async () => {}); // flush the auto-run check
    expect(container.textContent).toContain("does not mean the frame is safe - check it yourself");
  });

  it("surfaces a refusal as a manual-review message, with no automatic retry", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ detail: "Face proposals unavailable; manual whole-frame coverage review still required" }), { status: 409, headers: { "content-type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);
    await render();
    await act(async () => {}); // flush the auto-run check
    expect(container.textContent).toContain("manual whole-frame coverage review still required");
    // The mount auto-run was the only call: a refusal is never retried automatically.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    // A manual re-check stays available as an explicit operator action.
    expect([...container.querySelectorAll("button")].some((b) => b.textContent?.trim() === "Check for unmarked faces (review aid)")).toBe(true);
  });
});
