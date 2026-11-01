// Visitor BYOK hold: session binding, TTL, rate limit, forget, shape rules.
// The raw key must never appear in status output.
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  setVisitorKey, getVisitorKey, forgetVisitorKey, visitorKeyStatus,
  validateKeyShape, fingerprintKey, KeySetRateLimited, _resetVisitorKeys, KEY_TTL_MS,
} from "../vigilens-keys";

const S1 = { email: "judge@example.com", userId: "user-1", authUserId: "auth-1", token: "sess-token-1" };
const S2 = { email: "other@example.com", userId: "user-2", authUserId: "auth-2", token: "sess-token-2" };

beforeEach(() => {
  _resetVisitorKeys();
  vi.useRealTimers();
});

describe("visitor key hold", () => {
  it("stores per session token and forgets on demand", () => {
    setVisitorKey(S1, "meta-key-aaa");
    setVisitorKey(S2, "meta-key-bbb");
    expect(getVisitorKey(S1)?.key).toBe("meta-key-aaa");
    expect(getVisitorKey(S2)?.key).toBe("meta-key-bbb");
    expect(forgetVisitorKey(S1)).toBe(true);
    expect(getVisitorKey(S1)).toBeNull();
    expect(getVisitorKey(S2)?.key).toBe("meta-key-bbb");
  });

  it("a new session token for the same account does NOT inherit the key (logout revocation)", () => {
    setVisitorKey(S1, "meta-key-aaa");
    const relogin = { ...S1, token: "sess-token-NEW" };
    expect(getVisitorKey(relogin)).toBeNull();
  });

  it("expires after the TTL", () => {
    vi.useFakeTimers();
    setVisitorKey(S1, "meta-key-aaa");
    vi.advanceTimersByTime(KEY_TTL_MS + 1000);
    expect(getVisitorKey(S1)).toBeNull();
  });

  it("rate limits set attempts", () => {
    for (let i = 0; i < 10; i++) setVisitorKey(S1, "meta-key-aaa");
    expect(() => setVisitorKey(S1, "meta-key-aaa")).toThrow(KeySetRateLimited);
  });

  it("validates shape: printable ASCII only, bounded length", () => {
    expect(validateKeyShape("meta-key-0123456789")).toBe(true);
    expect(validateKeyShape("has space")).toBe(false);
    expect(validateKeyShape("has\nnewline")).toBe(false);
    expect(validateKeyShape("short")).toBe(false);
    expect(validateKeyShape("x".repeat(513))).toBe(false);
    expect(validateKeyShape(12345)).toBe(false);
  });

  it("status exposes no part of the raw key", () => {
    setVisitorKey(S1, "meta-key-aaa");
    const status = visitorKeyStatus(S1);
    expect(status.present).toBe(true);
    const serialized = JSON.stringify(status);
    expect(serialized).not.toContain("meta-key-aaa");
    expect(serialized).toContain(fingerprintKey("meta-key-aaa").slice(0, 12));
    expect(visitorKeyStatus(S2).present).toBe(false);
  });
});

describe("bounded memory", () => {
  it("sweeps expired entries and evicts beyond the cap", () => {
    vi.useFakeTimers();
    // 1005 distinct sessions; per-session rate limit (10) is not hit.
    for (let i = 0; i < 1005; i++) {
      setVisitorKey({ email: `v${i}@x.com`, token: `t-${i}` }, `key-${i}`);
    }
    vi.advanceTimersByTime(KEY_TTL_MS + 1000);
    // All expired now; a fresh set triggers the sweep, leaving only the new entry.
    setVisitorKey({ email: "new@x.com", token: "t-new" }, "key-new");
    expect(getVisitorKey({ email: "v0@x.com", token: "t-0" })).toBeNull();
    expect(getVisitorKey({ email: "new@x.com", token: "t-new" })?.key).toBe("key-new");
  });
});
