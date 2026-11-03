// @vitest-environment happy-dom
// R4: the explanation section shows actual attempt state + model commentary
// (never as validated fact) and lets the operator run one exact pre-reserved
// attempt; after running, the gated report is refetched for the current state.
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ contract: vi.fn(), report: vi.fn(), pdf: vi.fn(), explain: vi.fn() }));
vi.mock("../../api/backendClient", () => ({
  fetchIntegrationContract: mocks.contract,
  fetchPrivateReport: mocks.report,
  fetchPrivatePdfPreview: mocks.pdf,
  executeExplanation: mocks.explain,
}));

import { PrivateReportPanel } from "../PrivateReportPanel";

const AUDIT = { persons: [{ id: "0" }] };
const SESSION = { session_id: "sess-12345678", source_digest: "a".repeat(64) };

const RESERVED_REPORT = {
  status: "ok",
  evidence_export_allowed: false,
  spatial_explanations: {
    status: "model_commentary_requires_human_review",
    attempts: [{ attempt_id: "attempt-1234567890abcdef", state: "reserved_not_dispatched" }],
  },
};
const COMPLETED_REPORT = {
  status: "ok",
  evidence_export_allowed: false,
  spatial_explanations: {
    status: "model_commentary_requires_human_review",
    attempts: [{
      attempt_id: "attempt-1234567890abcdef",
      state: "completed",
      result: { explanations: [{ finding_key: "helmet_person_0", model_commentary: "region near head is consistent with a helmet" }] },
      content_review: { status: "unvalidated_requires_human_review", notice: "Commentary has not been accepted as accurate." },
    }],
  },
};

async function render(el: HTMLDivElement, root: ReturnType<typeof createRoot>) {
  await act(async () => root.render(<PrivateReportPanel audit={AUDIT as never} session={SESSION as never} />));
}

describe("PrivateReportPanel explanation workflow", () => {
  beforeEach(() => {
    mocks.contract.mockReset();
    mocks.report.mockReset();
    mocks.pdf.mockReset();
    mocks.explain.mockReset();
  });

  it("renders attempt state, runs one exact attempt, then shows unvalidated commentary", async () => {
    (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
    mocks.contract.mockResolvedValue({ assessment_id: "assess-1" });
    mocks.report.mockResolvedValueOnce(RESERVED_REPORT).mockResolvedValueOnce(COMPLETED_REPORT);
    mocks.pdf.mockResolvedValue(new Blob(["%PDF-"], { type: "application/pdf" }));
    mocks.explain.mockResolvedValue({ state: "completed" });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:preview");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(window, "open").mockImplementation(() => null);

    const el = document.createElement("div");
    document.body.append(el);
    const root = createRoot(el);
    await render(el, root);

    // Generate the gated report (reserved attempt is listed).
    await act(async () => ([...el.querySelectorAll("button")].find((b) => b.textContent?.includes("Generate private PDF preview")) as HTMLButtonElement).click());
    expect(el.textContent).toContain("reserved_not_dispatched");

    // Run the exact attempt; the report is refetched and commentary renders
    // with its unvalidated content review, never as accepted fact.
    await act(async () => ([...el.querySelectorAll("button")].find((b) => b.textContent?.includes("Run this exact explanation attempt")) as HTMLButtonElement).click());
    expect(mocks.explain).toHaveBeenCalledTimes(1);
    expect(String(mocks.explain.mock.calls[0]![3])).toBe("attempt-1234567890abcdef");
    expect(mocks.report).toHaveBeenCalledTimes(2);
    expect(el.textContent).toContain("region near head is consistent with a helmet");
    expect(el.textContent).toContain("unvalidated_requires_human_review");
    expect(el.textContent).toContain("never accepted as accurate");

    await act(async () => root.unmount());
    el.remove();
  });

  it("shows the not-configured state without an execute control", async () => {
    (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
    mocks.contract.mockResolvedValue({ assessment_id: "assess-1" });
    mocks.report.mockResolvedValue({ status: "ok", evidence_export_allowed: false, spatial_explanations: { status: "not_configured" } });
    mocks.pdf.mockResolvedValue(new Blob(["%PDF-"], { type: "application/pdf" }));
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:preview");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(window, "open").mockImplementation(() => null);

    const el = document.createElement("div");
    document.body.append(el);
    const root = createRoot(el);
    await render(el, root);
    await act(async () => ([...el.querySelectorAll("button")].find((b) => b.textContent?.includes("Generate private PDF preview")) as HTMLButtonElement).click());
    expect(el.textContent).toContain("not configured for this deployment");
    expect([...el.querySelectorAll("button")].some((b) => b.textContent?.includes("Run this exact explanation attempt"))).toBe(false);
    expect(mocks.explain).not.toHaveBeenCalled();
    await act(async () => root.unmount());
    el.remove();
  });
});
