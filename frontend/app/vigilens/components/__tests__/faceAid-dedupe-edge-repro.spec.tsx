// @vitest-environment happy-dom
// Detector-proposal disposition UX: every flagged candidate must be decided
// (masked or dismissed) before a preview can be prepared, decided ones travel
// as proposal_dispositions (the backend re-verifies against a fresh detector
// pass), and a "covered" decision contributes an editable mask region. This
// never claims detector coverage - misses stay possible, review stays manual.
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

let PROPS: any[] = [PROPOSAL];
const proposalsBody = {
  source_pixel_digest: SOURCE, frame: [1280, 720], detector: "YuNet2023mar", threshold: 0.6,
  proposals: PROPS, status: "needs_manual_review", coverage: "unverified",
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
    const body = url.endsWith("/face-proposals") ? { ...proposalsBody, proposals: PROPS } : sessionBody;
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } }));
  }));
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(createElement(PreviewCeremony, { audit: audit(), file: new File([new Uint8Array([1])], "scene.png", { type: "image/png" }), onAcknowledged: () => {}, onInvalidate: () => {} }));
  });
  const aid = [...container.querySelectorAll("button")].find((b) => b.textContent?.trim() === "Check for unmarked faces (review aid)");
  await act(async () => { aid!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
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


describe("independent edge cases", () => {
  it("two proposals with identical review_region (multiscale overlap) must not send duplicate dispositions", async () => {
    PROPS = [PROPOSAL, { ...PROPOSAL, pass_scale: 1.25 }];
    await setup();
    await act(async () => { click("Not a face"); });
    await act(async () => { click("Add a mask region"); }); // dismissing every proposal still needs a real region to prepare
    const again = [...container.querySelectorAll("button")].find((x) => x.textContent?.trim() === "Not a face");
    if (again) await act(async () => { again.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await act(async () => { click("Prepare a treated preview"); });
    const regs = sentReview().proposal_dispositions.map((d: any) => JSON.stringify(d.review_region));
    expect(new Set(regs).size).toBe(regs.length); // backend 409s on duplicate review_region
  });
  it("zero proposals with a manual region: no proposal_dispositions sent, prepare proceeds", async () => {
    PROPS = [];
    await setup();
    await act(async () => { click("Add a mask region"); });
    await act(async () => { click("Prepare a treated preview"); });
    expect(sentReview().proposal_dispositions).toBeUndefined();
  });
});
