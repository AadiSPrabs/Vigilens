// Deliberately narrow, secret-free diagnostics for two stored-only read flows.
// Never log a URL, source digest, account, header value, error text or body.
type RouteTag = "health" | "stored_reopen";

function statusOf(error: unknown): number {
  const value = error && typeof error === "object" && "statusCode" in error
    ? (error as { statusCode?: unknown }).statusCode : undefined;
  return typeof value === "number" && Number.isInteger(value) && value >= 400 && value <= 599 ? value : 500;
}

export function diagnosticHeaders(response: Response, privateCache = false): Headers {
  const headers = new Headers({ "content-type": response.headers.get("content-type") || "application/json" });
  if (privateCache) headers.set("cache-control", "private, no-store");
  const retry = response.headers.get("retry-after");
  // Copy only bounded standard values. Never turn an arbitrary header into UI text.
  if (retry && (/^\d{1,5}$/.test(retry) && Number(retry) <= 86400 ||
      /^[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} GMT$/.test(retry) && Number.isFinite(Date.parse(retry)))) {
    headers.set("retry-after", retry);
  }
  for (const name of ["rndr-id", "x-request-id"]) {
    const value = response.headers.get(name);
    if (value && /^[a-zA-Z0-9][a-zA-Z0-9_-]{7,127}$/.test(value)) headers.set(name, value);
  }
  return headers;
}

export async function diagnosticResponse(route: RouteTag, operation: () => Promise<Response>, privateCache = false): Promise<Response> {
  let response: Response;
  try {
    response = await operation();
  } catch (error) {
    console.info(JSON.stringify({ event: "vigilens.proxy_diagnostic", route, phase: "no_upstream_response", status: statusOf(error) }));
    throw error; // Preserve the original failure and every existing auth/dispatch gate.
  }
  console.info(JSON.stringify({ event: "vigilens.proxy_diagnostic", route, phase: "upstream_response", status: response.status }));
  return new Response(response.body, { status: response.status, headers: diagnosticHeaders(response, privateCache) });
}
