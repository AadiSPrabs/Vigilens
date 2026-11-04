// Server-side boundary for the Vigilens backend. The browser NEVER sees the
// backend token or URL: this proxy is the only path, and it requires a real
// login session (better-auth via @agent-native/core). The display-session value
// the backend uses to pin result viewing is DERIVED HERE from the authenticated
// account - a client cannot supply or spoof it.
import { createHash } from "node:crypto";
import { createError, getRequestHost, getHeader, type H3Event } from "h3";
import { getSession } from "@agent-native/core/server";
import { readFileSync } from "node:fs";
import { join } from "node:path";
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
const FRAMEWORK_SESSION_PATH = "/_agent-native/auth/session";

// Framework session cookie candidates. This mirrors
// @agent-native/core@0.222.2 dist/server/cookie-namespace.js, which the
// package does NOT re-export from its "./server" subpath (verified against
// the package exports map), so the derivation is replicated here and pinned
// to that version. The framework namespaces its session cookie
// an_session_<appSlug> whenever an app slug is in force (APP_NAME in any
// mode, or the package name in non-production local-isolated mode with no
// COOKIE_DOMAIN), plain "an_session" otherwise; its non-first-party read
// list is the clear-set in insertion order: [primary, "an_session",
// "an_session_<slug>"]. SCOPE CUT, documented: framework WORKSPACE-mode
// membership and ordering (primary an_session_workspace or an isolated
// an_session_<slug>, with an_session_workspace joining the read list) is
// NOT replicated - this replica covers exactly the non-workspace
// configurations this app is deployed in, and if the app is ever run in
// framework workspace mode this list must be re-derived from the framework
// rather than extended by hand. A first-party agent-native.com isolated
// realm reads ONLY its primary name; this app never runs in one (no
// agent-native.com cookie domain), and the framework itself throws without
// an app id if one were ever configured. Selection
// mirrors getLegacyCookieSession (dist/server/auth.js): iterate candidates
// in order, dedupe by value, and the FIRST token that resolves to a session
// email is the framework identity - a stale or invalid earlier cookie never
// blocks a later valid one, and a later valid cookie for a different
// account never overrides the first. Verification strength is unchanged:
// every candidate token still goes through verifiedFrameworkEmail (the
// database-backed loopback self-check) and vouches only when it equals the
// identity core resolved for this request.
function slugifyAppName(raw: string): string {
  // Exact mirror of the framework's slugifyAppName.
  return raw.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

let cachedPackageName: string | undefined;
function packageName(): string {
  if (cachedPackageName === undefined) {
    try {
      const raw = readFileSync(join(process.cwd(), "package.json"), "utf8");
      const parsed = JSON.parse(raw) as { name?: unknown };
      cachedPackageName = typeof parsed.name === "string" ? parsed.name : "";
    } catch {
      cachedPackageName = "";
    }
  }
  return cachedPackageName;
}

function frameworkCookieCandidates(): string[] {
  const cookieDomain = (process.env.COOKIE_DOMAIN || "").trim();
  const explicit = slugifyAppName(process.env.APP_NAME || "");
  const local =
    process.env.NODE_ENV !== "production" && !cookieDomain
      ? slugifyAppName(process.env.npm_package_name || packageName())
      : "";
  const slug = explicit || local;
  const primary = cookieDomain ? "an_session" : slug ? `an_session_${slug}` : "an_session";
  const names = [primary, "an_session"];
  if (slug) names.push(`an_session_${slug}`);
  return [...new Set(names)];
}

// Every value a name carries in the raw Cookie header, in order (H3 keeps
// only the first duplicate; the framework reads them all, and so do we).
function cookieValues(cookieHeader: string, name: string): string[] {
  const out: string[] = [];
  for (const part of cookieHeader.split(";")) {
    const eq = part.indexOf("=");
    if (eq < 0) continue;
    if (part.slice(0, eq).trim() === name) {
      const value = part.slice(eq + 1).trim();
      if (value) out.push(value);
    }
  }
  return out;
}

// Two session kinds reach this app:
// - The UI sign-in page authenticates through the framework's own
//   /_agent-native/auth/login and sets the framework session cookie
//   (`an_session`, namespaced an_session_<appSlug> when an app slug is in
//   force - see frameworkCookieCandidates). That token resolves
//   against the server-side sessions table on EVERY request (no signed
//   cookie cache), so re-checking it through the framework session endpoint
//   is database-authoritative: logout deletes the row and the next check
//   fails. A UI-signed-in visitor carries ONLY this cookie; sending them
//   through the better-auth check below 401s every action (the deployed
//   key-save regression).
// - Direct better-auth sign-in sets `an.session_token` plus a 5-minute
//   SIGNED cookie cache, so it needs the disableCookieCache database check.
// The verified identity must match the session core resolved: a request can
// carry both cookies, and core tries better-auth first, so a framework
// cookie belonging to another account must not vouch for a better-auth
// identity.
async function requireVerifiedSessionFor(event: H3Event, email: string) {
  const cookie = getHeader(event, "cookie") || "";
  const seen = new Set<string>();
  candidates: for (const name of frameworkCookieCandidates()) {
    for (const token of cookieValues(cookie, name)) {
      if (seen.has(token)) continue;
      seen.add(token);
      const verified = await verifiedFrameworkEmail(event, name, token);
      if (!verified) continue; // stale/invalid: try the next candidate, like the framework
      if (verified.toLowerCase() === email.toLowerCase()) return;
      // The first RESOLVING token is the framework identity. A valid token
      // for a different account never vouches, and no later cookie overrides
      // it - fall through to the better-auth check or 401.
      break candidates;
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
async function verifiedFrameworkEmail(event: H3Event, name: string, token: string): Promise<string | null> {
  const localPort = event.node?.req?.socket?.localPort;
  const port = localPort || process.env.PORT;
  if (!port) {
    throw createError({ statusCode: 503, statusMessage: "Session verification unavailable" });
  }
  let res: Response;
  try {
    res = await fetch(`http://127.0.0.1:${port}${FRAMEWORK_SESSION_PATH}`, {
      headers: { cookie: `${name}=${token}` },
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
      signal: AbortSignal.timeout(path === "/fresh-review-audit-governed" ? 330_000 : /\/explanation\/[0-9a-f]{64}$/.test(path) ? 120_000 : 75_000), // image: SAM + two sequential 90s PPE calls + overhead; reads stay bounded
      redirect: "error",
    });
  } catch {
    throw createError({ statusCode: 504, statusMessage: "Backend did not answer in time; the audit may still be running. No automatic retry." });
  }
  return res;
}
