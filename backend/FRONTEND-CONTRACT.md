# Frontend integration contract (LOCAL PROPOSAL, not agreed with any frontend)

Status: working draft. Describes what the runtime actually does today. Nothing here is a promise about accuracy.
Everything below was exercised with `scripts/frontend_contract_demo.py`: generated pixels, synthetic provider replies, loopback HTTP, zero provider calls. Real responses are saved in `frontend-contract-samples/`. Real-photo behavior is NOT shown by these samples.

## Run the demo
    cd backend && python scripts/frontend_contract_demo.py     # needs requirements.txt; starts uvicorn on 127.0.0.1:18477 and stops it

## Auth and sessions
- Every call needs header `X-Vigilens-Local-Access: <token>` (env VIGILENS_LOCAL_ACCESS_TOKEN). Missing token gives 403 (sample `fresh_review_SOURCE.403.0.json`).
- Review and report calls also need `X-Vigilens-Display-Session: <bearer session value; format-checked and compared for equality, not an identity>`. The preview `session_id` is returned by private-display and is bound to that bearer value.
- Local-only. No public hosting, no sharing, no export (`evidence_export_allowed` is always false).

## Flow (current routes)
1. `POST /fresh-review-upload` (multipart: image, zones JSON). Returns the job: `state` (terminal), `result.persons[]`, `provider_calls_this_request`. A repeat of the same image returns the stored result with 0 calls.
2. `GET /fresh-review/{source}` re-reads the stored job. `source` is the image pixel digest.
3. `GET /fresh-review/{source}/integration-contract` is the proposed frontend shape (`vigilens.private-review.proposal.v1`, `contract_status: local_proposal_not_agreed_with_frontend`).
4. `POST /fresh-review/{source}/private-display` then `POST /private-display/{sid}/review`: operator must acknowledge the whole-frame preview before any report.
5. `POST /fresh-review/{source}/contact`, `/zone-review` (GET too), `/rule-review`: operator contact points, zones, configured rules.
6. `POST /fresh-private-report/{sid}`, `/pdf-preview`, `/private-download`: private report JSON and PDF. `GET /fresh-private-report/{sid}/overlay` returns a PNG.
7. Clips: `POST /fresh-private-clip-report/{clip_id}` exists but needs a trusted clip decoder to be enabled and approved sources. NOT demonstrated (no real clip authority). The upload route is `/fresh-review-clip-upload`.

## Frontend v0.2 view (read-only, backend-only, PROPOSED, not adopted)
`GET /fresh-review/{source}/frontend-audit` (header `X-Vigilens-Local-Access`) maps the STORED result to the frontend's v0.2 audit shape (`schema_version 0.2-local-draft`). No provider call (`provider_calls_this_request: 0`), no new state. It never emits a `violation`: every unknown/absent reading becomes an `uncertainty` finding with `severity null` and `review_state needs_human_review`. Outline = the person's bounding box, `outline_basis bounding_box_display_only_not_segmentation` (masks are never sent). `zones []`, `zone_membership_status unknown`, `evidence_image null`, `evidence_status unavailable`, `evidence_export_allowed false`, `compliance_status not_evaluated`. Sample: `frontend-contract-samples/fresh_review_SOURCE_frontend_audit.200.0.json` (from the synthetic route test). Errors: 403 no token, 409 unavailable/unknown source.
Checked: backend test `tests/test_frontend_audit_route.py`, and the route output passes the frontend `validateAudit` (backend mode) copied verbatim from branch feat/frontend-dashboard at head 7a90eef (that branch head was not re-read after this change). NOT checked: a live browser run against this route. The UI still calls `POST /audit` (fixture) until the client is pointed at this route or a proxy; the UI cannot draw boxes without an evidence image (a UI choice, not changed here).
Auth for a browser: the access token must never be in the bundle, a VITE variable or chat. Use a server-side proxy with an origin check (see the integration brief draft); it is for the demo user's own machine only.
Gate: `/fresh-private-clip-report/*` is now inside the private-access gate (previously skipped the token check; session-value binding still applied).

## Semantics the UI must follow
- `state: completed` means execution is terminal. It is not assessment completeness (`execution_state_is_not_assessment_completeness: true`).
- Show completeness only from `all_detected_people_target_level_resolved`, `ppe_basis_counts`, `coverage`, `frames_with_unresolved_people` (clips). `all_detected_people_assessed` means "provider observation attempted" for every person, per `all_detected_people_assessed_meaning`. Never render it as "all people checked".
- Per person: use `ppe.helmet.status` / `ppe.vest.status` and `target_level_outcome_permitted`. When false, render "unknown / needs review" and keep the raw `provider_observation` out of the headline. A green tag means a reading was attempted, never "safe" or "clear".
- `crop_basis`: `clean_crop` (record-proven), `overlapped_crop`, `isolated_crop`, `crop_rule_ineligible` (see `crop_rule_reasons`), `not_recorded_legacy`. Only a clean crop can show present/absent. Even then it is an unvalidated provider reading and person association is not proven.
- `compliance.status` is `not_evaluated` in the contract. Configured rule results appear only in the private report and are operator rule checks, not safety clearance (`private_operator_rules_evaluated_not_safety_clearance`).
- `geometry_status` / `coverage` / `ppe_withheld_unverified_geometry` describe wide-scene limits. "Verified masks" means shape-consistent only.
- Errors: 403 no token, 409 unavailable/changed/unapproved ("no automatic retry"), 503 provider execution disabled. The UI must not retry automatically.

## Known limits (honest)
- Single-upload basis gap (approved seq16/17b runtime): the single-person fresh-upload path writes no crop-eligibility record, so even a brand-new upload shows helmet and vest as unknown/needs review (crop_basis not_recorded_legacy). PROPOSED seq18 delta (NOT adopted, awaiting review): record the same eligibility checks (verified mask, no other person's foreground in the crop, minimum crop size 32x64 from the wide-scene defaults) at crop creation. Eligible crops become clean_crop. Ineligible ones are recorded ineligible and stay unknown. The basis label is truthful: genuine overlap reasons keep `overlapped_crop`; any other reason (for example too small) is `crop_rule_ineligible`. The exact reasons are exposed as `crop_rule_reasons` in the API and printed in the report line. Dispatch is unchanged: the single path already made a PPE call for every detected person (1-2 people, after the cross-person foreground check), and recording the record changes no request, cost or call count (identical request-body hashes on seq17b and seq18 for three scenarios). Older stored results are untouched. Eligible still does not prove the person association.
- Real wide-photo test: stopped at the strict parser (documented in STATUS.md). Box/mask mismatch cause is unknown.
- No real clip test is approved.
- Contract not agreed with any frontend or team.

## Serving the UNCHANGED client (PROPOSED, not adopted)
Client facts (branch feat/frontend-dashboard head 7a90eef, remote re-checked 23:12 IST, unchanged): POST {VITE_API_BASE_URL or http://localhost:8000}/audit, multipart image+zones, header Idempotency-Key, NO token; errors read as {error:{message}} for 503/422, 409 means IDEMPOTENCY_CONFLICT; response must pass validateAudit (backend mode). Client colour rule (lib/severity.js): green "fully equipped" only when findings are empty AND helmet and vest are both present; any kind:uncertainty finding gives neutral grey.
Pieces:
1. Backend `POST /fresh-review-audit` and `GET /fresh-review/{source}/frontend-audit`: token-gated and session-header-gated (format check, like the other result routes). POST uses the SAME governed path as /fresh-review-upload (approvals, ledger, transport state all apply); a stored result returns with 0 calls, a new image runs only if the runtime already allows it, else 503/409.
2. View rules (fresh_review/frontend_audit.py): helmet/vest come only from ppe_basis.effective_value (present/absent only for a record-proven clean_crop; legacy, overlapped and ineligible bases show unknown). Every person always carries an uncertainty finding "provider readings are unvalidated", so the client can never show green. Per-person ppe_basis (crop_basis, outcome permitted, resolved), job_state, partial_result, coverage, ppe_withheld_unverified_geometry, all_detected_people_target_level_resolved, ppe_basis_counts. Invalid or out-of-bounds person boxes, duplicate ids or a forged clean_crop refuse the whole view (409). Full source_digest and image.pixel_digest are included; they are stable linkable identifiers, and the 16-char image.id is NOT anonymised. No masks, evidence null, export false, compliance not_evaluated, zones [] and not applied.
3. Gate is default-deny: every path needs X-Vigilens-Local-Access except /health and /audit (fixture skeleton, no private data); docs and openapi are gated. Test iterates every route in the OpenAPI schema.
4. `local_ui_proxy.py` + `run_ui_proxy.py`: loopback proxy on :8000 that forwards POST /audit to (1), adds the token and an HMAC-derived bearer session value (derived from the cookie session id with a per-process secret) server side (token from a private file, never logged), maps blocked or unavailable backend states to 501 and backend errors to 502, with neutral messages. It decides nothing about analysis and enables no transport. Run order: backend via run_private.py (its config governs dispatch; blocked by accounting), then run_ui_proxy.py --token-file <abs private file>.
LIMITS: the browser cannot authenticate to the proxy without a client change; Origin/Sec-Fetch-Site only blocks other websites in the user browser. Any process on this machine can use the proxy. Strong auth needs one small client change (a launch-bound header); not made. The owner-session id is a per-launch value shared by everything using the proxy, not a per-person identity. UI-drawn zones are not applied (zones_applied false). No on-photo boxes without an evidence image. Print is browser print only.
Tests: tests/test_frontend_audit_route.py, tests/test_local_ui_proxy.py; proxy output passes validateAudit.

## Error shapes through the proxy (checked against client auditClient.js at 7a90eef)
The unchanged client surfaces `error.message` verbatim only for statuses outside 400/409/413/415/422/429/503 (its 503 branch shows it only if the text contains "FIXTURE" or "Service"; its 422 branch swallows the message and shows "Unprocessable entity"). The proxy therefore returns 501 for "no stored result / live analysis not enabled" and 502 for backend failure, both with `{error:{code,message}}`. This is a compatibility choice and not a claim about HTTP semantics.

## /fresh-review-audit is stored-only (no dispatch)
The handler has no dispatch code and no switch: it reads an already stored verified result for the exact pixel digest, otherwise 409. A test asserts the handler text contains no SERVICE.run, dispatch or transport. The older /fresh-review-upload keeps its ledger-governed path and is unchanged. Stored-only is NOT the new-image API: new-image analysis for the frontend stays blocked behind the existing ledger and approvals and needs its own review.

## Serving contract (v5): callable authenticated upload with explicit unavailable states
Client (unchanged, head 7a90eef): POST /audit, multipart image+zones, Idempotency-Key, same origin as the UI. Served by local_ui_proxy.py (built bundle + /audit) after a one-time launch (nonce -> HttpOnly SameSite=Strict cookie). Backend token is server side only.
Proxy modes (selected at launch, default 1):
1. default: POST /audit -> backend POST /fresh-review-audit (STORED-ONLY handler, no dispatch code).
2. `--governed-new-image`: POST /audit -> backend POST /fresh-review-audit-governed. It serves a stored result for the exact digest, else calls the SAME governed SERVICE.run as /fresh-review-upload. The flag only SELECTS that handler. It grants no dispatch: source approval, ledger reservation and a configured transport still decide, and they refuse in the current runtime. Callable is not permission.
State table (client sees error.message verbatim): 200 view | 401 no launch session | 403 wrong origin | 501 no presentable stored result (stored-only) or ANALYSIS_REFUSED (governed: approval/accounting/config/not presentable; no automatic retry) or LIVE_ANALYSIS_UNAVAILABLE (transport disabled) | 502 backend failure. Zero-person results are refused. Partial results are served with a PARTIAL RESULT finding on every person.
Session scope (a bearer value, not ownership; local single user, not an account system): a session is bound to a source digest only by presenting that exact image to a frontend-audit POST (possession proof; in memory). GET /fresh-review/{source}/frontend-audit requires that binding. An unbound-but-stored digest and a nonexistent digest return identical 409 bodies (no existence oracle). The proxy exposes no GET by digest. Limits: the same image bytes always yield the same audit_id and digests for anyone holding the image (stable, linkable by design), the binding is per process and per session, and it is not multi-user isolation.
Dispatch, accounting: unchanged. A governed run's provider call count is reported as null with a pointer to the backend ledger, never as 0.


## Correction (supersedes earlier 'owner' wording)
Every 'owner', 'owner-bound' or 'owner session' above means a bearer session value, checked for format and equality only. It is not account ownership or multi-user isolation. Local single-user candidate only.
