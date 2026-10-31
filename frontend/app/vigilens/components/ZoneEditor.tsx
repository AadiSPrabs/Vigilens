import { IconArrowBackUp, IconPhotoPlus, IconRotate, IconTrash } from "@tabler/icons-react";
import { useState, type DragEvent } from "react";

import { Button } from "@/components/ui/button";
import type { SampleId } from "../fixtures/audits";
import { MAX_ZONES, validateZonePoints } from "../geometry";
import type { Point, Zone } from "../types";
import type { Source } from "../useVigilens";
import { Spinner } from "./primitives";

export type Draft = { points: Point[]; name: string; hazard: boolean; error: string | null };

const ACCEPTED = ["image/jpeg", "image/png", "image/webp"];
const MAX_BYTES = 15 * 1024 * 1024;
export const SAMPLES: { id: SampleId; label: string; url: string }[] = [
  { id: "sample-1", label: "Sample 1", url: "/vigilens/sample-1.svg" },
  { id: "sample-2", label: "Sample 2", url: "/vigilens/sample-2.svg" },
  { id: "sample-3", label: "Sample 3", url: "/vigilens/sample-3.svg" },
];

type Props = {
  source: Source | null;
  zones: Zone[];
  runWithoutZones: boolean;
  zonesEdited: boolean;
  loading: boolean;
  analyseBlockedReason: string | null;
  draft: Draft | null;
  onPickSample: (id: SampleId) => void;
  onPickFile: (file: File) => void;
  onSetRunWithoutZones: (v: boolean) => void;
  onResetZones: () => void;
  onSetZones: (zones: Zone[]) => void;
  onStartDraft: () => void;
  onCancelDraft: () => void;
  onUndo: () => void;
  onClearPoints: () => void;
  onFinishDraft: () => void;
  onAddCentre: () => void;
  onNudgeLast: (dx: number, dy: number) => void;
  onDraftName: (name: string) => void;
  onDraftHazard: (v: boolean) => void;
  onAnalyse: () => void;
  analyseDisabled: boolean;
};

export function ZoneEditor(props: Props) {
  const {
    source, zones, runWithoutZones, zonesEdited, loading, analyseBlockedReason, draft,
  } = props;
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);

  const acceptFile = (file: File | undefined) => {
    if (!file) return;
    if (!ACCEPTED.includes(file.type)) {
      setUploadError("That file type is not supported. Use a JPG, PNG or WebP image.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setUploadError("That file is larger than 15 MB. Choose a smaller image.");
      return;
    }
    setUploadError(null);
    props.onPickFile(file);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    acceptFile(e.dataTransfer.files[0]);
  };

  const hasSource = source !== null;
  const canDraw = hasSource && !loading && zones.length < MAX_ZONES;
  const draftError = draft ? validateZonePoints(draft.points) : null;

  return (
    <section aria-labelledby="zone-editor-title" className="flex flex-col gap-4 rounded-vg-lg border border-vg-border bg-vg-surface p-4 shadow-vg-1">
      <h2 id="zone-editor-title" className="text-lg font-semibold text-vg-text">Photo and zones</h2>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium text-vg-text">Upload a photo</h3>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`flex min-h-24 flex-col items-center justify-center gap-2 rounded-vg-md border border-dashed p-4 text-center ${dragging ? "border-vg-accent bg-vg-selected" : "border-vg-border-strong"}`}
          >
            <IconPhotoPlus size={22} stroke={1.5} className="text-vg-text-tertiary" aria-hidden="true" />
            <p className="text-sm text-vg-text-secondary">Drop a JPG, PNG or WebP here (15 MB max)</p>
            <label className="inline-flex min-h-10 cursor-pointer items-center rounded-vg-md border border-vg-border-strong px-3 text-sm font-medium text-vg-text hover:bg-vg-hover focus-within:ring-2 focus-within:ring-vg-focus-ring">
              Choose file
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="sr-only"
                onChange={(e) => { acceptFile(e.target.files?.[0]); e.target.value = ""; }}
              />
            </label>
          </div>
          {uploadError ? <p role="alert" className="text-sm text-sev-critical-fg">{uploadError}</p> : null}
        </div>

        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium text-vg-text">Bundled samples</h3>
          <div className="grid grid-cols-3 gap-2">
            {SAMPLES.map((s) => {
              const selected = source?.kind === "sample" && source.sampleId === s.id;
              return (
                <button
                  key={s.id}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => props.onPickSample(s.id)}
                  className={`flex flex-col gap-1 rounded-vg-md border p-1.5 text-left transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-vg-focus-ring ${selected ? "border-vg-accent bg-vg-selected" : "border-vg-border hover:bg-vg-hover"}`}
                >
                  <img src={s.url} alt={`${s.label} site scene`} className="aspect-video w-full rounded-vg-sm object-cover" />
                  <span className="px-0.5 text-xs font-medium text-vg-text">{s.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3 border-t border-vg-border pt-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-medium text-vg-text">Zones</h3>
          <div className="flex flex-wrap gap-2">
            {zonesEdited ? (
              <Button type="button" variant="outline" className="min-h-10" onClick={props.onResetZones}>
                <IconRotate size={16} aria-hidden="true" />
                Reset to sample zones
              </Button>
            ) : null}
            {!draft ? (
              <Button type="button" variant="outline" className="min-h-10" disabled={!canDraw} onClick={props.onStartDraft}>
                Draw zone
              </Button>
            ) : null}
          </div>
        </div>
        {!hasSource ? <p className="text-sm text-vg-text-secondary">Choose a photo before drawing zones.</p> : null}
        {zones.length >= MAX_ZONES ? <p className="text-sm text-vg-text-secondary">A photo can have at most {MAX_ZONES} zones.</p> : null}

        {draft ? (
          <div className="flex flex-col gap-3 rounded-vg-md border border-vg-border bg-vg-surface-sunken p-3">
            <p className="text-sm text-vg-text-secondary">
              Click the photo to add points. {draft.points.length} {draft.points.length === 1 ? "point" : "points"} so far, at least 3 needed.
            </p>
            <div
              tabIndex={0}
              role="group"
              aria-label="Keyboard drawing: arrow keys nudge the last point, Shift moves it faster"
              onKeyDown={(e) => {
                if (!draft.points.length) return;
                const step = e.shiftKey ? 0.02 : 0.005;
                const map: Record<string, [number, number]> = {
                  ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step],
                };
                const d = map[e.key];
                if (d) { e.preventDefault(); props.onNudgeLast(d[0], d[1]); }
              }}
              className="flex flex-wrap gap-2 rounded-vg-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-vg-focus-ring"
            >
              <Button type="button" variant="outline" className="min-h-10" onClick={props.onAddCentre}>Add point at centre</Button>
              <Button type="button" variant="outline" className="min-h-10" onClick={props.onUndo} disabled={!draft.points.length}>
                <IconArrowBackUp size={16} aria-hidden="true" />
                Undo last point
              </Button>
              <Button type="button" variant="outline" className="min-h-10" onClick={props.onClearPoints} disabled={!draft.points.length}>
                Clear points
              </Button>
            </div>
            <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
              <label className="flex flex-col gap-1 text-sm text-vg-text">
                Zone name
                <input
                  value={draft.name}
                  maxLength={200}
                  required
                  onChange={(e) => props.onDraftName(e.target.value)}
                  className="min-h-10 rounded-vg-md border border-vg-border-strong bg-vg-surface px-3 text-base text-vg-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-vg-focus-ring"
                />
              </label>
              <button
                type="button"
                role="switch"
                aria-checked={draft.hazard}
                onClick={() => props.onDraftHazard(!draft.hazard)}
                className="flex min-h-10 items-center gap-2 text-sm text-vg-text"
              >
                <Switch on={draft.hazard} />
                Hazard zone
              </button>
            </div>
            {draft.error || draftError ? <p role="alert" className="text-sm text-sev-critical-fg">{draft.error ?? draftError}</p> : null}
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                className="min-h-10"
                onClick={() => {
                  if (!draft.name.trim()) {
                    setNameError("Enter a zone name before finishing.");
                    return;
                  }
                  setNameError(null);
                  props.onFinishDraft();
                }}
                disabled={draft.points.length < 3 || !!draftError}
              >
                Finish zone
              </Button>
              <Button type="button" variant="ghost" className="min-h-10" onClick={props.onCancelDraft}>Cancel</Button>
              {nameError ? <p role="alert" className="self-center text-sm text-sev-critical-fg">{nameError}</p> : null}
            </div>
          </div>
        ) : null}

        {zones.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {zones.map((z) => (
              <ZoneRow
                key={z.id}
                zone={z}
                onRename={(name) => props.onSetZones(zones.map((x) => (x.id === z.id ? { ...x, name } : x)))}
                onToggleHazard={() => props.onSetZones(zones.map((x) => (x.id === z.id ? { ...x, hazard: !x.hazard } : x)))}
                onDelete={() => props.onSetZones(zones.filter((x) => x.id !== z.id))}
              />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-vg-text-secondary">No zones drawn. Draw a zone to tell the audit where to check.</p>
        )}

        <label className="flex min-h-10 items-center gap-2 text-sm text-vg-text">
          <input
            type="checkbox"
            checked={runWithoutZones}
            onChange={(e) => props.onSetRunWithoutZones(e.target.checked)}
            className="size-4"
            style={{ accentColor: "var(--vg-accent)" }}
          />
          Run without zones
        </label>
      </div>

      <div className="flex flex-col gap-2 border-t border-vg-border pt-4">
        {analyseBlockedReason ? <p className="text-sm text-vg-text-secondary">{analyseBlockedReason}</p> : null}
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="default"
            className="min-h-11 px-5"
            disabled={props.analyseDisabled}
            onClick={props.onAnalyse}
          >
            Analyse
          </Button>
          {loading ? <Spinner label="Analysing photo" /> : null}
        </div>
      </div>
    </section>
  );
}

export function Switch({ on }: { on: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`relative inline-flex h-6 w-10 shrink-0 items-center rounded-full border transition-colors duration-150 ${on ? "border-vg-accent bg-vg-accent" : "border-vg-border-strong bg-vg-surface-sunken"}`}
    >
      <span className={`absolute size-4 rounded-full bg-vg-surface transition-transform duration-150 ${on ? "translate-x-[18px]" : "translate-x-[3px]"}`} />
    </span>
  );
}

function ZoneRow({
  zone,
  onRename,
  onToggleHazard,
  onDelete,
}: {
  zone: Zone;
  onRename: (name: string) => void;
  onToggleHazard: () => void;
  onDelete: () => void;
}) {
  const [name, setName] = useState(zone.name);
  const [error, setError] = useState<string | null>(null);
  const commit = () => {
    const trimmed = name.trim();
    if (trimmed.length < 1 || trimmed.length > 200) {
      setError("Zone names need 1 to 200 characters.");
      setName(zone.name);
      return;
    }
    setError(null);
    if (trimmed !== zone.name) onRename(trimmed);
  };
  return (
    <li className="flex flex-col gap-1 rounded-vg-md border border-vg-border p-2">
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="size-4 shrink-0 rounded-vg-sm border"
          style={{
            borderColor: zone.hazard ? "var(--vg-zone-hazard)" : "var(--vg-zone-restricted)",
            background: zone.hazard ? "var(--vg-zone-hazard-fill)" : "var(--vg-zone-restricted-fill)",
          }}
        />
        <input
          aria-label={`Zone name for ${zone.name}`}
          value={name}
          maxLength={200}
          onChange={(e) => setName(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
          className="min-h-10 min-w-0 flex-1 rounded-vg-sm border border-transparent bg-transparent px-2 text-sm text-vg-text hover:border-vg-border focus-visible:border-vg-focus-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-vg-focus-ring"
        />
        <button
          type="button"
          role="switch"
          aria-checked={zone.hazard}
          onClick={onToggleHazard}
          className="flex min-h-10 shrink-0 items-center gap-2 text-xs text-vg-text-secondary"
        >
          <Switch on={zone.hazard} />
          <span className="hidden sm:inline">Hazard</span>
        </button>
        <button
          type="button"
          aria-label={`Delete zone ${zone.name}`}
          onClick={onDelete}
          className="inline-flex size-10 shrink-0 items-center justify-center rounded-vg-md text-vg-text-secondary hover:bg-vg-hover hover:text-vg-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-vg-focus-ring"
        >
          <IconTrash size={18} stroke={1.75} aria-hidden="true" />
        </button>
      </div>
      {error ? <p role="alert" className="pl-6 text-xs text-sev-critical-fg">{error}</p> : null}
    </li>
  );
}

