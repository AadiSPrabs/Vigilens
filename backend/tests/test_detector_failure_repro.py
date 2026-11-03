import json
from test_proposal_coverage_validation import review, prepare
from test_fresh_upload_routes import material

def test_broken_detector_path_must_not_pass_as_zero_proposals(material):
    p, raw, frame, calls, c, job = material
    p.face_proposal_model_path = '/nonexistent/detector.onnx'   # real propose_faces, not monkeypatched
    r = prepare(c, raw, frame, review(frame, [{'person_id': '0', 'box': [5, 5, 45, 55]}], proposal_dispositions=[]))
    assert r.status_code == 409, (r.status_code, r.text[:200])
