import { createError, defineEventHandler, getRouterParam, readRawBody } from "h3";
import { proxyToBackend } from "../../../../../utils/vigilens-proxy";

// Manual ground-contact claim passthrough: records one operator claim for one person of the
// exact source/result. The backend requires the acknowledged treated preview
// and the exact result digest and person mask; 409 otherwise. No retry.
export default defineEventHandler(async (event) => {
  const source = getRouterParam(event, "source") ?? "";
  if (!/^[0-9a-f]{64}$/.test(source)) {
    throw createError({ statusCode: 400, statusMessage: "Exact source identifier required" });
  }
  const raw = (await readRawBody(event, false)) ?? "";
  const res = await proxyToBackend(event, `/fresh-review/${source}/contact`, { method: "POST", body: raw });
  return new Response(res.body, { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json", "cache-control": "private, no-store" } });
});
