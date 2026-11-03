import { createError, defineEventHandler, getRouterParam, readRawBody } from "h3";
import { proxyToBackend } from "../../../../../utils/vigilens-proxy";

// Private PDF preview passthrough. The backend reuses every source/person/
// visibility/acknowledgment check of the JSON report route and renders the
// TREATED (operator-masked) preview into the PDF - never the original upload.
// The response stays export-disabled (X-Vigilens-Export-Allowed: false is
// forwarded verbatim). No retry on this path.
export default defineEventHandler(async (event) => {
  const sid = getRouterParam(event, "sid") ?? "";
  if (!/^[A-Za-z0-9_-]{16,64}$/.test(sid)) {
    throw createError({ statusCode: 400, statusMessage: "Exact preview session identifier required" });
  }
  const raw = (await readRawBody(event, false)) ?? "";
  const res = await proxyToBackend(event, `/fresh-private-report/${sid}/pdf-preview`, { method: "POST", body: raw });
  return new Response(res.body, {
    status: res.status,
    headers: {
      "content-type": res.headers.get("content-type") || "application/pdf",
      "cache-control": "private, no-store",
      ...(res.headers.get("content-disposition") ? { "content-disposition": res.headers.get("content-disposition") as string } : {}),
      ...(res.headers.get("x-vigilens-export-allowed") ? { "x-vigilens-export-allowed": res.headers.get("x-vigilens-export-allowed") as string } : {}),
      ...(res.headers.get("x-vigilens-pdf-sha256") ? { "x-vigilens-pdf-sha256": res.headers.get("x-vigilens-pdf-sha256") as string } : {}),
    },
  });
});
