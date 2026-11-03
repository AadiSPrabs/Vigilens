// @vitest-environment happy-dom
// Renders the ACTUAL backend v6.2 configured-synthetic report fixture
// (verbatim, no invented mock shape): deliberate_rechecks attempts carry
// binding.person_id + result.candidate_observations.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

const FIXTURE = JSON.parse(
  readFileSync(join(__dirname, "fixtures", "v35-actual-synthetic-report.json"), "utf8"),
) as Record<string, unknown>;

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

describe("PrivateReportPanel deliberate_rechecks (actual v6.2 contract)", () => {
  beforeEach(() => {
    (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
    Object.values(mocks).forEach((m) => m.mockReset());
    mocks.contract.mockResolvedValue({ assessment_id: "assess-1" });
    mocks.report.mockResolvedValue(FIXTURE);
    mocks.pdf.mockResolvedValue(new Blob(["%PDF-"], { type: "application/pdf" }));
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:preview");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  });

  it("renders the real recheck attempt: person from binding, state, candidate observations", async () => {
    const el = document.createElement("div");
    document.body.append(el);
    const root = createRoot(el);
    await act(async () => root.render(<PrivateReportPanel audit={AUDIT as never} session={SESSION as never} />));
    await act(async () => ([...el.querySelectorAll("button")].find((b) => b.textContent?.includes("Generate private PDF preview")) as HTMLButtonElement).click());
    const text = el.textContent ?? "";
    expect(text).toContain("Deliberate rechecks: separate_candidates_require_review");
    expect(text).toContain("Person 0: completed");
    expect(text).toContain("candidate needs separate human review, never adopted automatically");
    expect(text).toContain("candidate_observations");
    expect(text).not.toContain("Person ?:");
    await act(async () => root.unmount());
    el.remove();
  });
});
