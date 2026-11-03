// Route-level tests for zone-review, bounded-review-loop and camera-zones
// passthroughs. proxyToBackend is mocked; tests pin param validation and
// path/method/body forwarding. No retries on any of these paths.
import { beforeEach, describe, expect, it, vi } from "vitest";

const proxyMock = vi.fn();
const paramsStore: Record<string, string> = {};

vi.mock("h3", async (importOriginal) => {
  const actual = await importOriginal<typeof import("h3")>();
  return {
    ...actual,
    getRouterParam: (_event: unknown, name: string) => paramsStore[name],
    readRawBody: vi.fn().mockResolvedValue('{"source_digest":"x"}'),
  };
});
vi.mock("../../../../utils/vigilens-proxy", () => ({
  proxyToBackend: (...args: unknown[]) => proxyMock(...args),
}));

import zoneReviewRoute from "../fresh-review/[source]/zone-review.post";
import loopRoute from "../fresh-review/[source]/bounded-review-loop.post";
import cameraRoute from "../fresh-review/[source]/camera-zones/[operation].post";

const SOURCE = "b".repeat(64);

beforeEach(() => {
  proxyMock.mockReset();
  for (const key of Object.keys(paramsStore)) delete paramsStore[key];
});

describe("fresh-review/[source]/zone-review.post", () => {
  it("rejects a non-hex source with 400 before any backend call", async () => {
    paramsStore.source = "nope";
    await expect(zoneReviewRoute({} as never)).rejects.toMatchObject({ statusCode: 400 });
    expect(proxyMock).not.toHaveBeenCalled();
  });

  it("forwards POST to the exact zone-review path", async () => {
    paramsStore.source = SOURCE;
    proxyMock.mockResolvedValue(new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
    const res = await (zoneReviewRoute({} as never) as Promise<Response>);
    const [, path, init] = proxyMock.mock.calls[0] as [unknown, string, { method: string; body: string }];
    expect(path).toBe(`/fresh-review/${SOURCE}/zone-review`);
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"source_digest":"x"}');
    expect(res.status).toBe(200);
  });
});

describe("fresh-review/[source]/bounded-review-loop.post", () => {
  it("rejects a non-hex source with 400 before any backend call", async () => {
    paramsStore.source = "nope";
    await expect(loopRoute({} as never)).rejects.toMatchObject({ statusCode: 400 });
    expect(proxyMock).not.toHaveBeenCalled();
  });

  it("forwards POST and passes a 409 refusal through unchanged", async () => {
    paramsStore.source = SOURCE;
    proxyMock.mockResolvedValue(new Response("Configured exact recheck loop unavailable", { status: 409, headers: { "content-type": "text/plain" } }));
    const res = await (loopRoute({} as never) as Promise<Response>);
    const [, path, init] = proxyMock.mock.calls[0] as [unknown, string, { method: string }];
    expect(path).toBe(`/fresh-review/${SOURCE}/bounded-review-loop`);
    expect(init.method).toBe("POST");
    expect(res.status).toBe(409);
  });
});

describe("fresh-review/[source]/camera-zones/[operation].post", () => {
  it("rejects an unknown operation with 400 before any backend call", async () => {
    paramsStore.source = SOURCE;
    paramsStore.operation = "delete";
    await expect(cameraRoute({} as never)).rejects.toMatchObject({ statusCode: 400 });
    expect(proxyMock).not.toHaveBeenCalled();
  });

  it("rejects a non-hex source with 400 before any backend call", async () => {
    paramsStore.source = "nope";
    paramsStore.operation = "save";
    await expect(cameraRoute({} as never)).rejects.toMatchObject({ statusCode: 400 });
    expect(proxyMock).not.toHaveBeenCalled();
  });

  it.each(["save", "apply"])("forwards POST for operation %s", async (operation) => {
    paramsStore.source = SOURCE;
    paramsStore.operation = operation;
    proxyMock.mockResolvedValue(new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
    const res = await (cameraRoute({} as never) as Promise<Response>);
    const [, path, init] = proxyMock.mock.calls[0] as [unknown, string, { method: string }];
    expect(path).toBe(`/fresh-review/${SOURCE}/camera-zones/${operation}`);
    expect(init.method).toBe("POST");
    expect(res.status).toBe(200);
  });
});
