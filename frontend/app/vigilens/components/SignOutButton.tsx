import { useState } from "react";
import { useSession } from "@agent-native/core/client/hooks";
import { signOut } from "@agent-native/core/client/sign-out";

/**
 * The scaffold's only sign-out control lives in OrgSwitcher, which this app
 * shell does not mount - so without this button a signed-in visitor had no way
 * to end their session at all. Signing out also revokes the server-side BYOK
 * key hold, which is bound to the session token (server/utils/vigilens-keys.ts).
 *
 * Uses the toolkit's ordered signOut(): it blocks authenticated UI first,
 * waits for the server revocation, then leaves with a full navigation - the
 * app shell never paints authenticated queries over a dead cookie.
 */
export function SignOutButton() {
  const { status } = useSession();
  const [busy, setBusy] = useState(false);
  if (status !== "authenticated") return null;
  return (
    <button
      type="button"
      disabled={busy}
      aria-label="Sign out"
      onClick={async () => {
        if (busy) return;
        setBusy(true);
        await signOut();
      }}
      className="inline-flex min-h-10 items-center gap-2 rounded-vg-md border border-vg-border-strong px-3 text-sm font-medium text-vg-text hover:bg-vg-hover disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-vg-focus-ring"
    >
      <span>{busy ? "Signing out..." : "Sign out"}</span>
    </button>
  );
}
