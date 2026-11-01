import { FIXTURE_AUDITS, SAMPLE_PRESET_ZONES, type SampleId } from "../fixtures/audits";
import { validateAudit, AuditValidationError } from "../validate";
import { analyzeWithBackend, backendConfigured } from "./backendClient";
import type { Audit, Zone } from "../types";

export const FIXTURE_UPLOAD_MESSAGE =
  "Fixture mode only has results for the bundled sample images. Pick a sample, or switch to backend mode.";
export const FIXTURE_ZONES_MESSAGE =
  "Fixture mode only has results for the sample's preset zones. Reset to sample zones, or switch to backend mode.";

const SIMULATED_LATENCY_MS = 800;

export type AnalyzeParams = {
  file?: File | null;
  zones: Zone[];
  sampleId?: SampleId | null;
  signal?: AbortSignal;
};

function abortError() {
  return new DOMException("Analysis cancelled", "AbortError");
}

function sameZones(a: Zone[], b: Zone[]) {
  return JSON.stringify(a.map(zoneKey)) === JSON.stringify(b.map(zoneKey));
}

function zoneKey(z: Zone) {
  return { id: z.id, name: z.name, hazard: z.hazard, points: z.points.map((p) => [p.x, p.y]) };
}

function resolveFixture({ file, zones, sampleId }: AnalyzeParams): Audit {
  if (!sampleId || file) throw new Error(FIXTURE_UPLOAD_MESSAGE);
  const preset = SAMPLE_PRESET_ZONES[sampleId];
  if (!preset || !FIXTURE_AUDITS[sampleId]) throw new Error(FIXTURE_UPLOAD_MESSAGE);
  if (!sameZones(zones, preset)) throw new Error(FIXTURE_ZONES_MESSAGE);
  const audit = structuredClone(FIXTURE_AUDITS[sampleId]);
  return validateAudit(audit);
}

export const BACKEND_NOT_CONFIGURED_MESSAGE =
  "Upload analysis is unavailable because this deployment's backend connection is not configured. Pick a bundled sample instead.";

async function resolveBackend(params: AnalyzeParams): Promise<Audit> {
  const { file, zones, signal } = params;
  if (!file) throw new Error(FIXTURE_UPLOAD_MESSAGE);
  if (!backendConfigured()) throw new Error(BACKEND_NOT_CONFIGURED_MESSAGE);
  const audit = await analyzeWithBackend(file, zones, signal);
  return validateAudit(audit);
}

export function analyzeImage(params: AnalyzeParams): Promise<Audit> {
  const { signal } = params;
  // An uploaded image goes to the governed backend when this install is configured
  // for it; bundled samples keep working offline from fixtures either way.
  if (params.file) {
    if (!backendConfigured()) return Promise.reject(new Error(BACKEND_NOT_CONFIGURED_MESSAGE));
    return resolveBackend(params);
  }
  return new Promise<Audit>((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      try {
        resolve(resolveFixture(params));
      } catch (err) {
        reject(err instanceof AuditValidationError || err instanceof Error ? err : new Error("Analysis failed."));
      }
    }, SIMULATED_LATENCY_MS);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}
