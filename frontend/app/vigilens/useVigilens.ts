import { useCallback, useEffect, useReducer, useRef } from "react";

import { analyzeImage, FIXTURE_UPLOAD_MESSAGE } from "./api/auditClient";
import { SAMPLE_PRESET_ZONES, type SampleId } from "./fixtures/audits";
import { formatClock } from "./format";
import { MAX_ZONES } from "./geometry";
import type { Audit, ReviewDecision, Zone } from "./types";

export const UPLOAD_ZONES_KEY = "vigilens-upload-zones";

export type Source =
  | { kind: "sample"; sampleId: SampleId; imageUrl: string }
  | { kind: "upload"; imageUrl: string; name: string; file: File };

export type Filters = { severity: string; zone: string };

export type State = {
  source: Source | null;
  zones: Zone[];
  runWithoutZones: boolean;
  runId: number;
  status: "idle" | "loading" | "error" | "success";
  audit: Audit | null;
  error: string | null;
  loadedAt: string | null;
  reviews: Record<string, ReviewDecision>;
  selectedPersonId: string | null;
  filters: Filters;
};

type Action =
  | { type: "source"; source: Source; zones: Zone[] }
  | { type: "zones"; zones: Zone[] }
  | { type: "runWithoutZones"; value: boolean }
  | { type: "start"; runId: number }
  | { type: "success"; runId: number; audit: Audit; loadedAt: string }
  | { type: "fail"; runId: number; message: string }
  | { type: "cancel" }
  | { type: "review"; findingId: string; value: ReviewDecision }
  | { type: "select"; personId: string | null }
  | { type: "filters"; filters: Partial<Filters> };

export const initialState: State = {
  source: null,
  zones: [],
  runWithoutZones: false,
  runId: 0,
  status: "idle",
  audit: null,
  error: null,
  loadedAt: null,
  reviews: {},
  selectedPersonId: null,
  filters: { severity: "all", zone: "all" },
};

function cleared(state: State): State {
  return {
    ...state,
    runId: state.runId + 1,
    status: "idle",
    audit: null,
    error: null,
    loadedAt: null,
    reviews: {},
    selectedPersonId: null,
    filters: { severity: "all", zone: "all" },
  };
}

export function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "source":
      return { ...cleared(state), source: action.source, zones: action.zones, runWithoutZones: false };
    case "zones": {
      const added = action.zones.length > state.zones.length;
      return { ...cleared(state), zones: action.zones, runWithoutZones: added ? false : state.runWithoutZones };
    }
    case "runWithoutZones":
      return { ...cleared(state), runWithoutZones: action.value };
    case "start":
      return { ...state, runId: action.runId, status: "loading", error: null, audit: null };
    case "success":
      if (action.runId !== state.runId) return state;
      return { ...state, status: "success", audit: action.audit, loadedAt: action.loadedAt, error: null };
    case "fail":
      if (action.runId !== state.runId) return state;
      return { ...state, status: "error", error: action.message, audit: null };
    case "cancel":
      return { ...state, status: "idle" };
    case "review":
      return { ...state, reviews: { ...state.reviews, [action.findingId]: action.value } };
    case "select":
      return { ...state, selectedPersonId: action.personId };
    case "filters":
      return { ...state, filters: { ...state.filters, ...action.filters } };
  }
}

function loadUploadZones(): Zone[] {
  try {
    const raw = window.localStorage.getItem(UPLOAD_ZONES_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as Zone[]).slice(0, MAX_ZONES) : [];
  } catch {
    return [];
  }
}

function saveUploadZones(zones: Zone[]) {
  try {
    window.localStorage.setItem(UPLOAD_ZONES_KEY, JSON.stringify(zones));
  } catch {
    /* storage unavailable; zones stay in memory for this view */
  }
}

export function sampleZonesEqual(zones: Zone[], sampleId: SampleId) {
  const preset = SAMPLE_PRESET_ZONES[sampleId];
  return JSON.stringify(zones) === JSON.stringify(preset);
}

export function useVigilens(announce: (text: string) => void) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const controllerRef = useRef<AbortController | null>(null);
  const uploadUrlRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
      if (uploadUrlRef.current) URL.revokeObjectURL(uploadUrlRef.current);
    };
  }, []);

  const chooseSample = useCallback((sampleId: SampleId, imageUrl: string) => {
    if (uploadUrlRef.current) {
      URL.revokeObjectURL(uploadUrlRef.current);
      uploadUrlRef.current = null;
    }
    dispatch({
      type: "source",
      source: { kind: "sample", sampleId, imageUrl },
      zones: structuredClone(SAMPLE_PRESET_ZONES[sampleId]),
    });
  }, []);

  const chooseUpload = useCallback((file: File) => {
    if (uploadUrlRef.current) URL.revokeObjectURL(uploadUrlRef.current);
    const url = URL.createObjectURL(file);
    uploadUrlRef.current = url;
    dispatch({
      type: "source",
      source: { kind: "upload", imageUrl: url, name: file.name, file },
      zones: loadUploadZones(),
    });
  }, []);

  const setZones = useCallback(
    (zones: Zone[]) => {
      if (state.source?.kind === "upload") saveUploadZones(zones);
      dispatch({ type: "zones", zones });
    },
    [state.source],
  );

  const setRunWithoutZones = useCallback((value: boolean) => dispatch({ type: "runWithoutZones", value }), []);

  const cancel = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    dispatch({ type: "cancel" });
    announce("Analysis cancelled.");
  }, [announce]);

  const analyse = useCallback(() => {
    const { source, zones, runWithoutZones } = state;
    if (!source) return;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const runId = state.runId;
    dispatch({ type: "start", runId });
    analyzeImage({
      file: source.kind === "upload" ? source.file : null,
      zones: runWithoutZones ? [] : zones,
      sampleId: source.kind === "sample" ? source.sampleId : null,
      signal: controller.signal,
    })
      .then((audit) => {
        if (controller.signal.aborted) return;
        controllerRef.current = null;
        dispatch({ type: "success", runId, audit, loadedAt: formatClock(new Date()) });
        announce(`Analysis complete. ${audit.persons.reduce((n, p) => n + p.findings.length, 0)} findings.`);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        controllerRef.current = null;
        const message = err instanceof Error && err.message ? err.message : FIXTURE_UPLOAD_MESSAGE;
        dispatch({ type: "fail", runId, message });
        announce(`Analysis failed. ${message}`);
      });
  }, [state, announce]);

  return {
    state,
    chooseSample,
    chooseUpload,
    setZones,
    setRunWithoutZones,
    analyse,
    cancel,
    dispatch,
  };
}
