// @vitest-environment happy-dom
// Owner-authored rules: nothing defaulted, exact payload from the operator's own entries,
// blocked until every choice is made, reset on a different source/geometry.
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("../../api/backendClient", () => ({ postRuleReview: mocks.post }));
import { RuleReviewPanel } from "../RuleReviewPanel";

const SRC = "a".repeat(64);
const RES = "c".repeat(64);
const SNAP = { zones_sha256: "d".repeat(64), zones: [{ id: "zone-1", name: "Zone A", points: [{ x: 0.1, y: 0.1 }, { x: 0.5, y: 0.1 }, { x: 0.5, y: 0.5 }] }] };

let el: HTMLDivElement;
let root: ReturnType<typeof createRoot>;
async function mount(snapshot = SNAP, source = SRC) {
  (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
  el = document.createElement("div");
  document.body.append(el);
  root = createRoot(el);
  await act(async () => root.render(<RuleReviewPanel sourceDigest={source} resultSha={RES} snapshot={snapshot} enabled />));
}
const q = (label: string) => el.querySelector(`[aria-label="${label}"]`) as HTMLInputElement & HTMLSelectElement;
async function type(label: string, value: string) {
  const node = q(label);
  const proto = node.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  await act(async () => {
    Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(node, value);
    node.dispatchEvent(new Event(node.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
  });
}
const save = () => [...el.querySelectorAll("button")].find((b) => b.textContent?.includes("Save these rules")) as HTMLButtonElement;
async function click(node: Element) { await act(async () => (node as HTMLElement).click()); }

describe("RuleReviewPanel", () => {
  beforeEach(() => { mocks.post.mockReset(); });

  it("starts empty and refuses to submit until the operator has chosen everything", async () => {
    await mount();
    expect(q("Policy id").value).toBe("");
    expect(q("Scope").value).toBe("");
    expect(q("Access mode for Zone A").value).toBe("");
    expect([...el.querySelectorAll("input[type=checkbox]")].every((c) => !(c as HTMLInputElement).checked)).toBe(true);
    await click(save());
    expect(mocks.post).not.toHaveBeenCalled();
    expect(el.textContent).toContain("yours to enter");
  });

  it("sends exactly the operator's entries with exact bindings", async () => {
    mocks.post.mockResolvedValue({});
    await mount();
    await type("Policy id", "my-policy");
    await type("Policy version", "3");
    await type("Camera id", "cam-9");
    await type("Scope", "site_owner_policy");
    await type("Approval reference", "ticket-77");
    await type("Priority labels", "high, low");
    await type("Access mode for Zone A", "authorised_only");
    const boxes = [...el.querySelectorAll("input[type=checkbox]")];
    await click(boxes[1]!); // hardhat required
    await type("Priority for Hardhat required in Zone A", "high");
    await click(save());
    expect(mocks.post).toHaveBeenCalledTimes(1);
    const [src, res, zsha, cfg] = mocks.post.mock.calls[0]!;
    expect([src, res, zsha]).toEqual([SRC, RES, SNAP.zones_sha256]);
    expect(cfg.scope).toBe("site_owner_policy");
    expect(cfg.priorities).toEqual(["high", "low"]);
    expect(cfg.approval_reference).toBe("ticket-77");
    expect(cfg.zones[0].access_mode).toBe("authorised_only");
    expect(cfg.zones[0].rules).toEqual([{ id: "zone-1-helmet_worn", check: "helmet_worn", priority: "high" }]);
    expect(cfg.outside_rules).toEqual([]);
    expect(el.textContent).toContain("not an approval");
  });

  it("blocks an entry-prohibited rule on an allowed zone and surfaces backend refusal", async () => {
    mocks.post.mockRejectedValue(new Error("Rule configuration unavailable (409). No automatic retry."));
    await mount();
    for (const [l, v] of [["Policy id", "p"], ["Policy version", "1"], ["Camera id", "c"], ["Scope", "illustrative_demo"], ["Approval reference", "r"], ["Access mode for Zone A", "allowed"]] as const) await type(l, v);
    await click([...el.querySelectorAll("input[type=checkbox]")][0]!);
    await click(save());
    expect(mocks.post).not.toHaveBeenCalled();
    expect(el.textContent).toContain("conflicts with allowed entry");
    await click([...el.querySelectorAll("input[type=checkbox]")][0]!); // untick entry rule
    await click([...el.querySelectorAll("input[type=checkbox]")][2]!);
    await click(save());
    expect(mocks.post).toHaveBeenCalledTimes(1);
    expect(el.textContent).toContain("No automatic retry");
  });

  it("drops entered zone choices when the saved geometry changes", async () => {
    await mount();
    await type("Access mode for Zone A", "no_entry_all");
    expect(q("Access mode for Zone A").value).toBe("no_entry_all");
    await act(async () => root.render(<RuleReviewPanel sourceDigest={SRC} resultSha={RES} snapshot={{ ...SNAP, zones_sha256: "e".repeat(64) }} enabled />));
    expect(q("Access mode for Zone A").value).toBe("");
  });
});
