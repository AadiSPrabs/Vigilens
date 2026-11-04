// Backend adapter: the UI never calls a provider API itself, and never talks to
// the Vigilens backend directly. Uploads go to the same-origin server proxy at
// /api/vigilens/*, which requires the user's login session and attaches the
// backend token and the server-derived display session there. No credential of
// any kind is baked into this bundle. Refused/held responses surface as-is and
// are never retried automatically by this client.
import type { Audit, ClipSummary, FaceProposalsResult, PrivateDisplaySession, RecheckAttempt, Zone } from "../types";

const BACKEND_ENDPOINT = "/api/vigilens/fresh-review-audit-governed";
const HEALTH_ENDPOINT = "/api/vigilens/health";
const TIMEOUT_MS = 60000;
const EXECUTION_TIMEOUT_MS = 320000;

export class BackendError extends Error {
  noRetry = true;
}

export class PendingAuditError extends BackendError {
  pending = true;
}

export function backendConfigured(): boolean {
  // The proxy route always exists in this build; readiness (below) is the real gate.
  return true;
}

// Readiness probe for cold-starting hosts (Render free tier sleeps). /health is
// unauthenticated by design; a false return only means "not ready yet".
export async function checkBackendReady(): Promise<boolean> {
  try {
    const res = await fetch(HEALTH_ENDPOINT, { cache: "no-store" });
    if (!res.ok || !res.headers.get("content-type")?.includes("application/json")) return false;
    const health = await res.json();
    return health?.status === "ok";
  } catch {
    return false;
  }
}

function stripZone(zone: Zone) {
  return {
    id: zone.id,
    name: zone.name,
    hazard: zone.hazard,
    points: zone.points.map((p) => ({ x: p.x, y: p.y })),
  };
}

export async function analyzeWithBackend(
  file: File,
  zones: Zone[],
  signal?: AbortSignal,
): Promise<Audit> {
  const formData = new FormData();
  formData.append("image", file);
  formData.append("zones", JSON.stringify(zones.map(stripZone)));

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), EXECUTION_TIMEOUT_MS);
  if (signal) {
    signal.addEventListener("abort", () => controller.abort(signal.reason));
  }

  try {
    // Never set Content-Type manually on FormData.
    const response = await fetch(BACKEND_ENDPOINT, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });

    if (response.status === 403) {
      throw new BackendError(
        "The server's backend access was refused (403). The deployment's backend token needs operator attention; the upload was not processed. No automatic retry.",
      );
    }
    if (response.status === 503) {
      throw new BackendError("Provider execution disabled on this backend (503); no claim or call was created.");
    }
    if (response.status === 409) {
      try {
        const errJson = await response.json();
        const code = errJson?.detail?.code;
        if (code === "ATTEMPT_UNCERTAIN") {
          throw new PendingAuditError(
            "A provider attempt for this exact image was started and did not finish. It is held and never retried automatically; only the backend ledger reconciles it.",
          );
        }
      } catch (e) {
        if (e instanceof BackendError) throw e;
      }
      throw new BackendError(
        "This image is not approved for analysis on this install, or the result is not presentable (409). No automatic retry.",
      );
    }
    if (response.status === 400) {
      throw new BackendError("Invalid request (400): the backend rejected the upload fields.");
    }
    // Image-input failures carry operator-safe codes/messages from the backend
    // ({error:{code,message}}); surface them instead of a generic error so a too-large,
    // rotated or unsupported photo tells the user the real fix. No automatic retry.
    if (response.status === 413 || response.status === 415 || response.status === 422) {
      try {
        const errJson = await response.json();
        const code = errJson?.error?.code;
        const message = errJson?.error?.message;
        if (typeof code === "string" && typeof message === "string") {
          throw new BackendError(`${message} (${response.status} ${code}). No automatic retry.`);
        }
      } catch (e) {
        if (e instanceof BackendError) throw e;
      }
      throw new BackendError(`The backend refused this image (${response.status}). No automatic retry.`);
    }
    if (response.status >= 500 && response.status !== 503) throw new PendingAuditError("Status unknown; the audit may still be running. Check stored status only. Do not run analysis again.");
    if (!response.ok) {
      throw new BackendError(`Backend error: ${response.status}`);
    }

    const contentType = response.headers.get("content-type");
    if (!contentType || !contentType.includes("application/json")) {
      throw new BackendError("Invalid response format");
    }
    const audit = (await response.json()) as Audit;
    // Normalize to the UI's Audit shape: fields the UI renders but the governed
    // route does not emit. Extra governed-route fields (readings_origin, job_state,
    // zones_applied, ...) are preserved for honesty labeling.
    audit.fixture_loaded_at = audit.fixture_loaded_at ?? null;
    audit.fixture_notice = audit.fixture_notice ?? null;
    audit.rechecks = audit.rechecks ?? {
      status: "not_configured",
      attempts: [],
      original_result_unchanged: true,
    };
    for (const person of audit.persons) {
      for (const finding of person.findings) {
        finding.recheck_trace = finding.recheck_trace ?? [];
      }
    }
    return audit;
  } catch (err) {
    if (err instanceof BackendError) throw err;
    if ((err as DOMException)?.name === "AbortError" || err === "timeout") {
      throw new PendingAuditError("Status unknown; the audit may still be running. Check stored status only. Do not run analysis again.");
    }
    throw new PendingAuditError("Connection lost; analysis status is unknown. Check stored status only. Do not run analysis again.");
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function recoverUploadedAudit(file: File, zones: Zone[]): Promise<Audit> {
  const body = new FormData(); body.append("image", file); body.append("zones", JSON.stringify(zones.map(stripZone)));
  const res = await fetch("/api/vigilens/fresh-review-job-status", { method: "POST", body, signal: AbortSignal.timeout(TIMEOUT_MS) });
  if (!res.ok) throw new PendingAuditError("Stored status unavailable. No analysis was retried; check again later.");
  const out = await res.json();
  if (out.status !== "completed" || !out.audit) throw new PendingAuditError("No completed result visible yet. No analysis was retried; the hold remains pending reconciliation.");
  const audit = out.audit as Audit; audit.fixture_loaded_at ??= null; audit.fixture_notice ??= null;
  audit.rechecks ??= { status: "not_configured", attempts: [], original_result_unchanged: true };
  for (const p of audit.persons) for (const f of p.findings) f.recheck_trace ??= [];
  return audit;
}

// ---- Visitor BYOK (bring-your-own Meta key) -------------------------------
// The key is entered by the visitor and held only in the Nitro server's memory,
// bound to their login session (2h TTL, forget any time). It is never written
// to the database, this bundle, localStorage, or any log.
const KEY_ENDPOINT = "/api/vigilens/key";

export interface VisitorKeyStatus {
  present: boolean;
  fingerprint?: string;
  expiresAt?: string;
}


// Explicit, per-attempt, user-triggered recheck execution against the pinned grant.
// The payload is exactly the attempt binding {source_digest, result_sha256}; the
// backend re-binds it to the immutable original and refuses anything else. This
// client never retries and never adopts the returned candidate.
export async function executeRecheck(
  sourceDigest: string,
  attemptId: string,
  binding: { source_digest: string; result_sha256: string },
): Promise<RecheckAttempt> {
  const response = await fetch(
    `/api/vigilens/fresh-review/${encodeURIComponent(sourceDigest)}/recheck/${encodeURIComponent(attemptId)}`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ source_digest: binding.source_digest, result_sha256: binding.result_sha256 }),
    },
  );
  if (response.status === 409) {
    let detail = "";
    try {
      const errJson = await response.json();
      if (typeof errJson?.detail === "string") detail = errJson.detail;
    } catch {
      // fall through to the generic refusal below
    }
    throw new BackendError(
      detail ? `${detail} (409). No automatic retry.` : "Recheck refused (409). No new reservation, grant or automatic retry.",
    );
  }
  if (response.status === 503) {
    throw new BackendError("Recheck execution disabled on this backend (503); no claim or call was created.");
  }
  if (!response.ok) {
    throw new BackendError(`Backend error: ${response.status}. No automatic retry.`);
  }
  const contentType = response.headers.get("content-type");
  if (!contentType || !contentType.includes("application/json")) {
    throw new BackendError("Invalid response format");
  }
  return (await response.json()) as RecheckAttempt;
}


const CLIP_ENDPOINT = "/api/vigilens/fresh-review-clip-upload";

// Bounded local-clip sampling upload. The backend decodes MP4 frames locally under
// explicit trusted_clip_limits and audits each sampled frame through the existing
// approval pipeline; when no decoder limits are configured it refuses (409) and this
// client surfaces that refusal truthfully instead of a dead affordance. Never retried.
export async function uploadClip(file: File, offsetsSeconds: number[]): Promise<ClipSummary> {
  const formData = new FormData();
  formData.append("clip", file);
  formData.append("offsets", JSON.stringify(offsetsSeconds));

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(CLIP_ENDPOINT, { method: "POST", body: formData, signal: controller.signal });
    if (response.status === 403) {
      throw new BackendError("The server's backend access was refused (403). The upload was not processed. No automatic retry.");
    }
    if (response.status === 503) {
      throw new BackendError("Clip provider execution disabled on this backend (503); no claim or call was created.");
    }
    if (response.status === 409) {
      let detail = "";
      try {
        const errJson = await response.json();
        if (typeof errJson?.detail === "string") detail = errJson.detail;
      } catch {
        // fall through to the generic refusal below
      }
      throw new BackendError(
        detail
          ? `${detail} (409). No automatic retry.`
          : "Clip sampling is not enabled on this deployment (409). No automatic retry.",
      );
    }
    if (response.status === 400 || response.status === 413 || response.status === 415 || response.status === 422) {
      throw new BackendError(`The backend rejected this clip (${response.status}). Check the file type and size. No automatic retry.`);
    }
    if (!response.ok) {
      throw new BackendError(`Backend error: ${response.status}. No automatic retry.`);
    }
    const contentType = response.headers.get("content-type");
    if (!contentType || !contentType.includes("application/json")) {
      throw new BackendError("Invalid response format");
    }
    return (await response.json()) as ClipSummary;
  } catch (err) {
    if (err instanceof BackendError) throw err;
    if ((err as DOMException)?.name === "AbortError" || err === "timeout") {
      throw new Error("No response yet; the clip sampling may still be running. No automatic retry.");
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function getVisitorKeyStatus(): Promise<VisitorKeyStatus> {
  const res = await fetch(KEY_ENDPOINT, { cache: "no-store" });
  if (!res.ok) throw new BackendError(`Key status failed (${res.status})`);
  return res.json() as Promise<VisitorKeyStatus>;
}

export async function setVisitorKey(key: string): Promise<VisitorKeyStatus> {
  const res = await fetch(KEY_ENDPOINT, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ key }),
  });
  if (!res.ok) {
    let msg = `Could not save key (${res.status})`;
    if (res.status === 429) msg = "Too many key updates; try again later";
    if (res.status === 400) msg = "That key value was not accepted";
    throw new BackendError(msg);
  }
  return res.json() as Promise<VisitorKeyStatus>;
}

export async function forgetVisitorKey(): Promise<void> {
  const res = await fetch(KEY_ENDPOINT, { method: "DELETE" });
  if (!res.ok) throw new BackendError(`Could not forget key (${res.status})`);
}

// ---- Private-display ceremony (existing backend gate, wired end-to-end) ----

const HEX64 = /^[0-9a-f]{64}$/;

function isPrivateDisplaySession(value: unknown): value is PrivateDisplaySession {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.session_id === "string" && v.session_id.length >= 8 && v.session_id.length <= 128 &&
    typeof v.source_digest === "string" && HEX64.test(v.source_digest) &&
    typeof v.output_sha256 === "string" && HEX64.test(v.output_sha256) &&
    typeof v.regions_digest === "string" && HEX64.test(v.regions_digest) &&
    Number.isInteger(v.width) && (v.width as number) > 0 &&
    Number.isInteger(v.height) && (v.height as number) > 0
  );
}

async function readRefusal(response: Response, fallback: string): Promise<never> {
  let detail = "";
  try {
    const errJson = await response.json();
    if (typeof errJson?.detail === "string") detail = errJson.detail;
  } catch {
    // fall through to the generic refusal below
  }
  throw new BackendError(detail ? `${detail} (${response.status}). No automatic retry.` : `${fallback} (${response.status}). No automatic retry.`);
}

export async function preparePrivateDisplay(
  source: string,
  image: File | null,
  review: Record<string, unknown>,
): Promise<PrivateDisplaySession> {
  const formData = new FormData();
  // image === null means "reopen": the backend reads this account's own stored source.
  if (image) formData.append("image", image);
  formData.append("review", JSON.stringify(review));
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(`/api/vigilens/fresh-review/${source}/private-display${image ? "" : "/reopen"}`, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });
    if (response.status === 403) return readRefusal(response, "Private browser session required");
    if (response.status === 409) return readRefusal(response, "Fresh preview binding unavailable or changed");
    if (!response.ok) return readRefusal(response, "Preview preparation refused");
    const body: unknown = await response.json();
    if (!isPrivateDisplaySession(body)) {
      throw new BackendError("Invalid response format from the server: not a usable preview session. No automatic retry.");
    }
    return body;
  } finally {
    clearTimeout(timeoutId);
  }
}

function isFaceProposalsResult(value: unknown): value is FaceProposalsResult {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.source_pixel_digest === "string" && HEX64.test(v.source_pixel_digest) &&
    Array.isArray(v.frame) && v.frame.length === 2 && v.frame.every((n) => Number.isInteger(n) && (n as number) > 0) &&
    typeof v.detector === "string" &&
    Array.isArray(v.proposals) &&
    v.proposals.every((pr) => {
      if (typeof pr !== "object" || pr === null) return false;
      const r = pr as Record<string, unknown>;
      const boxOk = (b: unknown) => Array.isArray(b) && b.length === 4 && (b as unknown[]).every((n) => Number.isFinite(n));
      // helmet_overlap_unchecked must be exactly true on every proposal: this aid
      // never checks helmets or overlaps, so the UI caveat may never disappear.
      return boxOk(r.box) && boxOk(r.review_region) && typeof r.confidence === "number" && Number.isFinite(r.confidence) && r.helmet_overlap_unchecked === true;
    }) &&
    v.zero_detections_means_safe === false &&
    v.automatic_treatment_applied === false &&
    v.provider_calls_this_request === 0
  );
}

// Optional offline face-check proposals. A review aid for the operator's own
// whole-frame pass - the result never marks regions, never ticks a checkbox,
// and a 409 (detector unconfigured/unavailable) just means: do the manual
// review. No automatic retry.
export async function fetchFaceProposals(source: string, image: File | null): Promise<FaceProposalsResult> {
  const formData = new FormData();
  if (image) formData.append("image", image);
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(`/api/vigilens/fresh-review/${source}/face-proposals${image ? "" : "/reopen"}`, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });
    if (response.status === 403) return readRefusal(response, "Private browser session required");
    if (response.status === 409) return readRefusal(response, "Face check unavailable");
    if (!response.ok) return readRefusal(response, "Face check refused");
    const body: unknown = await response.json();
    if (!isFaceProposalsResult(body)) {
      throw new BackendError("Invalid response format from the server: not a usable face-check result. No automatic retry.");
    }
    // Bind the result to the requested source, analogous to the prepare digest
    // guard in the ceremony: a result computed for different pixels is never
    // rendered as if it belonged to this upload.
    if (body.source_pixel_digest !== source) {
      throw new BackendError("The server returned a face-check result bound to a different source than this upload. Refusing to use it. No automatic retry.");
    }
    return body;
  } finally {
    clearTimeout(timeoutId);
  }
}

export function privateDisplayImageUrl(sessionId: string): string {
  return `/api/vigilens/private-display/${encodeURIComponent(sessionId)}/image`;
}

export type PrivateDisplayChecks = {
  foreground_checked: boolean;
  background_checked: boolean;
  reflections_checked: boolean;
  derivative_checked: boolean;
};

export async function acknowledgePrivateDisplay(session: PrivateDisplaySession, checks: PrivateDisplayChecks): Promise<void> {
  // The acknowledgment carries the visitor's ACTUAL checkbox state; the UI only
  // enables this once every box is checked, but the client serializes the real
  // map either way - the backend requires all four true and refuses otherwise.
  const ack: Record<string, unknown> = {
    source_digest: session.source_digest,
    output_sha256: session.output_sha256,
    regions_digest: session.regions_digest,
    frame_size: [session.width, session.height],
    foreground_checked: checks.foreground_checked,
    background_checked: checks.background_checked,
    reflections_checked: checks.reflections_checked,
    derivative_checked: checks.derivative_checked,
  };
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(`/api/vigilens/private-display/${encodeURIComponent(session.session_id)}/review`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(ack),
      signal: controller.signal,
    });
    if (!response.ok) return readRefusal(response, "Review must match this exact derivative and include every visual check");
  } finally {
    clearTimeout(timeoutId);
  }
}

export type IntegrationContract = {
  assessment_id: string;
  contract_status?: string;
  evidence_export_allowed?: boolean;
};

export async function fetchIntegrationContract(sourceDigest: string): Promise<IntegrationContract> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(`/api/vigilens/fresh-review/${encodeURIComponent(sourceDigest)}/integration-contract`, {
      method: "GET",
      signal: controller.signal,
    });
    if (!response.ok) return readRefusal(response, "Private report contract unavailable for this exact source");
    const body: unknown = await response.json();
    if (
      typeof body !== "object" || body === null ||
      typeof (body as Record<string, unknown>).assessment_id !== "string"
    ) {
      throw new Error("Private report contract returned an unexpected shape");
    }
    return body as IntegrationContract;
  } finally {
    clearTimeout(timeoutId);
  }
}

export type PersonReportReview = {
  exact_source_confirmed: boolean;
  face_coverage_checked: boolean;
  head_evidence_visible: boolean;
  torso_evidence_visible: boolean;
};

// Private PDF preview: the backend re-runs every report gate (exact acked
// session, per-person review, treated derivative) and renders the TREATED
// image - never the original upload. The response stays export-disabled.
export async function fetchPrivatePdfPreview(
  session: PrivateDisplaySession,
  assessmentId: string,
  persons: Record<string, PersonReportReview>,
): Promise<Blob> {
  const payload = {
    assessment_id: assessmentId,
    source_digest: session.source_digest,
    output_sha256: session.output_sha256,
    regions_digest: session.regions_digest,
    persons,
  };
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(`/api/vigilens/private-report/${encodeURIComponent(session.session_id)}/pdf-preview`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (!response.ok) return readRefusal(response, "Private PDF preview unavailable; review the exact treated preview first");
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/pdf")) {
      throw new Error("Private PDF preview returned an unexpected content type");
    }
    return await response.blob();
  } finally {
    clearTimeout(timeoutId);
  }
}

export type PrivateReportDocument = {
  status?: string;
  evidence_export_allowed?: boolean;
  spatial_explanations?: { status?: string; attempts?: unknown[]; exact_plan_sha256?: string; reservation?: string };
  configured_rule_review?: { status?: string; persons?: { person_id: string; summary?: string; findings?: { rule_id: string; zone_id: string | null; status: string; priority: number | null; reason: string }[] }[] };
  bounded_review_loop?: { status?: string; attempt_count?: number; unknown_person_ids?: string[]; blocked_until?: string; note?: string; creates_grant_or_reservation?: boolean };
  notice?: string;
  [key: string]: unknown;
};

// Private report JSON: same acked-session and per-person review gates as the
// PDF preview. The document carries the spatial-explanation section (Muse
// commentary attempts, when configured) with deterministic fields unchanged.
export async function fetchPrivateReport(
  session: PrivateDisplaySession,
  assessmentId: string,
  persons: Record<string, PersonReportReview>,
): Promise<PrivateReportDocument> {
  const payload = {
    assessment_id: assessmentId,
    source_digest: session.source_digest,
    output_sha256: session.output_sha256,
    regions_digest: session.regions_digest,
    persons,
  };
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(`/api/vigilens/private-report/${encodeURIComponent(session.session_id)}/report`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (!response.ok) return readRefusal(response, "Private report unavailable; review the exact treated preview first");
    const body: unknown = await response.json();
    if (typeof body !== "object" || body === null) {
      throw new Error("Private report returned an unexpected shape");
    }
    return body as PrivateReportDocument;
  } finally {
    clearTimeout(timeoutId);
  }
}

// audit_id carries 'fresh:<source_sha256>:<result_sha256>' (or archive-review:).
// Parse strictly; anything else means the controls stay hidden.
export function resultShaFromAuditId(auditId: string): string | null {
  const match = /^(?:fresh|archive-review):[0-9a-f]{64}:([0-9a-f]{64})$/.exec(auditId);
  return match && match[1] !== undefined ? match[1] : null;
}

export type ZoneReviewResult = Record<string, unknown>;

export async function postZoneReview(
  sourceDigest: string,
  resultSha256: string,
  zones: Zone[],
  reviewerLabel: string,
): Promise<ZoneReviewResult> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(`/api/vigilens/fresh-review/${encodeURIComponent(sourceDigest)}/zone-review`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        source_digest: sourceDigest,
        result_sha256: resultSha256,
        zones: zones.map(stripZone),
        reviewer_label: reviewerLabel,
      }),
      signal: controller.signal,
    });
    if (!response.ok) return readRefusal(response, "Zone review unavailable or invalid; no safety policy applied");
    return (await response.json()) as ZoneReviewResult;
  } finally {
    clearTimeout(timeoutId);
  }
}

export type ContactClaimResult = { manual_contact?: { at?: number; event_id?: number }; automatic_contact?: boolean; [key: string]: unknown };

// One manual ground-contact claim for one mapped person, bound to the exact acknowledged source. The backend
// refuses a point outside that person's detected foreground; the refusal is shown as-is and never retried.
export async function postContactClaim(
  sourceDigest: string,
  claim: { personId: string; point: { x: number; y: number }; exactSourceConfirmed: boolean; bootsGroundVisible: boolean; reviewerLabel: string },
): Promise<ContactClaimResult> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(`/api/vigilens/fresh-review/${encodeURIComponent(sourceDigest)}/contact`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        person_id: claim.personId,
        point: [claim.point.x, claim.point.y],
        exact_source_confirmed: claim.exactSourceConfirmed,
        boots_ground_visible: claim.bootsGroundVisible,
        reviewer_label: claim.reviewerLabel,
      }),
      signal: controller.signal,
    });
    if (!response.ok) return readRefusal(response, "Manual contact claim unavailable or invalid; nothing recorded");
    return (await response.json()) as ContactClaimResult;
  } finally {
    clearTimeout(timeoutId);
  }
}

export type BoundedLoopResult = Record<string, unknown>;

export async function runBoundedReviewLoop(sourceDigest: string, resultSha256: string): Promise<BoundedLoopResult> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(`/api/vigilens/fresh-review/${encodeURIComponent(sourceDigest)}/bounded-review-loop`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ source_digest: sourceDigest, result_sha256: resultSha256 }),
      signal: controller.signal,
    });
    if (!response.ok) return readRefusal(response, "Configured exact recheck loop unavailable; no new grant, reservation or retry");
    return (await response.json()) as BoundedLoopResult;
  } finally {
    clearTimeout(timeoutId);
  }
}

export type CameraBinding = {
  camera_id: string;
  scene_revision: string;
  width: number;
  height: number;
  coordinate_space: "normalized_upright_source_v1";
  transform: "identity";
};

export type CameraZoneTemplateResult = {
  template_id?: string;
  template?: { zones?: Zone[]; camera_binding?: CameraBinding };
  automatic_scene_verification?: boolean;
  rules_or_contacts_transferred?: boolean;
  [key: string]: unknown;
};

export async function cameraZoneOperation(
  operation: "save" | "apply",
  sourceDigest: string,
  resultSha256: string,
  binding: CameraBinding,
  reviewerLabel: string,
  fixedSceneConfirmed: boolean,
  templateId?: string,
): Promise<CameraZoneTemplateResult> {
  const payload: Record<string, unknown> = {
    source_digest: sourceDigest,
    result_sha256: resultSha256,
    camera_binding: binding,
    reviewer_label: reviewerLabel,
    // The visitor's ACTUAL confirmation state; the backend requires true and
    // refuses otherwise. Never hardcoded.
    fixed_scene_confirmed: fixedSceneConfirmed,
  };
  if (operation === "apply") payload.template_id = templateId;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(
      `/api/vigilens/fresh-review/${encodeURIComponent(sourceDigest)}/camera-zones/${operation}`,
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload), signal: controller.signal },
    );
    if (!response.ok) return readRefusal(response, "Camera geometry unavailable; exact fixed-scene/raster confirmation required");
    return (await response.json()) as CameraZoneTemplateResult;
  } finally {
    clearTimeout(timeoutId);
  }
}

export type ExplanationResult = Record<string, unknown>;

// User-triggered explanation execution for one exact pre-reserved attempt.
// Backend gates: acked session, exact report review, exact grant. Refuses
// (409/503) when no executor/grant is configured; surfaced as-is, never retried.
export async function executeExplanation(
  session: PrivateDisplaySession,
  assessmentId: string,
  persons: Record<string, PersonReportReview>,
  attemptId: string,
): Promise<ExplanationResult> {
  const payload = {
    assessment_id: assessmentId,
    source_digest: session.source_digest,
    output_sha256: session.output_sha256,
    regions_digest: session.regions_digest,
    persons,
  };
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), 110000);
  try {
    const response = await fetch(
      `/api/vigilens/private-report/${encodeURIComponent(session.session_id)}/explanation/${encodeURIComponent(attemptId)}`,
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload), signal: controller.signal },
    );
    if (response.status >= 500 && response.status !== 503) throw new Error("No definite execution response");
    if (!response.ok) return readRefusal(response, "Explanation refused; no automatic retry");
    return (await response.json()) as ExplanationResult;
  } catch (err) {
    if (err instanceof BackendError) throw err;
    throw new BackendError("Explanation execution status unknown. Check existing report only; do not run again.");
  } finally {
    clearTimeout(timeoutId);
  }
}

// Gated LOCAL report download via the backend's own private-download route -
// never the inline preview blob converted to a file. Refuses (409) while the
// deployment keeps operator download disabled; the refusal surfaces as-is.
export async function fetchPrivateReportDownload(
  session: PrivateDisplaySession,
  assessmentId: string,
  persons: Record<string, PersonReportReview>,
): Promise<Blob> {
  const payload = {
    assessment_id: assessmentId,
    source_digest: session.source_digest,
    output_sha256: session.output_sha256,
    regions_digest: session.regions_digest,
    persons,
  };
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(
      `/api/vigilens/private-report/${encodeURIComponent(session.session_id)}/private-download`,
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload), signal: controller.signal },
    );
    if (!response.ok) return readRefusal(response, "Local report download is not enabled in this deployment; the inline preview is view-only");
    return response.blob();
  } finally {
    clearTimeout(timeoutId);
  }
}

export type RuleReviewConfiguration = {
  format: string;
  policy_id: string;
  version: string;
  scope: "illustrative_demo" | "site_owner_policy";
  camera_id: string;
  approval_reference: string;
  priorities: string[];
  zones: { id: string; name: string; points: unknown; access_mode: "allowed" | "authorised_only" | "no_entry_all"; rules: { id: string; check: "helmet_worn" | "vest_worn" | "access"; priority: string | null }[] }[];
  outside_rules: never[];
};

// Owner-authored rule configuration for the exact saved zones. Nothing is
// defaulted here: the caller passes exactly what the operator entered and the
// backend validates and refuses what it does not accept (no retry).
export async function postRuleReview(
  sourceDigest: string,
  resultSha256: string,
  zonesSha256: string,
  configuration: RuleReviewConfiguration,
): Promise<Record<string, unknown>> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(`/api/vigilens/fresh-review/${encodeURIComponent(sourceDigest)}/rule-review`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ source_digest: sourceDigest, result_sha256: resultSha256, zones_sha256: zonesSha256, configuration }),
      signal: controller.signal,
    });
    if (!response.ok) return readRefusal(response, "Rule configuration unavailable or invalid; no defaults or approval inferred");
    return (await response.json()) as Record<string, unknown>;
  } finally {
    clearTimeout(timeoutId);
  }
}

export type ExplanationReservation = { attempt_id: string; state: string; plan_sha256: string; provider_calls_this_request: number; grant_created_here: boolean };

// Reserve (not run) the exact current explanation plan. Backend needs configured
// rules AND an exact server-side grant for this plan; no grant is made here.
export async function reserveExplanation(
  session: PrivateDisplaySession,
  assessmentId: string,
  persons: Record<string, PersonReportReview>,
): Promise<ExplanationReservation> {
  const payload = { assessment_id: assessmentId, source_digest: session.source_digest, output_sha256: session.output_sha256, regions_digest: session.regions_digest, persons };
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(`/api/vigilens/private-report/${encodeURIComponent(session.session_id)}/explanation-reservation`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (response.status >= 500 && response.status !== 503) throw new Error("No definite reservation response");
    if (!response.ok) return readRefusal(response, "Explanation reservation refused; no automatic retry");
    return (await response.json()) as ExplanationReservation;
  } catch (err) {
    if (err instanceof BackendError) throw err;
    throw new BackendError("Explanation reservation status unknown. Check the existing report; do not reserve again. " + (err instanceof Error ? err.message : ""));
  } finally {
    clearTimeout(timeoutId);
  }
}

export type RecheckPlanView = {
  status: string;
  reason?: string;
  person_id: string;
  plan_sha256?: string;
  request_sha256?: string[];
  max_reserved_usd?: string;
  unknown_items?: unknown;
  executor_configured?: boolean;
  configured_grant_matches_this_plan?: boolean;
  provider_calls_this_request: number;
  reserved_nothing: boolean;
  grant_created_here: boolean;
};

export type RecheckReservationView = { attempt_id: string; state: string; new_reservation: boolean; plan_sha256: string; held_usd: string; provider_calls_this_request: number; grant_created_here: boolean };

async function postRecheckRoute<T>(sourceDigest: string, route: "recheck-plan" | "recheck-reservation", personId: string, fallback: string): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(`/api/vigilens/fresh-review/${encodeURIComponent(sourceDigest)}/${route}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ person_id: personId }),
      signal: controller.signal,
    });
    if (!response.ok) return readRefusal(response, fallback);
    return (await response.json()) as T;
  } finally {
    clearTimeout(timeoutId);
  }
}

// Visible exact plan for one person: hashes only, no booking, no grant, no provider call.
export const fetchRecheckPlan = (sourceDigest: string, personId: string) =>
  postRecheckRoute<RecheckPlanView>(sourceDigest, "recheck-plan", personId, "Recheck plan unavailable; nothing reserved or called");

// Reserve (not run) one attempt. Refused unless the exact pinned grant for this plan exists server-side.
export const reserveRecheck = (sourceDigest: string, personId: string) =>
  postRecheckRoute<RecheckReservationView>(sourceDigest, "recheck-reservation", personId, "Recheck reservation unavailable; nothing reserved or called");

const HEX64_SOURCE = /^[0-9a-f]{64}$/;

// Reopen the caller's OWN stored job by its exact source digest. Stored-only: the
// backend never dispatches, reserves or lists; a miss (unknown digest, other
// account, missing preserved source) is a 409 and nothing is reopened.
export async function reopenStoredAudit(source: string, zones: unknown[] = []): Promise<Audit> {
  const digest = source.trim().toLowerCase();
  if (!HEX64_SOURCE.test(digest)) throw new BackendError("Enter the full 64-character source digest of a job you ran earlier.");
  const formData = new FormData();
  formData.append("zones", JSON.stringify(zones));
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  try {
    const response = await fetch(`/api/vigilens/fresh-review/${digest}/reopen-audit`, { method: "POST", body: formData, signal: controller.signal });
    if (response.status === 403) return readRefusal(response, "Private browser session required");
    if (response.status === 409) throw new BackendError("No stored job with that digest is available to this account. Nothing was reopened and nothing was analysed. No automatic retry.");
    if (!response.ok) return readRefusal(response, "Reopen refused");
    const audit = (await response.json()) as Audit;
    if (!audit || audit.image?.pixel_digest !== digest) throw new BackendError("The server returned a result for a different source. Refusing to use it. No automatic retry.");
    audit.fixture_loaded_at = audit.fixture_loaded_at ?? null;
    audit.fixture_notice = audit.fixture_notice ?? null;
    audit.rechecks = audit.rechecks ?? { status: "not_configured", attempts: [], original_result_unchanged: true };
    for (const person of audit.persons) for (const finding of person.findings) finding.recheck_trace = finding.recheck_trace ?? [];
    return audit;
  } catch (err) {
    if (err instanceof BackendError) throw err;
    if ((err as DOMException)?.name === "AbortError" || err === "timeout") throw new BackendError("Reopen timed out. No automatic retry.");
    throw new BackendError("Could not reach the backend. No automatic retry.");
  } finally {
    clearTimeout(timeoutId);
  }
}
