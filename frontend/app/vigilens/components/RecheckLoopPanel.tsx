// Normal-UI control for the bounded recheck loop: see the exact plan, reserve it only when the
// server holds the exact grant for that plan, then run the reserved attempt. This page never creates a
// grant. Every step is explicit; there is no automatic retry and no candidate is adopted.
import { useState } from "react";
import {
  fetchRecheckPlan,
  reserveRecheck,
  runBoundedReviewLoop,
  type BoundedLoopResult,
  type RecheckPlanView,
} from "../api/backendClient";

type Loop = { status?: string; attempt_count?: number; unknown_person_ids?: string[]; blocked_until?: string; note?: string };

export function RecheckLoopPanel({ sourceDigest, resultSha, loop, onChanged }: { sourceDigest: string; resultSha: string; loop: Loop; onChanged: () => void }) {
  const [plans, setPlans] = useState<Record<string, RecheckPlanView>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loopResult, setLoopResult] = useState<BoundedLoopResult | null>(null);
  const unknown = loop.unknown_person_ids ?? [];
  const ready = loop.status === "ready_reserved_attempts";

  const act = async (key: string, fn: () => Promise<string>) => {
    if (busy) return;
    setBusy(key);
    setMessage(null);
    try {
      setMessage(await fn());
    } catch (err) {
      setMessage(err instanceof Error && err.message ? err.message : "Refused; nothing reserved or called");
    } finally {
      setBusy(null);
    }
  };

  const showPlan = (person: string) =>
    act("plan:" + person, async () => {
      const plan = await fetchRecheckPlan(sourceDigest, person);
      setPlans((p) => ({ ...p, [person]: plan }));
      return plan.status === "planned_requires_exact_grant" ? `Plan for person ${person} shown. Nothing reserved, no call made.` : `No recheck plan for person ${person}: ${plan.reason ?? plan.status}.`;
    });

  const reserve = (person: string) =>
    act("reserve:" + person, async () => {
      const r = await reserveRecheck(sourceDigest, person);
      onChanged();
      return `Reserved ${r.held_usd} USD ceiling for person ${person} (${r.new_reservation ? "new hold" : "already reserved"}). Provider calls made: ${r.provider_calls_this_request}. Run it below.`;
    });

  const run = () =>
    act("loop", async () => {
      const result = await runBoundedReviewLoop(sourceDigest, resultSha);
      setLoopResult(result);
      onChanged();
      return "Loop response received. Candidates stay separate; original readings are unchanged. No retry.";
    });

  return (
    <div className="mt-2 rounded border p-2" data-testid="recheck-loop">
      <p className="font-medium">Bounded recheck loop</p>
      {ready ? (
        <p className="mt-1 text-muted-foreground">{loop.attempt_count} reserved attempt(s) are ready. Running makes the approved provider calls for exactly those attempts, once, with no retry.</p>
      ) : (
        <p className="mt-1 text-muted-foreground" data-testid="recheck-loop-blocked">
          Blocked: {loop.blocked_until ?? "no reserved attempt for this photo"}. {loop.note ?? ""}
        </p>
      )}
      {unknown.length === 0 ? (
        <p className="mt-1 text-muted-foreground">No person has an unknown helmet or vest reading, so no recheck is needed.</p>
      ) : (
        unknown.map((person) => {
          const plan = plans[person];
          const planned = plan?.status === "planned_requires_exact_grant";
          return (
            <div key={person} className="mt-1 rounded border p-2">
              <p>Person {person}: helmet or vest reading unknown.</p>
              <button type="button" className="mt-1 rounded border px-3 py-1 disabled:opacity-50" disabled={busy !== null} onClick={() => void showPlan(person)}>
                {busy === "plan:" + person ? "Loading plan..." : "Show exact recheck plan"}
              </button>
              {planned ? (
                <div className="mt-1 text-muted-foreground">
                  <p>
                    Plan sha256 <code className="break-all">{plan.plan_sha256}</code>. Two crop requests, ceiling {plan.max_reserved_usd} USD held on reserve. Crop pixels are never shown here.
                  </p>
                  <p data-testid="grant-state">
                    {plan.configured_grant_matches_this_plan
                      ? "The server holds the exact approval for this plan. You can reserve it."
                      : "No exact approval for this plan is configured on the server. Approving this plan and ceiling in chat is the next step; reserve stays disabled until then."}
                  </p>
                  <button
                    type="button"
                    className="mt-1 rounded border px-3 py-1 disabled:opacity-50"
                    disabled={busy !== null || !plan.configured_grant_matches_this_plan}
                    onClick={() => void reserve(person)}
                  >
                    {busy === "reserve:" + person ? "Reserving..." : "Reserve this exact plan (no call yet)"}
                  </button>
                </div>
              ) : plan ? (
                <p className="mt-1 text-muted-foreground">No plan: {plan.reason ?? plan.status}.</p>
              ) : null}
            </div>
          );
        })
      )}
      <button type="button" className="mt-2 rounded border px-3 py-1 disabled:opacity-50" disabled={busy !== null || !ready} onClick={() => void run()}>
        {busy === "loop" ? "Running reserved attempts..." : "Run reserved attempts (once, no retry)"}
      </button>
      {message ? <p className="mt-1" role="status">{message}</p> : null}
      {loopResult && Array.isArray(loopResult.attempts) ? (
        <ul className="mt-1 text-muted-foreground">
          {(loopResult.attempts as { person_id?: string; state?: string }[]).map((a, i) => (
            <li key={i}>Person {a.person_id ?? "?"}: {a.state ?? "state not returned"}; candidate needs separate human review, never adopted.</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
