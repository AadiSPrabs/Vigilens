import { useCallback, useEffect, useState } from "react";
import {
  getVisitorKeyStatus,
  setVisitorKey,
  forgetVisitorKey,
  type VisitorKeyStatus,
} from "../api/backendClient";

// Visitor BYOK panel: each visitor uses their OWN Meta API key for analysis.
// Honest retention copy: server memory only, 2h, gone on restart/sleep; the
// visitor re-enters it. Never in the browser store, URL, or any database.
export function ApiKeyPanel() {
  const [status, setStatus] = useState<VisitorKeyStatus | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await getVisitorKeyStatus());
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      setStatus(await setVisitorKey(draft.trim()));
      setDraft("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save key");
    } finally {
      setBusy(false);
    }
  };

  const forget = async () => {
    setBusy(true);
    setError(null);
    try {
      await forgetVisitorKey();
      setStatus({ present: false });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not forget key");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      aria-label="Your API key"
      className="mx-4 mt-2 rounded-md border border-vg-border bg-vg-surface-sunken px-3 py-2 text-xs text-vg-text-secondary"
    >
      {status?.present ? (
        <div className="flex flex-wrap items-center gap-2">
          <span>
            Using your own Meta key (id {status.fingerprint}
            {status.expiresAt ? `, held until ${new Date(status.expiresAt).toLocaleTimeString()}` : ""}
            ). Analyses are charged by Meta to your key, not to anyone else.
          </span>
          <button
            type="button"
            onClick={() => void forget()}
            disabled={busy}
            className="rounded border border-vg-border px-2 py-0.5 text-vg-text hover:bg-vg-hover disabled:opacity-50"
          >
            Forget key
          </button>
        </div>
      ) : (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (draft.trim()) void save();
          }}
        >
          <label htmlFor="vg-api-key" className="text-vg-text">
            Your Meta API key (optional):
          </label>
          <input
            id="vg-api-key"
            type="password"
            autoComplete="off"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Paste your key to analyse with it"
            className="min-w-56 flex-1 rounded border border-vg-border bg-vg-bg px-2 py-1 text-vg-text"
          />
          <button
            type="submit"
            disabled={busy || !draft.trim()}
            className="rounded border border-vg-border px-2 py-0.5 text-vg-text hover:bg-vg-hover disabled:opacity-50"
          >
            Use my key
          </button>
          <span>
            Held in server memory for up to 2 hours, then forgotten (also on restart or
            sleep - re-enter it). Never stored in a database or your browser. Without your
            own key, real analysis of your uploads is disabled; you can still explore the
            bundled sample scenes, which are always labelled as samples.
          </span>
        </form>
      )}
      {error ? <p className="mt-1 text-vg-sev-critical-fg">{error}</p> : null}
    </section>
  );
}
