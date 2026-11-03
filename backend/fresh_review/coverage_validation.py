"""Detector-proposal disposition validation for masked preview preparation.

Contract (optional prepare-review field `proposal_dispositions`): a list with
exactly one entry per CURRENT detector proposal for the exact source, each:
  {"review_region": [x1, y1, x2, y2],  # exact ints from the detector result
   "disposition": "covered", "person_id": "<operator region person_id>"}
  or
  {"review_region": [...], "disposition": "dismissed",
   "dismiss_reason": "operator_confirmed_not_a_face" |
                     "operator_confirmed_already_shielded"}
"covered" requires the referenced operator region to fully CONTAIN the
proposal's review region. Shield dismissal requires the referenced person_id
to have an explicit face-covering review; coverings carry no geometry, so a
shield dismissal is an OPERATOR CLAIM ONLY, never geometrically verified.
The summary travels in session meta only; it is not part of the ack digests.

Limits (stated, not hidden):
- This covers ONLY what the detector returned. Detector misses are not
  addressed: zero proposals never means no faces, coverage stays
  'not_verified', privacy_review_status 'not_validated',
  evidence_export_allowed False, and the whole-frame review stays manual.
- The route must only call this after a COMPLETED detector pass (a success
  reason below); any other reason means the detector did not run and no
  disposition set may be accepted.
- This validates disposition completeness and geometric containment only. It
  does not validate that a mask hides identity, and it never enables release.
"""

DISMISS_REASONS = ('operator_confirmed_not_a_face', 'operator_confirmed_already_shielded')

# propose_faces outcomes that mean the detector actually ran to completion
# (genuine zero detections included). Any other reason is a failed pass.
DISPOSITION_SUCCESS_REASONS = ('proposals_require_face_and_helmet_review', 'no_faces_detected_still_requires_review')


def _region(value):
    if not isinstance(value, list) or len(value) != 4 or any(type(v) is not int for v in value):
        raise ValueError('Integer proposal review regions required')
    l, t, r, b = value
    if not (0 <= l < r and 0 <= t < b):
        raise ValueError('Ordered proposal review regions required')
    return tuple(value)


def validate_dispositions(dispositions, proposals, regions, coverings):
    """Raise ValueError unless every proposal is dispositioned exactly once and
    each disposition is internally consistent. Returns a compact summary for
    the session meta; the summary never claims coverage or safety."""
    if not isinstance(dispositions, list):
        raise ValueError('Explicit proposal disposition list required')
    boxes = {}
    for region in regions:
        b = region.get('box') if isinstance(region, dict) else None
        if isinstance(b, list) and len(b) == 4:
            boxes[region['person_id']] = tuple(b)
    covered_persons = {c['person_id'] for c in coverings} if coverings else set()
    expected = {}
    for pr in proposals:
        expected[_region(pr['review_region'])] = pr
    seen = set()
    covered = dismissed = shield_dismissed = 0
    for d in dispositions:
        if not isinstance(d, dict):
            raise ValueError('Exact proposal disposition required')
        region = _region(d.get('review_region'))
        if region not in expected:
            raise ValueError('Disposition does not match any current detector proposal')
        if region in seen:
            raise ValueError('Duplicate proposal disposition')
        seen.add(region)
        kind = d.get('disposition')
        if kind == 'covered':
            pid = d.get('person_id')
            if pid not in boxes:
                raise ValueError('Covered disposition must reference an operator region')
            l, t, r, b = boxes[pid]
            x1, y1, x2, y2 = region
            if not (l <= x1 and t <= y1 and r >= x2 and b >= y2):
                raise ValueError('Operator region must fully contain the proposal review region')
            covered += 1
        elif kind == 'dismissed':
            reason = d.get('dismiss_reason')
            if reason not in DISMISS_REASONS:
                raise ValueError('Bounded explicit dismiss reason required')
            if reason == 'operator_confirmed_already_shielded':
                if d.get('person_id') not in covered_persons:
                    raise ValueError('Shield dismissal must reference an explicit face covering review')
                shield_dismissed += 1
            dismissed += 1
        else:
            raise ValueError('Disposition must be covered or dismissed')
    missing = [list(k) for k in expected if k not in seen]
    if missing:
        raise ValueError('Every detector proposal requires an explicit disposition')
    extra = len(dispositions) - len(seen)
    if extra:
        raise ValueError('Disposition count must match the current detector proposals')
    return {'proposals_total': len(expected), 'covered': covered, 'dismissed': dismissed,
            'coverage': 'not_verified', 'privacy_review_status': 'not_validated',
            'evidence_export_allowed': False,
            'dispositions_are_operator_claims_only': True,
            'shield_dismissals_geometrically_verified': False if shield_dismissed else None,
            'scope': 'detector_proposal_dispositions_only_not_whole_frame_coverage',
            'meaning': 'Every returned detector proposal has an operator disposition (operator claims only). Detector misses, detector coverage and mask adequacy remain unproven.'}
