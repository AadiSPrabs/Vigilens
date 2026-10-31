import { useCallback, useEffect, useState } from "react";

import { ImageStage } from "@/vigilens/components/ImageStage";
import { Inspector } from "@/vigilens/components/Inspector";
import { PrintReport } from "@/vigilens/components/PrintReport";
import { BannerStack } from "@/vigilens/components/BannerStack";
import { TopBar } from "@/vigilens/components/TopBar";
import { SAMPLES, ZoneEditor, type Draft } from "@/vigilens/components/ZoneEditor";
import { SAMPLE_PRESET_ZONES, type SampleId } from "@/vigilens/fixtures/audits";
import { canAppendPoint, isNearPrevious, MAX_ZONES, validateZonePoints } from "@/vigilens/geometry";
import { applyThemePref, readThemePref, writeThemePref, type ThemePref } from "@/vigilens/theme";
import { sampleZonesEqual, useVigilens } from "@/vigilens/useVigilens";
import type { Point, Zone } from "@/vigilens/types";

export function meta() {
  return [{ title: "Vigilens" }, { name: "description", content: "PPE and site-safety audit prototype" }];
}

function nextZoneId(zones: Zone[]) {
  const max = zones.reduce((m, z) => {
    const n = /^zone-(\d+)$/.exec(z.id);
    return n ? Math.max(m, Number(n[1])) : m;
  }, 0);
  return `zone-${max + 1}`;
}

export default function VigilensRoute() {
  const [announcement, setAnnouncement] = useState("");
  const announce = useCallback((text: string) => setAnnouncement(text), []);
  const vg = useVigilens(announce);
  const { state, dispatch } = vg;
  const { source, zones, runWithoutZones, audit, status, error, loadedAt, reviews, selectedPersonId, filters } = state;

  const [draft, setDraft] = useState<Draft | null>(null);
  const [theme, setTheme] = useState<ThemePref>("system");

  useEffect(() => {
    setTheme(readThemePref());
  }, []);

  useEffect(() => {
    applyThemePref(theme);
    writeThemePref(theme);
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyThemePref("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [theme]);

  const sampleId = source?.kind === "sample" ? source.sampleId : null;
  const effectiveZones = runWithoutZones ? [] : zones;
  const zonesEdited = sampleId !== null && !sampleZonesEqual(zones, sampleId);
  const sampleBlocked = sampleId !== null && !sampleZonesEqual(effectiveZones, sampleId);
  const analyseDisabled = !source || status === "loading" || sampleBlocked;
  const analyseBlockedReason = sampleBlocked
    ? runWithoutZones
      ? "Fixture results need the sample's preset zones. Untick Run without zones to continue."
      : "Fixture results need the sample's preset zones. Reset to sample zones to continue."
    : null;

  const pickSample = (id: SampleId) => {
    setDraft(null);
    const url = SAMPLES.find((s) => s.id === id)?.url ?? "";
    vg.chooseSample(id, url);
  };

  const pickFile = (file: File) => {
    setDraft(null);
    vg.chooseUpload(file);
  };

  const startDraft = () => setDraft({ points: [], name: "", hazard: false, error: null });

  const addPoint = (p: Point) =>
    setDraft((d) => {
      if (!d || isNearPrevious(d.points, p)) return d;
      const err = canAppendPoint(d.points, p);
      if (err) return { ...d, error: err };
      return { ...d, points: [...d.points, p], error: null };
    });

  const nudgeLast = (dx: number, dy: number) =>
    setDraft((d) => {
      if (!d || d.points.length === 0) return d;
      const points = d.points.slice();
      const last = points[points.length - 1];
      if (!last) return d;
      const clamp = (v: number) => Math.min(1, Math.max(0, v));
      points[points.length - 1] = { x: clamp(last.x + dx), y: clamp(last.y + dy) };
      return { ...d, points, error: null };
    });

  const finishDraft = () => {
    if (!draft) return;
    const name = draft.name.trim();
    if (name.length < 1 || name.length > 200) {
      setDraft({ ...draft, error: "Zone names need 1 to 200 characters." });
      return;
    }
    const pointError = validateZonePoints(draft.points);
    if (pointError) {
      setDraft({ ...draft, error: pointError });
      return;
    }
    if (zones.length >= MAX_ZONES) {
      setDraft({ ...draft, error: `A photo can have at most ${MAX_ZONES} zones.` });
      return;
    }
    vg.setZones([...zones, { id: nextZoneId(zones), name, hazard: draft.hazard, points: draft.points }]);
    setDraft(null);
  };

  const audited = audit !== null;
  const displayZones = audit ? audit.zones : zones;

  return (
    <>
      <h1 className="sr-only">Vigilens</h1>
      <div className="vg-screen flex min-h-full flex-col bg-vg-bg text-vg-text">
        <TopBar
          theme={theme}
          onTheme={setTheme}
          onExport={() => window.print()}
          exportDisabled={!audit}
        />
        <BannerStack audit={audit} />

        <div className="grid flex-1 grid-cols-1 items-start gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="flex min-w-0 flex-col gap-4">
            <ImageStage
              imageUrl={source?.imageUrl ?? null}
              imageAlt={source?.kind === "sample" ? `${SAMPLES.find((s) => s.id === source.sampleId)?.label} site scene` : `Uploaded photo ${source?.kind === "upload" ? source.name : ""}`}
              zones={displayZones}
              persons={audit ? audit.persons : null}
              selectedPersonId={selectedPersonId}
              onSelectPerson={(id) => dispatch({ type: "select", personId: id })}
              draftPoints={draft?.points}
              onAddPoint={addPoint}
              drawing={draft !== null}
              caption={
                audited ? (
                  <span>Preview only, not evidence. Masked evidence unavailable.</span>
                ) : source ? (
                  <span>Zones are operator-drawn. The app does not infer them.</span>
                ) : null
              }
            />
            <ZoneEditor
              source={source}
              zones={zones}
              runWithoutZones={runWithoutZones}
              zonesEdited={zonesEdited}
              loading={status === "loading"}
              analyseBlockedReason={analyseBlockedReason}
              analyseDisabled={analyseDisabled}
              draft={draft}
              onPickSample={pickSample}
              onPickFile={pickFile}
              onSetRunWithoutZones={vg.setRunWithoutZones}
              onResetZones={() => sampleId && vg.setZones(structuredClone(SAMPLE_PRESET_ZONES[sampleId]))}
              onSetZones={vg.setZones}
              onStartDraft={startDraft}
              onCancelDraft={() => setDraft(null)}
              onUndo={() => setDraft((d) => (d ? { ...d, points: d.points.slice(0, -1), error: null } : d))}
              onClearPoints={() => setDraft((d) => (d ? { ...d, points: [], error: null } : d))}
              onFinishDraft={finishDraft}
              onAddCentre={() => addPoint({ x: 0.5, y: 0.5 })}
              onNudgeLast={nudgeLast}
              onDraftName={(name) => setDraft((d) => (d ? { ...d, name, error: null } : d))}
              onDraftHazard={(hazard) => setDraft((d) => (d ? { ...d, hazard } : d))}
              onAnalyse={vg.analyse}
            />
          </div>

          <aside className="flex min-w-0 flex-col lg:sticky lg:top-[72px] lg:max-h-[calc(100vh-88px)] lg:overflow-y-auto">
            <Inspector
              audit={audit}
              zones={displayZones}
              status={status}
              error={error}
              loadedAt={loadedAt}
              reviews={reviews}
              onReview={(findingId, value) => dispatch({ type: "review", findingId, value })}
              selectedPersonId={selectedPersonId}
              onSelect={(personId) => dispatch({ type: "select", personId })}
              filters={filters}
              onFilters={(f) => dispatch({ type: "filters", filters: f })}
              onCancel={vg.cancel}
              onRetry={vg.analyse}
            />
          </aside>
        </div>
      </div>

      <PrintReport
        audit={audit}
        zones={displayZones}
        imageUrl={source?.imageUrl ?? null}
        reviews={reviews}
        loadedAt={loadedAt}
      />

      <div aria-live="polite" className="sr-only">
        {announcement}
      </div>
    </>
  );
}
