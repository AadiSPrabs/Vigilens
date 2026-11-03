// @vitest-environment happy-dom
// Reopen-by-digest of the caller's OWN stored job: panel, client, ceremony without a browser file, reducer.
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { PreviewCeremony } from "../PreviewCeremony";
import { ReopenPanel } from "../ReopenPanel";
import { reducer, initialState } from "../../useVigilens";
import type { Audit } from "../../types";

const SOURCE = "a".repeat(64);
const audit = {
  audit_id: "fresh:abc:def", schema_version: "0.2-local-draft", source: "backend", created_at: null,
  image: { id: "0123456789abcdef", pixel_digest: SOURCE, width: 1280, height: 720 },
  source_digest: SOURCE, zones: [], evidence_image: null, evidence_status: "unavailable", evidence_export_allowed: false,
  persons: [{ id: "person-7", polygon: [{ x: 0.1, y: 0.1 }, { x: 0.5, y: 0.1 }, { x: 0.5, y: 0.9 }, { x: 0.1, y: 0.9 }], findings: [] }],
  readings_origin: "synthetic", readings_status: "unvalidated_provider_observations", zones_applied: false,
} as unknown as Audit;
const faces = { source_pixel_digest: SOURCE, frame: [1280, 720], detector: "YuNet2023mar", threshold: 0.6, proposals: [], status: "needs_manual_review", coverage: "unverified", zero_detections_means_safe: false, privacy_review_status: "not_validated", reason: "no_faces_detected_still_requires_review", automatic_treatment_applied: false, provider_calls_this_request: 0 };
const session = { session_id: "sess-12345678", source_digest: SOURCE, output_sha256: "b".repeat(64), regions_digest: "c".repeat(64), width: 1280, height: 720 };
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let container: HTMLDivElement;
let root: Root | null = null;
afterEach(async () => { if (root) { const r = root; root = null; await act(async () => r.unmount()); container.remove(); } vi.unstubAllGlobals(); });
async function mountEl(el: ReturnType<typeof createElement>) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root!.render(el); });
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}
const type = async (input: HTMLInputElement, value: string) => {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  await act(async () => { setter.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); });
};
const btn = (t: string) => [...container.querySelectorAll("button")].find((x) => x.textContent?.trim() === t) as HTMLButtonElement | undefined;

describe("ReopenPanel", () => {
  it("accepts only a full 64-hex digest and never calls on a malformed one", async () => {
    const onReopen = vi.fn().mockResolvedValue(undefined);
    await mountEl(createElement(ReopenPanel, { onReopen }));
    const input = container.querySelector("input") as HTMLInputElement;
    expect(container.textContent).toContain("original photo is never shown or returned");
    expect(container.textContent).not.toContain("not shown until you prepare and acknowledge");
    await type(input, "abc123");
    expect(btn("Reopen")!.disabled).toBe(true);
    expect(container.textContent).toContain("exactly 64 hex");
    await type(input, ` ${SOURCE.toUpperCase()} `);
    expect(btn("Reopen")!.disabled).toBe(false);
    await act(async () => { btn("Reopen")!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    expect(onReopen).toHaveBeenCalledWith(SOURCE);
  });
  it("shows a refusal and nothing else", async () => {
    const onReopen = vi.fn().mockRejectedValue(new Error("No stored job with that digest is available to this account."));
    await mountEl(createElement(ReopenPanel, { onReopen }));
    await type(container.querySelector("input") as HTMLInputElement, SOURCE);
    await act(async () => { btn("Reopen")!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await act(async () => {});
    expect(container.querySelector("[role=alert]")?.textContent).toContain("No stored job");
  });
});

describe("reopenStoredAudit client", () => {
  async function client() { vi.resetModules(); return await import("../../api/backendClient"); }
  it("rejects a malformed digest without any request", async () => {
    const f = vi.fn(); vi.stubGlobal("fetch", f);
    await expect((await client()).reopenStoredAudit("nope")).rejects.toThrow(/64-character/);
    expect(f).not.toHaveBeenCalled();
  });
  it("posts only to the exact reopen-audit route and refuses a digest mismatch or a 409 without retry", async () => {
    const f = vi.fn().mockResolvedValueOnce(json(200, { ...audit, image: { ...audit.image, pixel_digest: "d".repeat(64) } })).mockResolvedValueOnce(json(409, { detail: "x" }));
    vi.stubGlobal("fetch", f);
    const c = await client();
    await expect(c.reopenStoredAudit(SOURCE)).rejects.toThrow(/different source/);
    await expect(c.reopenStoredAudit(SOURCE)).rejects.toThrow(/Nothing was reopened and nothing was analysed/);
    expect(f).toHaveBeenCalledTimes(2);
    expect((f.mock.calls[0] as [string])[0]).toBe(`/api/vigilens/fresh-review/${SOURCE}/reopen-audit`);
  });
  it("returns a normalized audit on a bound 200", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(200, audit)));
    const out = await (await client()).reopenStoredAudit(SOURCE);
    expect(out.image.pixel_digest).toBe(SOURCE);
    expect(out.rechecks?.status).toBe("not_configured");
  });
});

describe("PreviewCeremony with no browser file (reopened stored job)", () => {
  it("uses the reopen routes and sends no image field", async () => {
    const f = vi.fn().mockImplementation((url: string) => Promise.resolve(json(200, String(url).includes("face-proposals") ? faces : session)));
    vi.stubGlobal("fetch", f);
    await mountEl(createElement(PreviewCeremony, { audit, file: null, onAcknowledged: () => {}, onInvalidate: () => {} }));
    await act(async () => {});
    expect((f.mock.calls[0] as [string])[0]).toBe(`/api/vigilens/fresh-review/${SOURCE}/face-proposals/reopen`);
    expect((f.mock.calls[0] as [string, RequestInit])[1].body && ((f.mock.calls[0] as [string, RequestInit])[1].body as FormData).get("image")).toBeFalsy();
    const box = [...container.querySelectorAll("label")].find((l) => l.textContent?.includes("Withhold the whole image"))!.querySelector("input") as HTMLInputElement;
    await act(async () => { box.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await act(async () => { btn("Prepare a treated preview")!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    const call = f.mock.calls[1] as [string, RequestInit];
    expect(call[0]).toBe(`/api/vigilens/fresh-review/${SOURCE}/private-display/reopen`);
    expect((call[1].body as FormData).get("image")).toBeNull();
    expect(JSON.parse(String((call[1].body as FormData).get("review"))).source_digest).toBe(SOURCE);
  });
});

describe("reducer: reopened", () => {
  it("sets a stored source and the audit with no zones, no analysis and no browser photo", () => {
    const next = reducer({ ...initialState, zones: [{ id: "z", name: "z", hazard: false, points: [] }] }, { type: "reopened", source: { kind: "stored", imageUrl: null, name: "Stored job", digest: SOURCE }, audit, loadedAt: "10:00" });
    expect(next.source).toMatchObject({ kind: "stored", imageUrl: null, digest: SOURCE });
    expect(next.audit).toBe(audit);
    expect(next.status).toBe("success");
    expect(next.zones).toEqual([]);
  });
});
