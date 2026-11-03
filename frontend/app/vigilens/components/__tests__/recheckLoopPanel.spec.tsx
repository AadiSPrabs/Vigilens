// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { RecheckLoopPanel } from "../RecheckLoopPanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const SRC = "a".repeat(64);
const RES = "b".repeat(64);
const planBody = (match: boolean) => ({ status: "planned_requires_exact_grant", person_id: "p1", plan_sha256: "c".repeat(64), request_sha256: ["d".repeat(64), "e".repeat(64)], max_reserved_usd: "1.314756", configured_grant_matches_this_plan: match, provider_calls_this_request: 0, reserved_nothing: true, grant_created_here: false });
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
let root: Root | null = null;
let host: HTMLElement | null = null;
const mount = async (loop: Record<string, unknown>, onChanged = () => {}) => {
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
  await act(async () => { root!.render(createElement(RecheckLoopPanel, { sourceDigest: SRC, resultSha: RES, loop, onChanged })); });
};
const btn = (label: string) => Array.from(host!.querySelectorAll("button")).find((b) => b.textContent === label) as HTMLButtonElement;
const click = async (label: string) => { await act(async () => { btn(label).click(); await new Promise((r) => setTimeout(r, 20)); }); };
afterEach(async () => { await act(async () => { root?.unmount(); }); host?.remove(); root = null; host = null; vi.restoreAllMocks(); });

describe("RecheckLoopPanel", () => {
  it("shows a visible blocked state and keeps reserve and run disabled without the exact approval", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockImplementation(async () => json(planBody(false)));
    await mount({ status: "blocked_no_reserved_attempts", unknown_person_ids: ["p1"], blocked_until: "the owner approves" });
    expect(host!.querySelector('[data-testid="recheck-loop-blocked"]')!.textContent).toContain("Blocked: the owner approves");
    expect(btn("Run reserved attempts (once, no retry)").disabled).toBe(true);
    await click("Show exact recheck plan");
    expect(host!.querySelector('[data-testid="grant-state"]')!.textContent).toContain("No exact approval");
    expect(btn("Reserve this exact plan (no call yet)").disabled).toBe(true);
    expect(f).toHaveBeenCalledTimes(1);
    expect(String(f.mock.calls[0]![0])).toContain("/recheck-plan");
    expect(host!.textContent).not.toContain("data:image");
  });

  it("enables reserve only when the server holds the exact approval, and reserve makes no run call", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) =>
      String(url).includes("/recheck-reservation") ? json({ attempt_id: "f".repeat(64), state: "reserved_not_dispatched", new_reservation: true, plan_sha256: "c".repeat(64), held_usd: "1.314756", provider_calls_this_request: 0, grant_created_here: false }) : json(planBody(true)));
    const changed = vi.fn();
    await mount({ status: "blocked_no_reserved_attempts", unknown_person_ids: ["p1"] }, changed);
    await click("Show exact recheck plan");
    expect(btn("Reserve this exact plan (no call yet)").disabled).toBe(false);
    await click("Reserve this exact plan (no call yet)");
    expect(host!.querySelector('[role="status"]')!.textContent).toContain("Provider calls made: 0");
    expect(f.mock.calls.map((c) => String(c[0])).some((u) => u.includes("bounded-review-loop"))).toBe(false);
    expect(changed).toHaveBeenCalled();
  });

  it("runs the loop only when attempts are ready, once, and shows a 409 refusal as-is", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => json({ detail: "Configured exact recheck loop unavailable; no new grant/reservation or retry" }, 409));
    await mount({ status: "ready_reserved_attempts", attempt_count: 1, unknown_person_ids: ["p1"] });
    await click("Run reserved attempts (once, no retry)");
    expect(host!.querySelector('[role="status"]')!.textContent).toContain("no new grant");
    expect(vi.mocked(globalThis.fetch)).toHaveBeenCalledTimes(1);
  });
});

describe("person labels match the stage", () => {
  it("names the person with the same label the outlined figure uses plus the backend id", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => json(planBody(false)));
    await mount({ status: "blocked_no_reserved_attempts", unknown_person_ids: ["0"] });
    expect(host!.textContent).toContain("Person 0: helmet or vest reading unknown."); // fallback without a label map
    await act(async () => { root!.render(createElement(RecheckLoopPanel, { sourceDigest: SRC, resultSha: RES, loop: { status: "blocked_no_reserved_attempts", unknown_person_ids: ["0"] }, onChanged: () => {}, labelFor: (id: string) => `Person 1 (backend id ${id}, the outlined figure with this label)` })); });
    expect(host!.textContent).toContain("Person 1 (backend id 0, the outlined figure with this label): helmet or vest reading unknown.");
  });
});
