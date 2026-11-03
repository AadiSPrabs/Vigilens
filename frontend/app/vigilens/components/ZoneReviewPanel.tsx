// Operator zone review + reusable camera geometry + configured bounded review
// loop. Every action is user-triggered and backend-gated: exact acknowledged
// preview, exact source/result, exact scene binding. The backend refuses
// (409/503) when configuration is absent; this panel never retries, never
// transfers rules/contacts, and never claims automatic scene verification.
import { useEffect, useRef, useState } from "react";
import { RuleReviewPanel, type SavedZoneSnapshot } from "./RuleReviewPanel";
import type { Audit, Zone } from "../types";
import {
  cameraZoneOperation,
  postZoneReview,
  resultShaFromAuditId,
  runBoundedReviewLoop,
  type BoundedLoopResult,
  type CameraBinding,
  type CameraZoneTemplateResult,
} from "../api/backendClient";

const TEMPLATES_KEY = "vigilens-camera-templates";

type SavedTemplate = { template_id: string; camera_id: string; scene_revision: string; width: number; height: number };

function loadTemplates(): SavedTemplate[] {
  try {
    const raw = localStorage.getItem(TEMPLATES_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (t): t is SavedTemplate =>
        typeof t === "object" && t !== null &&
        typeof (t as SavedTemplate).template_id === "string" &&
        typeof (t as SavedTemplate).camera_id === "string",
    );
  } catch {
    return [];
  }
}

function rememberTemplate(t: SavedTemplate) {
  const list = loadTemplates().filter((x) => x.template_id !== t.template_id);
  list.unshift(t);
  try {
    localStorage.setItem(TEMPLATES_KEY, JSON.stringify(list.slice(0, 16)));
  } catch {
    // Storage full or unavailable: the template still exists server-side; the
    // operator can note the id from the last result message.
  }
}

export function ZoneReviewPanel({ audit, zones, previewReady }: { audit: Audit; zones: Zone[]; previewReady: boolean }) {
  const sourceDigest = audit.image.pixel_digest ?? null;
  const resultSha = resultShaFromAuditId(audit.audit_id);
  const [reviewer, setReviewer] = useState("");
  const [cameraId, setCameraId] = useState("");
  const [sceneRevision, setSceneRevision] = useState("1");
  const [templates, setTemplates] = useState<SavedTemplate[]>(loadTemplates);
  const [selectedTemplate, setSelectedTemplate] = useState("");
  // Real operator confirmation, serialized as-is. Cleared whenever the source
  // or the scene binding inputs change - a stale confirmation never carries
  // over to a different photo or camera claim.
  const [fixedSceneConfirmed, setFixedSceneConfirmed] = useState(false);
  const [confirmedForSource, setConfirmedForSource] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState<CameraZoneTemplateResult | null>(null);
  const [loopResult, setLoopResult] = useState<BoundedLoopResult | null>(null);
  const [savedSnapshot, setSavedSnapshot] = useState<SavedZoneSnapshot | null>(null);
  // Lifecycle guard: pending review/apply/save/loop calls are bound to the
  // EXACT source+result they started with. Unmounting or a source/result
  // change invalidates them - no late state write for a stale photo.
  const generation = useRef(0);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; generation.current += 1; };
  }, []);
  useEffect(() => {
    generation.current += 1;
    setApplied(null);
    setLoopResult(null);
    setSavedSnapshot(null);
    setMessage(null);
    setError(null);
    setBusy(null);
  }, [sourceDigest, resultSha]);
  const live = (token: number) => mounted.current && generation.current === token;

  if (!sourceDigest || !resultSha) return null;
  const sceneConfirmed = fixedSceneConfirmed && confirmedForSource === sourceDigest;

  const blocked = !previewReady ? "Prepare and acknowledge a treated preview before zone review actions." : null;
  const binding = (): CameraBinding => ({
    camera_id: cameraId.trim(),
    scene_revision: sceneRevision.trim(),
    width: audit.image.width,
    height: audit.image.height,
    coordinate_space: "normalized_upright_source_v1",
    transform: "identity",
  });

  // The action receives a staleness check bound to THIS run's token: any state
  // write inside the action (applied geometry, loop result, template list)
  // must go through it - a resolved promise from an old source never lands.
  const run = async (kind: string, action: (isLive: () => boolean) => Promise<string>) => {
    const token = ++generation.current;
    const isLive = () => live(token);
    setBusy(kind);
    setError(null);
    setMessage(null);
    try {
      const text = await action(isLive);
      if (!isLive()) return; // stale: unmounted or source/result changed mid-flight
      setMessage(text);
    } catch (err) {
      if (!isLive()) return;
      setError(err instanceof Error && err.message ? err.message : "Action unavailable");
    } finally {
      if (isLive()) setBusy(null);
    }
  };

  const saveZones = () =>
    run("zones", async (isLive) => {
      const saved = await postZoneReview(sourceDigest, resultSha, zones, reviewer.trim());
      const snap = (saved as { zone_snapshot?: { zones_sha256?: unknown; zones?: unknown } | null }).zone_snapshot;
      if (isLive() && snap && typeof snap.zones_sha256 === "string" && Array.isArray(snap.zones)) {
        setSavedSnapshot({ zones_sha256: snap.zones_sha256, zones: snap.zones as SavedZoneSnapshot["zones"] });
      }
      return "Zones saved for this exact photo and result. They are review geometry, not a safety policy.";
    });

  const saveTemplate = () =>
    run("save", async (isLive) => {
      const result = await cameraZoneOperation("save", sourceDigest, resultSha, binding(), reviewer.trim(), sceneConfirmed);
      const id = typeof result.template_id === "string" ? result.template_id : "";
      if (id && isLive()) {
        const entry: SavedTemplate = { template_id: id, camera_id: cameraId.trim(), scene_revision: sceneRevision.trim(), width: audit.image.width, height: audit.image.height };
        rememberTemplate(entry);
        setTemplates(loadTemplates());
      }
      return `Camera template saved (${id || "id returned by backend"}). Scene equivalence is your claim; nothing was verified automatically.`;
    });

  const applyTemplate = () =>
    run("apply", async (isLive) => {
      const result = await cameraZoneOperation("apply", sourceDigest, resultSha, binding(), reviewer.trim(), sceneConfirmed, selectedTemplate);
      if (isLive()) setApplied(result);
      return "Template applied to this photo's server-side zone review; the applied geometry and review are shown below.";
    });

  const runLoop = () =>
    run("loop", async (isLive) => {
      const result = await runBoundedReviewLoop(sourceDigest, resultSha);
      if (isLive()) setLoopResult(result);
      const status = typeof result.status === "string" ? result.status : "unknown";
      return status === "no_initial_unknown_recheck_not_needed"
        ? "No initial-unknown person needed a recheck; the loop made no calls."
        : "Loop response received; attempt states are shown below. Candidates stay separate; original readings are unchanged.";
    });

  return (
    <section className="rounded-lg border p-3 text-xs">
      <h3 className="text-sm font-medium">Zone review and camera reuse</h3>
      <p className="text-muted-foreground">
        Persist the drawn zones for this exact photo, optionally save them as a
        reusable camera template, or run the configured bounded review loop.
        Scene equivalence is your claim - there is no automatic registration,
        and rules or contacts never transfer.
      </p>
      {blocked ? <p className="mt-2 text-muted-foreground">{blocked}</p> : null}
      <label className="mt-2 flex items-center gap-2">
        <span>Reviewer label</span>
        <input
          className="w-48 rounded border px-2 py-1"
          value={reviewer}
          onChange={(e) => setReviewer(e.target.value)}
          maxLength={80}
          placeholder="who is reviewing"
          disabled={busy !== null}
        />
      </label>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="rounded border px-3 py-1 font-medium disabled:opacity-50"
          disabled={busy !== null || blocked !== null || zones.length === 0 || reviewer.trim().length === 0}
          onClick={saveZones}
        >
          {busy === "zones" ? "Saving..." : "Save zones for this photo"}
        </button>
        <button
          type="button"
          className="rounded border px-3 py-1 font-medium disabled:opacity-50"
          disabled={busy !== null || blocked !== null}
          onClick={runLoop}
        >
          {busy === "loop" ? "Running..." : "Run configured bounded review loop"}
        </button>
      </div>
      <div className="mt-3 flex flex-col gap-2">
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={sceneConfirmed}
            onChange={(e) => {
              setFixedSceneConfirmed(e.target.checked);
              setConfirmedForSource(e.target.checked ? sourceDigest : null);
            }}
            disabled={busy !== null}
          />
          <span>
            I confirm this photo is the same fixed camera scene, at the same
            upright resolution, with no crop, rotation or camera move. This is
            my claim - nothing verifies it automatically.
          </span>
        </label>
        <div className="flex flex-wrap items-center gap-2">
        <input
          className="w-36 rounded border px-2 py-1"
          value={cameraId}
          onChange={(e) => {
            setCameraId(e.target.value);
            setFixedSceneConfirmed(false);
          }}
          maxLength={80}
          placeholder="camera id"
          disabled={busy !== null}
        />
        <input
          className="w-24 rounded border px-2 py-1"
          value={sceneRevision}
          onChange={(e) => {
            setSceneRevision(e.target.value);
            setFixedSceneConfirmed(false);
          }}
          maxLength={80}
          placeholder="scene rev"
          disabled={busy !== null}
        />
        <button
          type="button"
          className="rounded border px-3 py-1 font-medium disabled:opacity-50"
          disabled={busy !== null || blocked !== null || !sceneConfirmed || cameraId.trim().length === 0 || reviewer.trim().length === 0}
          onClick={saveTemplate}
        >
          {busy === "save" ? "Saving..." : "Save as camera template"}
        </button>
        </div>
      </div>
      {templates.length > 0 ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select
            className="rounded border px-2 py-1"
            value={selectedTemplate}
            onChange={(e) => setSelectedTemplate(e.target.value)}
            disabled={busy !== null}
          >
            <option value="">Choose a saved template</option>
            {templates.map((t) => (
              <option key={t.template_id} value={t.template_id}>
                {t.camera_id} rev {t.scene_revision} ({t.width}x{t.height})
              </option>
            ))}
          </select>
          <button
            type="button"
            className="rounded border px-3 py-1 font-medium disabled:opacity-50"
            disabled={busy !== null || blocked !== null || !sceneConfirmed || selectedTemplate === "" || cameraId.trim().length === 0 || reviewer.trim().length === 0}
            onClick={applyTemplate}
          >
            {busy === "apply" ? "Applying..." : "Apply template to this photo"}
          </button>
        </div>
      ) : null}
      {applied ? (
        <div className="mt-3 rounded border p-2">
          <p className="font-medium">Applied template geometry (server zone review)</p>
          <p className="mt-1 text-muted-foreground">
            {Array.isArray(applied.template?.zones) ? applied.template.zones.length : 0} zone(s) applied.
            Rules and contacts were not transferred; scene equivalence was your
            confirmation, not an automatic verification.
          </p>
          {Array.isArray(applied.template?.zones) ? (
            <ul className="mt-1 list-disc pl-4 text-muted-foreground">
              {applied.template.zones.map((z) => (
                <li key={z.id}>
                  {z.name || z.id}
                  {z.hazard ? " (hazard)" : ""}
                  {Array.isArray(z.points) && z.points.length > 0
                    ? ` - ${z.points.length} polygon points: ` +
                      z.points.map((pt) => `(${Number(pt.x).toFixed(3)}, ${Number(pt.y).toFixed(3)})`).join(" ")
                    : " - no polygon points returned"}
                </li>
              ))}
            </ul>
          ) : null}
          {applied.zone_review !== undefined && applied.zone_review !== null ? (
            <pre className="mt-1 max-h-32 overflow-auto rounded bg-muted p-2 text-[10px] text-muted-foreground">
              {"zone_review (verbatim from backend): " + JSON.stringify(applied.zone_review, null, 1)}
            </pre>
          ) : null}
          <p className="mt-1 text-muted-foreground">
            The headline findings above still reflect the zones posted at upload.
            This review geometry is visible here and in the gated private report;
            it does not rewrite the current audit.
          </p>
        </div>
      ) : null}
      {loopResult ? (
        <div className="mt-3 rounded border p-2">
          <p className="font-medium">Bounded review loop result</p>
          <p className="mt-1 text-muted-foreground">
            Status: {String(loopResult.status ?? "unknown")}.
            {Array.isArray(loopResult.unattempted_unknown_person_ids) && loopResult.unattempted_unknown_person_ids.length > 0
              ? ` Unresolved without attempt: ${loopResult.unattempted_unknown_person_ids.join(", ")}.`
              : ""}
          </p>
          {Array.isArray(loopResult.attempts) && loopResult.attempts.length > 0 ? (
            <ul className="mt-1 list-disc pl-4 text-muted-foreground">
              {loopResult.attempts.map((a, i) => {
                const attempt = a as { person_id?: string; attempt_id?: string; state?: string };
                return (
                  <li key={attempt.attempt_id ?? i}>
                    Person {attempt.person_id ?? "?"}: {attempt.state ?? "state not returned"}
                    {attempt.state !== "completed" ? " - held, no retry" : " - candidate returned, needs human review"}
                    {(attempt as { candidate?: unknown }).candidate !== undefined && (attempt as { candidate?: unknown }).candidate !== null ? (
                      <pre className="mt-1 max-h-32 overflow-auto rounded bg-muted p-2 text-[10px]">
                        {"candidate observations (separate, original unchanged): " + JSON.stringify((attempt as { candidate?: unknown }).candidate, null, 1)}
                      </pre>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-1 text-muted-foreground">No attempts ran.</p>
          )}
          <p className="mt-1 text-muted-foreground">
            Candidates are separate observations shown above; the original
            readings and the recheck list are unchanged. Completed candidates
            and unresolved unknowns need your review - nothing is adopted
            automatically.
          </p>
        </div>
      ) : null}
      {savedSnapshot ? <RuleReviewPanel sourceDigest={sourceDigest} resultSha={resultSha} snapshot={savedSnapshot} enabled={previewReady} /> : null}
      {message ? <p className="mt-2 text-muted-foreground">{message}</p> : null}
      {error ? <p className="mt-2 text-destructive">{error}</p> : null}
    </section>
  );
}
