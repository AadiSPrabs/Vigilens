import { createError, defineEventHandler, getRouterParam, readRawBody } from "h3";
import { proxyToBackend } from "../../../../../utils/vigilens-proxy";

// Private-display acknowledgment passthrough. The backend accepts only the exact
// acknowledgment of the exact derivative (strict typed equality) and refuses
// anything else with 409; this route never retries.
export default defineEventHandler(async (event) => {
  const sid = getRouterParam(event, "sid") ?? "";
  if (!/^[A-Za-z0-9_-]{16,64}$/.test(sid)) {
    throw createError({ statusCode: 400, statusMessage: "Exact preview session identifier required" });
  }
  const raw = (await readRawBody(event, false)) ?? "";
  const res = await proxyToBackend(event, `/private-display/${sid}/review`, { method: "POST", body: raw });
  return new Response(res.body, { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json" } });
});
