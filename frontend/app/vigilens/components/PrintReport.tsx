import { ImageStage } from "./ImageStage";
import { FindingsList } from "./FindingsList";
import { HazardLog } from "./HazardLog";
import { SeverityBadge, ClearBadge } from "./primitives";
import { formatFixtureTime } from "../format";
import type { Audit, ReviewDecision, Zone } from "../types";

export const REPORT_FOOTER = "Prototype audit for human review - not a compliance certification.";

const ALL_FILTERS = { severity: "all", zone: "all" };

export function PrintReport({
  audit,
  zones,
  imageUrl,
  reviews,
  loadedAt,
}: {
  audit: Audit | null;
  zones: Zone[];
  imageUrl: string | null;
  reviews: Record<string, ReviewDecision>;
  loadedAt: string | null;
}) {
  if (!audit) return null;
  return (
    <div className="vg-print-report hidden">
      <header className="flex flex-col gap-1 border-b border-vg-border pb-3">
        <h1 className="text-2xl font-semibold text-vg-text">Vigilens audit report</h1>
        <p className="font-mono text-xs text-vg-text-secondary">{audit.audit_id} - {audit.image.id}</p>
        <p className="text-sm text-vg-text-secondary">
          Fixture loaded at {formatFixtureTime(audit.fixture_loaded_at)}. Browser clock: loaded at {loadedAt ?? "--:--"}.
        </p>
      </header>

      {audit.source === "fixture" ? (
        <div className="my-3 border-2 border-vg-banner-border bg-vg-banner-bg px-3 py-2 text-center text-sm font-semibold text-vg-banner-fg">
          SAMPLE DATA - not a real audit
        </div>
      ) : null}

      <section className="mt-4 flex flex-col gap-2">
        <h2 className="text-lg font-semibold text-vg-text">Image</h2>
        <ImageStage
          imageUrl={imageUrl}
          imageAlt="Preview of the audited photo with zone and person overlays"
          zones={audit.zones.length ? audit.zones : zones}
          persons={audit.persons}
          selectedPersonId={null}
          readOnly
          caption={
            <span>
              Preview only, not evidence. Masked evidence unavailable.
            </span>
          }
        />
      </section>

      <section className="mt-4 flex flex-col gap-2">
        <h2 className="text-lg font-semibold text-vg-text">Severity legend</h2>
        <div className="flex flex-wrap gap-2">
          <SeverityBadge severity="Critical" />
          <SeverityBadge severity="Medium" />
          <SeverityBadge severity="Low" />
          <SeverityBadge severity={null} kind="uncertainty" />
          <ClearBadge />
        </div>
        <p className="text-xs text-vg-text-secondary">Any other severity text is shown as written.</p>
      </section>

      <section className="mt-4 flex flex-col gap-2">
        <h2 className="text-lg font-semibold text-vg-text">Findings</h2>
        <FindingsList audit={audit} zones={zones} reviews={reviews} selectedPersonId={null} filters={ALL_FILTERS} readOnly />
      </section>

      <section className="mt-4 flex flex-col gap-2">
        <h2 className="text-lg font-semibold text-vg-text">Hazard log</h2>
        <HazardLog audit={audit} zones={zones} reviews={reviews} loadedAt={loadedAt} selectedPersonId={null} filters={ALL_FILTERS} />
      </section>

      <footer className="mt-6 border-t border-vg-border pt-3 text-xs text-vg-text-secondary">{REPORT_FOOTER}</footer>
    </div>
  );
}
