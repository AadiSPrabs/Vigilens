import { createError, defineEventHandler, getRouterParam, readRawBody } from "h3";
import { proxyToBackend } from "../../../../../utils/vigilens-proxy";

// Gated LOCAL report download passthrough. This is the backend's own download
// route - the only sanctioned path from preview to a saved file. It refuses
// (409) while the deployment keeps operator_private_download_enabled false;
// the refusal is passed through and never worked around (the inline preview
// blob is never converted to a download). Saving to the operator's own
// machine is distinct from sending: no share/send path exists anywhere.
export default defineEventHandler(async (event) => {
  const sid = getRouterParam(event, "sid") ?? "";
  if (!/^[A-Za-z0-9_-]{16,64}$/.test(sid)) {
    throw createError({ statusCode: 400, statusMessage: "Exact preview session identifier required" });
  }
  const raw = (await readRawBody(event, false)) ?? "";
  const res = await proxyToBackend(event, `/fresh-private-report/${sid}/private-download`, { method: "POST", body: raw });
  const headers: Record<string, string> = {
    "content-type": res.headers.get("content-type") || "application/json",
    "cache-control": "private, no-store",
  };
  for (const h of ["content-disposition", "x-vigilens-export-allowed", "x-vigilens-use-restriction", "x-vigilens-pdf-sha256"]) {
    const v = res.headers.get(h);
    if (v) headers[h] = v;
  }
  return new Response(res.body, { status: res.status, headers });
});
