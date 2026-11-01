import { defineEventHandler, readRawBody } from "h3";
import { proxyToBackend } from "../../../utils/vigilens-proxy";

// Multipart upload passthrough: the raw body and content-type boundary are
// forwarded untouched; only the Vigilens auth headers are (re)written here.
export default defineEventHandler(async (event) => {
  const raw = (await readRawBody(event, false)) ?? "";
  const res = await proxyToBackend(event, "/fresh-review-audit-governed", { method: "POST", body: raw });
  return new Response(res.body, { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json" } });
});
