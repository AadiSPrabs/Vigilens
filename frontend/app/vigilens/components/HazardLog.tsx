import { findingRank } from "../severity";
import { personLabel, zoneNameFor } from "../format";
import { decisionFor, matchesSeverity, matchesZone, REVIEW_LABEL } from "../review";
import type { Audit, ReviewDecision, Zone } from "../types";
import type { Filters } from "../useVigilens";
import { SeverityBadge } from "./primitives";

type Props = {
  audit: Audit;
  zones: Zone[];
  reviews: Record<string, ReviewDecision>;
  loadedAt: string | null;
  selectedPersonId: string | null;
  onSelect?: ((personId: string) => void) | undefined;
  filters: Filters;
};

export function HazardLog({ audit, zones, reviews, loadedAt, selectedPersonId, onSelect, filters }: Props) {
  const rows = audit.persons
    .flatMap((person, personIndex) =>
      person.findings.map((finding) => ({ person, personIndex, finding })),
    )
    .filter(({ finding }) => matchesSeverity(finding, filters.severity) && matchesZone(finding.zone_id, filters.zone))
    .map((row, order) => ({ ...row, order }))
    .sort((a, b) => findingRank(a.finding) - findingRank(b.finding) || a.order - b.order);

  if (rows.length === 0) {
    return <p className="text-sm text-vg-text-secondary">No hazard log entries for these filters.</p>;
  }

  return (
    <div className="max-h-[60vh] overflow-auto rounded-vg-md border border-vg-border lg:max-h-[calc(100vh-200px)]">
      <table className="w-full min-w-[620px] border-collapse text-left text-sm tabular-nums">
        <caption className="sr-only">Hazard log, sorted by severity</caption>
        <thead className="sticky top-0 z-[1] bg-vg-surface-raised">
          <tr className="border-b border-vg-border text-xs font-medium text-vg-text-secondary">
            <th scope="col" className="px-3 py-2">Loaded at</th>
            <th scope="col" className="px-3 py-2">Person</th>
            <th scope="col" className="px-3 py-2">Zone</th>
            <th scope="col" className="px-3 py-2">Finding</th>
            <th scope="col" className="px-3 py-2">Severity</th>
            <th scope="col" className="px-3 py-2">Review</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ person, personIndex, finding }) => {
            const selected = person.id === selectedPersonId;
            return (
              <tr
                key={finding.id}
                onClick={onSelect ? () => onSelect(person.id) : undefined}
                className={`border-b border-vg-border align-top ${selected ? "bg-vg-selected" : onSelect ? "cursor-pointer hover:bg-vg-hover" : ""}`}
              >
                <td className="whitespace-nowrap px-3 py-2 text-vg-text-secondary">{loadedAt ?? "--:--"}</td>
                <td className="px-3 py-2">
                  {onSelect ? (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); onSelect(person.id); }}
                      className="min-h-10 rounded-vg-sm font-medium text-vg-text underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-vg-focus-ring"
                    >
                      {personLabel(person, personIndex)}
                    </button>
                  ) : (
                    <span className="font-medium text-vg-text">{personLabel(person, personIndex)}</span>
                  )}
                </td>
                <td className="px-3 py-2 text-vg-text">{zoneNameFor(zones, finding.zone_id)}</td>
                <td className="px-3 py-2">
                  <span className="block font-mono text-xs text-vg-text-tertiary">{finding.rule_id}</span>
                  <span className="block text-vg-text">{finding.message}</span>
                </td>
                <td className="px-3 py-2"><SeverityBadge severity={finding.severity} kind={finding.kind} /></td>
                <td className="px-3 py-2 text-vg-text-secondary">{REVIEW_LABEL[decisionFor(finding, reviews)]}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
