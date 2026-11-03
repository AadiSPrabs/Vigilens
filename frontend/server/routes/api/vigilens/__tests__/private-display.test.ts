// Route-level tests for the private-display ceremony passthroughs.
// proxyToBackend is mocked; these tests pin param validation, path/method
// forwarding, and content-type passthrough. No retries anywhere on this path.
import { beforeEach, describe, expect, it, vi } from "vitest";

const proxyMock = vi.fn();
const paramsStore: Record<string, string> = {};

vi.mock("h3", async (importOriginal) => {
  const actual = await importOriginal<typeof import("h3")>();
  return {
    ...actual,
    getRouterParam: (_event: unknown, name: string) => paramsStore[name],
    readRawBody: vi.fn().mockResolvedValue("RAW-MULTIPART-BODY"),
  };
});
vi.mock("../../../../utils/vigilens-proxy", () => ({
  proxyToBackend: (...args: unknown[]) => proxyMock(...args),
}));

import prepareRoute from "../fresh-review/[source]/private-display.post";
import imageRoute from "../private-display/[sid]/image.get";
import reviewRoute from "../private-display/[sid]/review.post";

const SOURCE = "a".repeat(64);
const SID = "sess-token_abc-1234567890";

function okResponse(body: string, contentType = "application/json") {
  return new Response(body, { status: 200, headers: { "content-type": contentType } });
}

beforeEach(() => {
  proxyMock.mockReset();
  for (const key of Object.keys(paramsStore)) delete paramsStore[key];
});

describe("fresh-review/[source]/private-display.post", () => {
  it("rejects a non-hex source with 400 before any backend call", async () => {
    paramsStore.source = "not-hex";
    await expect(prepareRoute({} as never)).rejects.toMatchObject({ statusCode: 400 });
    expect(proxyMock).not.toHaveBeenCalled();
  });

  it("forwards the multipart body untouched to the exact source path", async () => {
    paramsStore.source = SOURCE;
    proxyMock.mockResolvedValue(okResponse('{"session_id":"x"}'));
    const res = await (prepareRoute({} as never) as Promise<Response>);
    expect(proxyMock).toHaveBeenCalledTimes(1);
    const [ , path, init ] = proxyMock.mock.calls[0] as [unknown, string, { method: string; body: string }];
    expect(path).toBe(`/fresh-review/${SOURCE}/private-display`);
    expect(init.method).toBe("POST");
    expect(init.body).toBe("RAW-MULTIPART-BODY");
    expect(res.status).toBe(200);
    expect(await res.text()).toBe('{"session_id":"x"}');
  });
});

describe("private-display/[sid]/review.post", () => {
  it("rejects a session id with illegal characters with 400", async () => {
    paramsStore.sid = "bad/../sid";
    await expect(reviewRoute({} as never)).rejects.toMatchObject({ statusCode: 400 });
    expect(proxyMock).not.toHaveBeenCalled();
  });

  it("forwards the acknowledgment JSON to the exact session path", async () => {
    paramsStore.sid = SID;
    proxyMock.mockResolvedValue(okResponse('{"status":"acknowledged"}'));
    const res = await (reviewRoute({} as never) as Promise<Response>);
    const [ , path, init ] = proxyMock.mock.calls[0] as [unknown, string, { method: string; body: string }];
    expect(path).toBe(`/private-display/${SID}/review`);
    expect(init.method).toBe("POST");
    expect(init.body).toBe("RAW-MULTIPART-BODY");
    expect(res.status).toBe(200);
  });
});

describe("private-display/[sid]/image.get", () => {
  it("rejects an illegal session id with 400", async () => {
    paramsStore.sid = "!!";
    await expect(imageRoute({} as never)).rejects.toMatchObject({ statusCode: 400 });
    expect(proxyMock).not.toHaveBeenCalled();
  });

  it("streams the treated image with content-type passthrough and no-store", async () => {
    paramsStore.sid = SID;
    proxyMock.mockResolvedValue(okResponse("PNGBYTES", "image/png"));
    const res = await (imageRoute({} as never) as Promise<Response>);
    const [ , path, init ] = proxyMock.mock.calls[0] as [unknown, string, { method: string }];
    expect(path).toBe(`/private-display/${SID}/image`);
    expect(init.method).toBe("GET");
    expect(res.headers.get("content-type")).toBe("image/png");
    expect(res.headers.get("cache-control")).toBe("private, no-store");
    expect(await res.text()).toBe("PNGBYTES");
  });
});
