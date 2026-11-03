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

describe("executeRecheck", () => {
  const SRC = "a".repeat(64);
  const ATTEMPT = "b".repeat(64);
  const BINDING = { source_digest: SRC, result_sha256: "c".repeat(64) };

  it("posts the exact binding to the per-attempt proxy route and returns the view", async () => {
    const view = {
      attempt_id: ATTEMPT, state: "completed", retry_allowed: false,
      provider_calls_this_request: 2, evidence_export_allowed: false,
      result: { helmet: "present", vest: "unknown" },
      binding: { ...BINDING, person_id: "0", attempt: 0, crop_png_sha256: "d".repeat(64) },
      original_result_unchanged: true, candidate_adoption: "requires_separate_human_review",
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, view));
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    const out = await client.executeRecheck(SRC, ATTEMPT, BINDING);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const call = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(call[0]).toBe(`/api/vigilens/fresh-review/${SRC}/recheck/${ATTEMPT}`);
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body as string)).toEqual(BINDING);
    expect(out.state).toBe("completed");
  });

  it("surfaces the backend's exact 409 refusal, never retries", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(409, { detail: "Explicit recheck unavailable; no new reservation, grant or automatic retry" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    await expect(client.executeRecheck(SRC, ATTEMPT, BINDING)).rejects.toThrow(
      /Explicit recheck unavailable.*No automatic retry/,
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("maps 503 to execution-disabled without retry", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(503, { detail: "Recheck execution disabled" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    await expect(client.executeRecheck(SRC, ATTEMPT, BINDING)).rejects.toThrow(/disabled.*503/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("rejects a non-JSON success response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("ok", { status: 200, headers: { "content-type": "text/plain" } }));
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    await expect(client.executeRecheck(SRC, ATTEMPT, BINDING)).rejects.toThrow(/Invalid response format/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("uploadClip", () => {
  function clipSummary() {
    return {
      source_clip_sha256: "e".repeat(64), duration_seconds: 4.0,
      requested_sample_count: 2, completed_sample_count: 2,
      frames: [{
        sample_index: 0, requested_offset_seconds: 1.0, timestamp_basis: "container",
        source_clip_sha256: "e".repeat(64), pixel_digest: "f".repeat(64), width: 640, height: 360,
        image_job: { state: "completed", result: { persons: [] } },
        provider_calls_this_sample: 2, repeated_pixels_share_image_job: false,
      }],
      provider_calls_this_request: 2, status: "completed",
      frames_with_unassessed_people: [], frames_with_unresolved_people: [],
      attempted_is_not_resolved_assessment: true,
      completed_state_is_execution_terminal_not_assessment_complete: true,
      cross_frame_person_identity: "not_inferred",
      sampled_frames_are_not_complete_clip_coverage: true,
      clip_intrusion_or_crossing: "not_inferred_from_sampled_presence",
      privacy_review_status: "not_validated", evidence_export_allowed: false,
      automatic_retry_allowed: false,
      report_integration: "per_frame_private_image_review_required",
      decoder_scope: "local_trusted_clip_only_not_public_upload_service",
      private_clip_review_id: "review-1",
    };
  }

  it("posts clip + offsets as multipart and returns the summary", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, clipSummary()));
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    const file = new File([new Uint8Array([1, 2, 3])], "sample.mp4", { type: "video/mp4" });
    const out = await client.uploadClip(file, [0.5, 2.0]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const call = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(call[0]).toBe("/api/vigilens/fresh-review-clip-upload");
    expect(call[1].method).toBe("POST");
    const body = call[1].body as FormData;
    expect(body.get("offsets")).toBe("[0.5,2]");
    expect((body.get("clip") as File).name).toBe("sample.mp4");
    expect(out.status).toBe("completed");
    expect(out.sampled_frames_are_not_complete_clip_coverage).toBe(true);
  });

  it("surfaces the backend's not-configured 409 verbatim, never retries", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(409, { detail: "Trusted clip preparation/source approval unavailable; no automatic retry" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    const file = new File([new Uint8Array([1])], "c.mp4", { type: "video/mp4" });
    await expect(client.uploadClip(file, [1])).rejects.toThrow(/Trusted clip preparation.*No automatic retry/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("maps 503 to execution-disabled without retry", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(503, { detail: "Clip provider execution disabled" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    const file = new File([new Uint8Array([1])], "c.mp4", { type: "video/mp4" });
    await expect(client.uploadClip(file, [1])).rejects.toThrow(/disabled.*503/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("rejects a non-JSON success response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("ok", { status: 200, headers: { "content-type": "text/plain" } }));
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    const file = new File([new Uint8Array([1])], "c.mp4", { type: "video/mp4" });
    await expect(client.uploadClip(file, [1])).rejects.toThrow(/Invalid response format/);
  });
});

describe("private-display ceremony client", () => {
  const SOURCE = "a".repeat(64);
  function sessionBody() {
    return {
      session_id: "sess-token-abcdef-123456",
      source_digest: SOURCE,
      output_sha256: "b".repeat(64),
      regions_digest: "c".repeat(64),
      width: 1280, height: 720,
      preview_url: "/private-display/sess-token-abcdef-123456/image",
      warning: "Blur may retain identity.",
      evidence_export_allowed: false,
    };
  }

  it("posts image + review JSON as multipart to the exact source route", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, sessionBody()));
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    const file = new File([new Uint8Array([9, 9])], "scene.png", { type: "image/png" });
    const review = { source_digest: SOURCE, frame_size: [1280, 720], regions: [], reviewer_label: "visitor preview preparation", redaction_method: "opaque" };
    const out = await client.preparePrivateDisplay(SOURCE, file, review);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const call = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(call[0]).toBe(`/api/vigilens/fresh-review/${SOURCE}/private-display`);
    expect(call[1].method).toBe("POST");
    const body = call[1].body as FormData;
    expect((body.get("image") as File).name).toBe("scene.png");
    expect(JSON.parse(body.get("review") as string).redaction_method).toBe("opaque");
    expect(out.session_id).toBe("sess-token-abcdef-123456");
    expect(out.evidence_export_allowed).toBe(false);
  });

  it("surfaces a 409 binding refusal verbatim and never retries", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(409, { detail: "Fresh preview binding unavailable or changed" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    const file = new File([new Uint8Array([1])], "scene.png", { type: "image/png" });
    await expect(client.preparePrivateDisplay(SOURCE, file, {})).rejects.toThrow(/binding unavailable or changed.*409.*No automatic retry/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  const ALL_CHECKED = { foreground_checked: true, background_checked: true, reflections_checked: true, derivative_checked: true };

  it("acknowledges with the exact derivative fields and all four visual checks", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { status: "acknowledged" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    await client.acknowledgePrivateDisplay(sessionBody() as never, ALL_CHECKED);
    const call = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(call[0]).toBe("/api/vigilens/private-display/sess-token-abcdef-123456/review");
    const body = JSON.parse(call[1].body as string);
    expect(body).toEqual({
      source_digest: SOURCE,
      output_sha256: "b".repeat(64),
      regions_digest: "c".repeat(64),
      frame_size: [1280, 720],
      foreground_checked: true,
      background_checked: true,
      reflections_checked: true,
      derivative_checked: true,
    });
  });

  it("surfaces an acknowledgment mismatch refusal verbatim and never retries", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(409, { detail: "Review must match this exact derivative" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    await expect(client.acknowledgePrivateDisplay(sessionBody() as never, ALL_CHECKED)).rejects.toThrow(/exact derivative.*409/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("serializes the actual checkbox map, including a false value", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(409, { detail: "Review must match this exact derivative" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    await expect(
      client.acknowledgePrivateDisplay(sessionBody() as never, { ...ALL_CHECKED, reflections_checked: false }),
    ).rejects.toThrow(/409/);
    const call = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(call[1].body as string).reflections_checked).toBe(false);
  });

  it("rejects a malformed prepare response instead of trusting it", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { session_id: "x", source_digest: "not-hex" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    const file = new File([new Uint8Array([1])], "scene.png", { type: "image/png" });
    await expect(client.preparePrivateDisplay(SOURCE, file, {})).rejects.toThrow(/Invalid response format/);
  });

  it("builds the treated preview image URL from the session id", async () => {
    const client = await importClient({});
    expect(client.privateDisplayImageUrl("sess token")).toBe("/api/vigilens/private-display/sess%20token/image");
  });
});

describe("face-proposals review-aid client", () => {
  const SOURCE = "a".repeat(64);
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

  it("posts the exact original image to the source route and returns labeled proposals", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, proposalsBody()));
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    const file = new File([new Uint8Array([9, 9])], "scene.png", { type: "image/png" });
    const out = await client.fetchFaceProposals(SOURCE, file);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const call = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(call[0]).toBe(`/api/vigilens/fresh-review/${SOURCE}/face-proposals`);
    expect(call[1].method).toBe("POST");
    expect((call[1].body as FormData).get("image")).toBeTruthy();
    expect(out.proposals).toHaveLength(1);
    expect(out.coverage).toBe("unverified");
    expect(out.zero_detections_means_safe).toBe(false);
  });

  it("surfaces a 409 unavailability refusal and never retries", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(409, { detail: "Face proposals unavailable; manual whole-frame coverage review still required" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = await importClient({});
    const file = new File([new Uint8Array([9])], "scene.png", { type: "image/png" });
    await expect(client.fetchFaceProposals(SOURCE, file)).rejects.toThrow(/manual whole-frame coverage review still required.*409.*No automatic retry/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("rejects a result that claims zero detections mean safe", async () => {
    const bad = { ...proposalsBody(), proposals: [], zero_detections_means_safe: true };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, bad)));
    const client = await importClient({});
    const file = new File([new Uint8Array([9])], "scene.png", { type: "image/png" });
    await expect(client.fetchFaceProposals(SOURCE, file)).rejects.toThrow(/Invalid response format/);
  });

  it("rejects a result that claims automatic treatment or provider calls", async () => {
    const file = new File([new Uint8Array([9])], "scene.png", { type: "image/png" });
    const client = await importClient({});
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, { ...proposalsBody(), automatic_treatment_applied: true })));
    await expect(client.fetchFaceProposals(SOURCE, file)).rejects.toThrow(/Invalid response format/);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, { ...proposalsBody(), provider_calls_this_request: 1 })));
    await expect(client.fetchFaceProposals(SOURCE, file)).rejects.toThrow(/Invalid response format/);
  });

  it("rejects malformed proposal boxes", async () => {
    const bad = proposalsBody();
    (bad.proposals[0] as Record<string, unknown>).review_region = [1, 2, 3];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, bad)));
    const client = await importClient({});
    const file = new File([new Uint8Array([9])], "scene.png", { type: "image/png" });
    await expect(client.fetchFaceProposals(SOURCE, file)).rejects.toThrow(/Invalid response format/);
  });
});
