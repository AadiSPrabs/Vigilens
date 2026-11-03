// Private masked report (PDF preview). The backend renders the TREATED preview
// image (the one the visitor prepared and acknowledged in the preview ceremony),
// never the original upload. Every gate stays server-side: exact acked session,
// exact per-person review, no export. This panel never retries a refusal and
// never presents the PDF as released evidence.
import { useEffect, useRef, useState } from "react";
import type { Audit, PrivateDisplaySession } from "../types";
import {
  executeExplanation, reserveExplanation,
  fetchIntegrationContract,
  fetchPrivatePdfPreview,
  fetchPrivateReport,
  fetchPrivateReportDownload,
  type PersonReportReview,
  type PrivateReportDocument,
} from "../api/backendClient";

const UNCHECKED: PersonReportReview = {
  exact_source_confirmed: false,
  face_coverage_checked: false,
  head_evidence_visible: false,
  torso_evidence_visible: false,
};

const FIELD_LABELS: Array<{ key: keyof PersonReportReview; label: string }> = [
  { key: "exact_source_confirmed", label: "This is the exact photo I reviewed" },
  { key: "face_coverage_checked", label: "I checked face coverage on this person" },
  { key: "head_evidence_visible", label: "Head evidence is visible" },
  { key: "torso_evidence_visible", label: "Torso evidence is visible" },
];

export function PrivateReportPanel({ audit, session }: { audit: Audit; session: PrivateDisplaySession }) {
  const [reviews, setReviews] = useState<Record<string, PersonReportReview>>(() =>
    Object.fromEntries(audit.persons.map((person) => [person.id, { ...UNCHECKED }])),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [explainBusy, setExplainBusy] = useState<string | null>(null);
  const [explainError, setExplainError] = useState<string | null>(null);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [downloadNote, setDownloadNote] = useState<string | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);

  const toggle = (personId: string, key: keyof PersonReportReview) => {
    setReviews((current) => {
      const existing = current[personId] ?? { ...UNCHECKED };
      return { ...current, [personId]: { ...existing, [key]: !existing[key] } };
    });
    setDone(false);
  };

  const [report, setReport] = useState<PrivateReportDocument | null>(null);

  // Lifecycle guard: an in-flight generate() is bound to the EXACT session and
  // source it started with. Unmounting, or the ceremony producing a different
  // session/source, invalidates it - no late report request, PDF request or
  // preview window may happen for a stale generation. The backend would refuse
  // a mismatched session, but the UI must not issue the calls at all.
  const generation = useRef(0);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      generation.current += 1;
    };
  }, []);
  useEffect(() => {
    generation.current += 1;
    setReport(null);
    setDone(false);
    setError(null);
    setBusy(false);
    setExplainBusy(null);
    setExplainError(null);
    setDownloadBusy(false);
    setDownloadNote(null);
    setPdfUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return null;
    });
  }, [session.session_id, session.source_digest]);
  const live = (token: number, sessionId: string, sourceDigest: string) =>
    mounted.current &&
    generation.current === token &&
    session.session_id === sessionId &&
    session.source_digest === sourceDigest;

  const generate = async () => {
    const token = ++generation.current;
    const sessionId = session.session_id;
    const sourceDigest = session.source_digest;
    setBusy(true);
    setError(null);
    try {
      const contract = await fetchIntegrationContract(sourceDigest);
      if (!live(token, sessionId, sourceDigest)) return;
      // Build the gated report document first: it carries the explanation and
      // rule-review sections the visitor should see before any PDF exists.
      const reportDocument = await fetchPrivateReport(session, contract.assessment_id, reviews);
      if (!live(token, sessionId, sourceDigest)) return;
      setReport(reportDocument);
      const blob = await fetchPrivatePdfPreview(session, contract.assessment_id, reviews);
      if (!live(token, sessionId, sourceDigest)) return;
      // The backend sends this PDF as an INLINE private preview
      // (Content-Disposition: inline, X-Vigilens-Export-Allowed: false). We
      // keep it as an in-page prepared link the operator clicks - a window.open
      // after network awaits is popup-blocked and its "opened" claim would be
      // false. Never converted to a download here.
      const url = URL.createObjectURL(blob);
      setPdfUrl((old) => {
        if (old) URL.revokeObjectURL(old);
        return url;
      });
      setDone(true);
    } catch (err) {
      if (!live(token, sessionId, sourceDigest)) return;
      setReport(null);
      setError(err instanceof Error && err.message ? err.message : "Private PDF preview unavailable");
    } finally {
      if (live(token, sessionId, sourceDigest)) setBusy(false);
    }
  };

  // User-triggered execution of one exact pre-reserved explanation attempt.
  // The backend re-runs every report gate plus the attempt's exact grant and
  // refuses (409/503) when nothing is configured; the refusal is shown as-is
  // and never retried. Afterwards the gated report is refetched so the shown
  // attempt state/commentary review reflects the backend's current record.
  // Reserve (not run) the exact current explanation plan. The backend needs
  // configured rules and an exact server-side grant for this plan sha; it creates
  // no grant and makes no provider call. Refusal is shown as-is, never retried.
  const reservePlan = async () => {
    if (busy || explainBusy || downloadBusy) return;
    const token = ++generation.current;
    const sessionId = session.session_id;
    const sourceDigest = session.source_digest;
    setExplainBusy("reserve");
    setExplainError(null);
    try {
      const contract = await fetchIntegrationContract(sourceDigest);
      if (!live(token, sessionId, sourceDigest)) return;
      await reserveExplanation(session, contract.assessment_id, reviews);
      if (!live(token, sessionId, sourceDigest)) return;
      const refreshed = await fetchPrivateReport(session, contract.assessment_id, reviews);
      if (!live(token, sessionId, sourceDigest)) return;
      setReport(refreshed);
    } catch (err) {
      if (!live(token, sessionId, sourceDigest)) return;
      setExplainError(err instanceof Error && err.message ? err.message : "Explanation reservation unavailable");
    } finally {
      if (live(token, sessionId, sourceDigest)) setExplainBusy(null);
    }
  };

  const runExplanation = async (attemptId: string) => {
    if (busy || explainBusy || downloadBusy) return;
    const token = ++generation.current;
    const sessionId = session.session_id;
    const sourceDigest = session.source_digest;
    setExplainBusy(attemptId);
    setExplainError(null);
    try {
      const contract = await fetchIntegrationContract(sourceDigest);
      if (!live(token, sessionId, sourceDigest)) return;
      await executeExplanation(session, contract.assessment_id, reviews, attemptId);
      if (!live(token, sessionId, sourceDigest)) return;
      const refreshed = await fetchPrivateReport(session, contract.assessment_id, reviews);
      if (!live(token, sessionId, sourceDigest)) return;
      setReport(refreshed);
    } catch (err) {
      if (!live(token, sessionId, sourceDigest)) return;
      setExplainError(err instanceof Error && err.message ? err.message : "Explanation unavailable or not configured");
    } finally {
      if (live(token, sessionId, sourceDigest)) setExplainBusy(null);
    }
  };

  // Gated local download: the backend's own private-download route is the
  // only sanctioned preview-to-file path. While this deployment keeps operator
  // download disabled it refuses (409) and the refusal is shown as-is; the
  // inline preview blob is never converted into a file here. Saving to the
  // operator's own machine is distinct from sending - no share/send path exists.
  const downloadLocal = async () => {
    if (busy || downloadBusy || explainBusy) return;
    const token = ++generation.current;
    const sessionId = session.session_id;
    const sourceDigest = session.source_digest;
    setDownloadBusy(true);
    setDownloadNote(null);
    setError(null);
    try {
      const contract = await fetchIntegrationContract(sourceDigest);
      if (!live(token, sessionId, sourceDigest)) return;
      const blob = await fetchPrivateReportDownload(session, contract.assessment_id, reviews);
      if (!live(token, sessionId, sourceDigest)) return;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "vigilens-private-operator-preview.pdf";
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
      setDownloadNote("Saved through the gated local-download route. The file is marked private operator preview, not certified safe to share.");
    } catch (err) {
      if (!live(token, sessionId, sourceDigest)) return;
      setDownloadNote(err instanceof Error && err.message ? err.message : "Local report download unavailable");
    } finally {
      if (live(token, sessionId, sourceDigest)) setDownloadBusy(false);
    }
  };

  return (
    <section className="rounded-lg border p-3 text-xs">
      <h3 className="text-sm font-medium">Private masked report (PDF)</h3>
      <p className="text-muted-foreground">
        Builds a private PDF from the treated preview you acknowledged - the masked
        image, never the original upload. It opens inline for inspection: export
        stays off and there is no send/share path in this build. Masking is your
        review, not a guarantee every face is covered.
      </p>
      <div className="mt-2 flex flex-col gap-3">
        {audit.persons.map((person) => (
          <fieldset key={person.id} className="rounded border p-2">
            <legend className="px-1 font-medium">Person {person.id}</legend>
            {FIELD_LABELS.map(({ key, label }) => (
              <label key={key} className="mt-1 flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={reviews[person.id]?.[key] ?? false}
                  onChange={() => toggle(person.id, key)}
                  disabled={busy}
                />
                <span>{label}</span>
              </label>
            ))}
          </fieldset>
        ))}
      </div>
      <button
        type="button"
        className="mt-3 rounded border px-3 py-1 font-medium disabled:opacity-50"
        onClick={generate}
        disabled={busy || explainBusy !== null || downloadBusy}
      >
        {busy ? "Building PDF..." : "Generate private PDF preview"}
      </button>
      {report ? (
        <div className="mt-3 rounded border p-2">
          <p className="font-medium">Report sections</p>
          <p className="mt-1 text-muted-foreground">
            Report status: {report.status ?? "unknown"}. Exports stay off
            (evidence_export_allowed: {String(report.evidence_export_allowed ?? false)}).
          </p>
          <p className="mt-1 text-muted-foreground">
            Spatial explanations (Muse commentary):{" "}
            {report.spatial_explanations?.status === "model_commentary_requires_human_review"
              ? `${report.spatial_explanations.attempts?.length ?? 0} commentary attempt(s) attached - model text is unvalidated, deterministic fields unchanged, human review required.`
              : "not configured for this deployment. The report shows deterministic rule results only; no model commentary was added."}
          </p>
          {(report.spatial_explanations?.attempts ?? []).map((a) => {
            const attempt = a as {
              attempt_id?: string;
              state?: string;
              result?: { explanations?: { finding_key?: string; model_commentary?: string }[] };
              content_review?: { status?: string; notice?: string; flagged_finding_keys?: string[] };
            };
            const attemptId = String(attempt.attempt_id ?? "");
            const commentaryRows = attempt.result?.explanations ?? [];
            return (
              <div key={attemptId} className="mt-2 rounded border p-2">
                <p className="text-muted-foreground">
                  Attempt {attemptId.slice(0, 12)} - state: {attempt.state ?? "unknown"}; no retry allowed.
                </p>
                {commentaryRows.length > 0 ? (
                  <div className="mt-1 space-y-1">
                    {commentaryRows.map((row, i) => (
                      <p key={i} className="text-muted-foreground">
                        <span className="font-medium text-foreground">{row.finding_key ?? "finding"}:</span>{" "}
                        {row.model_commentary ?? "(no commentary returned)"}
                      </p>
                    ))}
                  </div>
                ) : (
                  <p className="mt-1 text-muted-foreground">No commentary returned for this attempt yet.</p>
                )}
                {attempt.content_review ? (
                  <p className="mt-1 text-muted-foreground">
                    Content review: {attempt.content_review.status ?? "unvalidated"}.{" "}
                    {attempt.content_review.notice ?? ""}
                  </p>
                ) : null}
                <p className="mt-1 text-muted-foreground">
                  Model commentary is unvalidated: never accepted as accurate and never
                  rewrites the deterministic readings above. Compare it against the source photo.
                </p>
                {attempt.state === "reserved_not_dispatched" ? (
                  <button
                    type="button"
                    className="mt-1 rounded border px-3 py-1 disabled:opacity-50"
                    disabled={busy || explainBusy !== null}
                    onClick={() => void runExplanation(attemptId)}
                  >
                    {explainBusy === attemptId ? "Running explanation..." : "Run this exact explanation attempt"}
                  </button>
                ) : null}
              </div>
            );
          })}
          {report.spatial_explanations?.exact_plan_sha256 && !(report.spatial_explanations.attempts ?? []).length ? (
            <div className="mt-1">
              <p className="text-muted-foreground">
                Rules are configured, so an explanation can be requested for this exact plan (plan sha256{" "}
                <code className="break-all">{report.spatial_explanations.exact_plan_sha256}</code>). It runs only under an
                exact server-side grant for that plan, which this page cannot create. Reserving makes no provider call.
              </p>
              <button type="button" className="mt-1 rounded border px-3 py-1 disabled:opacity-50" disabled={busy || explainBusy !== null} onClick={() => void reservePlan()}>
                {explainBusy === "reserve" ? "Reserving..." : "Reserve this exact explanation (no call yet)"}
              </button>
            </div>
          ) : null}
          {explainError ? <p className="mt-1 text-destructive">{explainError}</p> : null}
          <p className="mt-1 text-muted-foreground">
            Configured rule review: {report.configured_rule_review?.status ?? "not evaluated"}.
          </p>
          {(() => {
            // Real v6.2 recheck_view contract: attempt_id/state/result +
            // binding.person_id; candidate observations live in `result`.
            const dr = (report as { deliberate_rechecks?: { status?: string; attempts?: { attempt_id?: string; state?: string; result?: unknown; binding?: { person_id?: string }; candidate_adoption?: string }[]; original_result_unchanged?: boolean } }).deliberate_rechecks;
            if (!dr) return null;
            return (
              <div className="mt-2 rounded border p-2">
                <p className="text-muted-foreground">
                  Deliberate rechecks: {dr.status ?? "unknown"}; original result unchanged: {String(dr.original_result_unchanged ?? true)}.
                </p>
                {(dr.attempts ?? []).map((a, i) => (
                  <div key={a.attempt_id ?? i} className="mt-1">
                    <p className="text-muted-foreground">
                      Person {a.binding?.person_id ?? "?"}: {a.state ?? "state not returned"};{" "}
                      {a.candidate_adoption === "requires_separate_human_review" ? "candidate needs separate human review, never adopted automatically." : ""}
                    </p>
                    {a.result !== undefined && a.result !== null ? (
                      <pre className="mt-1 max-h-32 overflow-auto rounded bg-muted p-2 text-[10px] text-muted-foreground">
                        {"candidate observations (separate; original readings unchanged): " + JSON.stringify(a.result, null, 1)}
                      </pre>
                    ) : null}
                  </div>
                ))}
              </div>
            );
          })()}
          {report.notice ? <p className="mt-1 text-muted-foreground">{String(report.notice)}</p> : null}
        </div>
      ) : null}
      {done && pdfUrl ? (
        <p className="mt-2">
          <a href={pdfUrl} target="_blank" rel="noopener" className="font-medium underline">
            Open the prepared inline PDF preview
          </a>
        </p>
      ) : null}
      {done ? (
        <p className="mt-2 text-muted-foreground">
          The preview opens inline, marked private preview, not released
          evidence. Your browser can still save or print what it displays - the
          markings and the unvalidated-observation labels travel with it. The
          sanctioned file path is the gated download route below; sending or
          sharing a report has no path in this build.
        </p>
      ) : null}
      <div className="mt-2">
        <button
          type="button"
          className="rounded border px-3 py-1 disabled:opacity-50"
          onClick={downloadLocal}
          disabled={busy || downloadBusy || explainBusy !== null}
        >
          {downloadBusy ? "Requesting gated download..." : "Save a local copy (gated download route)"}
        </button>
        {downloadNote ? <p className="mt-1 text-muted-foreground">{downloadNote}</p> : null}
      </div>
      {error ? <p className="mt-2 text-destructive">{error}</p> : null}
    </section>
  );
}
