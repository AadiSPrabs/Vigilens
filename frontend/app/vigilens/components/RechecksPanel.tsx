// Deliberate recheck surface. Display-only: recheck execution stays a per-attempt,
// user-triggered, grant-gated backend ceremony; this panel never retries, never adopts
// a candidate, and never presents one as replacing the original readings.
import type { RecheckAttempt, RecheckSurface } from "../types";

const STATE_LABELS: Record<string, string> = {
  reserved_not_dispatched: "Reserved, not run",
  attempted_uncertain: "Attempted; outcome uncertain - held, no retry",
  completed: "Candidate returned",
};

type ExecuteProps = {
  onExecute?: (attempt: RecheckAttempt) => void;
  executeBlockedReason?: string | null;
  busyAttemptId?: string | null;
  executeError?: string | null;
};

export function RechecksPanel({ rechecks, onExecute, executeBlockedReason, busyAttemptId, executeError }: { rechecks: RecheckSurface } & ExecuteProps) {
  if (rechecks.status === "not_configured") {
    return (
      <section className="rounded-lg border p-3 text-xs text-muted-foreground">
        <h3 className="text-sm font-medium text-foreground">Deliberate rechecks</h3>
        <p>
          Recheck is not configured for this deployment. Unknown readings are not
          re-asked; they stay with human review.
        </p>
      </section>
    );
  }
  return (
    <section className="rounded-lg border p-3 text-xs">
      <h3 className="text-sm font-medium">Deliberate rechecks</h3>
      <p className="text-muted-foreground">
        Separate candidate observations bound to the exact original result. The
        original readings are unchanged; a candidate never replaces them and is never
        adopted automatically. No automatic retry.
      </p>
      {rechecks.attempts.length === 0 ? (
        <p className="text-muted-foreground">No recheck attempts exist for this result.</p>
      ) : (
        <ul className="space-y-2">
          {rechecks.attempts.map((a) => (
            <li key={a.attempt_id} className="rounded border p-2">
              <p>
                Person {a.binding.person_id}: {STATE_LABELS[a.state] ?? a.state}
              </p>
              {a.state === "completed" && a.result ? (
                <p>
                  Candidate reading: helmet {a.result.helmet ?? "not reported"}, vest{" "}
                  {a.result.vest ?? "not reported"}. Requires separate human review;
                  not adopted.
                </p>
              ) : null}
              {a.state === "attempted_uncertain" ? (
                <p>Held as uncertain. The original is unchanged; human review required.</p>
              ) : null}
              <p className="text-muted-foreground">Retry allowed: no. Evidence export: no.</p>
              {a.state === "reserved_not_dispatched" && onExecute ? (
                <div className="mt-1">
                  <button
                    type="button"
                    disabled={busyAttemptId === a.attempt_id || !!executeBlockedReason}
                    onClick={() => onExecute(a)}
                    className="rounded border px-2 py-1 text-xs disabled:opacity-50"
                  >
                    {busyAttemptId === a.attempt_id ? "Running recheck..." : "Run this recheck now"}
                  </button>
                  <p className="mt-1 text-muted-foreground">
                    Runs once against the pinned grant. No automatic retry; the original
                    readings stay unchanged and any result returns as a separate candidate.
                  </p>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {executeError ? <p className="mt-2 text-destructive">{executeError}</p> : null}
    </section>
  );
}
