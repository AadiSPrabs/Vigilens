// Stage image for a REOPENED stored job. The original is never returned, so the only image the stage may show is the
// treated preview the visitor acknowledged, and only while that exact session is bound to this stored source and audit.
import { privateDisplayImageUrl } from "./api/backendClient";
import type { PrivateDisplaySession } from "./types";

export function storedStageImageUrl(
  source: { kind: string; digest?: string } | null,
  session: PrivateDisplaySession | null,
  previewReady: boolean,
): string | null {
  if (!source || source.kind !== "stored" || !source.digest || !session || !previewReady) return null;
  if (session.source_digest !== source.digest) return null;
  return privateDisplayImageUrl(session.session_id);
}
