import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatFixtureTime } from "../format";
import { SEVERITY_FILTERS } from "../review";
import type { Audit, ReviewDecision, Zone } from "../types";
import type { Filters } from "../useVigilens";
import { FindingsList } from "./FindingsList";
import { HazardLog } from "./HazardLog";
import { EmptyState, ErrorPanel, Spinner } from "./primitives";

type Props = {
  audit: Audit | null;
  zones: Zone[];
  status: "idle" | "loading" | "error" | "success";
  error: string | null;
  loadedAt: string | null;
  reviews: Record<string, ReviewDecision>;
  onReview: (findingId: string, value: ReviewDecision) => void;
  selectedPersonId: string | null;
  onSelect: (personId: string | null) => void;
  filters: Filters;
  onFilters: (filters: Partial<Filters>) => void;
  onCancel: () => void;
  onRetry: () => void;
};

type Tab = "findings" | "log";

export function Inspector(props: Props) {
  const { audit, zones, status, error, loadedAt, filters } = props;
  const [tab, setTab] = useState<Tab>("findings");

  return (
    <div className="flex flex-col gap-4">
      <section aria-labelledby="summary-title" className="flex flex-col gap-3 rounded-vg-lg border border-vg-border bg-vg-surface p-4 shadow-vg-1">
        <h2 id="summary-title" className="text-lg font-semibold text-vg-text">Audit</h2>
        {audit ? (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm tabular-nums">
            <dt className="text-vg-text-secondary">Loaded at</dt>
            <dd className="text-vg-text">{loadedAt ?? "--:--"} (browser clock)</dd>
            <dt className="text-vg-text-secondary">Fixture loaded at</dt>
            <dd className="text-vg-text">{formatFixtureTime(audit.fixture_loaded_at)}</dd>
            <dt className="text-vg-text-secondary">Image</dt>
            <dd className="font-mono text-xs text-vg-text">{audit.image.id} - {audit.image.width} x {audit.image.height}</dd>
            <dt className="text-vg-text-secondary">Evidence</dt>
            <dd className="text-vg-text">Masked evidence unavailable</dd>
          </dl>
        ) : null}

        {status === "loading" ? (
          <div className="flex flex-wrap items-center gap-3">
            <Spinner label="Analysing photo" />
            <Button type="button" variant="outline" className="min-h-10" onClick={props.onCancel}>Cancel</Button>
          </div>
        ) : null}
        {status === "error" && error ? <ErrorPanel message={error} onRetry={props.onRetry} /> : null}
        {!audit && status !== "loading" && status !== "error" ? (
          <p className="text-sm text-vg-text-secondary">Analyse a photo to see findings, people and the hazard log.</p>
        ) : null}
      </section>

      {audit ? (
        <section aria-label="Findings and hazard log" className="flex flex-col gap-3 rounded-vg-lg border border-vg-border bg-vg-surface p-4 shadow-vg-1">
          <div role="tablist" aria-label="Inspector views" className="grid grid-cols-2 gap-1 rounded-vg-md bg-vg-surface-sunken p-1">
            {(["findings", "log"] as Tab[]).map((t) => (
              <button
                key={t}
                id={`tab-${t}`}
                role="tab"
                type="button"
                aria-selected={tab === t}
                aria-controls={`panel-${t}`}
                onClick={() => setTab(t)}
                className={`min-h-10 rounded-vg-sm text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-vg-focus-ring ${tab === t ? "bg-vg-surface-raised text-vg-text shadow-vg-1" : "text-vg-text-secondary hover:text-vg-text"}`}
              >
                {t === "findings" ? "Findings" : "Hazard Log"}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <label className="flex flex-col gap-1 text-xs font-medium text-vg-text-secondary">
              Severity
              <select
                value={filters.severity}
                onChange={(e) => props.onFilters({ severity: e.target.value })}
                className="min-h-10 rounded-vg-md border border-vg-border-strong bg-vg-surface px-2 text-sm font-normal text-vg-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-vg-focus-ring"
              >
                {SEVERITY_FILTERS.map((f) => (
                  <option key={f.value} value={f.value}>{f.label}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-vg-text-secondary">
              Zone
              <select
                value={filters.zone}
                onChange={(e) => props.onFilters({ zone: e.target.value })}
                className="min-h-10 rounded-vg-md border border-vg-border-strong bg-vg-surface px-2 text-sm font-normal text-vg-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-vg-focus-ring"
              >
                <option value="all">All zones</option>
                {zones.map((z) => (
                  <option key={z.id} value={z.id}>{z.name}</option>
                ))}
                <option value="none">No zone shown</option>
              </select>
            </label>
          </div>

          <div id="panel-findings" role="tabpanel" aria-labelledby="tab-findings" hidden={tab !== "findings"}>
            {audit.persons.length === 0 ? (
              <EmptyState title="No people detected">No people detected; not a safety clearance.</EmptyState>
            ) : (
              <FindingsList
                audit={audit}
                zones={zones}
                reviews={props.reviews}
                onReview={props.onReview}
                selectedPersonId={props.selectedPersonId}
                onSelect={(id) => props.onSelect(id === props.selectedPersonId ? null : id)}
                filters={filters}
              />
            )}
          </div>
          <div id="panel-log" role="tabpanel" aria-labelledby="tab-log" hidden={tab !== "log"}>
            <HazardLog
              audit={audit}
              zones={zones}
              reviews={props.reviews}
              loadedAt={loadedAt}
              selectedPersonId={props.selectedPersonId}
              onSelect={(id) => props.onSelect(id)}
              filters={filters}
            />
          </div>
        </section>
      ) : null}
    </div>
  );
}
