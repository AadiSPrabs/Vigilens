// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { ContactClaimPanel } from "../ContactClaimPanel";
import type { Audit } from "../../types";

const SOURCE = "a".repeat(64);
const box = (x1: number, x2: number) => [{ x: x1, y: 0.2 }, { x: x2, y: 0.2 }, { x: x2, y: 0.9 }, { x: x1, y: 0.9 }];
const audit = {
  audit_id: "fresh:abc:def", source: "backend", image: { pixel_digest: SOURCE, width: 100, height: 100 },
  persons: [{ id: "7", polygon: box(0.1, 0.3) }, { id: "3", polygon: box(0.5, 0.6) }, { id: "3", polygon: box(0.7, 0.8) }],
} as unknown as Audit;
const session = { session_id: "sess-12345678", source_digest: SOURCE, output_sha256: "b".repeat(64), regions_digest: "c".repeat(64), width: 100, height: 100 };
let container: HTMLDivElement;
let root: Root;
afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function mount(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100, x: 0, y: 0, toJSON: () => ({}) });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(createElement(ContactClaimPanel, { audit, session: session as never })); });
  return fetchMock;
}
const click = async (el: Element) => { await act(async () => { el.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: Number((el as HTMLElement).dataset.cx ?? 0), clientY: 0 })); }); };
const clickAt = async (x: number, y: number) => {
  const wrap = container.querySelector("img")!.parentElement!;
  await act(async () => { wrap.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: x, clientY: y })); });
};
const saveBtn = () => [...container.querySelectorAll("button")].find((b) => b.textContent === "Record contact claim") as HTMLButtonElement;
async function choose(id: string) {
  const sel = container.querySelector("select")!;
  await act(async () => { sel.value = id; sel.dispatchEvent(new Event("change", { bubbles: true })); });
}
async function type(value: string) {
  const input = container.querySelector("input[type=text]") as HTMLInputElement;
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  await act(async () => { setter.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); });
}

describe("ContactClaimPanel", () => {
  it("offers only mapped people, with the backend id, and no unmapped duplicate ids", async () => {
    await mount(new Response("{}", { status: 200 }));
    const options = [...container.querySelectorAll("option")].map((o) => o.textContent);
    expect(options).toEqual(["Choose a person", "Person 1 (backend id 7)"]);
  });

  it("refuses a point outside the chosen outline and needs both confirmations, a name and a point", async () => {
    const f = await mount(new Response("{}", { status: 200 }));
    await choose("7");
    await clickAt(90, 50);
    expect(container.querySelector("[data-testid=contact-point]")).toBeNull();
    expect(container.textContent).toContain("Click inside the outline of Person 1");
    expect(saveBtn().disabled).toBe(true);
    await clickAt(20, 80);
    expect(container.querySelector("[data-testid=contact-point]")).not.toBeNull();
    expect(saveBtn().disabled).toBe(true);
    const boxes = [...container.querySelectorAll("input[type=checkbox]")] as HTMLInputElement[];
    for (const b of boxes) await click(b);
    expect(saveBtn().disabled).toBe(true); // still no name
    await type("assistant test");
    expect(saveBtn().disabled).toBe(false);
    expect(f).not.toHaveBeenCalled();
  });

  it("posts the exact claim shape and reports it as the operator's own claim", async () => {
    const f = await mount(new Response(JSON.stringify({ manual_contact: { event_id: 1 }, automatic_contact: false }), { status: 200 }));
    await choose("7");
    await clickAt(20, 80);
    for (const b of [...container.querySelectorAll("input[type=checkbox]")]) await click(b);
    await type("assistant test");
    await click(saveBtn());
    expect(f).toHaveBeenCalledTimes(1);
    const [url, init] = f.mock.calls[0]!;
    expect(String(url)).toBe(`/api/vigilens/fresh-review/${SOURCE}/contact`);
    expect(JSON.parse(String(init.body))).toEqual({ person_id: "7", point: [0.2, 0.8], exact_source_confirmed: true, boots_ground_visible: true, reviewer_label: "assistant test" });
    expect(container.textContent).toContain("It is your claim, not an automatic reading");
  });

  it("shows the backend refusal as-is and records nothing", async () => {
    await mount(new Response(JSON.stringify({ detail: "Point outside verified person foreground" }), { status: 409 }));
    await choose("7");
    await clickAt(20, 80);
    for (const b of [...container.querySelectorAll("input[type=checkbox]")]) await click(b);
    await type("assistant test");
    await click(saveBtn());
    expect(container.textContent).toContain("Point outside verified person foreground");
    expect(container.textContent).not.toContain("Contact claim recorded");
  });
});
