import { createError, defineEventHandler, getRouterParam, readRawBody } from "h3";
import { proxyToBackend } from "../../../../../../utils/vigilens-proxy";

// Owner-bound reopen of an EXISTING stored job: form body is only the visitor's region
// review (no image). The backend reads the caller's own preserved source, re-verifies
// it, and creates the same in-memory, TTL-bound, unacknowledged preview session as an
// upload. No listing, no download, no provider call, no retry.
export default defineEventHandler(async (event) => {
  const source = getRouterParam(event, "source") ?? "";
  if (!/^[0-9a-f]{64}$/.test(source)) {
    throw createError({ statusCode: 400, statusMessage: "Exact source identifier required" });
  }
  const raw = (await readRawBody(event, false)) ?? "";
  const res = await proxyToBackend(event, `/fresh-review/${source}/private-display/reopen`, { method: "POST", body: raw });
  return new Response(res.body, { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json", "cache-control": "private, no-store" } });
});
