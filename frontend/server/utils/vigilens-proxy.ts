// Server-side boundary for the Vigilens backend. The browser NEVER sees the
// backend token or URL: this proxy is the only path, and it requires a real
// login session (better-auth via @agent-native/core). The display-session value
// the backend uses to pin result viewing is DERIVED HERE from the authenticated
// account - a client cannot supply or spoof it.
import { createHash } from "node:crypto";
import { createError, getRequestHost, getHeader, type H3Event } from "h3";
import { getSession } from "@agent-native/core/server";
import { getVisitorKey } from "./vigilens-keys";

const BACKEND_URL = () => (process.env.VIGILENS_BACKEND_URL || "").replace(/\/+$/, "");
const BACKEND_TOKEN = () => process.env.VIGILENS_LOCAL_ACCESS_TOKEN || "";

export function displaySessionFor(session: { email: string; userId?: string; authUserId?: string }): string {
  // Account-only and STABLE across key set/forget/TTL: a visitor must never lose
  // sight of their own stored results because a key expired. Per-key charging
  // isolation lives in the backend's job ownership (journal partition), not in
  // the view identity.
  const stable = session.authUserId || session.userId || session.email;
  return createHash("sha256").update(`vigilens-display:${stable}`).digest("hex");
}

export async function requireVigilensSession(event: H3Event) {
  const session = await getSession(event);
  if (!session || !session.email) {
    throw createError({ statusCode: 401, statusMessage: "Sign in required" });
  }
  await requireVerifiedSessionFor(event, session.email);
  return session;
}

const BA_SESSION_COOKIE_RE = /(?:^|;\s*)(?:__Secure-)?[\w.-]*session_token\s*=/;
const FRAMEWORK_SESSION_COOKIE = "an_session";
const FRAMEWORK_SESSION_PATH = "/_agent-native/auth/session";

function cookieValue(cookieHeader: string, name: string): string | null {
  for (const part of cookieHeader.split(";")) {
    const eq = part.indexOf("=");
    if (eq < 0) continue;
    if (part.slice(0, eq).trim() === name) {
      const value = part.slice(eq + 1).trim();
      return value.length > 0 ? value : null;
    }
  }
  return null;
}

// Two session kinds reach this app:
// - The UI sign-in page authenticates through the framework's own
//   /_agent-native/auth/login and sets `an_session`. That token resolves
//   against the server-side sessions table on EVERY request (no signed
//   cookie cache), so re-checking it through the framework session endpoint
//   is database-authoritative: logout deletes the row and the next check
//   fails. A UI-signed-in visitor carries ONLY this cookie; sending them
//   through the better-auth check below 401s every action (the deployed
//   key-save regression).
// - Direct better-auth sign-in sets `an.session_token` plus a 5-minute
//   SIGNED cookie cache, so it needs the disableCookieCache database check.
// The verified identity must match the session core resolved: a request can
// carry both cookies, and core tries better-auth first, so an `an_session`
// belonging to another account must not vouch for a better-auth identity.
async function requireVerifiedSessionFor(event: H3Event, email: string) {
  const cookie = getHeader(event, "cookie") || "";
  const frameworkToken = cookieValue(cookie, FRAMEWORK_SESSION_COOKIE);
  if (frameworkToken) {
    const verified = await verifiedFrameworkEmail(event, frameworkToken);
    if (verified && verified.toLowerCase() === email.toLowerCase()) return;
    if (!BA_SESSION_COOKIE_RE.test(cookie)) {
      throw createError({ statusCode: 401, statusMessage: "Sign in required" });
    }
  }
  if (BA_SESSION_COOKIE_RE.test(cookie)) {
    await requireServerVerifiedSession(event);
    return;
  }
  throw createError({ statusCode: 401, statusMessage: "Sign in required" });
}

// Same loopback discipline as requireServerVerifiedSession: the actual
// connection's local port (never the Host header), transport failure is a
// 503 (fail closed), an unauthenticated answer is a plain null so the caller
// can fall through to the better-auth check or 401. The framework endpoint
// answers 200 with {"error":"Not authenticated"} for a dead token, so only a
// body email counts. Only the framework cookie is forwarded - a stale
// better-auth jar must not ride along and satisfy this check.
async function verifiedFrameworkEmail(event: H3Event, token: string): Promise<string | null> {
  const localPort = event.node?.req?.socket?.localPort;
  const port = localPort || process.env.PORT;
  if (!port) {
    throw createError({ statusCode: 503, statusMessage: "Session verification unavailable" });
  }
  let res: Response;
  try {
    res = await fetch(`http://127.0.0.1:${port}${FRAMEWORK_SESSION_PATH}`, {
      headers: { cookie: `${FRAMEWORK_SESSION_COOKIE}=${token}` },
      signal: AbortSignal.timeout(10_000),
      redirect: "error",
    });
  } catch {
    throw createError({ statusCode: 503, statusMessage: "Session verification unavailable" });
  }
  if (!res.ok) return null;
  const body = (await res.json().catch(() => null)) as { email?: unknown } | null;
  return body && typeof body.email === "string" && body.email ? body.email : null;
}

// Server-verified revocation: better-auth keeps a 5-minute SIGNED cookie cache
// (session_data). Trusting it means a logged-out session - and a visitor key
// bound to its token - stays usable for up to 5 minutes if the FULL pre-logout
// cookie set is replayed. Logout deletes the session row, so ask our own auth
// API with disableCookieCache and let the database be authoritative. The
// self-fetch goes to loopback on the actual local port of THIS connection
// (falling back to the PORT env); never to the request's Host header, which an
// attacker can point at a server that always answers "signed in".
async function requireServerVerifiedSession(event: H3Event) {
  const cookie = getHeader(event, "cookie") || "";
  const localPort = event.node?.req?.socket?.localPort;
  const port = localPort || process.env.PORT;
  if (!port) {
    // Fail closed: without a trustworthy self-address we cannot verify
    // revocation, and an unverified session must not reach keys or results.
    throw createError({ statusCode: 503, statusMessage: "Session verification unavailable" });
  }
  let res: Response;
  try {
    res = await fetch(`http://127.0.0.1:${port}/_agent-native/auth/ba/get-session?disableCookieCache=true`, {
      headers: { cookie },
      signal: AbortSignal.timeout(10_000),
      redirect: "error",
    });
  } catch {
    throw createError({ statusCode: 503, statusMessage: "Session verification unavailable" });
  }
  if (!res.ok) {
    throw createError({ statusCode: 401, statusMessage: "Sign in required" });
  }
  const body = (await res.json().catch(() => null)) as { user?: { email?: string } } | null;
  if (!body || !body.user || !body.user.email) {
    throw createError({ statusCode: 401, statusMessage: "Sign in required" });
  }
}

// CSRF / cross-origin defence in depth on top of the SameSite session cookie:
// a browser POST from another site would carry a foreign Origin and is refused.
export function requireSameOrigin(event: H3Event) {
  const origin = getHeader(event, "origin");
  if (!origin) return; // non-browser clients still need the session cookie
  let originHost: string;
  try {
    originHost = new URL(origin).host;
  } catch {
    throw createError({ statusCode: 403, statusMessage: "Bad origin" });
  }
  if (originHost !== getRequestHost(event)) {
    throw createError({ statusCode: 403, statusMessage: "Cross-origin request refused" });
  }
}

export async function proxyToBackend(
  event: H3Event,
  path: string,
  init: { method: string; body?: string | Uint8Array },
): Promise<Response> {
  const session = await requireVigilensSession(event);
  requireSameOrigin(event);
  const base = BACKEND_URL();
  const token = BACKEND_TOKEN();
  if (!base || !token) {
    throw createError({ statusCode: 503, statusMessage: "Vigilens backend not configured on this server" });
  }
  // The visitor's own Meta key, if they set one: held only in this process's
  // memory, attached here server-to-server, never logged and never in the bundle.
  const visitor = getVisitorKey(session);
  const headers: Record<string, string> = {
    "X-Vigilens-Local-Access": token,
    "X-Vigilens-Display-Session": displaySessionFor(session),
  };
  if (visitor) headers["X-Vigilens-Visitor-Key"] = visitor.key;
  const contentType = getHeader(event, "content-type");
  if (contentType) headers["content-type"] = contentType;
  let res: Response;
  try {
    res = await fetch(base + path, {
      method: init.method,
      headers,
      body: (init.body ?? null) as BodyInit | null,
      signal: AbortSignal.timeout(75_000), // above the client's 60s so the client aborts first
      redirect: "error",
    });
  } catch {
    throw createError({ statusCode: 504, statusMessage: "Backend did not answer in time; the audit may still be running. No automatic retry." });
  }
  return res;
}
