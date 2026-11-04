// One public health request per frontend process start. Not a readiness promise,
// keep-alive, authenticated operation, provider call, or analysis retry.
export async function wakeVigilensBackend(
  base = process.env.VIGILENS_BACKEND_URL || "",
  request: typeof fetch = fetch,
): Promise<"skipped" | "requested" | "unavailable"> {
  if (!base.trim()) return "skipped";
  let url: URL;
  try {
    url = new URL(base.replace(/\/+$/, "") + "/health");
    if (!["https:", "http:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) return "skipped";
  } catch {
    return "skipped";
  }
  try {
    const response = await request(url.toString(), {
      method: "GET",
      redirect: "error",
      signal: AbortSignal.timeout(75_000),
      // /health is public. Never attach backend access or visitor API keys.
    });
    await response.body?.cancel();
    return response.ok ? "requested" : "unavailable";
  } catch {
    return "unavailable";
  }
}
