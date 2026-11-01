import { backendConfigured } from "../api/backendClient";
import type { Audit } from "../types";

export function BannerStack({ audit }: { audit: Audit | null }) {
  if (audit?.source === "backend") {
    if (audit.readings_origin === "synthetic") {
      return (
        <div role="status" className="border-b-2 border-vg-banner-border bg-vg-banner-bg px-4 py-2.5 text-center text-sm font-semibold tracking-wide text-vg-banner-fg">
          SYNTHETIC READINGS - boxes and PPE values are generated test data, not detections
        </div>
      );
    }
    return (
      <div role="status" className="border-b-2 border-vg-banner-border bg-vg-banner-bg px-4 py-2.5 text-center text-sm font-semibold tracking-wide text-vg-banner-fg">
        UNVALIDATED PROVIDER READINGS - not a safety clearance
      </div>
    );
  }
  if (audit?.source === "fixture") {
    return (
      <div role="status" className="border-b-2 border-vg-banner-border bg-vg-banner-bg px-4 py-2.5 text-center text-sm font-semibold tracking-wide text-vg-banner-fg">
        SAMPLE DATA - not a real audit
      </div>
    );
  }
  return (
    <div className="border-b border-vg-border bg-vg-surface-sunken px-4 py-2 text-sm text-vg-text-secondary">
      {backendConfigured()
        ? "Connected to a local backend. Uploads are analysed by this install; bundled samples stay offline fixtures. This tool supports human review and is not a safety clearance."
        : "Fixture mode. Results come only from the bundled sample photos. This tool supports human review and is not a safety clearance."}
    </div>
  );
}
