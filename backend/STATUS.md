# Current backend status

Updated October 28, 2026. Local implementation, not pushed or deployed. This replaces
an obsolete October 27 fixture-only status table. Current implementation details and
verification commands are in FRESH-REVIEW.md.

Implemented: exact-source original SAM/person and Spark PPE jobs; manual contact,
operator zones and fixed-scene reuse; configurable deterministic rules; private
JSON/overlay/PDF; bounded trusted-local MP4 frame analysis; browser/source/result-
bound combined sampled-clip JSON/PDF; exact-granted crop recheck and spatial
commentary executors; optional face candidates; manual treatment/explicit opaque
shield coverage review; per-access artifact/accounting validation and pure parse
memo. All public release/export flags remain false. Default startup has no paid
transport, source authority or actual spending ledger.

Actually qualified privately: selected retained real-image original person/PPE,
auxiliary helmet/vest segmentation and actual HTTP review/report pixels, original
source repeat/restart zero extra calls. Details/private artifacts are not bundled.
Generated local tests are not real-model evidence. Independent review applies only
to the exact checkpoint it names, not later additions.

Implemented configured exact-granted bounded recheck-to-human loop; genuine
initial-unknown real recheck remains unqualified. A narrow illustrative demo scope ran:
rooftop rule/contact demo and one spatial commentary call; one real call completed but commentary quality was insufficient for spatial
reasoning qualification. Raw model text is retained and flagged, not accepted. Human-reviewed private-only report downloads are available
as a local option and verified on retained welder HTTP/PDF, not automatic privacy or
public sharing. Real clip qualification, reliable default face coverage and
public release/export remain open. Three paths exist; do not conflate them. (1) Legacy fresh review: 1-2 people, strict parser, the default. (2) Opt-in sequential wide scene: up to 64 detected people, one SAM call then up to 16 sequential PPE crop calls; a crop is eligible only at the minimum size with no other person's mask pixel inside it, all others stay unassessed; per-stage worst-case reservation (listed, not an enforced bill bound), aggregate cap via a pinned carry, partial stop, terminal uncertain call, no-repeat resume. Low assessed coverage is not the validated full goal. (3) Opt-in geometry_quarantine (reviewed as seq9, NOT adopted as policy): a box/mask size mismatch of at most 1 px per dimension becomes an unverified object; if any object is unverified no PPE call is made for the whole source. A "completed" job state means execution terminal, never assessment complete; read wide_scene.coverage and all_detected_people_assessed. The one actual wide-scene real test (a seated crowd photo, October 29) stopped after the SAM call at a strict-parser failure; no PPE ran and no accepted result exists. Crowd coverage on that photo under the current crop rule was about 3-4 of 23 detections. Actual frontend/browser
integration remains open. Strong hosted-user authentication/tenancy, hostile-input
isolation, ingress limits and operational retention/load work are not complete.

No safe/compliant claim follows from known PPE, manual acknowledgment or a test pass.

## October 29 doc-only update (seq17-docs; runtime identical to seq16)

Implemented policy (derived evidence policy only; approval provenance is not recorded in this file and was not independently re-verified by the backend agent):
- A PPE reading from a partial crop (overlapped or isolated) or with no recorded crop basis (older stored results) displays as unknown / needs review. Raw model readings stay preserved.
- Regenerating an older report that has no basis record now shows needs_review for those people. Nothing stored is changed.
- seq9's geometry_quarantine stays opt-in and default off. Strict parsing is still the default. It is not adopted as policy.
- Nothing was pushed, deployed or published. No provider call was made for this update.

Olson wide-scene test (closed): one SAM call was stopped by the strict parser (text size, summed mask area, one box/mask size mismatch). No PPE call, no accepted result. See "Box/mask mismatch diagnosis" below.

## Consumer contract

- "completed" means the job execution is terminal. It does not mean every person was assessed.
- Read these before showing any completeness claim: all_detected_people_target_level_resolved, ppe_basis_counts, coverage, all_detected_people_assessed_meaning, frames_with_unresolved_people.
- Older names (PPE_assessed_count, all_detected_people_assessed, ppe_assessed, frames_with_unassessed_people) mean "attempted", not resolved.
- A green "assessed" tag means a provider observation was attempted. It never means safe or clear.
- Low coverage is not the validated full goal. "Verified masks" means shape-consistent only.

## Box/mask mismatch diagnosis (read-only, retained reply, no calls)

Frame 3264x2448. In the retained SAM reply, 23 objects declare box x1,y1,x2,y2 (inclusive) and mask w,h. For 22 objects, mask = (x2-x1+1, y2-y1+1) exactly. One object's box gives 657x1025 inclusive, but its declared mask is 656x1024, one pixel smaller in each direction. Mask offsets are x=0,y=0 for every object, so the mask is box-relative.
One other object also reaches the frame edge and its mask matches its box, so an image-edge clamp does not explain the mismatch.
Cause: UNKNOWN (documented, not established). One object in one reply is not enough to infer a rule. Strict parsing stays the default.

## seq18 PROPOSAL (not adopted): record crop eligibility for single uploads
Runtime delta in fresh_review/pipeline.py only: new single-upload persons carry crop_eligibility from the same eligibility() function and WideLimits defaults. See FRONTEND-CONTRACT.md. Older stored results untouched. Awaiting review.
Why clean is supported for an eligible single-upload crop: before any PPE call the path already refuses the whole job if any other detected person's verified mask foreground falls inside a person's crop box, and the record adds the same minimum-size check as the wide gate. This is the retained crop rule on predicted masks. It does not detect undetected people or prove the person association. Recording changes no dispatch: same requests, same cost, same call count (hash-compared against seq17b on three scenarios). Basis labels: overlapped_crop only for genuine overlap reasons, crop_rule_ineligible for the rest, reasons in crop_rule_reasons.

## October 29 seq19 (runtime delta: one line in fresh_review/wide_sequential.py, plus two tests)

After a fresh sequential job dispatches the SAM call and then stops (for example the strict parser rejects the reply), the returned job now reports the calls actually journaled in provider_calls_this_request. Before, it reported 0, and a clip summary repeated that 0. Repeat runs still make no second call and report 0 NEW calls. Independently source-reviewed by Muse (frozen package ef4ea538134dfbe35dd60bd8ea25417ca278360bd72cb8e2cb9b0a4df3d79c17; 621 tests passed in its fresh venv).

Unchanged on purpose: requires_operator_reconciliation. It flags an uncertain in-flight call or unsettled cost, not "the job stopped". A completed, costed SAM call followed by a parser stop therefore shows False while the clip status is partial_requires_operator_reconciliation. Treat the clip status and the job state (running_uncertain, result none) as the stopped signal. The name is ambiguous; any rename or redefinition is a separate change.

Strict parsing, eligibility, geometry quarantine (off by default) and thresholds are unchanged. Not pushed or deployed. Two real SAM replies (one earlier photo, one clip frame) were stopped by a box/mask size mismatch in which the mask was the box scaled to a 1024 long side; that pattern is an observation from those two replies, not a confirmed provider rule, and no mask is resampled.
