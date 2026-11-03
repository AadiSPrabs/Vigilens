// @vitest-environment happy-dom
// R5 regression: the ceremony must NOT auto-mask whole-person boxes (that
// erased PPE evidence). Masking is face-proposal-driven plus generic manual
// regions the operator adds. The face check auto-runs once on mount.
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { createElement } from "react";
import { PreviewCeremony } from "../PreviewCeremony";
import type { Audit } from "../../types";

const SOURCE = "a".repeat(64);

function audit(): Audit {
  return {
    audit_id: "fresh:abc:def", schema_version: "0.2-local-draft", source: "backend", created_at: null,
    image: { id: "0123456789abcdef", pixel_digest: SOURCE, width: 1280, height: 720 },
    source_digest: SOURCE, zones: [], evidence_image: null, evidence_status: "unavailable",
    evidence_export_allowed: false,
    persons: [
      { id: "person-7", polygon: [{ x: 0.1, y: 0.1 }, { x: 0.5, y: 0.1 }, { x: 0.5, y: 0.9 }, { x: 0.1, y: 0.9 }] },
    ],
    readings_origin: "synthetic", readings_status: "unvalidated_provider_observations", zones_applied: false,
  } as unknown as Audit;
}

const facesBody = {
  source_pixel_digest: SOURCE, frame: [1280, 720], detector: "YuNet2023mar", threshold: 0.6,
  proposals: [], status: "needs_manual_review", coverage: "unverified",
  zero_detections_means_safe: false, privacy_review_status: "not_validated",
  reason: "no_faces_detected_still_requires_review", automatic_treatment_applied: false, provider_calls_this_request: 0,
};
const session = { session_id: "sess-12345678", source_digest: SOURCE, output_sha256: "b".repeat(64), regions_digest: "c".repeat(64), width: 1280, height: 720 };

let container: HTMLDivElement;
let root: Root;

async function clickButton(text: string) {
  const button = [...container.querySelectorAll("button")].find((b) => b.textContent?.trim() === text);
  expect(button, `button "${text}"`).toBeTruthy();
  await act(async () => { button!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
}

afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.unstubAllGlobals(); });

describe("PreviewCeremony manual regions (no whole-person auto-masking)", () => {
  it("auto-runs the face check on mount and prepares only operator-chosen regions", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (String(url).includes("face-proposals")) {
        return Promise.resolve(new Response(JSON.stringify(facesBody), { status: 200, headers: { "content-type": "application/json" } }));
      }
      return Promise.resolve(new Response(JSON.stringify(session), { status: 200, headers: { "content-type": "application/json" } }));
    });
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(createElement(PreviewCeremony, { audit: audit(), file: new File([new Uint8Array([1])], "scene.png", { type: "image/png" }), onAcknowledged: () => {}, onInvalidate: () => {} }));
    });
    await act(async () => {}); // flush the auto-run check

    // The face check auto-ran on mount, without any click.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]![0])).toContain("/face-proposals");

    await clickButton("Add a mask region");
    await clickButton("Prepare a treated preview");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const prepareBody = JSON.parse(String((fetchMock.mock.calls[1]![1]?.body as FormData).get("review"))) as {
      regions: { person_id: string; box: number[] }[];
    };
    // Only the operator's manual region is masked; person-7's whole-person box
    // is NOT auto-masked, so PPE evidence on the body stays visible.
    expect(prepareBody.regions).toHaveLength(1);
    expect(prepareBody.regions[0]!.person_id).toBe("manual-region-1");
    expect(prepareBody.regions.some((r) => r.person_id === "person-7")).toBe(false);
    const [x1, y1, x2, y2] = prepareBody.regions[0]!.box as [number, number, number, number];
    expect(x2 - x1).toBeLessThan(1280 / 4); // a face-sized box, not a body
    expect(y2 - y1).toBeLessThan(720 / 4);
    // The UI states the default face-area masking + manual review rule.
    expect(container.textContent).toContain("masked by default");
    expect(container.textContent).toContain("not a guarantee every face is covered");
  });

  it("refuses a zero-region prepare client-side with the honest shield path named", async () => {
    // Backend v6.2 rejects zero-region previews ("Zero regions cannot establish
    // no faces"); the client refuses first and names the legitimate paths -
    // never a fake box, never a bare no-faces claim.
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (String(url).includes("face-proposals")) {
        return Promise.resolve(new Response(JSON.stringify(facesBody), { status: 200, headers: { "content-type": "application/json" } }));
      }
      return Promise.resolve(new Response(JSON.stringify(session), { status: 200, headers: { "content-type": "application/json" } }));
    });
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(createElement(PreviewCeremony, { audit: audit(), file: new File([new Uint8Array([1])], "scene.png", { type: "image/png" }), onAcknowledged: () => {}, onInvalidate: () => {} }));
    });
    await act(async () => {});
    await clickButton("Prepare a treated preview");
    expect(container.textContent).toContain("The backend refuses a zero-region preview");
    expect(container.textContent).toContain("opaque-shield review");
    expect(fetchMock).toHaveBeenCalledTimes(1); // only the auto-run face check; no prepare call
  });

  it("an exact opaque-shield review is a legitimate zero-region path", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (String(url).includes("face-proposals")) {
        return Promise.resolve(new Response(JSON.stringify(facesBody), { status: 200, headers: { "content-type": "application/json" } }));
      }
      return Promise.resolve(new Response(JSON.stringify(session), { status: 200, headers: { "content-type": "application/json" } }));
    });
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(createElement(PreviewCeremony, { audit: audit(), file: new File([new Uint8Array([1])], "scene.png", { type: "image/png" }), onAcknowledged: () => {}, onInvalidate: () => {} }));
    });
    await act(async () => {});
    const shield = [...container.querySelectorAll("input[type=checkbox]")].find((c) =>
      c.closest("label")?.textContent?.includes("opaque face shield"),
    ) as HTMLInputElement;
    expect(shield).toBeTruthy();
    await act(async () => { shield.click(); });
    await clickButton("Prepare a treated preview");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const review = JSON.parse(String((fetchMock.mock.calls[1]![1]?.body as FormData).get("review"))) as {
      regions: unknown[];
      face_coverings: Record<string, unknown>[];
    };
    expect(review.regions).toHaveLength(0);
    expect(review.face_coverings).toEqual([{
      person_id: "person-7",
      basis: "opaque_worn_face_shield",
      face_fully_hidden: true,
      no_visible_face_pixels: true,
      exact_source_confirmed: true,
    }]);
  });
});
