import { describe, expect, it } from "vitest";
import { reducer, initialState } from "../app/vigilens/useVigilens";

const zone = { id: "z1", name: "TEST zone", hazard: false, points: [{ x: 0.1, y: 0.1 }, { x: 0.9, y: 0.1 }, { x: 0.5, y: 0.9 }] };

function reopened() {
  const base = initialState;
  return reducer(base, {
    type: "reopened",
    source: { kind: "stored", imageUrl: null, name: "Stored job x", digest: "d" },
    audit: { source: "backend", persons: [] } as never,
    loadedAt: "00:00",
  } as never);
}

describe("zone edits on a reopened stored job", () => {
  it("keep the stored audit and source", () => {
    const s = reducer(reopened(), { type: "zones", zones: [zone] } as never);
    expect(s.audit).not.toBeNull();
    expect(s.source?.kind).toBe("stored");
    expect(s.zones).toHaveLength(1);
  });
  it("ignore the run-without-zones toggle", () => {
    const s = reducer(reopened(), { type: "runWithoutZones", value: false } as never);
    expect(s.audit).not.toBeNull();
  });
});
