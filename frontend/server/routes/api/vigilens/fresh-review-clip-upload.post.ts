import { defineEventHandler, readRawBody } from "h3";
import { proxyToBackend } from "../../../utils/vigilens-proxy";

// Bounded local-clip passthrough: raw multipart body and boundary forwarded
// untouched; only the Vigilens auth headers are (re)written server-side. The
// backend refuses cleanly (409) when no trusted local decoder limits are
// configured; this route never retries.
export default defineEventHandler(async (event) => {
  const raw = (await readRawBody(event, false)) ?? "";
  const res = await proxyToBackend(event, "/fresh-review-clip-upload", { method: "POST", body: raw });
  return new Response(res.body, { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json" } });
});
