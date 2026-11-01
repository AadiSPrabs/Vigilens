// Backend adapter: the UI never calls a provider API itself, and never talks to
// the Vigilens backend directly. Uploads go to the same-origin server proxy at
// /api/vigilens/*, which requires the user's login session and attaches the
// backend token and the server-derived display session there. No credential of
// any kind is baked into this bundle. Refused/held responses surface as-is and
// are never retried automatically by this client.
import type { Audit, Zone } from "../types";

const BACKEND_ENDPOINT = "/api/vigilens/fresh-review-audit-governed";
const HEALTH_ENDPOINT = "/api/vigilens/health";
const TIMEOUT_MS = 60000;

export class BackendError extends Error {
  noRetry = true;
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
    return res.ok;
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
  const timeoutId = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
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
          throw new BackendError(
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
    for (const person of audit.persons) {
      for (const finding of person.findings) {
        finding.recheck_trace = finding.recheck_trace ?? [];
      }
    }
    return audit;
  } catch (err) {
    if (err instanceof BackendError) throw err;
    if ((err as DOMException)?.name === "AbortError" || err === "timeout") {
      throw new Error("No response yet; the audit may still be running.");
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
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
