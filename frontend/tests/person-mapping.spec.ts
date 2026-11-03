import { describe, expect, it } from "vitest";
import { personMappings } from "../app/vigilens/format";

const sq = (x: number) => [{ x, y: 0.1 }, { x: x + 0.2, y: 0.1 }, { x: x + 0.2, y: 0.9 }, { x, y: 0.9 }];
const person = (id: string, polygon: unknown) => ({ id, polygon, findings: [] }) as never;

describe("personMappings", () => {
  it("labels each person by its own record, so ids map to Person N", () => {
    const m = personMappings([person("7", sq(0.1)), person("3", sq(0.6))]);
    expect(m.get("7")).toMatchObject({ mapped: true, label: "Person 1" });
    expect(m.get("3")).toMatchObject({ mapped: true, label: "Person 2" });
  });
  it("marks a person unmapped when the outline is unusable or the id repeats", () => {
    const m = personMappings([person("a", [{ x: 0.1, y: 0.1 }, { x: 0.2, y: 0.2 }]), person("b", sq(0.5)), person("b", sq(0.1))]);
    expect(m.get("a")).toMatchObject({ mapped: false, label: "Unmapped person" });
    expect(m.get("b")?.mapped).toBe(false);
  });
  it("rejects outlines outside the frame", () => {
    expect(personMappings([person("x", [{ x: 0, y: 0 }, { x: 2, y: 0 }, { x: 1, y: 1 }])]).get("x")?.mapped).toBe(false);
  });
});
