import { createError, defineEventHandler, getRouterParam, readRawBody } from "h3";
import { proxyToBackend } from "../../../../../../utils/vigilens-proxy";

// Explanation execution passthrough. The backend re-runs every report gate
// (acked session, exact derivative binding, exact per-person review), then runs
// only the exact pre-reserved attempt under its own exact grant; refusal
// (409/503) is passed through and never retried here. Commentary stays
// unvalidated model text; deterministic fields are unchanged by it.
export default defineEventHandler(async (event) => {
  const sid = getRouterParam(event, "sid") ?? "";
  const attempt = getRouterParam(event, "attempt") ?? "";
  if (!/^[A-Za-z0-9_-]{16,64}$/.test(sid)) {
    throw createError({ statusCode: 400, statusMessage: "Exact preview session identifier required" });
  }
  if (!/^[A-Za-z0-9_-]{4,80}$/.test(attempt)) {
    throw createError({ statusCode: 400, statusMessage: "Exact explanation attempt identifier required" });
  }
  const raw = (await readRawBody(event, false)) ?? "";
  const res = await proxyToBackend(event, `/fresh-private-report/${sid}/explanation/${attempt}`, { method: "POST", body: raw });
  return new Response(res.body, { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json", "cache-control": "private, no-store" } });
});
