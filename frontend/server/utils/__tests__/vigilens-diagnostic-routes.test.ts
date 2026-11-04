import { afterEach, describe, expect, it, vi } from "vitest";
import http from "node:http";
import { createApp, createRouter, toNodeListener, createError } from "h3";
vi.mock("../vigilens-proxy", () => ({ proxyToBackend: vi.fn() }));
import { proxyToBackend } from "../vigilens-proxy";
import health from "../../routes/api/vigilens/health.get";
import reopen from "../../routes/api/vigilens/fresh-review/[source]/reopen-audit.post";
afterEach(() => vi.restoreAllMocks());

describe("diagnostic route wiring via real local HTTP", () => {
  it("preserves health/reopen429 and does not retry; rejects invalid source before backend", async () => {
    const log = vi.spyOn(console, "info").mockImplementation(() => {});
    const proxy = vi.mocked(proxyToBackend);
    proxy.mockImplementation(async () => new Response("edge refusal", { status: 429, headers: { "retry-after": "30", "rndr-id": "abcdef12-abcdef12", "set-cookie": "private-cookie" } }));
    const router = createRouter(); router.get("/health", health); router.post("/reopen/:source", reopen);
    const app = createApp(); app.use(router);
    const server = http.createServer(toNodeListener(app));
    await new Promise<void>(r => server.listen(0, "127.0.0.1", r));
    const base = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
    try {
      for (const [path, method] of [["/health", "GET"], ["/reopen/" + "a".repeat(64), "POST"]]) {
        const out = await fetch(base + path, { method: method! });
        expect(out.status).toBe(429); expect(await out.text()).toBe("edge refusal");
        expect(out.headers.get("retry-after")).toBe("30"); expect(out.headers.get("rndr-id")).toBe("abcdef12-abcdef12");
        expect(out.headers.has("set-cookie")).toBe(false);
      }
      expect(proxy).toHaveBeenCalledTimes(2);
      expect((await fetch(base + "/reopen/bad", { method: "POST" })).status).toBe(400);
      expect(proxy).toHaveBeenCalledTimes(2);
      proxy.mockImplementationOnce(async () => { throw createError({ statusCode: 403, statusMessage: "Denied" }); });
      expect((await fetch(base + "/health")).status).toBe(403);
      expect(proxy).toHaveBeenCalledTimes(3);
      const rows = log.mock.calls.map(c => JSON.parse(c[0]));
      expect(rows).toEqual([
        { event: "vigilens.proxy_diagnostic", route: "health", phase: "upstream_response", status: 429 },
        { event: "vigilens.proxy_diagnostic", route: "stored_reopen", phase: "upstream_response", status: 429 },
        { event: "vigilens.proxy_diagnostic", route: "health", phase: "no_upstream_response", status: 403 },
      ]);
    } finally { server.closeAllConnections(); await new Promise<void>(r => server.close(() => r())); }
  });
});
