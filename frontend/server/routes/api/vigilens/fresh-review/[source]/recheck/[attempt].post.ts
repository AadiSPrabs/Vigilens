import { createError, defineEventHandler, getRouterParam, readRawBody } from "h3";
import { proxyToBackend } from "../../../../../../utils/vigilens-proxy";

// Explicit per-attempt recheck execution passthrough. The body must be exactly
// {source_digest, result_sha256} of the attempt's immutable original; the backend
// re-binds and refuses anything else. No retry on this path.
export default defineEventHandler(async (event) => {
  const source = getRouterParam(event, "source") ?? "";
  const attempt = getRouterParam(event, "attempt") ?? "";
  if (!/^[0-9a-f]{64}$/.test(source) || !/^[0-9a-f]{16,64}$/.test(attempt)) {
    throw createError({ statusCode: 400, statusMessage: "Exact source and attempt identifiers required" });
  }
  const raw = (await readRawBody(event, false)) ?? "";
  const res = await proxyToBackend(event, `/fresh-review/${source}/recheck/${attempt}`, { method: "POST", body: raw });
  return new Response(res.body, { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json" } });
});
