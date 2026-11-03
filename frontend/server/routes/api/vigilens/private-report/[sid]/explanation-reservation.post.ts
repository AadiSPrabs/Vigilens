import { createError, defineEventHandler, getRouterParam, readRawBody } from "h3";
import { proxyToBackend } from "../../../../../utils/vigilens-proxy";

// Reserve (not run) the exact current explanation plan. The backend requires
// configured rules and an exact server-side grant for this plan; it creates no
// grant and makes no provider call. Refusal (409) passes through, no retry.
export default defineEventHandler(async (event) => {
  const sid = getRouterParam(event, "sid") ?? "";
  if (!/^[A-Za-z0-9_-]{16,64}$/.test(sid)) {
    throw createError({ statusCode: 400, statusMessage: "Exact preview session identifier required" });
  }
  const raw = (await readRawBody(event, false)) ?? "";
  const res = await proxyToBackend(event, `/fresh-private-report/${sid}/explanation-reservation`, { method: "POST", body: raw });
  return new Response(res.body, { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json", "cache-control": "private, no-store" } });
});
