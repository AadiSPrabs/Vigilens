// Framework session cookie candidate tests for the Vigilens proxy. The
// framework namespaces its session cookie an_session_<appSlug> when an app
// slug is in force; the proxy must read the framework's candidate set in
// framework order, skip stale/invalid tokens, treat the first RESOLVING
// token as the framework identity, and never accept an arbitrary
// similarly-prefixed cookie. No network: fetch and the auth session
// resolver are mocked.
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

const SESSION = { email: "judge@example.com", userId: "user-1", authUserId: "auth-1" };
const OTHER = "other@example.com";

vi.mock("@agent-native/core/server", () => ({
  getSession: vi.fn(),
}));

import { getSession } from "@agent-native/core/server";
import { requireVigilensSession } from "../vigilens-proxy";

const mockedSession = vi.mocked(getSession);
const FRAMEWORK_SESSION_PATH = "/_agent-native/auth/session";
const BA_PATH = "/_agent-native/auth/ba/get-session";

function fakeEvent(cookie: string) {
  return {
    req: new Request("https://localhost/api/vigilens/health", { headers: { cookie } }),
    node: { req: { headers: { cookie }, socket: { localPort: 4317 } } },
    context: {},
  } as never;
}

// tokenTable maps a framework token to the email the framework session
// endpoint would return for it; unknown tokens answer "Not authenticated".
// NAME-AWARE like the real endpoint: a token arriving under a cookie name
// the framework would not read in this configuration resolves to
// "Not authenticated" even when the token itself is valid.
function stubAuthFetch(tokenTable: Record<string, string>, baEmail: string | null = null, allowedNames: string[] = ["an_session_app", "an_session"]) {
  const f = vi.fn((url: unknown, init?: RequestInit) => {
    const u = String(url);
    if (u.includes(FRAMEWORK_SESSION_PATH)) {
      const raw = (init?.headers as Record<string, string>)?.cookie || "";
      const name = raw.slice(0, raw.indexOf("="));
      const token = raw.slice(raw.indexOf("=") + 1);
      const email = allowedNames.includes(name) ? tokenTable[token] : undefined;
      const body = email ? { email } : { error: "Not authenticated" };
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    }
    if (u.includes(BA_PATH)) {
      const body = baEmail ? { user: { email: baEmail } } : {};
      return Promise.resolve(new Response(JSON.stringify(body), { status: baEmail ? 200 : 401 }));
    }
    return Promise.resolve(new Response("unexpected", { status: 500 }));
  });
  vi.stubGlobal("fetch", f);
  return f;
}

const ENV_KEYS = ["APP_NAME", "COOKIE_DOMAIN", "npm_package_name"] as const;
let savedEnv: Record<string, string | undefined> = {};
let savedNodeEnv: string | undefined;

beforeEach(() => {
  mockedSession.mockResolvedValue(SESSION as never);
  savedEnv = {};
  for (const k of ENV_KEYS) {
    savedEnv[k] = process.env[k];
    delete process.env[k];
  }
  savedNodeEnv = process.env.NODE_ENV;
});

afterEach(() => {
  vi.unstubAllGlobals();
  for (const k of ENV_KEYS) {
    if (savedEnv[k] === undefined) delete process.env[k];
    else process.env[k] = savedEnv[k];
  }
  if (savedNodeEnv === undefined) delete process.env.NODE_ENV;
  else process.env.NODE_ENV = savedNodeEnv;
});

describe("framework session cookie candidates", () => {
  it("accepts a valid namespaced cookie (app slug in force)", async () => {
    process.env.APP_NAME = "app";
    stubAuthFetch({ "tok-a": SESSION.email });
    const session = await requireVigilensSession(fakeEvent("an_session_app=tok-a"));
    expect(session.email).toBe(SESSION.email);
  });

  it("accepts a valid plain an_session cookie", async () => {
    process.env.APP_NAME = "app";
    stubAuthFetch({ "tok-p": SESSION.email });
    const session = await requireVigilensSession(fakeEvent("an_session=tok-p"));
    expect(session.email).toBe(SESSION.email);
  });

  it("accepts plain an_session under production no-slug semantics", async () => {
    process.env.NODE_ENV = "production";
    stubAuthFetch({ "tok-p": SESSION.email }, null, ["an_session"]);
    const session = await requireVigilensSession(fakeEvent("an_session=tok-p"));
    expect(session.email).toBe(SESSION.email);
  });

  it("skips a stale plain cookie and accepts a valid namespaced one", async () => {
    process.env.APP_NAME = "app";
    const f = stubAuthFetch({ "tok-a": SESSION.email });
    const session = await requireVigilensSession(fakeEvent("an_session=dead-token; an_session_app=tok-a"));
    expect(session.email).toBe(SESSION.email);
    const checked = f.mock.calls.filter((c) => String(c[0]).includes(FRAMEWORK_SESSION_PATH)).map((c) => String((c[1]?.headers as Record<string, string>).cookie));
    expect(checked).toContain("an_session_app=tok-a");
  });

  it("skips a stale namespaced cookie and accepts a valid plain one", async () => {
    process.env.APP_NAME = "app";
    stubAuthFetch({ "tok-p": SESSION.email });
    const session = await requireVigilensSession(fakeEvent("an_session_app=dead-token; an_session=tok-p"));
    expect(session.email).toBe(SESSION.email);
  });

  it("first resolving token wins when it matches the resolved identity (conflicting valid accounts)", async () => {
    process.env.APP_NAME = "app";
    stubAuthFetch({ "tok-a": SESSION.email, "tok-b": OTHER });
    const session = await requireVigilensSession(fakeEvent("an_session_app=tok-a; an_session=tok-b"));
    expect(session.email).toBe(SESSION.email);
  });

  it("refuses when the first resolving framework identity is a different account and no better-auth cookie exists", async () => {
    process.env.APP_NAME = "app";
    stubAuthFetch({ "tok-a": OTHER, "tok-b": SESSION.email });
    await expect(requireVigilensSession(fakeEvent("an_session_app=tok-a; an_session=tok-b"))).rejects.toMatchObject({ statusCode: 401 });
  });

  it("falls back to the better-auth database check when the framework identity differs but a better-auth cookie is present", async () => {
    process.env.APP_NAME = "app";
    stubAuthFetch({ "tok-a": OTHER }, SESSION.email);
    const session = await requireVigilensSession(fakeEvent("an_session_app=tok-a; an.session_token=ba-token.sig"));
    expect(session.email).toBe(SESSION.email);
  });

  it("never accepts an arbitrary similarly-prefixed cookie, even with a valid token", async () => {
    process.env.APP_NAME = "app";
    const f = stubAuthFetch({ "tok-e": SESSION.email });
    await expect(requireVigilensSession(fakeEvent("an_session_evil=tok-e"))).rejects.toMatchObject({ statusCode: 401 });
    expect(f.mock.calls.filter((c) => String(c[0]).includes(FRAMEWORK_SESSION_PATH))).toHaveLength(0);
  });

  it("rejects when no session cookie is present", async () => {
    process.env.APP_NAME = "app";
    stubAuthFetch({});
    await expect(requireVigilensSession(fakeEvent(""))).rejects.toMatchObject({ statusCode: 401 });
  });

  it("never reads a workspace-named cookie in a non-workspace config, even with a valid token", async () => {
    process.env.APP_NAME = "app";
    const f = stubAuthFetch({ "tok-w": SESSION.email });
    await expect(requireVigilensSession(fakeEvent("an_session_workspace=tok-w"))).rejects.toMatchObject({ statusCode: 401 });
    expect(f.mock.calls.filter((c) => String(c[0]).includes(FRAMEWORK_SESSION_PATH))).toHaveLength(0);
  });

  it("rejects a stale-only jar with no better-auth cookie", async () => {
    process.env.APP_NAME = "app";
    stubAuthFetch({});
    await expect(requireVigilensSession(fakeEvent("an_session=dead; an_session_app=dead2"))).rejects.toMatchObject({ statusCode: 401 });
  });
});
