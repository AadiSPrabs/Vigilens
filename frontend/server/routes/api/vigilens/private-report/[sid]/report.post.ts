import { createError, defineEventHandler, getRouterParam, readRawBody } from "h3";
import { proxyToBackend } from "../../../../../utils/vigilens-proxy";

// Private report JSON passthrough. The backend enforces the acknowledged
// session, exact derivative binding and exact per-person review; the document
// it returns is a private operator preview (evidence_export_allowed false),
// never released evidence. No retry on this path.
export default defineEventHandler(async (event) => {
  const sid = getRouterParam(event, "sid") ?? "";
  if (!/^[A-Za-z0-9_-]{16,64}$/.test(sid)) {
    throw createError({ statusCode: 400, statusMessage: "Exact preview session identifier required" });
  }
  const raw = (await readRawBody(event, false)) ?? "";
  const res = await proxyToBackend(event, `/fresh-private-report/${sid}`, { method: "POST", body: raw });
  return new Response(res.body, { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json", "cache-control": "private, no-store" } });
});
