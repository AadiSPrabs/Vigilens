import { useState } from "react";

const HEX64 = /^[0-9a-f]{64}$/;

// Reopen a job THIS account already ran, by its exact 64-character source digest.
// Stored-only: no analysis, no provider call, no listing of other jobs, no image
// download. A miss (unknown digest, another account's job, missing preserved
// source) opens nothing. Pixels only ever appear through the treated preview.
export function ReopenPanel(props: { onReopen: (digest: string) => Promise<void>; disabled?: boolean }) {
  const { onReopen, disabled } = props;
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const clean = draft.trim().toLowerCase();
  const valid = HEX64.test(clean);

  const submit = async () => {
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onReopen(clean);
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "Could not reopen that job. Nothing was analysed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="Reopen a stored job" className="mx-4 mt-2 rounded-md border border-vg-border bg-vg-surface-sunken px-3 py-2 text-xs text-vg-text-secondary">
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <label htmlFor="vg-reopen-digest" className="text-vg-text">
          Reopen a stored job (source digest):
        </label>
        <input
          id="vg-reopen-digest"
          type="text"
          autoComplete="off"
          spellCheck={false}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="64-character digest of a job you ran earlier"
          className="min-w-56 flex-1 rounded border border-vg-border bg-vg-bg px-2 py-1 font-mono text-vg-text"
        />
        <button
          type="submit"
          disabled={disabled || busy || !valid}
          className="rounded border border-vg-border px-2 py-0.5 text-vg-text hover:bg-vg-hover disabled:opacity-50"
        >
          {busy ? "Reopening..." : "Reopen"}
        </button>
        <span>
          Shows the stored result only. Nothing is analysed or charged, and the photo is not shown until you prepare and acknowledge a treated preview.
        </span>
      </form>
      {draft && !valid ? <p className="mt-1">A digest is exactly 64 hex characters (0-9, a-f).</p> : null}
      {error ? (
        <p role="alert" className="mt-1 text-vg-sev-critical-fg">
          {error}
        </p>
      ) : null}
    </section>
  );
}
