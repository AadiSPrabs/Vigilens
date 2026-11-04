import { defineEventHandler, readRawBody } from "h3";
import { proxyToBackend } from "../../../utils/vigilens-proxy";
// Exact uploaded source lookup, owner derived by proxy. Read-only backend action.
export default defineEventHandler(async (event) => {
  const body = (await readRawBody(event, false)) ?? "";
  const res = await proxyToBackend(event, "/fresh-review-job-status", { method: "POST", body });
  return new Response(res.body, { status: res.status, headers: { "content-type": "application/json", "cache-control": "private, no-store" } });
});
