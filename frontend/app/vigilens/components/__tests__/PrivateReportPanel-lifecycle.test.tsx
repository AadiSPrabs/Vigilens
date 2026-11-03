// @vitest-environment happy-dom
// Regression: an in-flight generate() must not issue report/PDF requests or
// open a preview window after the panel unmounts or the session changes.
// Inverted from the independent v3.3 review probe that proved the stale bug.
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ contract: vi.fn(), report: vi.fn(), pdf: vi.fn() }));
vi.mock("../../api/backendClient", () => ({
  fetchIntegrationContract: mocks.contract,
  fetchPrivateReport: mocks.report,
  fetchPrivatePdfPreview: mocks.pdf,
}));

import { PrivateReportPanel } from "../PrivateReportPanel";

const AUDIT = { persons: [{ id: "0" }] };
const SESSION = { session_id: "old-session", source_digest: "old-source" };

describe("PrivateReportPanel lifecycle guard", () => {
  it("issues no report/PDF request and opens no preview after unmount", async () => {
    (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
    let resolve!: (x: unknown) => void;
    mocks.contract.mockReturnValue(new Promise((r) => (resolve = r)));
    mocks.report.mockResolvedValue({ evidence_export_allowed: false });
    mocks.pdf.mockResolvedValue(new Blob(["%PDF-"], { type: "application/pdf" }));
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:old-preview");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    const el = document.createElement("div");
    document.body.append(el);
    const root = createRoot(el);
    await act(async () => root.render(<PrivateReportPanel audit={AUDIT as never} session={SESSION as never} />));
    await act(async () => (el.querySelectorAll("button")[0] as HTMLButtonElement).click());
    await act(async () => root.unmount());
    await act(async () => {
      resolve({ assessment_id: "old-assessment" });
      await new Promise((r) => setTimeout(r, 10));
    });
    expect(mocks.contract).toHaveBeenCalledTimes(1);
    expect(mocks.report).not.toHaveBeenCalled();
    expect(mocks.pdf).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
  });

  it("ignores a stale generation after the session changes mid-flight", async () => {
    (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
    let resolve!: (x: unknown) => void;
    mocks.contract.mockReturnValue(new Promise((r) => (resolve = r)));
    mocks.report.mockResolvedValue({ evidence_export_allowed: false });
    mocks.pdf.mockResolvedValue(new Blob(["%PDF-"], { type: "application/pdf" }));
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    const el = document.createElement("div");
    document.body.append(el);
    const root = createRoot(el);
    await act(async () => root.render(<PrivateReportPanel audit={AUDIT as never} session={SESSION as never} />));
    await act(async () => (el.querySelectorAll("button")[0] as HTMLButtonElement).click());
    await act(async () =>
      root.render(<PrivateReportPanel audit={AUDIT as never} session={{ session_id: "new-session", source_digest: "new-source" } as never} />),
    );
    await act(async () => {
      resolve({ assessment_id: "old-assessment" });
      await new Promise((r) => setTimeout(r, 10));
    });
    expect(mocks.report).not.toHaveBeenCalled();
    expect(mocks.pdf).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
  });
});
