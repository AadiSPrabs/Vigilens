import type { Audit } from "../types";

export function BannerStack({ audit }: { audit: Audit | null }) {
  if (audit?.source === "fixture") {
    return (
      <div role="status" className="border-b-2 border-vg-banner-border bg-vg-banner-bg px-4 py-2.5 text-center text-sm font-semibold tracking-wide text-vg-banner-fg">
        SAMPLE DATA - not a real audit
      </div>
    );
  }
  return (
    <div className="border-b border-vg-border bg-vg-surface-sunken px-4 py-2 text-sm text-vg-text-secondary">
      Fixture mode. Results come only from the bundled sample photos. This tool supports human review and is not a safety clearance.
    </div>
  );
}
