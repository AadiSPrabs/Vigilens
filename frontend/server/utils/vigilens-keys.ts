// Visitor BYOK hold: a visitor's own Meta API key, kept ONLY in this Nitro
// process's memory, bound to their login session token, with an absolute TTL.
// Never written to the database, session store, localStorage, URLs, or logs.
// Spin-down / restart / logout / forget all drop it; the visitor re-enters it.
// The raw key leaves this module only inside the server-to-server proxy header.
import { createHash } from "node:crypto";

export const KEY_TTL_MS = 2 * 60 * 60 * 1000; // 2h absolute from set
const MAX_KEY_LEN = 512;
const MIN_KEY_LEN = 8;
const SET_LIMIT = 10; // set attempts per session per hour
const MAX_HELD_KEYS = 1000; // bounded memory: evict soonest-expiring beyond this
const SET_WINDOW_MS = 60 * 60 * 1000;

interface HeldKey {
  key: string;
  keyFp: string;
  expiresAt: number;
}

const hold = new Map<string, HeldKey>();
const setAttempts = new Map<string, number[]>();

class SessionCannotHoldKey extends Error {}

function holdId(session: { email: string; userId?: string; authUserId?: string; token?: string }): string {
  // The hold is bound to the session TOKEN only: logout invalidates the token,
  // so a held key becomes unreachable the moment the visitor signs out. No
  // account-id fallback - an account-stable id would leak the key to a later
  // session. If the platform session ever arrives without a token we fail
  // closed rather than guess an identity.
  if (!session.token) throw new SessionCannotHoldKey("Session cannot hold a key");
  return session.token;
}

export function fingerprintKey(key: string): string {
  return createHash("sha256").update(`vigilens-visitor-key:${key}`).digest("hex");
}

export function validateKeyShape(key: unknown): key is string {
  if (typeof key !== "string") return false;
  if (key.length < MIN_KEY_LEN || key.length > MAX_KEY_LEN) return false;
  for (const c of key) {
    const code = c.codePointAt(0)!;
    if (code < 33 || code > 126) return false;
  }
  return true;
}

export class KeySetRateLimited extends Error {}
export { SessionCannotHoldKey };

export function setVisitorKey(session: { email: string; userId?: string; authUserId?: string; token?: string }, key: string): void {
  const id = holdId(session);
  const now = Date.now();
  const attempts = (setAttempts.get(id) || []).filter((t) => now - t < SET_WINDOW_MS);
  if (attempts.length >= SET_LIMIT) {
    setAttempts.set(id, attempts);
    throw new KeySetRateLimited("Too many key updates; try again later");
  }
  attempts.push(now);
  setAttempts.set(id, attempts);
  // Janitor: drop expired holds and bound total memory. A logout orphans an entry
  // until this sweep or its TTL - bounded by MAX_HELD_KEYS and KEY_TTL_MS.
  for (const [k, v] of hold) if (now >= v.expiresAt) hold.delete(k);
  if (hold.size >= MAX_HELD_KEYS && !hold.has(id)) {
    let oldestKey: string | null = null;
    let oldestExp = Infinity;
    for (const [k, v] of hold) if (v.expiresAt < oldestExp) { oldestExp = v.expiresAt; oldestKey = k; }
    if (oldestKey !== null) hold.delete(oldestKey);
  }
  hold.set(id, {
    key,
    keyFp: fingerprintKey(key),
    expiresAt: now + KEY_TTL_MS,
  });
}

export function getVisitorKey(session: { email: string; userId?: string; authUserId?: string; token?: string }): HeldKey | null {
  let id: string;
  try {
    id = holdId(session);
  } catch {
    return null; // tokenless session: fail closed, treated as no key held
  }
  const entry = hold.get(id);
  if (!entry) return null;
  if (Date.now() >= entry.expiresAt) {
    hold.delete(id);
    return null;
  }
  return entry;
}

export function forgetVisitorKey(session: { email: string; userId?: string; authUserId?: string; token?: string }): boolean {
  try {
    return hold.delete(holdId(session));
  } catch {
    return false;
  }
}

export function visitorKeyStatus(session: { email: string; userId?: string; authUserId?: string; token?: string }) {
  const entry = getVisitorKey(session);
  if (!entry) return { present: false as const };
  return {
    present: true as const,
    // Opaque identifier only - never any part of the raw key.
    fingerprint: entry.keyFp.slice(0, 12),
    expiresAt: new Date(entry.expiresAt).toISOString(),
  };
}

// Test-only: wipe all state.
export function _resetVisitorKeys(): void {
  hold.clear();
  setAttempts.clear();
}
