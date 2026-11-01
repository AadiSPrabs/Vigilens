// Focused tests for the governed-backend client and fixture/backend routing.
// No network: global fetch is mocked; module env is set before dynamic import.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const TOKEN = "test-local-access-key-0123456789abcdef";

function governedAudit() {
  return {
    audit_id: "fresh:abc:def",
    schema_version: "0.2-local-draft",
    source: "backend",
    created_at: null,
    image: { id: "0123456789abcdef", pixel_digest: "0".repeat(64), width: 1280, height: 720 },
    source_digest: "0".repeat(64),
    zones: [{ id: "z1", name: "Edge", hazard: true, points: [{ x: 0.1, y: 0.1 }, { x: 0.5, y: 0.1 }, { x: 0.5, y: 0.5 }] }],
    evidence_image: null,
    evidence_status: "unavailable",
    evidence_export_allowed: false,
    persons: [{
      id: "0",
      polygon: [{ x: 0.1, y: 0.1 }, { x: 0.2, y: 0.1 }, { x: 0.2, y: 0.5 }, { x: 0.1, y: 0.5 }],
      helmet: "unknown", vest: "present",
      zone_id: null, zone_ids: [], zone_membership_status: "unknown", worst_severity: null,
      findings: [{ id: "f1", rule_id: "helmet_reading", kind: "uncertainty", severity: null,
                   zone_id: null, message: "Synthetic transport generated a helmet-absent reading", review_state: "needs_human_review" }],
    }],
    readings_origin: "synthetic",
    readings_status: "unvalidated_provider_observations",
    zones_applied: false,
  };
}

function jsonResponse(status: number, body: unknown) {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function importClient(env: Record<string, string>) {
  vi.resetModules();
  Object.assign(import.meta.env, env);
  return await import("../backendClient");
}

beforeEach(() => {
  (import.meta.env as Record<string, unknown>).VITE_VIGILENS_LOCAL_ACCESS = "";
  (import.meta.env as Record<string, unknown>).VITE_API_BASE_URL = "";
});
afterEach(() => vi.unstubAllGlobals());

describe("backendClient", () => {
  it("posts the exact governed contract: multipart fields, headers, strict zone shape", async () => {
    const mod = await importClient({});
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, governedAudit()));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File([new Uint8Array([1, 2, 3])], "photo.png", { type: "image/png" });
    const zones = [
      { id: "z1", name: "Edge", hazard: true, points: [{ x: 0.1, y: 0.1 }, { x: 0.5, y: 0.1 }, { x: 0.5, y: 0.5 }], extra: "dropped" } as never,
    ];
    const audit = await mod.analyzeWithBackend(file, zones);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    // Same-origin proxy route only; the browser must never see a backend URL or token.
    expect(url).toBe("/api/vigilens/fresh-review-audit-governed");
    const headers = (init.headers ?? {}) as Record<string, string>;
    expect(headers["X-Vigilens-Local-Access"]).toBeUndefined();
    expect(headers["X-Vigilens-Display-Session"]).toBeUndefined();
    const form = init.body as FormData;
    expect((form.get("image") as File).name).toBe("photo.png");
    // strict wire shape: exactly id/name/hazard/points, points reduced to {x,y}
    expect(JSON.parse(form.get("zones") as string)).toEqual([
      { id: "z1", name: "Edge", hazard: true, points: [{ x: 0.1, y: 0.1 }, { x: 0.5, y: 0.1 }, { x: 0.5, y: 0.5 }] },
    ]);
    // UI-shape normalization: fixture fields nulled, recheck_trace supplied
    expect(audit.fixture_loaded_at).toBeNull();
    expect(audit.persons[0]!.findings[0]!.recheck_trace).toEqual([]);
    expect(audit.readings_origin).toBe("synthetic");
  });

  it("maps refusal statuses to no-retry errors", async () => {
    const mod = await importClient({});
    const file = new File([new Uint8Array([1])], "p.png", { type: "image/png" });
    for (const [status, body, needle] of [
      [403, {}, "server's backend access was refused (403)"],
      [503, {}, "Provider execution disabled on this backend (503)"],
      [400, {}, "Invalid request (400)"],
      [409, {}, "not approved for analysis on this install"],
      [409, { detail: { code: "ATTEMPT_UNCERTAIN" } }, "started and did not finish"],
    ] as const) {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(status, body)));
      const err = await mod.analyzeWithBackend(file, []).catch((e) => e);
      expect(err).toBeInstanceOf(mod.BackendError);
      expect(err.message).toContain(needle);
      expect(err.noRetry).toBe(true);
    }
  });

  it("surfaces exact image-refusal codes for 413/415/422 without retry", async () => {
    const mod = await importClient({});
    const file = new File([new Uint8Array([1])], "p.png", { type: "image/png" });
    for (const [status, body, needle] of [
      [413, { error: { code: "IMAGE_TOO_LARGE", message: "File exceeds 15,000,000 bytes." } }, "15,000,000 bytes"],
      [415, { error: { code: "UNSUPPORTED_MEDIA_TYPE", message: "Use JPEG, PNG or WebP." } }, "JPEG, PNG or WebP"],
      [422, { error: { code: "IMAGE_ORIENTATION_UNSUPPORTED", message: "Normalize EXIF orientation before uploading" } }, "EXIF orientation"],
    ] as const) {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(status, body)));
      const err = await mod.analyzeWithBackend(file, []).catch((e) => e);
      expect(err).toBeInstanceOf(mod.BackendError);
      expect(err.message).toContain(needle);
      expect(err.noRetry).toBe(true);
    }
    // malformed refusal body falls back to a bounded generic message
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(413, "not json")));
    const err = await mod.analyzeWithBackend(file, []).catch((e) => e);
    expect(err.message).toContain("refused this image (413)");
  });

  it("rejects non-JSON success responses", async () => {
    const mod = await importClient({});
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response("<html>proxy page</html>", { status: 200, headers: { "content-type": "text/html" } })));
    const file = new File([new Uint8Array([1])], "p.png", { type: "image/png" });
    await expect(mod.analyzeWithBackend(file, [])).rejects.toThrow("Invalid response format");
  });

  it("reports a timeout as still-running, never as failure", async () => {
    const mod = await importClient({});
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockImplementation((_u: string, init: RequestInit) =>
      new Promise((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => reject(init.signal?.reason));
      })));
    const file = new File([new Uint8Array([1])], "p.png", { type: "image/png" });
    const pending = mod.analyzeWithBackend(file, []);
    const assertion = expect(pending).rejects.toThrow("No response yet; the audit may still be running.");
    await vi.advanceTimersByTimeAsync(61000);
    await assertion;
    vi.useRealTimers();
  });

  it("backendConfigured is always true in the proxied build (readiness is the gate)", async () => {
    const mod = await importClient({});
    expect(mod.backendConfigured()).toBe(true);
  });

  it("checkBackendReady pings the same-origin proxy health route", async () => {
    const mod = await importClient({});
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(mod.checkBackendReady()).resolves.toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/vigilens/health");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    const mod2 = await importClient({});
    await expect(mod2.checkBackendReady()).resolves.toBe(false);
  });
});

describe("auditClient routing", () => {
  it("resolves bundled samples from fixtures without any fetch", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.resetModules();
    Object.assign(import.meta.env, { VITE_VIGILENS_LOCAL_ACCESS: "" });
    const client = await import("../auditClient");
    const { SAMPLE_PRESET_ZONES } = await import("../../fixtures/audits");
    const zones = structuredClone(SAMPLE_PRESET_ZONES["sample-1"]);
    const audit = await client.analyzeImage({ file: null, zones, sampleId: "sample-1" });
    expect(audit.source).toBe("fixture");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("upload always routes to the same-origin proxy in this build", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, governedAudit()));
    vi.stubGlobal("fetch", fetchMock);
    vi.resetModules();
    const client = await import("../auditClient");
    const file = new File([new Uint8Array([1])], "p.png", { type: "image/png" });
    await client.analyzeImage({ file, zones: [], sampleId: null });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/vigilens/fresh-review-audit-governed");
  });

  it("upload with backend config goes to the governed route and validates", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, governedAudit()));
    vi.stubGlobal("fetch", fetchMock);
    vi.resetModules();
    Object.assign(import.meta.env, { VITE_VIGILENS_LOCAL_ACCESS: TOKEN });
    const client = await import("../auditClient");
    const file = new File([new Uint8Array([1])], "p.png", { type: "image/png" });
    const audit = await client.analyzeImage({ file, zones: [], sampleId: null });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(audit.source).toBe("backend");
    expect(audit.readings_origin).toBe("synthetic");
  });

  it("upload with backend config surfaces refusal without retry", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(409, { detail: { code: "ATTEMPT_UNCERTAIN" } }));
    vi.stubGlobal("fetch", fetchMock);
    vi.resetModules();
    Object.assign(import.meta.env, { VITE_VIGILENS_LOCAL_ACCESS: TOKEN });
    const client = await import("../auditClient");
    const file = new File([new Uint8Array([1])], "p.png", { type: "image/png" });
    await expect(client.analyzeImage({ file, zones: [], sampleId: null }))
      .rejects.toThrow("started and did not finish");
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});
