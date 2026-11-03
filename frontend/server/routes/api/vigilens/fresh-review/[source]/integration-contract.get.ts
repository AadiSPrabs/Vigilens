import { createError, defineEventHandler, getRouterParam } from "h3";
import { proxyToBackend } from "../../../../../utils/vigilens-proxy";

// Integration-contract passthrough: returns the backend-computed assessment_id
// and stored provider-observation shape for the caller's own exact source.
// Read-only; the backend reports provider_calls_this_request: 0 on this route.
export default defineEventHandler(async (event) => {
  const source = getRouterParam(event, "source") ?? "";
  if (!/^[0-9a-f]{64}$/.test(source)) {
    throw createError({ statusCode: 400, statusMessage: "Exact source identifier required" });
  }
  const res = await proxyToBackend(event, `/fresh-review/${source}/integration-contract`, { method: "GET" });
  return new Response(res.body, { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json", "cache-control": "private, no-store" } });
});
