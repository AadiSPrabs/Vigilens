"""Proposal coverage validation at preview prepare (offline, fail-closed).

When a review carries proposal_dispositions, the route recomputes the offline
detector proposals for the exact source and requires one explicit disposition
per proposal: covered by a containing operator region, or dismissed with a
bounded reason. Absent field keeps the established manual flow. The detector
is monkeypatched in these tests; zero provider calls throughout."""
import json
from test_fresh_upload_routes import material

PROPS = [{'box': [12, 12, 38, 48], 'review_region': [10, 10, 40, 50], 'confidence': 0.9, 'pass_scale': 1, 'helmet_overlap_unchecked': True}]

def review(frame, regions, **extra):
    return {'source_digest': frame.digest, 'frame_size': [80, 80], 'regions': regions,
            'reviewer_label': 'synthetic operator', 'redaction_method': 'opaque', **extra}

def prepare(c, raw, frame, r):
    return c.post('/fresh-review/' + frame.digest + '/private-display',
                  files={'image': ('x.png', raw, 'image/png')}, data={'review': json.dumps(r)})

def armed(p, monkeypatch, proposals=PROPS):
    p.face_proposal_model_path = '/configured/detector.onnx'
    import fresh_review.face_proposals as fp
    monkeypatch.setattr(fp, 'propose_faces', lambda raw, mime, path: {'proposals': proposals, 'reason': 'proposals_require_face_and_helmet_review'})

def test_happy_covered_and_summary_in_report(material, monkeypatch):
    p, raw, frame, calls, c, job = material
    armed(p, monkeypatch)
    r = prepare(c, raw, frame, review(frame, [{'person_id': '0', 'box': [5, 5, 45, 55]}],
                proposal_dispositions=[{'review_region': [10, 10, 40, 50], 'disposition': 'covered', 'person_id': '0'}]))
    assert r.status_code == 200, r.text
    cov = r.json()['proposal_coverage']
    assert cov['proposals_total'] == 1 and cov['covered'] == 1
    assert cov['coverage'] == 'not_verified' and cov['evidence_export_allowed'] is False
    assert len(calls) == 2

def test_every_proposal_needs_a_disposition(material, monkeypatch):
    p, raw, frame, calls, c, job = material
    armed(p, monkeypatch)
    r = prepare(c, raw, frame, review(frame, [{'person_id': '0', 'box': [5, 5, 45, 55]}], proposal_dispositions=[]))
    assert r.status_code == 409 and len(calls) == 2

def test_region_must_contain_review_region(material, monkeypatch):
    p, raw, frame, calls, c, job = material
    armed(p, monkeypatch)
    r = prepare(c, raw, frame, review(frame, [{'person_id': '0', 'box': [20, 20, 30, 40]}],
                proposal_dispositions=[{'review_region': [10, 10, 40, 50], 'disposition': 'covered', 'person_id': '0'}]))
    assert r.status_code == 409 and len(calls) == 2

def test_dismissal_with_bounded_reason(material, monkeypatch):
    p, raw, frame, calls, c, job = material
    armed(p, monkeypatch)
    ok = prepare(c, raw, frame, review(frame, [{'person_id': '0', 'box': [60, 60, 70, 70]}],
                 proposal_dispositions=[{'review_region': [10, 10, 40, 50], 'disposition': 'dismissed', 'dismiss_reason': 'operator_confirmed_not_a_face'}]))
    assert ok.status_code == 200 and ok.json()['proposal_coverage']['dismissed'] == 1
    bad = prepare(c, raw, frame, review(frame, [{'person_id': '0', 'box': [60, 60, 70, 70]}],
                  proposal_dispositions=[{'review_region': [10, 10, 40, 50], 'disposition': 'dismissed', 'dismiss_reason': 'looks_safe'}]))
    assert bad.status_code == 409 and len(calls) == 2

def test_stale_or_unknown_proposal_region_refused(material, monkeypatch):
    p, raw, frame, calls, c, job = material
    armed(p, monkeypatch)
    r = prepare(c, raw, frame, review(frame, [{'person_id': '0', 'box': [5, 5, 45, 55]}],
                proposal_dispositions=[{'review_region': [1, 1, 9, 9], 'disposition': 'covered', 'person_id': '0'}]))
    assert r.status_code == 409 and len(calls) == 2

def test_dispositions_require_configured_detector(material, monkeypatch):
    p, raw, frame, calls, c, job = material
    r = prepare(c, raw, frame, review(frame, [{'person_id': '0', 'box': [5, 5, 45, 55]}],
                proposal_dispositions=[{'review_region': [10, 10, 40, 50], 'disposition': 'covered', 'person_id': '0'}]))
    assert r.status_code == 409 and len(calls) == 2

def test_absent_field_keeps_established_flow(material, monkeypatch):
    p, raw, frame, calls, c, job = material
    r = prepare(c, raw, frame, review(frame, [{'person_id': '0', 'box': [5, 5, 45, 55]}]))
    assert r.status_code == 200 and 'proposal_coverage' not in r.json() and len(calls) == 2


def _failed_pass(reason):
    return lambda raw, mime, path: {'proposals': [], 'reason': reason}


def test_failed_detector_pass_rejected_no_session(material, monkeypatch):
    # A detector pass that did not complete returns zero proposals with a
    # failure reason. That is never a valid base for accepting dispositions:
    # the route must 409 and create no session, for every failure reason.
    p, raw, frame, calls, c, job = material
    p.face_proposal_model_path = '/configured/detector.onnx'
    import fresh_review.face_proposals as fp
    for reason in ('model_unavailable', 'model_digest_mismatch',
                   'optional_runtime_unavailable', 'detector_failure_discarded_partial_output'):
        monkeypatch.setattr(fp, 'propose_faces', _failed_pass(reason))
        r = prepare(c, raw, frame, review(frame, [{'person_id': '0', 'box': [5, 5, 45, 55]}], proposal_dispositions=[]))
        assert r.status_code == 409, (reason, r.status_code, r.text[:200])
    assert len(calls) == 2


def test_missing_model_file_real_detector_rejected(material):
    # No monkeypatch: real propose_faces against a configured-but-absent model
    # returns model_unavailable; empty dispositions must not pass as zero
    # proposals (independent reviewer repro test_detector_failure_repro).
    p, raw, frame, calls, c, job = material
    p.face_proposal_model_path = '/nonexistent/detector.onnx'
    r = prepare(c, raw, frame, review(frame, [{'person_id': '0', 'box': [5, 5, 45, 55]}], proposal_dispositions=[]))
    assert r.status_code == 409, (r.status_code, r.text[:200])
    assert len(calls) == 2


def test_wrong_pinned_model_real_detector_rejected(material, tmp_path):
    # No monkeypatch: an on-disk model whose sha256 does not match the pinned
    # digest must never silently validate as zero proposals.
    p, raw, frame, calls, c, job = material
    bogus = tmp_path / 'model.onnx'
    bogus.write_bytes(b'not the pinned yunet model')
    p.face_proposal_model_path = str(bogus)
    r = prepare(c, raw, frame, review(frame, [{'person_id': '0', 'box': [5, 5, 45, 55]}], proposal_dispositions=[]))
    assert r.status_code == 409, (r.status_code, r.text[:200])
    assert len(calls) == 2


def test_genuine_zero_detections_accepted_and_truthful(material, monkeypatch):
    # A completed pass with zero detections is a real outcome: dispositions []
    # validate and the summary records the detector outcome truthfully without
    # claiming coverage (detector misses stay possible; review stays manual).
    p, raw, frame, calls, c, job = material
    p.face_proposal_model_path = '/configured/detector.onnx'
    import fresh_review.face_proposals as fp
    monkeypatch.setattr(fp, 'propose_faces', _failed_pass('no_faces_detected_still_requires_review'))
    r = prepare(c, raw, frame, review(frame, [{'person_id': '0', 'box': [5, 5, 45, 55]}], proposal_dispositions=[]))
    assert r.status_code == 200, r.text
    cov = r.json()['proposal_coverage']
    assert cov['detector_ran'] is True
    assert cov['detector_outcome_reason'] == 'no_faces_detected_still_requires_review'
    assert cov['proposals_total'] == 0 and cov['coverage'] == 'not_verified'
    assert cov['evidence_export_allowed'] is False


def test_summary_records_operator_claim_truthfulness(material, monkeypatch):
    # Dispositions are operator claims, never detector-verified facts; shield
    # dismissals are claims without geometry and must say so explicitly.
    p, raw, frame, calls, c, job = material
    armed(p, monkeypatch)
    r = prepare(c, raw, frame, review(frame, [],
                face_coverings=[{'person_id': '0', 'basis': 'opaque_worn_face_shield', 'face_fully_hidden': True,
                                 'no_visible_face_pixels': True, 'exact_source_confirmed': True}],
                proposal_dispositions=[{'review_region': [10, 10, 40, 50], 'disposition': 'dismissed',
                                        'dismiss_reason': 'operator_confirmed_already_shielded', 'person_id': '0'}]))
    assert r.status_code == 200, r.text
    cov = r.json()['proposal_coverage']
    assert cov['dispositions_are_operator_claims_only'] is True
    assert cov['shield_dismissals_geometrically_verified'] is False
    assert cov['scope'] == 'detector_proposal_dispositions_only_not_whole_frame_coverage'
