// @vitest-environment happy-dom
// Detector-proposal disposition UX: every flagged candidate is MASKED BY
// DEFAULT (automatic default face-area treatment) and stays reviewable - the
// operator can adjust the box or mark it not a face before preparing. Decisions
// travel as proposal_dispositions (the backend re-verifies against a fresh
// detector pass); a covered decision contributes an editable mask region.
// Defaults never claim detector coverage - misses stay possible, review stays
// manual.
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { createElement } from "react";
import { PreviewCeremony } from "../PreviewCeremony";
import type { Audit } from "../../types";

const SOURCE = "a".repeat(64);
const PROPOSAL = { box: [12, 12, 38, 48], review_region: [10, 10, 40, 50], confidence: 0.91, pass_scale: 1, helmet_overlap_unchecked: true };

function audit(): Audit {
  return {
    audit_id: "fresh:abc:def", schema_version: "0.2-local-draft", source: "backend", created_at: null,
    image: { id: "0123456789abcdef", pixel_digest: SOURCE, width: 1280, height: 720 },
    source_digest: SOURCE, zones: [], evidence_image: null, evidence_status: "unavailable",
    evidence_export_allowed: false, persons: [], readings_origin: "synthetic",
    readings_status: "unvalidated_provider_observations", zones_applied: false,
  } as unknown as Audit;
}

const proposalsBody = {
  source_pixel_digest: SOURCE, frame: [1280, 720], detector: "YuNet2023mar", threshold: 0.6,
  proposals: [PROPOSAL], status: "needs_manual_review", coverage: "unverified",
  zero_detections_means_safe: false, privacy_review_status: "not_validated",
  reason: "proposals_require_face_and_helmet_review", automatic_treatment_applied: false,
  provider_calls_this_request: 0,
};

const sessionBody = {
  session_id: "sess-1", source_digest: SOURCE, output_sha256: "c".repeat(64), regions_digest: "d".repeat(64),
  width: 1280, height: 720, preview_url: "/x.png",
};

let container: HTMLDivElement;
let root: Root;
let fetches: { url: string; form: FormData | undefined }[];

async function setup() {
  fetches = [];
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string, init?: { body?: FormData }) => {
    fetches.push({ url, form: init?.body instanceof FormData ? init.body : undefined });
    const body = url.endsWith("/face-proposals") ? proposalsBody : sessionBody;
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } }));
  }));
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(createElement(PreviewCeremony, { audit: audit(), file: new File([new Uint8Array([1])], "scene.png", { type: "image/png" }), onAcknowledged: () => {}, onInvalidate: () => {} }));
  });
  await act(async () => {}); // flush the mount auto-run check
}

function click(label: string) {
  const b = [...container.querySelectorAll("button")].find((x) => x.textContent?.trim() === label);
  expect(b, `button ${label}`).toBeTruthy();
  b!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

function prepareCalls() {
  return fetches.filter((f) => f.url.endsWith("/private-display"));
}

function sentReview() {
  const calls = prepareCalls();
  expect(calls).toHaveLength(1);
  const form = calls[0]?.form;
  if (!form) throw new Error("prepare call carried no form body");
  return JSON.parse(form.get("review") as string);
}

afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.unstubAllGlobals(); });

describe("detector-proposal dispositions", () => {
  it("masks every flagged face by default and prepares with no extra clicks", async () => {
    await setup();
    expect(container.textContent).toContain("masked by default");
    await act(async () => { click("Prepare a treated preview"); });
    const review = sentReview();
    expect(review.proposal_dispositions).toEqual([
      { review_region: [10, 10, 40, 50], disposition: "covered", person_id: "flagged-face-1" },
    ]);
    expect(review.regions).toEqual([{ person_id: "flagged-face-1", box: [10, 10, 40, 50] }]);
  });

  it("dismiss then re-mask toggles the default decision", async () => {
    await setup();
    await act(async () => { click("Not a face"); });
    expect(container.textContent).toContain("marked not a face by you");
    await act(async () => { click("Mask it after all"); });
    expect(container.textContent).toContain("masked by default");
    await act(async () => { click("Prepare a treated preview"); });
    const review = sentReview();
    expect(review.proposal_dispositions).toEqual([
      { review_region: [10, 10, 40, 50], disposition: "covered", person_id: "flagged-face-1" },
    ]);
    expect(review.regions).toEqual([{ person_id: "flagged-face-1", box: [10, 10, 40, 50] }]);
  });

  it("the default covered decision travels as a covered disposition and mask region", async () => {
    await setup();
    await act(async () => { click("Prepare a treated preview"); });
    const review = sentReview();
    expect(review.proposal_dispositions).toEqual([
      { review_region: [10, 10, 40, 50], disposition: "covered", person_id: "flagged-face-1" },
    ]);
    expect(review.regions).toEqual([{ person_id: "flagged-face-1", box: [10, 10, 40, 50] }]);
  });

  it("not-a-face decision alone cannot prepare (bare no-face claim refused); with a real region the bounded dismissal travels", async () => {
    await setup();
    await act(async () => { click("Not a face"); });
    await act(async () => { click("Prepare a treated preview"); });
    // Dismissing every proposal leaves zero regions: refused, no prepare call.
    expect(container.textContent).toContain("refuses a zero-region preview");
    expect(prepareCalls()).toHaveLength(0);
    // A real operator region makes the dismissal sendable.
    await act(async () => { click("Add a mask region"); });
    await act(async () => { click("Prepare a treated preview"); });
    const review = sentReview();
    expect(review.proposal_dispositions).toEqual([
      { review_region: [10, 10, 40, 50], disposition: "dismissed", dismiss_reason: "operator_confirmed_not_a_face" },
    ]);
    expect(review.regions).toHaveLength(1);
    expect(review.regions[0].person_id).toBe("manual-region-1");
  });

  it("an edited default mask box travels in the region", async () => {
    await setup();
    const corner = container.querySelector('input[aria-label="flagged face 1 box corner 1"]') as HTMLInputElement;
    expect(corner).toBeTruthy();
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
      setter.call(corner, "4");
      corner.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => { click("Prepare a treated preview"); });
    expect(sentReview().regions).toEqual([{ person_id: "flagged-face-1", box: [4, 10, 40, 50] }]);
  });

  it("rejects an out-of-order mask box client-side with a specific error", async () => {
    await setup();
    const corner = container.querySelector('input[aria-label="flagged face 1 box corner 1"]') as HTMLInputElement;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
      setter.call(corner, "60");
      corner.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => { click("Prepare a treated preview"); });
    expect(container.textContent).toContain("Flagged face 1: the mask box is invalid");
    expect(prepareCalls()).toHaveLength(0);
  });

  it("rejects a mask box that no longer contains the flagged area", async () => {
    await setup();
    const corner = container.querySelector('input[aria-label="flagged face 1 box corner 1"]') as HTMLInputElement;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
      setter.call(corner, "30");
      corner.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => { click("Prepare a treated preview"); });
    expect(container.textContent).toContain("Flagged face 1: the mask box must fully contain the flagged area.");
    expect(prepareCalls()).toHaveLength(0);
  });
});
