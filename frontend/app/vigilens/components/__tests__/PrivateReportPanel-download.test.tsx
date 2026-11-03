// @vitest-environment happy-dom
// Gated local download control: uses ONLY the backend private-download route.
// A refusal (409 while the deployment keeps operator download disabled) is
// surfaced as-is; the inline preview blob is never converted into a file.
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ contract: vi.fn(), report: vi.fn(), pdf: vi.fn(), explain: vi.fn(), download: vi.fn() }));
vi.mock("../../api/backendClient", () => ({
  fetchIntegrationContract: mocks.contract,
  fetchPrivateReport: mocks.report,
  fetchPrivatePdfPreview: mocks.pdf,
  executeExplanation: mocks.explain,
  fetchPrivateReportDownload: mocks.download,
}));

import { PrivateReportPanel } from "../PrivateReportPanel";

const AUDIT = { persons: [{ id: "0" }] };
const SESSION = { session_id: "sess-12345678", source_digest: "a".repeat(64) };

describe("PrivateReportPanel gated local download", () => {
  beforeEach(() => {
    (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
    Object.values(mocks).forEach((m) => m.mockReset());
    mocks.contract.mockResolvedValue({ assessment_id: "assess-1" });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:dl");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  });

  it("surfaces the gated refusal as-is and downloads nothing", async () => {
    mocks.download.mockRejectedValue(new Error("Local report download is not enabled in this deployment; the inline preview is view-only"));
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const el = document.createElement("div");
    document.body.append(el);
    const root = createRoot(el);
    await act(async () => root.render(<PrivateReportPanel audit={AUDIT as never} session={SESSION as never} />));
    await act(async () => ([...el.querySelectorAll("button")].find((b) => b.textContent?.includes("Save a local copy")) as HTMLButtonElement).click());
    expect(mocks.download).toHaveBeenCalledTimes(1);
    expect(el.textContent).toContain("not enabled in this deployment");
    expect(anchorClick).not.toHaveBeenCalled();
    await act(async () => root.unmount());
    el.remove();
  });

  it("a successful gated response downloads via an anchor with the private filename", async () => {
    mocks.download.mockResolvedValue(new Blob(["%PDF-"], { type: "application/pdf" }));
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const el = document.createElement("div");
    document.body.append(el);
    const root = createRoot(el);
    await act(async () => root.render(<PrivateReportPanel audit={AUDIT as never} session={SESSION as never} />));
    await act(async () => ([...el.querySelectorAll("button")].find((b) => b.textContent?.includes("Save a local copy")) as HTMLButtonElement).click());
    expect(anchorClick).toHaveBeenCalledTimes(1);
    expect(el.textContent).toContain("not certified safe to share");
    await act(async () => root.unmount());
    el.remove();
  });
});
