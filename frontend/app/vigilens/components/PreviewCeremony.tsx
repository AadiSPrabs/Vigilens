import { personMappings } from "../format";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { Audit, FaceProposalsResult, PrivateDisplaySession } from "../types";
import { acknowledgePrivateDisplay, fetchFaceProposals, preparePrivateDisplay, privateDisplayImageUrl } from "../api/backendClient";

// The existing backend gate, made usable: recheck execution requires a treated
// preview the visitor actually looked at, acknowledged for the exact derivative.
// Binding discipline (reviewer-required): all state is keyed to the exact
// (pixel digest, File) pair; any source change resets the ceremony and
// invalidates in-flight prepares; a prepared or acknowledged session is only
// usable while its source_digest still matches the current audit.
type CheckKey = "foreground" | "background" | "reflections" | "derivative";

// Detector-proposal dispositions (operator decisions on each flagged candidate
// face). "covered" becomes an editable mask region; "dismissed" records the
// bounded operator reason. Neither claims detector coverage - misses stay
// possible and the whole-frame review stays manual.
type ProposalDisposition =
  | { kind: "covered"; person_id: string; box: [number, number, number, number] }
  | { kind: "dismissed"; dismiss_reason: "operator_confirmed_not_a_face" };
const CHECKS: { key: CheckKey; label: string }[] = [
  { key: "foreground", label: "I checked the foreground for recognizable faces or identifying details" },
  { key: "background", label: "I checked the background, including people I did not mark" },
  { key: "reflections", label: "I checked reflections and screens" },
  { key: "derivative", label: "I checked that this treated copy - not the original - is what a recheck would use" },
];
// Reason-aware wording for a zero-proposal result: a genuine completed
// no-face pass reads differently from a check that could not run (detector
// unavailable, model digest mismatch, runtime missing, detector failure).
// Neither is ever presented as safe; the manual whole-frame review stays
// the requirement in every case.
const ZERO_REASON_WORDING: Record<string, string> = {
  model_unavailable: "the detector model file is unavailable",
  model_digest_mismatch: "the detector model file does not match its pinned digest",
  optional_runtime_unavailable: "the optional detector runtime is not installed",
  detector_failure_discarded_partial_output: "the detector failed and its partial output was discarded",
};

function zeroFacesWording(result: FaceProposalsResult): string {
  if (result.reason === "no_faces_detected_still_requires_review") {
    return "The face check found no faces. That does not mean the frame is safe - check it yourself.";
  }
  const why = (result.reason && ZERO_REASON_WORDING[result.reason]) || "the check did not complete";
  return `The face check could not run (${why}). That does not mean the frame is safe - check it yourself.`;
}

const UNCHECKED: Record<CheckKey, boolean> = { foreground: false, background: false, reflections: false, derivative: false };

// Pixel box as CORNERS [x1, y1, x2, y2] (the backend treats the region box with
// PIL crop semantics: left, upper, right, lower) from a normalized polygon, or
// null when the polygon is missing, degenerate, or non-finite. Kept for its
// unit tests; the ceremony deliberately does NOT auto-mask whole-person boxes
// (that erased the PPE evidence reports exist to show).
export function polygonBox(polygon: { x: number; y: number }[], width: number, height: number): [number, number, number, number] | null {
  if (!Array.isArray(polygon) || polygon.length < 3) return null;
  if (polygon.some((p) => !Number.isFinite(p.x) || !Number.isFinite(p.y))) return null;
  const xs = polygon.map((p) => p.x * width);
  const ys = polygon.map((p) => p.y * height);
  const x1 = Math.max(0, Math.floor(Math.min(...xs)));
  const y1 = Math.max(0, Math.floor(Math.min(...ys)));
  const x2 = Math.min(width, Math.ceil(Math.max(...xs)));
  const y2 = Math.min(height, Math.ceil(Math.max(...ys)));
  if (x2 <= x1 || y2 <= y1) return null;
  return [x1, y1, x2, y2];
}

export function PreviewCeremony(props: {
  audit: Audit;
  // null = reopened stored job: the backend reads this account's own preserved source.
  file: File | null;
  onAcknowledged: (session: PrivateDisplaySession) => void;
  onInvalidate: () => void;
}) {
  const { audit, file, onAcknowledged, onInvalidate } = props;
  const digest = audit.image.pixel_digest;
  const [prepared, setPrepared] = useState<{ session: PrivateDisplaySession; digest: string } | null>(null);
  const [proposals, setProposals] = useState<{ result: FaceProposalsResult; digest: string } | null>(null);
  const [proposalsBusy, setProposalsBusy] = useState(false);
  const [proposalsError, setProposalsError] = useState<string | null>(null);
  const [dispositions, setDispositions] = useState<Record<number, ProposalDisposition>>({});
  // Generic manual mask regions: faces and identifying details the detector
  // missed (background people, reflections, screens) are the operator's to
  // mark. Nothing is masked automatically except what the operator decides.
  const [manualRegions, setManualRegions] = useState<[number, number, number, number][]>([]);
  // Legitimate zero-region path: an explicit per-person OPAQUE SHIELD review
  // (backend redaction contract: basis opaque_worn_face_shield, three exact
  // attestations, never detector absence). Never a fake box.
  const [shielded, setShielded] = useState<Record<string, boolean>>({});
  // Explicit, non-default privacy fallback: withhold the whole image (full-frame
  // opaque redaction). Asserts nothing about faces and is never no-face
  // verification; PPE from this image is not displayed.
  const [withholdImage, setWithholdImage] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checked, setChecked] = useState<Record<CheckKey, boolean>>({ ...UNCHECKED });
  const prepareSeq = useRef(0);
  // The face-check aid gets its OWN sequence: a prepare/discard must never
  // strand an in-flight check (stuck busy), and a discarded ceremony must
  // never accept a late face response.
  const faceSeq = useRef(0);
  const allChecked = CHECKS.every((c) => checked[c.key]);
  // Any decision, undo or box edit clears a stale "decide on every flagged face"
  // refusal; the prepare gate re-checks and re-refuses if decisions are still missing.
  const updateDispositions = (fn: (prev: Record<number, ProposalDisposition>) => Record<number, ProposalDisposition>) => {
    setError(null);
    setDispositions(fn);
  };

  // Any change of the bound source pair (new upload or new audit) resets the
  // whole ceremony and invalidates any in-flight prepare response.
  useEffect(() => {
    prepareSeq.current += 1;
    faceSeq.current += 1;
    setPrepared(null);
    setAcknowledged(false);
    setBusy(false);
    setError(null);
    setProposals(null);
    setProposalsBusy(false);
    setProposalsError(null);
    setManualRegions([]);
    setShielded({});
    setWithholdImage(false);
    setChecked({ ...UNCHECKED });
    // The parent's readiness marker must not survive a source/file change:
    // a stale ack would leave Execute looking enabled only to be refused 409.
    onInvalidate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [digest, file]);

  // Auto-run the offline face check once per bound source so proposal-driven
  // masking is the default starting point, not an optional extra. Failures only
  // surface the aid error; the manual whole-frame review stays the requirement.
  const autoRanFor = useRef<string | null>(null);
  const sourceKey = `${digest ?? ""}:${file ? `${file.name}:${file.size}` : "stored"}`;
  useEffect(() => {
    if (!digest) return;
    if (autoRanFor.current === sourceKey) return;
    autoRanFor.current = sourceKey;
    void checkFaces();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceKey]);

  if (!digest) return null;

  // Optional review aid: offline face-check proposals for the operator's own
  // whole-frame pass. Proposals never create regions, never tick a checkbox,
  // and never change the acknowledgment - the four checks stay explicit and
  // manual. A refusal just means the aid is unavailable; the manual review is
  // still the requirement.
  const checkFaces = async () => {
    const boundDigest = digest;
    const boundFile = file;
    const seq = ++faceSeq.current;
    setProposalsBusy(true);
    setProposalsError(null);
    setDispositions({});
    try {
      const result = await fetchFaceProposals(boundDigest, boundFile);
      if (seq !== faceSeq.current) return; // stale: source changed or the aid state was reset mid-flight
      // Dedupe by exact review_region: multiscale detector passes can flag the
      // same region twice, and the backend keys dispositions by review_region
      // and rejects duplicates - sending both would deadlock preparation.
      // Overlapping-but-different regions are kept.
      const seen = new Set<string>();
      const deduped = result.proposals.filter((pr) => {
        const key = pr.review_region.join(",");
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      setProposals({ result: { ...result, proposals: deduped }, digest: boundDigest });
      // Automatic default treatment: every flagged face starts MASKED (its
      // review_region as the default box). Each mask stays reviewable - the
      // operator can adjust it or mark the candidate not a face before
      // anything is prepared. Defaults never claim detector coverage.
      setDispositions(Object.fromEntries(deduped.map((pr, i) => [i, {
        kind: "covered" as const,
        person_id: `flagged-face-${i + 1}`,
        box: [...pr.review_region] as [number, number, number, number],
      }])));
    } catch (err) {
      if (seq !== faceSeq.current) return;
      setProposals(null);
      setProposalsError(err instanceof Error && err.message ? err.message : "Face check unavailable; continue with a careful manual whole-frame review.");
    } finally {
      if (seq === faceSeq.current) setProposalsBusy(false);
    }
  };

  const prepare = async () => {
    const seq = ++prepareSeq.current;
    const boundDigest = digest;
    const boundFile = file;
    setBusy(true);
    setError(null);
    try {
      const regions: { person_id: string; box: [number, number, number, number] }[] = [];
      // Generic manual regions first: faces/details the detector missed. Each
      // must be whole-pixel corners inside the frame with x1 < x2, y1 < y2.
      for (let i = 0; i < manualRegions.length; i += 1) {
        const box = manualRegions[i];
        if (!box) continue;
        const [x1, y1, x2, y2] = box;
        if (!(Number.isInteger(x1) && Number.isInteger(y1) && Number.isInteger(x2) && Number.isInteger(y2)
          && x1 >= 0 && y1 >= 0 && x1 < x2 && y1 < y2
          && x2 <= audit.image.width && y2 <= audit.image.height)) {
          setError(`Mask region ${i + 1}: corners must be whole pixels inside the frame with x1 < x2 and y1 < y2.`);
          return;
        }
        regions.push({ person_id: `manual-region-${i + 1}`, box: [x1, y1, x2, y2] });
      }
      const faceCoverings = audit.persons
        .filter((person) => shielded[person.id])
        .map((person) => ({
          person_id: person.id,
          basis: "opaque_worn_face_shield",
          face_fully_hidden: true,
          no_visible_face_pixels: true,
          exact_source_confirmed: true,
        }));
      const review: Record<string, unknown> = {
        source_digest: boundDigest,
        frame_size: [audit.image.width, audit.image.height],
        regions,
        reviewer_label: "visitor preview preparation",
        redaction_method: "opaque",
      };
      if (faceCoverings.length > 0 && !withholdImage) review.face_coverings = faceCoverings;
      if (withholdImage) {
        review.regions = [];
        review.image_withheld = { basis: "operator_elected_image_withheld", exact_source_confirmed: true, withhold_entire_frame: true };
      }
      // If the detector aid was used, every flagged candidate must be decided
      // (masked or dismissed) before preparing: an undecided proposal must
      // never sail through. Decided ones travel as proposal_dispositions and
      // the backend re-verifies them against a fresh detector pass.
      const aid = proposals && proposals.digest === boundDigest ? proposals.result.proposals : null;
      if (aid && aid.length > 0 && !withholdImage) {
        const undecided = aid.filter((_, i) => !dispositions[i]);
        if (undecided.length > 0) {
          setError(`Decide on every flagged face first (${aid.length - undecided.length} of ${aid.length} decided): mask it or mark it not a face.`);
          return;
        }
        for (let i = 0; i < aid.length; i += 1) {
          const d = dispositions[i];
          const pr = aid[i];
          if (!d || !pr) {
            setError(`Decide on every flagged face first: flagged face ${i + 1} has no recorded decision.`);
            return;
          }
          if (d.kind !== "covered") continue;
          const [x1, y1, x2, y2] = d.box;
          if (!(Number.isInteger(x1) && Number.isInteger(y1) && Number.isInteger(x2) && Number.isInteger(y2)
            && x1 >= 0 && y1 >= 0 && x1 < x2 && y1 < y2
            && x2 <= audit.image.width && y2 <= audit.image.height)) {
            setError(`Flagged face ${i + 1}: the mask box is invalid - corners must be whole pixels inside the frame with x1 < x2 and y1 < y2.`);
            return;
          }
          const [rx1, ry1, rx2, ry2] = pr.review_region;
          if (!(x1 <= rx1 && y1 <= ry1 && x2 >= rx2 && y2 >= ry2)) {
            setError(`Flagged face ${i + 1}: the mask box must fully contain the flagged area.`);
            return;
          }
          regions.push({ person_id: d.person_id, box: d.box });
        }
        const decided: Record<string, unknown>[] = [];
        for (let i = 0; i < aid.length; i += 1) {
          const d = dispositions[i];
          const pr = aid[i];
          if (!d || !pr) {
            setError(`Decide on every flagged face first: flagged face ${i + 1} has no recorded decision.`);
            return;
          }
          decided.push(d.kind === "covered"
            ? { review_region: pr.review_region, disposition: "covered", person_id: d.person_id }
            : { review_region: pr.review_region, disposition: "dismissed", dismiss_reason: d.dismiss_reason });
        }
        review.proposal_dispositions = decided;
      }
      // Backend v6.2 rejects a zero-region preview ("Zero regions cannot
      // establish no faces"). Refuse client-side first, naming the legitimate
      // paths - never a fake box, never a bare no-faces claim.
      if (!withholdImage && regions.length === 0 && faceCoverings.length === 0) {
        setError("No mask regions added. The backend refuses a zero-region preview: mask a flagged face, add a region yourself, or record an exact opaque-shield review for a person whose face is fully hidden. A bare 'no faces' claim is never accepted.");
        return;
      }
      const session = await preparePrivateDisplay(boundDigest, boundFile, review);
      if (seq !== prepareSeq.current) return; // stale response: the source changed mid-flight
      if (session.source_digest !== boundDigest) {
        setError("The server returned a preview bound to a different source. Refusing to use it.");
        return;
      }
      setPrepared({ session, digest: boundDigest });
    } catch (err) {
      if (seq !== prepareSeq.current) return;
      setError(err instanceof Error ? err.message : "Preview preparation failed.");
    } finally {
      if (seq === prepareSeq.current) setBusy(false);
    }
  };

  const acknowledge = async () => {
    // Accept only an ack for a session still bound to the current audit digest.
    if (!prepared || prepared.digest !== digest || prepared.session.source_digest !== digest) {
      setError("This preview no longer matches the current upload. Prepare a new one.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await acknowledgePrivateDisplay(prepared.session, {
        foreground_checked: checked.foreground,
        background_checked: checked.background,
        reflections_checked: checked.reflections,
        derivative_checked: checked.derivative,
      });
      setAcknowledged(true);
      onAcknowledged(prepared.session);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Acknowledgment refused.");
    } finally {
      setBusy(false);
    }
  };

  const reprepare = () => {
    prepareSeq.current += 1;
    faceSeq.current += 1;
    setPrepared(null);
    setAcknowledged(false);
    setBusy(false);
    setError(null);
    // Discard resets ALL proposal aid state too: no stale result, no stuck
    // busy flag, no carried error survives into the fresh cycle.
    setProposals(null);
    setProposalsBusy(false);
    setProposalsError(null);
    setDispositions({});
    setManualRegions([]);
    setShielded({});
    setWithholdImage(false);
    setChecked({ ...UNCHECKED });
    onInvalidate();
  };

  return (
    <section className="flex flex-col gap-3 rounded-vg-lg border border-vg-border bg-vg-surface p-4 shadow-vg-1" aria-label="Privacy preview for recheck">
      <h3 className="text-base font-semibold text-vg-text">Reviewed preview required</h3>
      <p className="text-sm text-vg-text-secondary">
        The backend only runs a recheck against a treated copy you have actually looked at and acknowledged. The original
        upload stays separate; the treated preview is display-only and is never exported. Faces the offline check
        flags are masked by default below; every mask is yours to inspect, adjust or remove before anything is
        prepared, and you can add mask regions yourself for faces the check missed (background people, reflections,
        screens). Only face-area boxes are masked - bodies and protective equipment stay visible. The check can miss
        faces, so masking stays your review, not a guarantee every face is covered.
      </p>
      {acknowledged && prepared ? (
        <>
          <p role="status" className="text-sm text-vg-text">Preview acknowledged for this exact upload. Any available recheck will use this treated copy only.</p>
          <Button type="button" variant="outline" className="min-h-10" onClick={reprepare}>Prepare a new preview</Button>
        </>
      ) : !prepared ? (
        <>
          <div className="flex flex-col gap-3">
            <Button type="button" variant="outline" className="min-h-10" disabled={proposalsBusy || busy} onClick={checkFaces}>
              {proposalsBusy ? "Checking for faces…" : "Check for unmarked faces (review aid)"}
            </Button>
            {proposals && proposals.digest === digest ? (
              <div role="note" className="flex flex-col gap-3 rounded-vg-md border border-vg-border bg-vg-surface-sunken p-3 text-sm text-vg-text">
                <p>
                  {proposals.result.proposals.length === 0
                    ? zeroFacesWording(proposals.result)
                    : `The face check flagged ${proposals.result.proposals.length} possible face${proposals.result.proposals.length === 1 ? "" : "s"} for you to review:`}
                </p>
                {proposals.result.proposals.length > 0 ? (
                  <ul className="flex flex-col gap-3">
                    {proposals.result.proposals.map((pr, i) => {
                      const d = dispositions[i];
                      return (
                        <li key={i} className="flex flex-col gap-2 rounded-vg-md border border-vg-border bg-vg-surface p-3">
                          Possible face near ({pr.review_region[0]}, {pr.review_region[1]}) to ({pr.review_region[2]}, {pr.review_region[3]})
                          {typeof pr.confidence === "number" ? ` (confidence ${pr.confidence.toFixed(2)})` : ""}
                          {" - helmets and overlaps not checked"}
                          {!d || d.kind === "covered" ? (
                            <span className="flex flex-wrap items-center gap-2">
                              {" - masked by default. Adjust the box if needed: "}
                              {([0, 1, 2, 3] as const).map((corner) => (
                                <input
                                  key={corner}
                                  type="number"
                                  aria-label={`flagged face ${i + 1} box corner ${corner + 1}`}
                                  className="h-9 w-20 rounded-vg-sm border border-vg-border bg-vg-surface px-2 text-sm text-vg-text"
                                  value={(d && d.kind === "covered" ? d.box : pr.review_region)[corner]}
                                  onChange={(e) => {
                                    const v = Math.trunc(Number(e.target.value));
                                    if (!Number.isFinite(v)) return;
                                    updateDispositions((prev) => {
                                      const cur = prev[i];
                                      if (!cur || cur.kind !== "covered") return prev;
                                      const box = [...cur.box] as [number, number, number, number];
                                      box[corner] = v;
                                      return { ...prev, [i]: { ...cur, box } };
                                    });
                                  }}
                                />
                              ))}{" "}
                              <Button
                                type="button"
                                variant="outline"
                                className="min-h-10"
                                onClick={() => updateDispositions((prev) => ({ ...prev, [i]: { kind: "dismissed", dismiss_reason: "operator_confirmed_not_a_face" } }))}
                              >
                                Not a face
                              </Button>
                            </span>
                          ) : (
                            <span className="flex flex-wrap items-center gap-2">
                              {" - marked not a face by you. "}
                              <Button
                                type="button"
                                variant="outline"
                                className="min-h-10"
                                onClick={() =>
                                  updateDispositions((prev) => ({
                                    ...prev,
                                    [i]: { kind: "covered", person_id: `flagged-face-${i + 1}`, box: [...pr.review_region] as [number, number, number, number] },
                                  }))
                                }
                              >
                                Mask it after all
                              </Button>
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
                <p className="rounded-vg-md border border-sev-medium-border bg-sev-medium-bg p-3 text-sm text-sev-medium-fg">
                  Faces the check flagged are masked by default above; inspect, adjust or remove each mask. Coverage
                  is unverified: the check can miss faces, and helmet, reflection and background checks stay yours.
                  Add regions for anything it missed below.
                </p>
              </div>
            ) : null}
            {proposalsError ? <p role="alert" className="rounded-vg-md border border-sev-critical-border bg-sev-critical-bg p-3 text-sm text-sev-critical-fg">{proposalsError}</p> : null}
            <div className="flex flex-col gap-2 rounded-vg-md border border-vg-border bg-vg-surface-sunken p-3 text-sm text-vg-text">
              <p className="font-medium">Mask regions you add yourself</p>
              <p className="text-vg-text-secondary">
                Add a box for anything the check did not flag - background people, reflections, screens, badges.
                Corners are whole pixels [x1, y1, x2, y2] of the original photo ({audit.image.width} x {audit.image.height}).
              </p>
              {manualRegions.map((box, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2">
                  <span>Mask region {i + 1}:</span>
                  {([0, 1, 2, 3] as const).map((corner) => (
                    <input
                      key={corner}
                      type="number"
                      aria-label={`mask region ${i + 1} corner ${corner + 1}`}
                      className="h-9 w-20 rounded-vg-sm border border-vg-border bg-vg-surface px-2 text-sm text-vg-text"
                      value={box[corner]}
                      onChange={(e) => {
                        const v = Math.trunc(Number(e.target.value));
                        if (!Number.isFinite(v)) return;
                        setError(null);
                        setManualRegions((prev) => prev.map((b, j) => {
                          if (j !== i) return b;
                          const next = [...b] as [number, number, number, number];
                          next[corner] = v;
                          return next;
                        }));
                      }}
                    />
                  ))}
                  <Button type="button" variant="outline" className="min-h-10" onClick={() => { setError(null); setManualRegions((prev) => prev.filter((_, j) => j !== i)); }}>
                    Remove
                  </Button>
                </div>
              ))}
              {audit.persons.length > 0 ? (
                <div className="mt-1 flex flex-col gap-1">
                  {audit.persons.map((person) => (
                    <label key={person.id} className="flex items-start gap-2">
                      <input
                        type="checkbox"
                        className="mt-0.5 size-4 shrink-0"
                        disabled={!personMappings(audit.persons).get(person.id)?.mapped}
                        checked={shielded[person.id] ?? false}
                        onChange={(e) => { setError(null); setShielded((prev) => ({ ...prev, [person.id]: e.target.checked })); }}
                      />
                      <span>
                        {personMappings(audit.persons).get(person.id)?.mapped ? `${personMappings(audit.persons).get(person.id)!.label} (backend id ${person.id}, labelled on the photo)` : `Unmapped person (backend id ${person.id}), not attestable`} wears an opaque face shield that fully hides their face - I verified no
                        face pixels are visible on this exact photo. (Exact shield review, not a detector result.)
                      </span>
                    </label>
                  ))}
                </div>
              ) : null}
              <label className="mt-1 flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 shrink-0"
                  checked={withholdImage}
                  onChange={(e) => { setError(null); setWithholdImage(e.target.checked); }}
                />
                <span>
                  Withhold the whole image (privacy fallback, off by default). The preview and report show a fully black
                  frame and no PPE findings from this image. This is not face masking and does not show that the image has
                  no faces.
                </span>
              </label>
              <Button
                type="button"
                variant="outline"
                className="min-h-10 self-start"
                disabled={busy}
                onClick={() => {
                  setError(null);
                  const cx = Math.floor(audit.image.width / 2);
                  const cy = Math.floor(audit.image.height / 2);
                  const half = Math.max(8, Math.floor(Math.min(audit.image.width, audit.image.height) / 20));
                  setManualRegions((prev) => [...prev, [Math.max(0, cx - half), Math.max(0, cy - half), Math.min(audit.image.width, cx + half), Math.min(audit.image.height, cy + half)]]);
                }}
              >
                Add a mask region
              </Button>
            </div>
          </div>
          <Button type="button" variant="default" className="min-h-10 self-start" disabled={busy} onClick={prepare}>
            {busy ? "Preparing…" : "Prepare a treated preview"}
          </Button>
        </>
      ) : (
        <>
          <img src={privateDisplayImageUrl(prepared.session.session_id)} alt="Treated preview for privacy review" className="max-h-80 w-auto max-w-full self-start rounded-vg-md border border-vg-border" />
          {prepared.session.warning ? <p className="rounded-vg-md border border-sev-medium-border bg-sev-medium-bg p-3 text-sm text-sev-medium-fg">{prepared.session.warning}</p> : null}
          {typeof prepared.session.expires_in_seconds === "number" ? (
            <p className="text-sm text-vg-text-secondary">This preview stays valid for about {Math.ceil(prepared.session.expires_in_seconds / 60)} minute(s); the acknowledgment binds only this exact treated copy.</p>
          ) : null}
          <fieldset className="flex flex-col gap-1 rounded-vg-md border border-vg-border p-3">
            <legend className="px-1 text-sm font-semibold text-vg-text">Confirm what you checked</legend>
            {CHECKS.map((check) => (
              <label key={check.key} className="flex min-h-10 items-start gap-2 py-1 text-sm text-vg-text">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 shrink-0"
                  style={{ accentColor: "var(--vg-accent)" }}
                  checked={checked[check.key]}
                  onChange={(e) => setChecked((prev) => ({ ...prev, [check.key]: e.target.checked }))}
                />
                {check.label}
              </label>
            ))}
          </fieldset>
          <Button type="button" variant="default" className="h-auto min-h-10 whitespace-normal py-2 text-center" disabled={busy || !allChecked} onClick={acknowledge}>
            {busy ? "Acknowledging…" : "Acknowledge this treated preview"}
          </Button>
          <Button type="button" variant="outline" className="min-h-10" disabled={busy} onClick={reprepare}>Discard and prepare again</Button>
        </>
      )}
      {error ? <p role="alert" className="rounded-vg-md border border-sev-critical-border bg-sev-critical-bg p-3 text-sm text-sev-critical-fg">{error}</p> : null}
    </section>
  );
}
