// @vitest-environment happy-dom
// Explicit, non-default image-withhold election: no face assertions, no regions.
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { createElement } from "react";
import { PreviewCeremony } from "../PreviewCeremony";
import type { Audit } from "../../types";

const SOURCE = "a".repeat(64);
const audit = {
  audit_id: "fresh:abc:def", schema_version: "0.2-local-draft", source: "backend", created_at: null,
  image: { id: "0123456789abcdef", pixel_digest: SOURCE, width: 1280, height: 720 },
  source_digest: SOURCE, zones: [], evidence_image: null, evidence_status: "unavailable", evidence_export_allowed: false,
  persons: [{ id: "person-7", polygon: [{ x: 0.1, y: 0.1 }, { x: 0.5, y: 0.1 }, { x: 0.5, y: 0.9 }, { x: 0.1, y: 0.9 }] }],
  readings_origin: "synthetic", readings_status: "unvalidated_provider_observations", zones_applied: false,
} as unknown as Audit;
const facesBody = {
  source_pixel_digest: SOURCE, frame: [1280, 720], detector: "YuNet2023mar", threshold: 0.6,
  proposals: [], status: "needs_manual_review", coverage: "unverified", zero_detections_means_safe: false,
  privacy_review_status: "not_validated", reason: "no_faces_detected_still_requires_review",
  automatic_treatment_applied: false, provider_calls_this_request: 0,
};
const session = { session_id: "sess-12345678", source_digest: SOURCE, output_sha256: "b".repeat(64), regions_digest: "c".repeat(64), width: 1280, height: 720 };
let container: HTMLDivElement;
let root: Root;
afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.unstubAllGlobals(); });

async function mount() {
  const fetchMock = vi.fn().mockImplementation((url: string) => Promise.resolve(new Response(JSON.stringify(String(url).includes("face-proposals") ? facesBody : session), { status: 200, headers: { "content-type": "application/json" } })));
  vi.stubGlobal("fetch", fetchMock);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(createElement(PreviewCeremony, { audit, file: new File([new Uint8Array([1])], "s.png", { type: "image/png" }), onAcknowledged: () => {}, onInvalidate: () => {} })); });
  await act(async () => {});
  return fetchMock;
}
async function clickButton(text: string) {
  const b = [...container.querySelectorAll("button")].find((x) => x.textContent?.trim() === text);
  expect(b, text).toBeTruthy();
  await act(async () => { b!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
}
const withholdBox = () => [...container.querySelectorAll("label")].find((l) => l.textContent?.includes("Withhold the whole image"))!.querySelector("input") as HTMLInputElement;

describe("image withhold election", () => {
  it("is unchecked by default and a plain prepare still refuses zero regions", async () => {
    const f = await mount();
    expect(withholdBox().checked).toBe(false);
    await clickButton("Prepare a treated preview");
    expect(f).toHaveBeenCalledTimes(1); // only the face check; nothing prepared
  });
  it("sends exactly the election with no regions, coverings or face assertions", async () => {
    const f = await mount();
    await act(async () => { withholdBox().dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    expect(withholdBox().checked).toBe(true);
    expect(container.textContent).toContain("does not show that the image has");
    await clickButton("Prepare a treated preview");
    expect(f).toHaveBeenCalledTimes(2);
    const body = JSON.parse(String((f.mock.calls[1]![1]?.body as FormData).get("review")));
    expect(body.regions).toEqual([]);
    expect(body.image_withheld).toEqual({ basis: "operator_elected_image_withheld", exact_source_confirmed: true, withhold_entire_frame: true });
    expect(body.face_coverings).toBeUndefined();
    expect(body.proposal_dispositions).toBeUndefined();
    expect(body.redaction_method).toBe("opaque");
  });
  it("does not carry the election to a re-prepare or to a different source", async () => {
    const f = await mount();
    await act(async () => { withholdBox().dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await clickButton("Prepare a treated preview");
    await clickButton("Discard and prepare again");
    expect(withholdBox().checked).toBe(false);
    // Elect again, then swap the bound source (new digest + file): must reset.
    await act(async () => { withholdBox().dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    expect(withholdBox().checked).toBe(true);
    const other = "d".repeat(64);
    const audit2 = { ...audit, source_digest: other, image: { ...audit.image, pixel_digest: other } } as unknown as Audit;
    await act(async () => { root.render(createElement(PreviewCeremony, { audit: audit2, file: new File([new Uint8Array([2])], "b.png", { type: "image/png" }), onAcknowledged: () => {}, onInvalidate: () => {} })); });
    await act(async () => {});
    expect(withholdBox().checked).toBe(false);
    expect(f).toHaveBeenCalled();
  });
});
