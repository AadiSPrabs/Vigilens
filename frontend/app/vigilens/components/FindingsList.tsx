import { personLabel, zoneNameFor } from "../format";
import { decisionFor, matchesSeverity, matchesZone, REVIEW_LABEL } from "../review";
import type { Audit, Finding, ReviewDecision, Zone } from "../types";
import type { Filters } from "../useVigilens";
import { EmptyState, PpeChip, SeverityBadge } from "./primitives";

type Props = {
  audit: Audit;
  zones: Zone[];
  reviews: Record<string, ReviewDecision>;
  onReview?: ((findingId: string, value: ReviewDecision) => void) | undefined;
  selectedPersonId: string | null;
  onSelect?: ((personId: string) => void) | undefined;
  filters: Filters;
  readOnly?: boolean;
};

const DECISIONS: ReviewDecision[] = ["unreviewed", "reviewed", "needs_human_review"];

export function FindingsList({ audit, zones, reviews, onReview, selectedPersonId, onSelect, filters, readOnly = false }: Props) {
  const all = audit.persons.flatMap((person, personIndex) => person.findings.map((finding) => ({ person, personIndex, finding })));
  const needsReview = all.filter(({ finding }) => decisionFor(finding, reviews) === "needs_human_review").length;
  const critical = all.filter(({ finding }) => finding.severity === "Critical" && finding.kind !== "uncertainty").length;
  const sourceIsFixture = audit.source === "fixture";

  if (audit.persons.length === 0) {
    return (
      <EmptyState title="No people detected">
        No people detected; not a safety clearance.
      </EmptyState>
    );
  }

  const visible = all.filter(
    ({ finding }) => matchesSeverity(finding, filters.severity) && matchesZone(finding.zone_id, filters.zone),
  );

  const byPerson = audit.persons.map((person, personIndex) => ({
    person,
    personIndex,
    findings: visible.filter((v) => v.person.id === person.id).map((v) => v.finding),
  }));

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm font-medium tabular-nums text-vg-text">
        {all.length} {all.length === 1 ? "finding" : "findings"}
        {critical > 0 ? ` - ${critical} Critical` : ""}
        {needsReview > 0 ? ` - ${needsReview} Needs human review` : ""}
      </p>
      {zones.length === 0 ? (
        <p className="rounded-vg-md border border-vg-border bg-vg-surface-sunken p-3 text-sm text-vg-text-secondary">
          No zones were checked; this is not proof the area is safe.
        </p>
      ) : null}
      {all.length === 0 ? (
        <p className="text-sm text-vg-text-secondary">No findings in this audit. Not a safety clearance.</p>
      ) : visible.length === 0 ? (
        <p className="text-sm text-vg-text-secondary">No findings match these filters.</p>
      ) : null}

      <ul className="flex flex-col gap-3">
        {byPerson.flatMap(({ person, personIndex, findings }) =>
          findings.map((finding) => (
            <FindingCard
              key={finding.id}
              person={person}
              label={personLabel(person, personIndex)}
              finding={finding}
              zoneName={zoneNameFor(zones, finding.zone_id)}
              decision={decisionFor(finding, reviews)}
              selected={person.id === selectedPersonId}
              onSelect={onSelect ? () => onSelect(person.id) : undefined}
              onReview={onReview ? (v) => onReview(finding.id, v) : undefined}
              fixture={sourceIsFixture}
              readOnly={readOnly}
            />
          )),
        )}
      </ul>
    </div>
  );
}

function FindingCard({
  person, label, finding, zoneName, decision, selected, onSelect, onReview, fixture, readOnly,
}: {
  person: Audit["persons"][number];
  label: string;
  finding: Finding;
  zoneName: string;
  decision: ReviewDecision;
  selected: boolean;
  onSelect?: (() => void) | undefined;
  onReview?: ((v: ReviewDecision) => void) | undefined;
  fixture: boolean;
  readOnly: boolean;
}) {
  const body = (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold text-vg-text">{label}</span>
        <SeverityBadge severity={finding.severity} kind={finding.kind} />
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <PpeChip label="Helmet" state={person.helmet} />
        <PpeChip label="Vest" state={person.vest} />
      </div>
      <p className="mt-2 text-sm text-vg-text-secondary">Zone: {zoneName}</p>
      <p className="mt-1 font-mono text-xs text-vg-text-tertiary">{finding.rule_id}</p>
      <p className="mt-1 text-sm text-vg-text">{finding.message}</p>
    </>
  );

  return (
    <li
      data-finding-id={finding.id}
      className={`rounded-vg-md border p-3 transition-colors duration-150 ${selected ? "border-vg-accent bg-vg-selected" : "border-vg-border bg-vg-surface-raised"}`}
    >
      {onSelect ? (
        <button
          type="button"
          onClick={onSelect}
          aria-pressed={selected}
          className="block w-full min-h-10 rounded-vg-sm text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-vg-focus-ring"
        >
          {body}
        </button>
      ) : (
        <div>{body}</div>
      )}

      <details open={readOnly} className="mt-3 text-sm">
        <summary className="min-h-10 cursor-pointer text-vg-text-secondary focus-visible:outline-2 focus-visible:outline-vg-focus-ring">
          How was this checked?
        </summary>
        <div className="mt-1 flex flex-col gap-1 pl-1 text-vg-text-secondary">
          {fixture ? <p className="text-xs italic">Illustrative (fixture), not a real re-check</p> : null}
          {finding.recheck_trace.length === 0 ? (
            <p className="text-xs">No recheck trace recorded.</p>
          ) : (
            <ol className="list-decimal pl-5 text-xs">
              {finding.recheck_trace.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
          )}
        </div>
      </details>

      <fieldset className="mt-3 border-t border-vg-border pt-3">
        <legend className="sr-only">Review decision for {finding.rule_id}</legend>
        {readOnly || !onReview ? (
          <p className="text-sm text-vg-text">Review: {REVIEW_LABEL[decision]}</p>
        ) : (
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {DECISIONS.map((value) => (
              <label key={value} className="flex min-h-10 cursor-pointer items-center gap-2 text-sm text-vg-text">
                <input
                  type="radio"
                  name={`review-${finding.id}`}
                  value={value}
                  checked={decision === value}
                  onChange={() => onReview(value)}
                  className="size-4"
                  style={{ accentColor: "var(--vg-accent)" }}
                />
                {REVIEW_LABEL[value]}
              </label>
            ))}
          </div>
        )}
      </fieldset>
    </li>
  );
}
