import { createError, defineEventHandler, getRouterParam } from "h3";
import { proxyToBackend } from "../../../../../utils/vigilens-proxy";

// Treated preview image passthrough for the caller's own session. The backend
// enforces session ownership; the image is display-only, never exported.
export default defineEventHandler(async (event) => {
  const sid = getRouterParam(event, "sid") ?? "";
  if (!/^[A-Za-z0-9_-]{16,64}$/.test(sid)) {
    throw createError({ statusCode: 400, statusMessage: "Exact preview session identifier required" });
  }
  const res = await proxyToBackend(event, `/private-display/${sid}/image`, { method: "GET" });
  return new Response(res.body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") || "image/png", "cache-control": "private, no-store" },
  });
});
