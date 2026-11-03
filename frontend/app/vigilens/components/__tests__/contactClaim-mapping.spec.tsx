// @vitest-environment happy-dom
// Real-sized (1600x1000, non-square) geometry: a click maps to the same normalized point at any display size, which the
// backend scales by the source frame; labels equal the backend's labels for the same result; a new session resets the panel.
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { ContactClaimPanel } from "../ContactClaimPanel";
import { personMappings } from "../../format";
import parity from "./fixtures/person-label-parity.json";
import type { Audit, Person } from "../../types";

const SOURCE = "a".repeat(64);
const persons = parity.audit_persons as unknown as Person[];
const audit = { audit_id: "fresh:abc:def", source: "backend", image: { pixel_digest: SOURCE, width: 1600, height: 1000 }, persons } as unknown as Audit;
const sess = (id: string) => ({ session_id: id, source_digest: SOURCE, output_sha256: "b".repeat(64), regions_digest: "c".repeat(64), width: 1600, height: 1000 });
let container: HTMLDivElement;
let root: Root;
afterEach(async () => { if (root) { await act(async () => root.unmount()); container.remove(); root = undefined as unknown as Root; } vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const mountWith = async (rect: { left: number; top: number; width: number; height: number }, s = sess("sess-aaaaaaaa")) => {
  const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ ...rect, right: rect.left + rect.width, bottom: rect.top + rect.height, x: rect.left, y: rect.top, toJSON: () => ({}) });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(createElement(ContactClaimPanel, { audit, session: s as never })); });
  return fetchMock;
};
const choose = async (id: string) => { const sel = container.querySelector("select")!; await act(async () => { sel.value = id; sel.dispatchEvent(new Event("change", { bubbles: true })); }); };
const clickAt = async (x: number, y: number) => { await act(async () => { container.querySelector("img")!.parentElement!.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: x, clientY: y })); }); };
const fill = async () => {
  for (const b of container.querySelectorAll("input[type=checkbox]")) await act(async () => { b.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
  const input = container.querySelector("input[type=text]") as HTMLInputElement;
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "assistant test"); input.dispatchEvent(new Event("input", { bubbles: true })); });
};
const save = async () => { const b = [...container.querySelectorAll("button")].find((x) => x.textContent === "Record contact claim")!; await act(async () => { b.dispatchEvent(new MouseEvent("click", { bubbles: true })); }); };

describe("contact click mapping on a 1600x1000 source", () => {
  it("frontend labels equal the backend labels for the same stored result", () => {
    const m = personMappings(persons);
    for (const [id, expected] of Object.entries(parity.backend_labels as Record<string, { label: string; mapped: boolean }>)) {
      expect(m.get(id)).toMatchObject({ mapped: expected.mapped, label: expected.label });
    }
  });

  // Display sizes and page offsets differ; the source point is always the same fraction of the frame.
  it.each([
    { left: 0, top: 0, width: 1600, height: 1000 },
    { left: 40, top: 300, width: 800, height: 500 },
    { left: 17, top: 55, width: 354, height: 221.25 },
  ])("posts the same normalized point and expected source pixel at display %j", async (rect) => {
    const f = await mountWith(rect);
    await choose("7");
    // Person 1 (id 7) source box is x 300..640, y 220..900. Aim at source pixel (480, 880) = (0.3, 0.88).
    await clickAt(rect.left + rect.width * 0.3, rect.top + rect.height * 0.88);
    await fill();
    await save();
    const body = JSON.parse(String(f.mock.calls[0]![1].body));
    expect(body.person_id).toBe("7");
    expect(body.point[0]).toBeCloseTo(0.3, 6);
    expect(body.point[1]).toBeCloseTo(0.88, 6);
    expect(body.point[0] * 1600).toBeCloseTo(480, 3);
    expect(body.point[1] * 1000).toBeCloseTo(880, 3);
    expect(body.point[0] * 1600).toBeGreaterThanOrEqual(300);
    expect(body.point[0] * 1600).toBeLessThan(640);
  });

  it("a point on Person 2's body is refused for Person 1 and posts nothing", async () => {
    const f = await mountWith({ left: 0, top: 0, width: 800, height: 500 });
    await choose("7");
    await clickAt(800 * 0.7, 500 * 0.8);
    expect(container.textContent).toContain("Click inside the outline of Person 1");
    expect(f).not.toHaveBeenCalled();
  });

  it("a session change clears the point, confirmations and recorded markers", async () => {
    const f = await mountWith({ left: 0, top: 0, width: 800, height: 500 });
    await choose("7");
    await clickAt(240, 440);
    await fill();
    expect(container.querySelector("[data-testid=contact-point]")).not.toBeNull();
    await act(async () => { root.render(createElement(ContactClaimPanel, { audit, session: sess("sess-bbbbbbbb") as never })); });
    expect(container.querySelector("[data-testid=contact-point]")).toBeNull();
    expect((container.querySelector("select") as HTMLSelectElement).value).toBe("");
    expect([...container.querySelectorAll("input[type=checkbox]")].every((c) => !(c as HTMLInputElement).checked)).toBe(true);
    expect(f).not.toHaveBeenCalled();
  });
});
