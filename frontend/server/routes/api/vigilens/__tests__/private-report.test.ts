// Route-level tests for the integration-contract and private PDF preview
// passthroughs. proxyToBackend is mocked; these tests pin param validation,
// path/method forwarding, and PDF header passthrough. No retries on this path.
import { beforeEach, describe, expect, it, vi } from "vitest";

const proxyMock = vi.fn();
const paramsStore: Record<string, string> = {};

vi.mock("h3", async (importOriginal) => {
  const actual = await importOriginal<typeof import("h3")>();
  return {
    ...actual,
    getRouterParam: (_event: unknown, name: string) => paramsStore[name],
    readRawBody: vi.fn().mockResolvedValue('{"assessment_id":"fresh:a:b"}'),
  };
});
vi.mock("../../../../utils/vigilens-proxy", () => ({
  proxyToBackend: (...args: unknown[]) => proxyMock(...args),
}));

import contractRoute from "../fresh-review/[source]/integration-contract.get";
import pdfRoute from "../private-report/[sid]/pdf-preview.post";
import reportRoute from "../private-report/[sid]/report.post";

const SOURCE = "a".repeat(64);
const SID = "sess-token_abc-1234567890";

beforeEach(() => {
  proxyMock.mockReset();
  for (const key of Object.keys(paramsStore)) delete paramsStore[key];
});

describe("fresh-review/[source]/integration-contract.get", () => {
  it("rejects a non-hex source with 400 before any backend call", async () => {
    paramsStore.source = "not-hex";
    await expect(contractRoute({} as never)).rejects.toMatchObject({ statusCode: 400 });
    expect(proxyMock).not.toHaveBeenCalled();
  });

  it("forwards GET to the exact source contract path", async () => {
    paramsStore.source = SOURCE;
    proxyMock.mockResolvedValue(new Response('{"assessment_id":"fresh:x:y"}', { status: 200, headers: { "content-type": "application/json" } }));
    const res = await (contractRoute({} as never) as Promise<Response>);
    expect(proxyMock).toHaveBeenCalledTimes(1);
    const [, path, init] = proxyMock.mock.calls[0] as [unknown, string, { method: string }];
    expect(path).toBe(`/fresh-review/${SOURCE}/integration-contract`);
    expect(init.method).toBe("GET");
    expect(res.status).toBe(200);
  });
});

describe("private-report/[sid]/pdf-preview.post", () => {
  it("rejects a malformed session id with 400 before any backend call", async () => {
    paramsStore.sid = "bad sid!";
    await expect(pdfRoute({} as never)).rejects.toMatchObject({ statusCode: 400 });
    expect(proxyMock).not.toHaveBeenCalled();
  });

  it("forwards the exact review body and passes PDF headers through", async () => {
    paramsStore.sid = SID;
    proxyMock.mockResolvedValue(
      new Response(new Uint8Array([0x25, 0x50, 0x44, 0x46]), {
        status: 200,
        headers: {
          "content-type": "application/pdf",
          "content-disposition": 'inline; filename="vigilens-private-preview.pdf"',
          "x-vigilens-export-allowed": "false",
          "x-vigilens-pdf-sha256": "abc123",
        },
      }),
    );
    const res = await (pdfRoute({} as never) as Promise<Response>);
    expect(proxyMock).toHaveBeenCalledTimes(1);
    const [, path, init] = proxyMock.mock.calls[0] as [unknown, string, { method: string; body: string }];
    expect(path).toBe(`/fresh-private-report/${SID}/pdf-preview`);
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"assessment_id":"fresh:a:b"}');
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("application/pdf");
    expect(res.headers.get("x-vigilens-export-allowed")).toBe("false");
    expect(res.headers.get("x-vigilens-pdf-sha256")).toBe("abc123");
    expect(res.headers.get("cache-control")).toBe("private, no-store");
  });

  it("passes a backend refusal through unchanged", async () => {
    paramsStore.sid = SID;
    proxyMock.mockResolvedValue(new Response("Private PDF preview unavailable; no original fallback or release", { status: 409, headers: { "content-type": "text/plain" } }));
    const res = await (pdfRoute({} as never) as Promise<Response>);
    expect(res.status).toBe(409);
  });
});

describe("private-report/[sid]/report.post", () => {
  it("rejects a malformed session id with 400 before any backend call", async () => {
    paramsStore.sid = "bad sid!";
    await expect(reportRoute({} as never)).rejects.toMatchObject({ statusCode: 400 });
    expect(proxyMock).not.toHaveBeenCalled();
  });

  it("forwards the exact review body to the report path", async () => {
    paramsStore.sid = SID;
    proxyMock.mockResolvedValue(new Response('{"status":"needs_human_review","evidence_export_allowed":false}', { status: 200, headers: { "content-type": "application/json" } }));
    const res = await (reportRoute({} as never) as Promise<Response>);
    expect(proxyMock).toHaveBeenCalledTimes(1);
    const [, path, init] = proxyMock.mock.calls[0] as [unknown, string, { method: string; body: string }];
    expect(path).toBe(`/fresh-private-report/${SID}`);
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"assessment_id":"fresh:a:b"}');
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("private, no-store");
  });
});
