// Manual ground-contact claims. A claim is the operator's own statement, made on the treated copy, that one
// mapped person's boots or feet touch the ground at a marked point. The app never estimates contact itself and
// the claim is not a safety, zone or compliance finding. Unmapped people cannot take a claim. The backend
// additionally refuses a point outside that person's detected foreground and records nothing in that case.
import { useEffect, useRef, useState, type MouseEvent } from "react";
import { clientToNormalized } from "../geometry";
import { personMappings } from "../format";
import { postContactClaim, privateDisplayImageUrl } from "../api/backendClient";
import type { Audit, PrivateDisplaySession } from "../types";

const CLAIM_TTL_MINUTES = 30;

export function ContactClaimPanel({ audit, session }: { audit: Audit; session: PrivateDisplaySession }) {
  const mappings = personMappings(audit.persons);
  const mapped = audit.persons.filter((p) => mappings.get(p.id)?.mapped);
  const [personId, setPersonId] = useState<string>("");
  const [point, setPoint] = useState<{ x: number; y: number } | null>(null);
  const [exact, setExact] = useState(false);
  const [boots, setBoots] = useState(false);
  const [reviewer, setReviewer] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recorded, setRecorded] = useState<Record<string, { x: number; y: number }>>({});
  const imgRef = useRef<HTMLImageElement>(null);
  const generation = useRef(0);
  useEffect(() => {
    generation.current += 1;
    setPoint(null);
    setExact(false);
    setBoots(false);
    setMessage(null);
    setError(null);
    setRecorded({});
    setPersonId("");
    setBusy(false);
  }, [session.session_id, session.source_digest]);

  const selected = audit.persons.find((p) => p.id === personId && mappings.get(p.id)?.mapped);
  const insideOutline = (x: number, y: number) => {
    if (!selected) return false;
    const xs = selected.polygon.map((q) => q.x);
    const ys = selected.polygon.map((q) => q.y);
    return x >= Math.min(...xs) && x <= Math.max(...xs) && y >= Math.min(...ys) && y <= Math.max(...ys);
  };

  const onImageClick = (e: MouseEvent<HTMLDivElement>) => {
    if (!selected || !imgRef.current) return;
    const p = clientToNormalized(e.clientX, e.clientY, imgRef.current.getBoundingClientRect());
    setMessage(null);
    if (!p) return;
    if (!insideOutline(p.x, p.y)) {
      setPoint(null);
      setError(`Click inside the outline of ${mappings.get(selected.id)?.label}. A point outside it is not accepted.`);
      return;
    }
    setError(null);
    setPoint(p);
  };

  const canSave = !busy && !!selected && !!point && exact && boots && reviewer.trim().length >= 1 && reviewer.trim().length <= 80;

  const save = async () => {
    if (!selected || !point || !canSave) return;
    const token = ++generation.current;
    const sourceDigest = session.source_digest;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await postContactClaim(sourceDigest, {
        personId: selected.id,
        point,
        exactSourceConfirmed: exact,
        bootsGroundVisible: boots,
        reviewerLabel: reviewer.trim(),
      });
      if (generation.current !== token) return;
      setRecorded((r) => ({ ...r, [selected.id]: point }));
      setMessage(
        `Contact claim recorded for ${mappings.get(selected.id)?.label} (backend id ${selected.id}). It is your claim, not an automatic reading, and it expires after about ${CLAIM_TTL_MINUTES} minutes. Generate the private PDF again to see the rule outcome.`,
      );
      setPoint(null);
      setExact(false);
      setBoots(false);
    } catch (err) {
      if (generation.current !== token) return;
      setError(err instanceof Error && err.message ? err.message : "Manual contact claim unavailable");
    } finally {
      if (generation.current === token) setBusy(false);
    }
  };

  return (
    <section className="rounded-lg border p-3 text-xs" aria-label="Manual ground contact claims">
      <h3 className="text-sm font-medium">Manual ground contact (operator claim)</h3>
      <p className="text-muted-foreground">
        Zone rules can only say inside or outside a zone when you state where a person stands. Pick a person, click the point on the
        treated copy where their boots or feet meet the ground, and confirm. The app does not estimate contact itself, the point must
        fall on that person's detected shape (the backend refuses it otherwise), and a claim is not a safety, zone or compliance
        finding. If you cannot see the feet or boots, do not record a claim.
      </p>
      {mapped.length === 0 ? (
        <p className="mt-2 text-muted-foreground">No person has a usable outline and a unique id, so no contact claim can be recorded.</p>
      ) : (
        <div className="mt-2 flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            Person
            <select
              value={personId}
              onChange={(e) => {
                setPersonId(e.target.value);
                setPoint(null);
                setError(null);
                setMessage(null);
              }}
              className="rounded border px-1 py-0.5"
            >
              <option value="">Choose a person</option>
              {mapped.map((p) => (
                <option key={p.id} value={p.id}>
                  {`${mappings.get(p.id)?.label} (backend id ${p.id})${recorded[p.id] ? " - claim recorded" : ""}`}
                </option>
              ))}
            </select>
          </label>
          <div
            style={{ position: "relative", display: "inline-block", lineHeight: 0, maxWidth: "100%" }}
            onClick={onImageClick}
            className={selected ? "cursor-crosshair" : undefined}
          >
            <img
              ref={imgRef}
              src={privateDisplayImageUrl(session.session_id)}
              alt="Treated copy for choosing a ground contact point, not the original"
              draggable={false}
              style={{ display: "block", maxWidth: "100%", height: "auto" }}
            />
            <svg aria-hidden="true" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} viewBox="0 0 1 1" preserveAspectRatio="none">
              {selected ? (
                <polygon
                  points={selected.polygon.map((q) => `${q.x},${q.y}`).join(" ")}
                  style={{ fill: "none", stroke: "#2563eb", strokeWidth: 2 }}
                  vectorEffect="non-scaling-stroke"
                />
              ) : null}
              {Object.entries(recorded).map(([id, q]) => (
                <circle key={id} cx={q.x} cy={q.y} r={0.006} style={{ fill: "#16a34a", stroke: "#fff", strokeWidth: 1 }} vectorEffect="non-scaling-stroke" />
              ))}
              {point ? (
                <g data-testid="contact-point">
                  <circle cx={point.x} cy={point.y} r={0.008} style={{ fill: "#dc2626", stroke: "#fff", strokeWidth: 1.5 }} vectorEffect="non-scaling-stroke" />
                </g>
              ) : null}
            </svg>
          </div>
          <p className="text-muted-foreground" aria-live="polite">
            {!selected
              ? "Choose a person to enable clicking."
              : point
                ? `Point marked in red for ${mappings.get(selected.id)?.label}: ${point.x.toFixed(3)}, ${point.y.toFixed(3)} (fraction of the image). Check it sits at their feet before confirming.`
                : "Click inside the blue outline at the person's feet."}
          </p>
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={exact} onChange={(e) => setExact(e.target.checked)} disabled={busy} />
            <span>This is the exact photo I reviewed and acknowledged, not another frame or scene.</span>
          </label>
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={boots} onChange={(e) => setBoots(e.target.checked)} disabled={busy} />
            <span>On this treated copy I can see this person's boots or feet on the ground at the red point.</span>
          </label>
          <label className="flex flex-col gap-1">
            Who is making this claim (shown in the record, max 80 characters)
            <input
              type="text"
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
              placeholder="who is making this claim"
              maxLength={80}
              className="rounded border px-1 py-0.5"
            />
          </label>
          <button type="button" onClick={() => void save()} disabled={!canSave} className="self-start rounded border px-2 py-1 font-medium disabled:opacity-50">
            Record contact claim
          </button>
          {message ? <p role="status">{message}</p> : null}
          {error ? <p role="alert" className="text-destructive">{error}</p> : null}
        </div>
      )}
    </section>
  );
}
