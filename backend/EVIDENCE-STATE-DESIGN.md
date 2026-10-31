# Evidence basis for PPE crops (offline implementation, reviewed-before-adoption, not adopted)

Status: implemented as a read-time derivation in fresh_review/ppe_basis.py plus report/API/PDF labels. No crop builder, prompt, schema, eligibility rule, parser, quarantine, dispatch or accounting change. Nothing stored changes. Not reviewed, not pushed.

## Problem
The provider returns present/absent/unknown for one crop. policy.py maps absent to observed_violation and present to no_observed_violation; rules.py does likewise. That is only as safe as the crop. Predicted masks and boxes may be wrong, so even a crop with no other person's mask pixel is NOT proven to show only the target; the existing eligibility rule is retained behavior, not a certification.
With partial crops (other-person foreground in the box, or only predicted mask pixels kept):
- false present: a neighbour's helmet or vest in the crop is attributed to the target (attribution failure);
- false absent: a predicted mask clips the target's own helmet or vest, or the body part is hidden or cut.
Neither is evidence about the target.

## Contract
crop_basis per assessed person: clean_crop (admitted by the existing rule), overlapped_crop, isolated_crop, or not_recorded_legacy. A clean_crop claim is accepted only when the stored eligibility record proves it (otherwise it raises); a person without any record is NOT called clean. A person with an observation on a crop the rule did not admit is treated as overlapped_crop. Forged or unknown crop_basis values raise.
- clean_crop / legacy: unchanged outcomes; target_attribution = crop_rule_retained_not_verified.
- overlapped_crop / isolated_crop: provider reading preserved as provider_observation, resolved_state present_attribution_unresolved or absent_attribution_unresolved (unknown stays unknown), target_level_outcome_permitted false. Report display, API status, and rule inputs get "unknown". Such a person can produce neither a clear (no_observed_violation) nor a violation, only needs_review.
- Three different things, never merged: attempted (provider reading exists), outcome emitted (a present/absent value may be shown or used: clean-rule basis only), and resolved. Resolved per item = known value (present/absent) AND a clean_crop basis proven by the stored eligibility record. Permission to emit is not resolution. Legacy missing-basis is never resolved; clean with unknown is not resolved; partial is never resolved. A person is fully resolved only if both items are.
- Counts: provider_observation_attempted_count, outcome_emitted_count (clean-rule only), legacy_outcome_withheld_count, attribution_unresolved_partial_count, attempted_clean_rule_both_items_unknown_count, resolved_item_count, fully_resolved_person_count. all_detected_people_target_level_resolved is true only if every detected person is fully resolved. Resolved still means an unvalidated provider reading, not safe or compliant, and not the 10+ person qualification.
"Verified masks" elsewhere means shape-consistent only, never verified true person masks.

## Acceptance tests (tests/test_ppe_basis.py, synthetic only)
clean crop keeps existing outcomes with the not-verified label; partial basis with every present/absent combination yields unknown display, needs_human_review, raw reading preserved; policy rule evaluation on partial inputs yields needs_review only; ineligible-with-observation never clean; legacy unchanged and forged basis refused; unassessed never an outcome; counts separate attempt from outcomes; report and API contract carry basis and counts.

## Not proven
Model accuracy on any crop type; SAM mask correctness; that a relaxed or isolation crop builder helps (none exists). Any such builder needs its own review and a labeled real-call evaluation with a manual reference and owner approval.

## Legacy results with no recorded crop basis (exception removed after independent review)
Older single-crop paths (1-2 people, strict parser) store no eligibility record. A review found that emitting their present/absent outcomes let an unverified basis drive display and rule findings. Now: raw reading preserved (provider_*_observation, provider_observation), but report display, API status and rule inputs are unknown, so rules give needs_review only; resolved_state legacy_present_/absent_basis_not_recorded, target_level_outcome_permitted false, never resolved, counted in legacy_basis_not_recorded_count and legacy_outcome_withheld_count. No migration of stored results: derived at read time. Behavior change on the legacy path: its reports and rule reviews now show unknown/needs_review where they used to show present/absent; that is the intended adoption question for the owner, not yet adopted.
Existing tests of downstream display/rule/explanation mechanics that used legacy fixtures now patch basis_of to clean_crop so they keep exercising those paths (3 tests); real legacy behavior is tested separately.

## Older field names (unchanged for compatibility, meaning stated explicitly)
PPE_assessed_count, all_detected_people_assessed, ppe_assessed and frames_with_unassessed_people mean provider observation attempted, not resolved assessment. New fields: ppe_basis_counts, all_detected_people_assessed_meaning, all_detected_people_target_level_resolved, frames_with_unresolved_people. PDF headlines now say "provider PPE observation attempted (not resolved assessments)".
