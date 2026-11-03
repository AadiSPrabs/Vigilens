import { afterEach, describe, expect, it, vi } from "vitest";
import { diagnosticHeaders, diagnosticResponse } from "../vigilens-response-diagnostics";

afterEach(() => vi.restoreAllMocks());

describe("secret-free read-flow diagnostics", () => {
  it("preserves upstream status/body without retry, logs only route/phase/status", async () => {
    const log = vi.spyOn(console, "info").mockImplementation(() => {});
    const run = vi.fn(async () => new Response("private body secret", { status: 429, headers: {
      "retry-after": "60", "rndr-id": "1d5d5b2e-1288-4519-9e88-0f4da07e0bdb", "set-cookie": "private cookie", "authorization": "private token",
    } }));
    const out = await diagnosticResponse("stored_reopen", run, true);
    expect(run).toHaveBeenCalledTimes(1);
    expect(out.status).toBe(429);
    expect(await out.text()).toBe("private body secret");
    expect(out.headers.get("retry-after")).toBe("60");
    expect(out.headers.get("rndr-id")).toBe("1d5d5b2e-1288-4519-9e88-0f4da07e0bdb");
    expect(out.headers.get("cache-control")).toBe("private, no-store");
    expect(out.headers.has("set-cookie")).toBe(false);
    expect(out.headers.has("authorization")).toBe(false);
    expect(log.mock.calls).toEqual([[JSON.stringify({ event: "vigilens.proxy_diagnostic", route: "stored_reopen", phase: "upstream_response", status: 429 })]]);
  });
  it.each([401, 403, 503, 504])("preserves refusal %i and never logs exception text or retries", async statusCode => {
    const log = vi.spyOn(console, "info").mockImplementation(() => {});
    const err = { statusCode, message: "secret key cookie source account", url: "private-url" };
    const run = vi.fn(async (): Promise<Response> => { throw err; });
    await expect(diagnosticResponse("health", run)).rejects.toBe(err);
    expect(run).toHaveBeenCalledTimes(1);
    expect(JSON.parse(log.mock.calls[0][0])).toEqual({ event: "vigilens.proxy_diagnostic", route: "health", phase: "no_upstream_response", status: statusCode });
  });
  it("keeps unknown exceptions out of logs and uses a bounded numeric status", async () => {
    const log = vi.spyOn(console, "info").mockImplementation(() => {});
    await expect(diagnosticResponse("health", async () => { throw { statusCode: "secret" }; })).rejects.toEqual({ statusCode: "secret" });
    expect(JSON.parse(log.mock.calls[0][0]).status).toBe(500);
    expect(log.mock.calls[0][0]).not.toContain("secret");
  });
  it.each(["9999999", "-1", "secret value", "https://private.invalid", "99999"])("drops unsafe Retry-After %s", value => {
    expect(diagnosticHeaders(new Response(null, { headers: { "retry-after": value } })).has("retry-after")).toBe(false);
  });
  it("accepts an HTTP-date and rejects arbitrary request identifiers", () => {
    const h = diagnosticHeaders(new Response(null, { headers: { "retry-after": "Tue, 03 Nov 2026 16:30:00 GMT", "x-request-id": "private@email.invalid" } }));
    expect(h.get("retry-after")).toBe("Tue, 03 Nov 2026 16:30:00 GMT");
    expect(h.has("x-request-id")).toBe(false);
  });
});
