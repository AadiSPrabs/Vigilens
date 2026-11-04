import { describe, expect, it, vi } from "vitest";
import http from "node:http";
import { wakeVigilensBackend } from "../vigilens-startup-wake";

describe("frontend startup backend wake", () => {
  it("makes one credential-free GET to configured health, not analysis", async () => {
    const request = vi.fn(async () => new Response("starting", { headers: { "content-type": "text/html" } }));
    expect(await wakeVigilensBackend("https://backend.example/", request)).toBe("requested");
    expect(request).toHaveBeenCalledTimes(1);
    const [url, init] = request.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://backend.example/health");
    expect(init.method).toBe("GET"); expect(init.redirect).toBe("error");
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(init.headers).toBeUndefined(); expect(init.body).toBeUndefined();
  });
  it.each(["", "not a URL", "file:///tmp/backend", "https://user:secret@backend.example", "https://backend.example/?x=1"])("skips missing/invalid configuration without a request", async (base) => {
    const request = vi.fn(); expect(await wakeVigilensBackend(base, request)).toBe("skipped");
    expect(request).not.toHaveBeenCalled();
  });
  it.each([429, 503])("does not retry refusal %i", async (status) => {
    const request = vi.fn(async () => new Response("refused", { status }));
    expect(await wakeVigilensBackend("https://backend.example", request)).toBe("unavailable");
    expect(request).toHaveBeenCalledTimes(1);
  });
  it("contains transport failure without retries or throwing at boot", async () => {
    const request = vi.fn(async () => { throw Error("private network detail"); });
    expect(await wakeVigilensBackend("https://backend.example", request)).toBe("unavailable");
    expect(request).toHaveBeenCalledTimes(1);
  });
  it("reaches real HTTP health once and never follows redirect", async () => {
    const hits: string[] = [];
    const server = http.createServer((req, res) => { hits.push(req.url!); res.writeHead(302, { location: "/analysis" }); res.end(); });
    await new Promise<void>(r => server.listen(0, "127.0.0.1", r));
    try {
      const base = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
      expect(await wakeVigilensBackend(base)).toBe("unavailable");
      expect(hits).toEqual(["/health"]);
    } finally { server.closeAllConnections(); await new Promise<void>(r => server.close(() => r())); }
  });
});
