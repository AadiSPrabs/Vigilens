// Bounded local-clip sampling. Prep-stage surface: the backend refuses cleanly when
// no trusted local decoder limits are configured, and this panel shows that state
// instead of a dead affordance. Sampled frames are not complete clip coverage;
// cross-frame identity is never inferred; every frame still needs its own private
// image review. No automatic retry, no export, no adoption.
import { useState } from "react";
import { uploadClip } from "../api/backendClient";
import type { ClipSummary } from "../types";

const MAX_OFFSETS = 16;

function parseOffsets(raw: string): { offsets?: number[]; error?: string } {
  const parts = raw.split(",").map((p) => p.trim()).filter((p) => p.length > 0);
  if (parts.length === 0) return { error: "Enter at least one sample offset in seconds." };
  if (parts.length > MAX_OFFSETS) return { error: `At most ${MAX_OFFSETS} sample offsets.` };
  const offsets: number[] = [];
  for (const part of parts) {
    const value = Number(part);
    if (!Number.isFinite(value) || value < 0 || value > 120) {
      return { error: `Offset "${part}" is not a finite number between 0 and 120 seconds.` };
    }
    offsets.push(value);
  }
  return { offsets };
}

export function ClipPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [offsetsRaw, setOffsetsRaw] = useState("1, 3");
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState<ClipSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = () => {
    if (!file || busy) return;
    const parsed = parseOffsets(offsetsRaw);
    if (parsed.error || !parsed.offsets) {
      setError(parsed.error ?? "Invalid offsets.");
      return;
    }
    setBusy(true);
    setError(null);
    setSummary(null);
    uploadClip(file, parsed.offsets)
      .then((out) => setSummary(out))
      .catch((err: unknown) => setError(err instanceof Error && err.message ? err.message : "Clip sampling refused. No automatic retry."))
      .finally(() => setBusy(false));
  };

  return (
    <section className="rounded-lg border p-3 text-xs">
      <h3 className="text-sm font-medium">Short clip sampling (bounded, local)</h3>
      <p className="text-muted-foreground">
        Sampled frames only - never complete clip coverage. Each frame is audited as its
        own image and still needs its own private review. People are not matched across
        frames, and presence in a sample is not an intrusion or crossing finding. No
        automatic retry; export stays disabled.
      </p>
      <div className="mt-2 space-y-2">
        <input
          type="file"
          accept="video/mp4"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="block text-xs"
        />
        <label className="block">
          <span className="text-muted-foreground">Sample offsets (seconds, comma separated)</span>
          <input
            type="text"
            value={offsetsRaw}
            onChange={(e) => setOffsetsRaw(e.target.value)}
            className="mt-1 w-full rounded border bg-background px-2 py-1 text-xs"
          />
        </label>
        <button
          type="button"
          disabled={!file || busy}
          onClick={run}
          className="rounded border px-2 py-1 text-xs disabled:opacity-50"
        >
          {busy ? "Sampling frames..." : "Sample and audit frames"}
        </button>
      </div>
      {error ? <p className="mt-2 text-destructive">{error}</p> : null}
      {summary ? (
        <div className="mt-2 space-y-1">
          <p>
            Status: {summary.status === "completed" ? "All sampled frames audited" : summary.status}.
            {" "}{summary.completed_sample_count} of {summary.requested_sample_count} requested samples completed.
          </p>
          {summary.frames_with_unresolved_people.length > 0 ? (
            <p>
              Frames with unresolved people (not attempted, partial, or unknown readings):{" "}
              {summary.frames_with_unresolved_people.join(", ")}. Attempted is not resolved;
              these stay with human review.
            </p>
          ) : null}
          <ul className="space-y-1">
            {summary.frames.map((f) => (
              <li key={f.sample_index} className="rounded border p-1">
                Frame {f.sample_index} at {f.requested_offset_seconds}s: {f.image_job.state}.
                Requires its own private image review.
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground">
            Export disabled. No automatic retry. Decoder scope: local trusted clip only, not a
            public upload service.
          </p>
        </div>
      ) : null}
    </section>
  );
}
