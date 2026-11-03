import { useEffect, useRef, useState } from "react";
import { postRuleReview, type RuleReviewConfiguration } from "../api/backendClient";

export type SavedZoneSnapshot = { zones_sha256: string; zones: { id: string; name: string; points: unknown }[] };

type Check = "access" | "helmet_worn" | "vest_worn";
type ZoneChoice = { access_mode: "" | "allowed" | "authorised_only" | "no_entry_all"; checks: Partial<Record<Check, boolean>>; priority: Partial<Record<Check, string>> };
const CHECKS: { key: Check; label: string }[] = [
  { key: "access", label: "Entry is prohibited (access rule)" },
  { key: "helmet_worn", label: "Hardhat required" },
  { key: "vest_worn", label: "Reflective vest required" },
];

// Owner-authored rule configuration for the EXACT saved zones. Every field starts
// empty: nothing is defaulted, inferred or pre-approved. A saved configuration is
// structure only (not owner approval, not a safety policy); explanations stay
// gated behind it plus an exact server-side grant.
export function RuleReviewPanel({ sourceDigest, resultSha, snapshot, enabled }: { sourceDigest: string; resultSha: string; snapshot: SavedZoneSnapshot; enabled: boolean }) {
  const [policyId, setPolicyId] = useState("");
  const [version, setVersion] = useState("");
  const [scope, setScope] = useState<"" | "illustrative_demo" | "site_owner_policy">("");
  const [cameraId, setCameraId] = useState("");
  const [approvalReference, setApprovalReference] = useState("");
  const [prioritiesText, setPrioritiesText] = useState("");
  const [zoneChoices, setZoneChoices] = useState<Record<string, ZoneChoice>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; generation.current += 1; };
  }, []);
  // A different source, result or saved geometry invalidates entered choices and any pending call.
  useEffect(() => {
    generation.current += 1;
    setZoneChoices({});
    setBusy(false);
    setMessage(null);
    setError(null);
  }, [sourceDigest, resultSha, snapshot.zones_sha256]);

  const choice = (id: string): ZoneChoice => zoneChoices[id] ?? { access_mode: "", checks: {}, priority: {} };
  const patchZone = (id: string, next: Partial<ZoneChoice>) => {
    setError(null);
    setMessage(null);
    setZoneChoices((prev) => ({ ...prev, [id]: { ...choice(id), ...next } }));
  };
  const priorities = prioritiesText.split(",").map((p) => p.trim()).filter(Boolean);

  const problem = (): string | null => {
    if (!enabled) return "Prepare and acknowledge a treated preview, and save zones, first.";
    if (![policyId, version, cameraId, approvalReference].every((v) => v.trim().length > 0)) return "Policy id, version, camera id and approval reference are yours to enter.";
    if (!scope) return "Choose the scope: illustrative demo or site owner policy.";
    if (new Set(priorities).size !== priorities.length) return "Priority labels must be unique.";
    for (const z of snapshot.zones) {
      const c = choice(z.id);
      if (!c.access_mode) return `Choose the access mode for ${z.name}.`;
      if (c.checks.access && c.access_mode === "allowed") return `${z.name}: an entry-prohibited rule conflicts with allowed entry.`;
      const picked = CHECKS.filter((k) => c.checks[k.key]);
      if (picked.length === 0) return `${z.name}: pick at least one rule, or leave rules to a later configuration.`;
      for (const k of picked) {
        const pr = c.priority[k.key] ?? "";
        if (pr && !priorities.includes(pr)) return `${z.name}: priority "${pr}" is not in your priority list.`;
      }
    }
    return null;
  };

  const submit = async () => {
    const blocked = problem();
    if (blocked) { setError(blocked); return; }
    const token = ++generation.current;
    const live = () => mounted.current && generation.current === token;
    const configuration: RuleReviewConfiguration = {
      format: "vigilens.site-policy.proposal.v1",
      policy_id: policyId.trim(),
      version: version.trim(),
      scope: scope as "illustrative_demo" | "site_owner_policy",
      camera_id: cameraId.trim(),
      approval_reference: approvalReference.trim(),
      priorities,
      zones: snapshot.zones.map((z) => {
        const c = choice(z.id);
        return {
          id: z.id,
          name: z.name,
          points: z.points,
          access_mode: c.access_mode as "allowed" | "authorised_only" | "no_entry_all",
          rules: CHECKS.filter((k) => c.checks[k.key]).map((k) => ({ id: `${z.id}-${k.key}`, check: k.key, priority: c.priority[k.key] ? (c.priority[k.key] as string) : null })),
        };
      }),
      outside_rules: [],
    };
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await postRuleReview(sourceDigest, resultSha, snapshot.zones_sha256, configuration);
      if (!live()) return;
      setMessage("Rule configuration saved for these exact zones. It is your configuration, not an approval or a safety policy; the report now evaluates it.");
    } catch (err) {
      if (!live()) return;
      setError(err instanceof Error && err.message ? err.message : "Rule configuration unavailable");
    } finally {
      if (live()) setBusy(false);
    }
  };

  return (
    <div className="mt-3 rounded border p-2" data-testid="rule-review-panel">
      <h4 className="font-medium">Rules for these saved zones (yours to author)</h4>
      <p className="text-muted-foreground">
        Nothing here is pre-filled or assumed. The report evaluates only what you enter; there are no default safety
        rules. This is configuration for review, not owner approval or a compliance finding.
      </p>
      <div className="mt-1 grid grid-cols-2 gap-1">
        <input aria-label="Policy id" placeholder="Policy id" className="rounded border px-2 py-1" value={policyId} onChange={(e) => { setPolicyId(e.target.value); setError(null); }} />
        <input aria-label="Policy version" placeholder="Version" className="rounded border px-2 py-1" value={version} onChange={(e) => { setVersion(e.target.value); setError(null); }} />
        <input aria-label="Camera id" placeholder="Camera id" className="rounded border px-2 py-1" value={cameraId} onChange={(e) => { setCameraId(e.target.value); setError(null); }} />
        <select aria-label="Scope" className="rounded border px-2 py-1" value={scope} onChange={(e) => { setScope(e.target.value as typeof scope); setError(null); }}>
          <option value="">Choose scope</option>
          <option value="illustrative_demo">Illustrative demo</option>
          <option value="site_owner_policy">Site owner policy</option>
        </select>
        <input aria-label="Approval reference" placeholder="Your approval reference" className="col-span-2 rounded border px-2 py-1" value={approvalReference} onChange={(e) => { setApprovalReference(e.target.value); setError(null); }} />
        <input aria-label="Priority labels" placeholder="Priority labels, comma separated (optional)" className="col-span-2 rounded border px-2 py-1" value={prioritiesText} onChange={(e) => { setPrioritiesText(e.target.value); setError(null); }} />
      </div>
      {snapshot.zones.map((z) => {
        const c = choice(z.id);
        return (
          <div key={z.id} className="mt-2 rounded border p-1">
            <p className="font-medium">{z.name}</p>
            <select aria-label={`Access mode for ${z.name}`} className="rounded border px-2 py-1" value={c.access_mode} onChange={(e) => patchZone(z.id, { access_mode: e.target.value as ZoneChoice["access_mode"] })}>
              <option value="">Choose access mode</option>
              <option value="allowed">Entry allowed</option>
              <option value="authorised_only">Authorised people only</option>
              <option value="no_entry_all">No entry for anyone</option>
            </select>
            {CHECKS.map((k) => (
              <div key={k.key} className="mt-1 flex items-center gap-2">
                <label className="flex items-center gap-1">
                  <input type="checkbox" checked={!!c.checks[k.key]} onChange={(e) => patchZone(z.id, { checks: { ...c.checks, [k.key]: e.target.checked } })} />
                  <span>{k.label}</span>
                </label>
                {c.checks[k.key] && priorities.length > 0 ? (
                  <select aria-label={`Priority for ${k.label} in ${z.name}`} className="rounded border px-1" value={c.priority[k.key] ?? ""} onChange={(e) => patchZone(z.id, { priority: { ...c.priority, [k.key]: e.target.value } })}>
                    <option value="">Unrated</option>
                    {priorities.map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                ) : null}
              </div>
            ))}
          </div>
        );
      })}
      <button type="button" className="mt-2 rounded border px-3 py-1 disabled:opacity-50" disabled={busy || !enabled} onClick={() => void submit()}>
        {busy ? "Saving rules..." : "Save these rules"}
      </button>
      {message ? <p className="mt-1 text-muted-foreground">{message}</p> : null}
      {error ? <p className="mt-1 text-destructive">{error}</p> : null}
    </div>
  );
}
