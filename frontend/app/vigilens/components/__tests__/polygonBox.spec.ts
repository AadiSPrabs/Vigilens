import { describe, expect, it } from "vitest";
import { polygonBox } from "../PreviewCeremony";

describe("polygonBox (backend corner-box semantics [x1,y1,x2,y2])", () => {
  it("converts a normalized polygon to clamped corner coordinates", () => {
    const box = polygonBox([{ x: 0.2, y: 0.25 }, { x: 0.6, y: 0.25 }, { x: 0.6, y: 0.75 }, { x: 0.2, y: 0.75 }], 100, 80);
    expect(box).toEqual([20, 20, 60, 60]);
  });
  it("clamps to the frame", () => {
    const box = polygonBox([{ x: -0.5, y: -0.5 }, { x: 1.5, y: 0.5 }, { x: 0.5, y: 1.5 }], 100, 80);
    expect(box).toEqual([0, 0, 100, 80]);
  });
  it("returns null for missing, short, non-finite or degenerate polygons", () => {
    expect(polygonBox([], 100, 80)).toBeNull();
    expect(polygonBox([{ x: 0.1, y: 0.1 }, { x: 0.2, y: 0.2 }], 100, 80)).toBeNull();
    expect(polygonBox([{ x: NaN, y: 0.1 }, { x: 0.2, y: 0.2 }, { x: 0.3, y: 0.3 }], 100, 80)).toBeNull();
    expect(polygonBox([{ x: 0.5, y: 0.5 }, { x: 0.5, y: 0.5 }, { x: 0.5, y: 0.5 }], 100, 80)).toBeNull();
  });
});
