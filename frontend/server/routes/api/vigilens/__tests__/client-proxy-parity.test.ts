// Every /api/vigilens path the browser client calls must have a matching proxy route file with the same method.
// (The manual contact POST once had none and returned 404 on the hosted app.)
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const ROUTES = path.resolve(__dirname, "..");
const CLIENT_FILES = [path.resolve(__dirname, "../../../../../app/vigilens/api/backendClient.ts")];

function routeFiles(dir: string, prefix = ""): { pattern: string; method: string }[] {
  const out: { pattern: string; method: string }[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "__tests__") continue;
    if (entry.isDirectory()) {
      out.push(...routeFiles(path.join(dir, entry.name), `${prefix}/${entry.name.replace(/^\[(.+)\]$/, ":$1")}`));
    } else {
      const m = /^(.+)\.(get|post|put|delete)\.ts$/.exec(entry.name);
      if (m) out.push({ pattern: `${prefix}/${m[1]!.replace(/^\[(.+)\]$/, ":$1")}`, method: m[2]!.toUpperCase() });
    }
  }
  return out;
}

function clientCalls(source: string): { url: string; method: string }[] {
  const calls: { url: string; method: string }[] = [];
  const re = /fetch\(\s*([`"'])(\/api\/vigilens\/[^`"']*)\1\s*(?:,\s*\{([\s\S]*?)\}\s*\))?/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(source))) {
    const url = m[2]!.replace(/\$\{[^}]*\}/g, ":p").replace(/\?.*$/, "");
    const method = /method:\s*"(\w+)"/.exec(m[3] ?? "")?.[1] ?? "GET";
    calls.push({ url: url.replace(/^\/api\/vigilens/, ""), method });
  }
  return calls;
}

const matches = (pattern: string, url: string) => {
  const a = pattern.split("/");
  const b = url.split("/");
  return a.length === b.length && a.every((seg, i) => seg.startsWith(":") || b[i]!.startsWith(":") || seg === b[i]);
};

describe("browser client paths have proxy routes", () => {
  const routes = routeFiles(path.join(ROUTES));
  const calls = CLIENT_FILES.flatMap((f) => clientCalls(fs.readFileSync(f, "utf8")));
  it("finds a meaningful number of client calls and routes", () => {
    expect(calls.length).toBeGreaterThan(10);
    expect(routes.length).toBeGreaterThan(10);
    expect(calls.some((c) => c.url.endsWith("/contact") && c.method === "POST")).toBe(true);
  });
  it.each(calls.map((c) => [`${c.method} ${c.url}`, c] as const))("%s has a matching route file", (_label, call) => {
    expect(routes.some((r) => r.method === call.method && matches(r.pattern, call.url)), `no proxy route for ${call.method} ${call.url}`).toBe(true);
  });
});
