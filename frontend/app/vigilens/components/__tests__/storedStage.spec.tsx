// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { storedStageImageUrl } from "../../storedStage";
import { ImageStage } from "../ImageStage";
import type { PrivateDisplaySession } from "../../types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const D = "a".repeat(64);
const session = { session_id: "s".repeat(32), source_digest: D, output_sha256: "o".repeat(64), regions_digest: "r".repeat(64), width: 1600, height: 1000, preview_url: "x" } as PrivateDisplaySession;
const stored = { kind: "stored", digest: D };

describe("stored-mode stage image", () => {
  it("uses only the acknowledged treated preview bound to this stored source", () => {
    expect(storedStageImageUrl(stored, session, true)).toContain(session.session_id);
    expect(storedStageImageUrl(stored, session, false)).toBeNull();                       // not acknowledged / not ready
    expect(storedStageImageUrl(stored, null, true)).toBeNull();                           // expired or discarded
    expect(storedStageImageUrl(stored, { ...session, source_digest: "b".repeat(64) }, true)).toBeNull(); // other source
    expect(storedStageImageUrl({ kind: "stored", digest: "b".repeat(64) }, session, true)).toBeNull();   // changed source
    expect(storedStageImageUrl({ kind: "upload" }, session, true)).toBeNull();            // never for uploads or samples
    expect(storedStageImageUrl(null, session, true)).toBeNull();
  });

  let root: Root | null = null;
  afterEach(async () => { await act(async () => { root?.unmount(); }); root = null; vi.restoreAllMocks(); });
  it("clears the stage image through onImageError so a dead treated copy never lingers", async () => {
    const host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
    const onErr = vi.fn();
    await act(async () => { root!.render(createElement(ImageStage, { imageUrl: "/api/vigilens/private-display/x/image", imageAlt: "t", zones: [], persons: null, selectedPersonId: null, onImageError: onErr })); });
    const img = host.querySelector("img")!;
    await act(async () => { img.dispatchEvent(new Event("error")); });
    expect(onErr).toHaveBeenCalledTimes(1);
    host.remove();
  });
});
