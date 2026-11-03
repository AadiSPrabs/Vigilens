// Route-level test for the manual contact-claim passthrough. proxyToBackend is mocked; the test pins param validation and
// path/method/body forwarding. No retry. (A missing route made the hosted contact POST return 404 before this existed.)
import { beforeEach, describe, expect, it, vi } from "vitest";

const proxyMock = vi.fn();
const paramsStore: Record<string, string> = {};

vi.mock("h3", async (importOriginal) => {
  const actual = await importOriginal<typeof import("h3")>();
  return {
    ...actual,
    getRouterParam: (_event: unknown, name: string) => paramsStore[name],
    readRawBody: vi.fn().mockResolvedValue('{"person_id":"0"}'),
  };
});
vi.mock("../../../../utils/vigilens-proxy", () => ({
  proxyToBackend: (...args: unknown[]) => proxyMock(...args),
}));

import contactRoute from "../fresh-review/[source]/contact.post";

const SOURCE = "b".repeat(64);

beforeEach(() => {
  proxyMock.mockReset();
  for (const key of Object.keys(paramsStore)) delete paramsStore[key];
});

describe("fresh-review/[source]/contact.post", () => {
  it("rejects a non-hex source with 400 before any backend call", async () => {
    paramsStore.source = "nope";
    await expect(contactRoute({} as never)).rejects.toMatchObject({ statusCode: 400 });
    expect(proxyMock).not.toHaveBeenCalled();
  });

  it("forwards POST to the exact contact path and passes a 409 refusal through", async () => {
    paramsStore.source = SOURCE;
    proxyMock.mockResolvedValue(new Response('{"detail":"Fresh manual contact claim unavailable or invalid"}', { status: 409, headers: { "content-type": "application/json" } }));
    const res = await (contactRoute({} as never) as Promise<Response>);
    const [, path, init] = proxyMock.mock.calls[0] as [unknown, string, { method: string; body: string }];
    expect(path).toBe(`/fresh-review/${SOURCE}/contact`);
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"person_id":"0"}');
    expect(res.status).toBe(409);
  });
});
