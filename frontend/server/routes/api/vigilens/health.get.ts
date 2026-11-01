import { defineEventHandler } from "h3";
import { proxyToBackend } from "../../../utils/vigilens-proxy";

export default defineEventHandler(async (event) => {
  const res = await proxyToBackend(event, "/health", { method: "GET" });
  return new Response(res.body, { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json" } });
});
