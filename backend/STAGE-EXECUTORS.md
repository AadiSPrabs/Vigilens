# Recheck / explanation executors on the Render boot path

Status: opt-in, off by default. Qualified offline on real Postgres with a synthetic transport and
synthetic grants only. Not run on Render. No live grant exists.

## What is wired
- `VIGILENS_STAGE_EXECUTORS=on` attaches a RecheckExecutor and an ExplanationExecutor at boot (Postgres path only).
  Unset or any other value: nothing is attached and the report says "not configured".
- Attached with no grant, an executor can show the exact plan hash but cannot reserve or dispatch (409, 0 provider calls).
- The bounded review loop is NOT wired at boot. It needs a server-side `review_loop_attempts` map of already
  reserved attempts, which no boot path creates. It stays unavailable on the host.

## How a grant is made (the user never hand-authors JSON)
1. The private report shows `exact_plan_sha256` and the reservation route for the current plan.
2. The assistant tells the owner, in plain words, what that exact plan will do and the ceiling it can hold
   (an explanation reservation holds the full `MAX_COST` on the ledger even if no call is made).
3. The owner approves that specific plan in words. Nothing earlier counts as approval.
4. The assistant formats the grant with `python backend/make_explanation_grant.py --plan-sha256 HEX
   --execution-scope SCOPE --authority-reference REF`. The tool only prints a document: it calls no provider,
   reserves nothing and writes no file. It PRINTS the grant to stdout, so mind where stdout goes (the grant is an approval document, not an API secret, but its integrity matters). It refuses a malformed hash or a different ceiling.
5. The grant is placed in `VIGILENS_EXPLANATION_GRANT_JSON` (a Render dashboard action by the owner) and the
   service is restarted. The grant is read once at boot into a 0700 temp dir as a 0600 file and pinned by sha256.
   It covers one plan hash. A different plan, scope or ceiling is refused without a call.
6. Remove the variable and restart to revoke. A grant is not reusable for another plan.
Recheck grants bind a source, result, person, plan and request hashes; format them from the reserved attempt's
plan in the same way (not automated here).

## Properties covered by tests (real Postgres, synthetic)
Normal run, repeat serves the stored result with 0 calls, restart does not re-dispatch, a timeout is held as
uncertain and is never retried, ambiguous crops stop before any PPE call, a wrong or malformed grant makes no call,
another account cannot reserve, run or loop another account's job, original results are never overwritten.
See tests/test_render_stage_executors_pg.py and tests/test_recheck_execution_pg.py.

## Not covered
Live provider behaviour, Render itself, Python 3.13, and any real grant. Money: each approved plan is a
separate approval with its own accounting plan.

## Recheck and bounded review loop (Render path)
State ledger: implemented in code, configured only by the steps below, verified on host only when someone observes it there.
1. The private report shows `bounded_review_loop`: `blocked_no_reserved_attempts` (visible blocked plan, creates nothing) until configured.
2. `POST /fresh-review/{source}/recheck-plan {"person_id": ...}` (acknowledged preview session) returns hashes only: plan_sha256, request_sha256, ceiling. No booking, no grant, no provider call. Crop pixels are never returned.
3. The owner approves that plan and ceiling in words. `python make_recheck_grant.py --authority-reference REF < plan.json` prints the grant (stdout).
4. Operator action: place it in VIGILENS_RECHECK_GRANT_JSON and restart (read at boot). `/recheck-plan` then shows `configured_grant_matches_this_plan: true`.
5. `POST /fresh-review/{source}/recheck-reservation` checks the exact grant BEFORE booking, then holds the full reserve with no provider call. No grant means 409 and nothing booked. Repeat requests dedupe.
6. The report's loop block turns to `ready_reserved_attempts` (the server reads this owner's reserved, not yet run attempts for the exact source and result; at most 2). "Run reserved attempts" calls `/bounded-review-loop`, which preflights every attempt against the pinned grant and then runs each once. A completed attempt is no longer pending, so a repeat is refused (no retry). No attempt-id env step and no second restart. VIGILENS_REVIEW_LOOP_ATTEMPTS_JSON remains an optional fixed override.
All of steps 2, 5 and 6 are buttons in the report panel ("Bounded recheck loop"). Only step 4 is a dashboard action.
No endpoint creates a grant. A reservation holds money against the ceiling and needs its own accounting approval.
