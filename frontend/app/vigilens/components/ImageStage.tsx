import { IconCamera } from "@tabler/icons-react";
import { useId, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";

import { clientToNormalized } from "../geometry";
import { personOutline } from "../severity";
import { personLabel, zoneNameFor } from "../format";
import type { Person, Point, Zone } from "../types";

type Props = {
  imageUrl: string | null;
  imageAlt: string;
  zones: Zone[];
  persons: Person[] | null;
  selectedPersonId: string | null;
  onSelectPerson?: ((id: string) => void) | undefined;
  draftPoints?: Point[] | undefined;
  onAddPoint?: ((p: Point) => void) | undefined;
  drawing?: boolean;
  readOnly?: boolean;
  caption?: ReactNode;
};

const pts = (points: Point[]) => points.map((p) => `${p.x},${p.y}`).join(" ");

function bounds(points: Point[]) {
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  return { left: Math.min(...xs), top: Math.min(...ys) };
}

export function ImageStage({
  imageUrl,
  imageAlt,
  zones,
  persons,
  selectedPersonId,
  onSelectPerson,
  draftPoints,
  onAddPoint,
  drawing = false,
  readOnly = false,
  caption,
}: Props) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [hover, setHover] = useState<Point | null>(null);
  const hatchId = `vg-hatch-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;

  if (!imageUrl) {
    return (
      <div className="flex min-h-64 items-center justify-center rounded-vg-lg border border-dashed border-vg-border-strong bg-vg-surface p-6">
        <div className="flex max-w-sm flex-col items-center gap-3 text-center">
          <IconCamera size={48} stroke={1.25} className="text-vg-text-tertiary" aria-hidden="true" />
          <p className="text-sm text-vg-text-secondary">Upload a site photo or pick a sample to start the zone setup.</p>
        </div>
      </div>
    );
  }

  const interactive = !readOnly && !drawing;

  const toNormalized = (e: MouseEvent<HTMLDivElement>): Point | null => {
    const img = imgRef.current;
    if (!img) return null;
    return clientToNormalized(e.clientX, e.clientY, img.getBoundingClientRect());
  };

  const handleClick = (e: MouseEvent<HTMLDivElement>) => {
    if (!drawing || !onAddPoint) return;
    const p = toNormalized(e);
    if (p) onAddPoint(p);
  };

  const handleMove = (e: MouseEvent<HTMLDivElement>) => {
    if (!drawing) return;
    setHover(toNormalized(e));
  };

  const handleKey = (e: KeyboardEvent<SVGPolygonElement>, id: string) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelectPerson?.(id);
    }
  };

  const previewPoints = draftPoints && draftPoints.length > 0 ? (hover ? [...draftPoints, hover] : draftPoints) : null;

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-hidden rounded-vg-lg border border-vg-border bg-vg-surface-sunken shadow-vg-1">
        <div
          style={{ position: "relative", display: "inline-block", lineHeight: 0, maxWidth: "100%" }}
          onClick={handleClick}
          onMouseMove={handleMove}
          onMouseLeave={() => setHover(null)}
          className={drawing ? "cursor-crosshair" : undefined}
        >
          <img
            ref={imgRef}
            src={imageUrl}
            alt={imageAlt}
            draggable={false}
            style={{ display: "block", maxWidth: "100%", height: "auto" }}
          />
          <svg
            aria-hidden={persons ? undefined : true}
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
            viewBox="0 0 1 1"
            preserveAspectRatio="none"
          >
            <defs>
              <pattern id={hatchId} patternUnits="userSpaceOnUse" width="0.03" height="0.05">
                <rect width="0.03" height="0.05" style={{ fill: "var(--vg-zone-hazard-fill)" }} />
                <path
                  d="M0 0.05 L0.03 0"
                  style={{ stroke: "var(--vg-zone-hazard)" }}
                  strokeWidth={2}
                  vectorEffect="non-scaling-stroke"
                />
              </pattern>
            </defs>

            {zones.map((z) => {
              const hazard = z.hazard;
              return (
                <g key={z.id} pointerEvents="none">
                  <polygon className="vg-overlay-halo" points={pts(z.points)} />
                  <polygon
                    points={pts(z.points)}
                    style={{
                      stroke: hazard ? "var(--vg-zone-hazard)" : "var(--vg-zone-restricted)",
                      fill: hazard ? `url(#${hatchId})` : "var(--vg-zone-restricted-fill)",
                    }}
                    strokeWidth={hazard ? 2.5 : 2}
                    strokeDasharray={hazard ? "6 3" : "10 6"}
                    vectorEffect="non-scaling-stroke"
                  />
                </g>
              );
            })}

            {persons?.map((person, index) => {
              const kind = personOutline(person);
              const selected = person.id === selectedPersonId;
              const zoneName = zoneNameFor(zones, person.zone_id);
              const count = person.findings.length;
              const label = `${personLabel(person, index)}, ${count} ${count === 1 ? "finding" : "findings"}, ${zoneName}`;
              return (
                <g key={person.id}>
                  <polygon className="vg-overlay-halo" points={pts(person.polygon)} />
                  <polygon
                    className="vg-person"
                    points={pts(person.polygon)}
                    data-selected={selected ? "true" : "false"}
                    style={{ stroke: `var(--vg-sev-${kind}-stroke)`, pointerEvents: interactive ? "auto" : "none" }}
                    role={interactive ? "button" : undefined}
                    tabIndex={interactive ? 0 : -1}
                    aria-label={interactive ? label : undefined}
                    aria-pressed={interactive ? selected : undefined}
                    onClick={interactive ? () => onSelectPerson?.(person.id) : undefined}
                    onKeyDown={interactive ? (e) => handleKey(e, person.id) : undefined}
                  />
                </g>
              );
            })}

            {previewPoints && previewPoints.length >= 2 ? (
              <g pointerEvents="none">
                {previewPoints.length >= 3 ? (
                  <polygon points={pts(previewPoints)} style={{ fill: "var(--vg-zone-restricted-fill)", stroke: "none" }} />
                ) : null}
                <polyline
                  points={pts(previewPoints)}
                  fill="none"
                  style={{ stroke: "var(--vg-accent)" }}
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  vectorEffect="non-scaling-stroke"
                />
              </g>
            ) : null}
          </svg>

          {zones.map((z) => {
            const { left, top } = bounds(z.points);
            return (
              <span
                key={`label-${z.id}`}
                className="pointer-events-none absolute rounded-vg-sm bg-vg-surface px-1.5 py-0.5 text-xs font-medium text-vg-text shadow-vg-1"
                style={{ left: `${left * 100}%`, top: `${top * 100}%`, lineHeight: "16px", marginTop: 4, marginLeft: 4 }}
              >
                {z.name}
              </span>
            );
          })}

          {draftPoints?.map((p, i) => (
            <span
              key={`draft-${i}`}
              className="pointer-events-none absolute size-2 rounded-full border border-vg-surface bg-vg-accent"
              style={{ left: `${p.x * 100}%`, top: `${p.y * 100}%`, transform: "translate(-50%, -50%)" }}
            />
          ))}
        </div>
      </div>
      {caption ? <div className="text-xs text-vg-text-tertiary">{caption}</div> : null}
    </div>
  );
}
