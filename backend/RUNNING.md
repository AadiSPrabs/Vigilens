# Vigilens backend: run and verify (offline, synthetic only)

This directory is a complete source-only backend tree (no private data, journals, results, tokens or ledger records). Requires Python 3.10 and the pins in requirements.txt (meta-sam-parser is the official parser).

1. Install: python3.10 -m venv .venv && .venv/bin/pip install -r requirements.txt
2. Test: .venv/bin/python -m pytest -q   (662 passed in a clean copy of this exact tree; no network or provider call is made. Tests use stub transports and synthetic images.)
3. Synthetic rehearsal of the proxy contract: REHEARSAL_UI_DIST=<built dist> REHEARSAL_OUT=<scratch dir> REHEARSAL_GOVERNED=1 .venv/bin/python rehearsal/serve_synthetic.py (stub backend and stub transport, port 8000; writes two synthetic PNGs to REHEARSAL_OUT; prints nothing secret). Build the bundle first (step 5). Open http://localhost:8000/launch#n=rehearsal-launch-nonce-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx once, upload the synthetic PNG, expect a result; upload a different image, expect a refusal (501 ATTEMPT/ANALYSIS_REFUSED text).
4. Real launcher (stored results only by default): run_ui_proxy.py --token-file <absolute 0600 file> --ui-dist <built dist> --port 8000. The built bundle must contain http://localhost:8000; the launcher refuses otherwise. Open the printed /launch#n=... link at http://localhost:8000 (not 127.0.0.1). New-image analysis is NOT available: it needs a source approval, a ledger release and a provider transport, none of which this tree enables. Do not pass --governed-new-image unless those exist.
5. Frontend bundle: from the unchanged frontend repo (head 7a90eef), VITE_AUDIT_MODE=backend VITE_API_BASE_URL=http://localhost:8000 npm run build.

Not done or not validated: zone analysis (posted zones are validated and echoed; membership is never determined), review/report wiring in the frontend, the cookie-to-display-session bridge (design only, SESSION-BRIDGE-DESIGN.md), native Windows, native-mouse zone drawing, any real provider run, reconciliation of an uncertain attempt. Contract: FRONTEND-CONTRACT.md and FRONTEND-WORKFLOW-CONTRACT.md. Stored-only covers only proxy -> /fresh-review-audit.

Network note: pip/npm installs need the network. Tests, the harness and the launcher make no provider or external call.

v3 changes vs clean-v2: documentation correction ('owner-bound' meant a bearer session value, never account ownership; see the CORRECTION blocks in FRONTEND-WORKFLOW-CONTRACT.md, FRONTEND-CONTRACT.md and SESSION-BRIDGE-DESIGN.md) and a default-off, unwired session-bridge helper in local_ui_proxy.py with 1 new test. No route, behaviour or exposure changed. Supersedes the 'owner' wording in all earlier packages.

v4 = clean-v3 + derived display-session forwarding in POST /audit (reviewed by Muse by code read, subset only) + wording and comment corrections + STATUS.md approval-claim removal. 663 tests passed in our run. Muse did not independently verify the backend audit handler binding or the full suite. Python 3.10, Linux; real token-file launcher and native Windows not exercised.
