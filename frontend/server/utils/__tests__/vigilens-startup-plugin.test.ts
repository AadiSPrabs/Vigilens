import { describe, expect, it, vi, afterEach } from "vitest";
const setup = vi.hoisted(() => ({ wake: vi.fn() }));
vi.mock("@agent-native/core/server", () => ({ defineNitroPlugin: (fn: () => void) => fn }));
vi.mock("../vigilens-startup-wake", () => ({ wakeVigilensBackend: setup.wake }));
import startup from "../../plugins/vigilens-startup-wake";
afterEach(() => vi.restoreAllMocks());
describe("startup plugin wiring", () => {
  it("fires exactly once without waiting for backend or logging secrets", async () => {
    let finish!: (value: string) => void;
    setup.wake.mockReturnValueOnce(new Promise(r => { finish = r; }));
    const log = vi.spyOn(console, "info").mockImplementation(() => {});
    expect((startup as unknown as () => unknown)()).toBeUndefined();
    expect(setup.wake).toHaveBeenCalledTimes(1);
    expect(log).not.toHaveBeenCalled();
    finish("unavailable"); await Promise.resolve();
    expect(log.mock.calls).toEqual([[JSON.stringify({ event: "vigilens.backend_startup_wake", status: "unavailable" })]]);
  });
});
