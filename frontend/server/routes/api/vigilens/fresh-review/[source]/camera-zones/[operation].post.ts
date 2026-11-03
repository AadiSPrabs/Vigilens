import { createError, defineEventHandler, getRouterParam, readRawBody } from "h3";
import { proxyToBackend } from "../../../../../../utils/vigilens-proxy";

// Camera-zone template passthrough (save | apply). The backend enforces the
// acknowledged preview, the exact source/result, the exact scene/raster binding
// and an operator fixed-scene confirmation; no automatic registration or
// transform exists. This route never retries.
export default defineEventHandler(async (event) => {
  const source = getRouterParam(event, "source") ?? "";
  const operation = getRouterParam(event, "operation") ?? "";
  if (!/^[0-9a-f]{64}$/.test(source)) {
    throw createError({ statusCode: 400, statusMessage: "Exact source identifier required" });
  }
  if (operation !== "save" && operation !== "apply") {
    throw createError({ statusCode: 400, statusMessage: "Exact template action required" });
  }
  const raw = (await readRawBody(event, false)) ?? "";
  const res = await proxyToBackend(event, `/fresh-review/${source}/camera-zones/${operation}`, { method: "POST", body: raw });
  return new Response(res.body, { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json", "cache-control": "private, no-store" } });
});
