import { createError, defineEventHandler, getRouterParam, readRawBody } from "h3";
import { diagnosticResponse } from "../../../../../utils/vigilens-response-diagnostics";
import { proxyToBackend } from "../../../../../utils/vigilens-proxy";

// Stored-only audit view of the caller's own job. Never dispatches, reserves or lists; a miss is 409. No retry.
export default defineEventHandler(async (event) => {
  const source = getRouterParam(event, "source") ?? "";
  if (!/^[0-9a-f]{64}$/.test(source)) {
    throw createError({ statusCode: 400, statusMessage: "Exact source identifier required" });
  }
  const raw = (await readRawBody(event, false)) ?? "";
  return diagnosticResponse("stored_reopen", () => proxyToBackend(event, `/fresh-review/${source}/reopen-audit`, { method: "POST", body: raw }), true);
});
