// @vitest-environment happy-dom
// Product reservation path: when rules are configured the report exposes the exact plan sha;
// the operator can reserve (no provider call) and the report is refetched so the
// reserved attempt (and its run button) appears. Refusal shows as-is, no retry.
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ contract: vi.fn(), report: vi.fn(), pdf: vi.fn(), explain: vi.fn(), reserve: vi.fn() }));
vi.mock("../../api/backendClient", () => ({
  fetchIntegrationContract: mocks.contract,
  fetchPrivateReport: mocks.report,
  fetchPrivatePdfPreview: mocks.pdf,
  executeExplanation: mocks.explain,
  reserveExplanation: mocks.reserve,
}));
import { PrivateReportPanel } from "../PrivateReportPanel";

const SESSION = { session_id: "sess-12345678", source_digest: "a".repeat(64) };
const PLAN = "b".repeat(64);
const READY = { status: "ok", evidence_export_allowed: false, spatial_explanations: { status: "model_commentary_requires_human_review", attempts: [], exact_plan_sha256: PLAN } };
const RESERVED = { ...READY, spatial_explanations: { ...READY.spatial_explanations, attempts: [{ attempt_id: "attempt-1234567890abcdef", state: "reserved_not_dispatched" }] } };

async function mount() {
  (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
  mocks.contract.mockResolvedValue({ assessment_id: "assess-1" });
  mocks.pdf.mockResolvedValue(new Blob(["%PDF-"], { type: "application/pdf" }));
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:preview");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  const el = document.createElement("div");
  document.body.append(el);
  const root = createRoot(el);
  await act(async () => root.render(<PrivateReportPanel audit={{ persons: [{ id: "0" }] } as never} session={SESSION as never} />));
  await act(async () => ([...el.querySelectorAll("button")].find((b) => b.textContent?.includes("Generate private PDF preview")) as HTMLButtonElement).click());
  return el;
}
const btn = (el: HTMLElement, t: string) => [...el.querySelectorAll("button")].find((b) => b.textContent?.includes(t)) as HTMLButtonElement | undefined;

describe("explanation reservation", () => {
  beforeEach(() => { Object.values(mocks).forEach((m) => m.mockReset()); });

  it("shows the exact plan, reserves with no run, then offers the run button", async () => {
    mocks.report.mockResolvedValueOnce(READY).mockResolvedValueOnce(RESERVED);
    mocks.reserve.mockResolvedValue({ attempt_id: "attempt-1234567890abcdef", state: "reserved_not_dispatched", plan_sha256: PLAN, provider_calls_this_request: 0, grant_created_here: false });
    const el = await mount();
    expect(el.textContent).toContain(PLAN);
    expect(el.textContent).toContain("cannot create");
    expect(btn(el, "Run this exact explanation attempt")).toBeUndefined();
    await act(async () => btn(el, "Reserve this exact explanation")!.click());
    expect(mocks.reserve).toHaveBeenCalledTimes(1);
    expect(mocks.explain).not.toHaveBeenCalled();
    expect(mocks.report).toHaveBeenCalledTimes(2);
    expect(btn(el, "Run this exact explanation attempt")).toBeTruthy();
    expect(btn(el, "Reserve this exact explanation")).toBeUndefined();
  });

  it("surfaces a refusal as-is with no retry and no run", async () => {
    mocks.report.mockResolvedValueOnce(READY);
    mocks.reserve.mockRejectedValue(new Error("Explanation reservation unavailable (409). No automatic retry."));
    const el = await mount();
    await act(async () => btn(el, "Reserve this exact explanation")!.click());
    expect(el.textContent).toContain("No automatic retry");
    expect(mocks.reserve).toHaveBeenCalledTimes(1);
    expect(mocks.explain).not.toHaveBeenCalled();
    expect(mocks.report).toHaveBeenCalledTimes(1);
  });
});
