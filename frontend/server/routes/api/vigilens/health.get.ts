import { defineEventHandler } from "h3";
import { diagnosticResponse } from "../../../utils/vigilens-response-diagnostics";
import { proxyToBackend } from "../../../utils/vigilens-proxy";

export default defineEventHandler(async (event) => {
  return diagnosticResponse("health", () => proxyToBackend(event, "/health", { method: "GET" }));
});
