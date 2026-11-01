// Boundary tests for the server-side Vigilens proxy. No network: fetch and the
// auth session resolver are mocked. These pin the rules that keep the backend
// token and the display-session identity server-side.
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { createHash } from "node:crypto";

const SESSION = { email: "judge@example.com", userId: "user-1", authUserId: "auth-1" };

vi.mock("@agent-native/core/server", () => ({
  getSession: vi.fn(),
}));

import { getSession } from "@agent-native/core/server";
import { proxyToBackend, displaySessionFor } from "../vigilens-proxy";

function fakeEvent(headers: Record<string, string> = {}) {
  // A resolved better-auth session implies the request presented its cookie;
  // default to one so tests exercise the verified path. Tests override by
  // passing their own cookie header.
  const base = { host: "vigilens-frontend.onrender.com", cookie: "an.session_token=test-ba-token.testsig" };
  const h = new Headers({ ...base, ...headers });
  return {
    req: new Request("https://vigilens-frontend.onrender.com/api/vigilens/health", { headers: h }),
    node: { req: { headers: { ...base, ...headers }, socket: { localPort: 4317 } } },
    context: {},
  } as never;
}

const mockedSession = vi.mocked(getSession);

// The proxy now verifies revocation against our own auth API
// (get-session?disableCookieCache=true) before any backend call. Tests route
// that loopback self-fetch to a valid session and delegate everything else to
// the per-test backend stub.
const SELF_AUTH_PATH = "/_agent-native/auth/ba/get-session?disableCookieCache=true";
function routingFetch(backendImpl: (url: string, init?: RequestInit) => Promise<Response> | Response) {
  return vi.fn((url: unknown, init?: RequestInit) => {
    const u = String(url);
    if (u.includes(SELF_AUTH_PATH)) {
      return Promise.resolve(new Response(JSON.stringify({ user: { email: SESSION.email } }), { status: 200 }));
    }
    return Promise.resolve(backendImpl(u, init));
  });
}
function backendCalls(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls.filter((c) => String(c[0]).includes("onrender.com"));
}

beforeEach(() => {
  mockedSession.mockResolvedValue(SESSION as never);
  process.env.VIGILENS_BACKEND_URL = "https://vigilens-backend.onrender.com";
  process.env.VIGILENS_LOCAL_ACCESS_TOKEN = "server-side-token-0123456789abcdef";
});
afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.VIGILENS_BACKEND_URL;
  delete process.env.VIGILENS_LOCAL_ACCESS_TOKEN;
});

const FRAMEWORK_SESSION_PATH = "/_agent-native/auth/session";

describe("framework (UI login) session verification", () => {
  it("accepts a UI-login an_session verified through the framework session endpoint; the better-auth check is not called", async () => {
    const fetchMock = vi.fn((url: unknown) => {
      const u = String(url);
      if (u.includes(FRAMEWORK_SESSION_PATH)) {
        return Promise.resolve(new Response(JSON.stringify({ email: SESSION.email }), { status: 200 }));
      }
      if (u.includes(SELF_AUTH_PATH)) {
        return Promise.resolve(new Response(JSON.stringify({ user: null }), { status: 200 }));
      }
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const event = fakeEvent({ cookie: "an_session=fw-token-123; an_session_hint=1" });
    await proxyToBackend(event, "/health", { method: "GET" });
    expect(fetchMock.mock.calls.some((c) => String(c[0]).includes(FRAMEWORK_SESSION_PATH))).toBe(true);
    expect(fetchMock.mock.calls.some((c) => String(c[0]).includes(SELF_AUTH_PATH))).toBe(false);
    const fwCall = fetchMock.mock.calls.find((c) => String(c[0]).includes(FRAMEWORK_SESSION_PATH));
    expect((fwCall?.[1] as RequestInit).headers).toEqual({ cookie: "an_session=fw-token-123" });
    expect(backendCalls(fetchMock)).toHaveLength(1);
  });

  it("rejects a revoked UI-login session (framework endpoint says not authenticated) with 401 before any backend call", async () => {
    const fetchMock = vi.fn((url: unknown) => {
      const u = String(url);
      if (u.includes(FRAMEWORK_SESSION_PATH)) {
        return Promise.resolve(new Response(JSON.stringify({ error: "Not authenticated" }), { status: 200 }));
      }
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const event = fakeEvent({ cookie: "an_session=revoked-token" });
    await expect(proxyToBackend(event, "/health", { method: "GET" })).rejects.toMatchObject({ statusCode: 401 });
    expect(backendCalls(fetchMock)).toHaveLength(0);
  });

  it("fails closed 503 when the framework session endpoint is unreachable", async () => {
    const fetchMock = vi.fn(() => Promise.reject(new Error("connection refused")));
    vi.stubGlobal("fetch", fetchMock);
    const event = fakeEvent({ cookie: "an_session=fw-token-123" });
    await expect(proxyToBackend(event, "/health", { method: "GET" })).rejects.toMatchObject({ statusCode: 503 });
    expect(backendCalls(fetchMock)).toHaveLength(0);
  });

  it("falls back to the better-auth check when the framework cookie belongs to a different account than the resolved session", async () => {
    const fetchMock = vi.fn((url: unknown) => {
      const u = String(url);
      if (u.includes(FRAMEWORK_SESSION_PATH)) {
        return Promise.resolve(new Response(JSON.stringify({ email: "someone-else@example.com" }), { status: 200 }));
      }
      if (u.includes(SELF_AUTH_PATH)) {
        return Promise.resolve(new Response(JSON.stringify({ user: { email: SESSION.email } }), { status: 200 }));
      }
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const event = fakeEvent({ cookie: "an_session=other-account; an.session_token=ba-token.sig" });
    await proxyToBackend(event, "/health", { method: "GET" });
    expect(fetchMock.mock.calls.some((c) => String(c[0]).includes(SELF_AUTH_PATH))).toBe(true);
    expect(backendCalls(fetchMock)).toHaveLength(1);
  });

  it("still 401s a session that resolved with neither known session cookie", async () => {
    const fetchMock = routingFetch(() => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const event = fakeEvent({ cookie: "an_session_hint=1" });
    await expect(proxyToBackend(event, "/health", { method: "GET" })).rejects.toMatchObject({ statusCode: 401 });
    expect(backendCalls(fetchMock)).toHaveLength(0);
  });
});

describe("vigilens proxy boundary", () => {
  it("rejects unauthenticated requests with 401 before any backend call", async () => {
    mockedSession.mockResolvedValue(null as never);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(proxyToBackend(fakeEvent(), "/health", { method: "GET" })).rejects.toMatchObject({ statusCode: 401 });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("attaches the server-side token and an account-derived display session; client headers are never forwarded", async () => {
    const fetchMock = routingFetch(() => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const event = fakeEvent({
      "x-vigilens-local-access": "spoofed-client-token",
      "x-vigilens-display-session": "spoofed-session",
      "content-type": "multipart/form-data; boundary=xyz",
    });
    await proxyToBackend(event, "/fresh-review-audit-governed", { method: "POST", body: "raw-body" });
    const [url, init] = backendCalls(fetchMock)[0] as [string, RequestInit];
    expect(url).toBe("https://vigilens-backend.onrender.com/fresh-review-audit-governed");
    const headers = init.headers as Record<string, string>;
    expect(headers["X-Vigilens-Local-Access"]).toBe("server-side-token-0123456789abcdef");
    expect(headers["X-Vigilens-Display-Session"]).toBe(displaySessionFor(SESSION));
    expect(headers["content-type"]).toBe("multipart/form-data; boundary=xyz");
    // only those three headers exist - nothing else was forwarded
    expect(Object.keys(headers).sort()).toEqual(["X-Vigilens-Display-Session", "X-Vigilens-Local-Access", "content-type"]);
  });

  it("derives the display session from the account, stable and distinct per account, never client input", () => {
    const a = displaySessionFor(SESSION);
    expect(a).toMatch(/^[0-9a-f]{64}$/);
    expect(a).toBe(displaySessionFor({ email: "judge@example.com", authUserId: "auth-1" }));
    expect(a).toBe(createHash("sha256").update("vigilens-display:auth-1").digest("hex"));
    expect(a).not.toBe(displaySessionFor({ email: "other@example.com", authUserId: "auth-2" }));
  });

  it("refuses cross-origin browser posts (CSRF defence in depth)", async () => {
    vi.stubGlobal("fetch", routingFetch(() => new Response("{}", { status: 200 })));
    await expect(
      proxyToBackend(fakeEvent({ origin: "https://evil.example" }), "/health", { method: "GET" }),
    ).rejects.toMatchObject({ statusCode: 403 });
    // same-origin origin header is fine
    const fetchMock = routingFetch(() => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await proxyToBackend(fakeEvent({ origin: "https://vigilens-frontend.onrender.com" }), "/health", { method: "GET" });
    expect(backendCalls(fetchMock)).toHaveLength(1);
  });

  it("returns 503 when the backend is not configured, before any BACKEND fetch", async () => {
    delete process.env.VIGILENS_LOCAL_ACCESS_TOKEN;
    const fetchMock = routingFetch(() => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(proxyToBackend(fakeEvent(), "/health", { method: "GET" })).rejects.toMatchObject({ statusCode: 503 });
    expect(backendCalls(fetchMock)).toHaveLength(0);
  });

  it("passes backend refusals through unchanged (wrong-token 403, uncertain 409)", async () => {
    for (const status of [403, 409]) {
      const body = status === 409 ? { detail: { code: "ATTEMPT_UNCERTAIN" } } : {};
      vi.stubGlobal("fetch", routingFetch(() =>
        new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })));
      const res = await proxyToBackend(fakeEvent(), "/fresh-review-audit-governed", { method: "POST", body: "x" });
      expect(res.status).toBe(status);
      expect(await res.json()).toEqual(body);
    }
  });

  it("maps a backend timeout to 504 with a still-running message, never a retry hint", async () => {
    vi.stubGlobal("fetch", routingFetch(() => { throw new DOMException("aborted", "TimeoutError"); }));
    await expect(proxyToBackend(fakeEvent(), "/health", { method: "GET" })).rejects.toMatchObject({
      statusCode: 504,
      statusMessage: expect.stringMatching(/may still be running/),
    });
  });
});

describe("visitor BYOK plumbing", () => {
  it("attaches the visitor key server-to-server when held; the display session stays account-stable", async () => {
    const { setVisitorKey, _resetVisitorKeys } = await import("../vigilens-keys");
    _resetVisitorKeys();
    const fetchMock = routingFetch(() => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const sessionWithToken = { ...SESSION, token: "sess-token-1" };
    mockedSession.mockResolvedValue(sessionWithToken as never);
    setVisitorKey(sessionWithToken, "visitor-meta-key-999");

    await proxyToBackend(fakeEvent(), "/api/whatever", { method: "POST", body: "x" });
    const call = backendCalls(fetchMock)[0] as unknown as [string, { headers: Record<string, string> }];
    const headers = call[1].headers;
    expect(Object.keys(headers).sort()).toEqual([
      "X-Vigilens-Display-Session",
      "X-Vigilens-Local-Access",
      "X-Vigilens-Visitor-Key",
    ]);
    expect(headers["X-Vigilens-Visitor-Key"]).toBe("visitor-meta-key-999");
    // View identity is account-only and STABLE: setting/forgetting a key must not
    // hide the visitor's own stored results. Per-key charging isolation is the
    // backend journal partition's job, not the display session's.
    const expected = createHash("sha256").update(`vigilens-display:${SESSION.authUserId}`).digest("hex");
    expect(headers["X-Vigilens-Display-Session"]).toBe(expected);
    expect(displaySessionFor(SESSION)).toBe(expected);
    _resetVisitorKeys();
  });

  it("never forwards a client-supplied visitor-key header", async () => {
    const { _resetVisitorKeys } = await import("../vigilens-keys");
    _resetVisitorKeys();
    const fetchMock = routingFetch(() => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const event = fakeEvent({ "x-vigilens-visitor-key": "spoofed-key" });
    await proxyToBackend(event, "/health", { method: "GET" });
    const call = backendCalls(fetchMock)[0] as unknown as [string, { headers: Record<string, string> }];
    const headers = call[1].headers;
    expect(headers["X-Vigilens-Visitor-Key"]).toBeUndefined();
  });
});

describe("server-verified session revocation", () => {
  it("401s before any backend call when the DB-backed session check finds no session (replayed cookie cache)", async () => {
    const fetchMock = vi.fn((url: unknown) => {
      const u = String(url);
      if (u.includes(SELF_AUTH_PATH)) return Promise.resolve(new Response("null", { status: 200 }));
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(proxyToBackend(fakeEvent(), "/health", { method: "GET" })).rejects.toMatchObject({ statusCode: 401 });
    expect(backendCalls(fetchMock)).toHaveLength(0);
  });

  it("fails closed (503) when the revocation check itself cannot run", async () => {
    const fetchMock = vi.fn((url: unknown) => {
      const u = String(url);
      if (u.includes(SELF_AUTH_PATH)) return Promise.reject(new Error("connection refused"));
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(proxyToBackend(fakeEvent(), "/health", { method: "GET" })).rejects.toMatchObject({ statusCode: 503 });
    expect(backendCalls(fetchMock)).toHaveLength(0);
  });
});
