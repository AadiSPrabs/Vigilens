// @vitest-environment happy-dom
// Regression: a pending zone-panel action bound to an old source must not land
// its result after the source changes (inverted from the independent v3.4
// review probe that proved the stale bug) or after unmount.
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ loop: vi.fn() }));
vi.mock("../../api/backendClient", () => ({
  runBoundedReviewLoop: m.loop,
  resultShaFromAuditId: () => "b".repeat(64),
  cameraZoneOperation: vi.fn(),
  postZoneReview: vi.fn(),
}));

import { ZoneReviewPanel } from "../ZoneReviewPanel";

const audit = (s: string) => ({ audit_id: s, image: { pixel_digest: s, width: 1280, height: 720 }, persons: [] }) as never;

function loopButton(el: HTMLElement): HTMLButtonElement {
  const b = [...el.querySelectorAll("button")].find((x) => x.textContent?.includes("Run configured"));
  expect(b, "loop button").toBeTruthy();
  return b as HTMLButtonElement;
}

describe("ZoneReviewPanel lifecycle guard", () => {
  it("an old loop response never appears on a replacement source", async () => {
    (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
    let resolve!: (x: unknown) => void;
    m.loop.mockReturnValue(new Promise((r) => (resolve = r)));
    const el = document.createElement("div");
    document.body.append(el);
    const root = createRoot(el);
    await act(async () => root.render(<ZoneReviewPanel audit={audit("old-source")} zones={[]} previewReady />));
    await act(async () => loopButton(el).click());
    await act(async () => root.render(<ZoneReviewPanel audit={audit("new-source")} zones={[]} previewReady />));
    await act(async () => {
      resolve({ status: "human_review_required", unattempted_unknown_person_ids: ["OLD-SOURCE-PERSON"], attempts: [] });
      await new Promise((r) => setTimeout(r, 5));
    });
    expect(el.textContent).not.toContain("OLD-SOURCE-PERSON");
    await act(async () => root.unmount());
    el.remove();
  });

  it("a late loop response after unmount writes nothing", async () => {
    (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
    let resolve!: (x: unknown) => void;
    m.loop.mockReturnValue(new Promise((r) => (resolve = r)));
    const el = document.createElement("div");
    document.body.append(el);
    const root = createRoot(el);
    await act(async () => root.render(<ZoneReviewPanel audit={audit("old-source")} zones={[]} previewReady />));
    await act(async () => loopButton(el).click());
    await act(async () => root.unmount());
    await act(async () => {
      resolve({ status: "human_review_required", unattempted_unknown_person_ids: ["OLD-SOURCE-PERSON"], attempts: [] });
      await new Promise((r) => setTimeout(r, 5));
    });
    expect(el.textContent).not.toContain("OLD-SOURCE-PERSON");
    el.remove();
  });
});
